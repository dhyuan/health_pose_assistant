#!/usr/bin/env python3
"""
pose_detect_mediapipe.py
========================
Mac 端接收 Pi 视频流，使用 MediaPipe Pose 实时检测：
  1. 坐姿 / 驼背
  2. 运动计数（深蹲 / 俯卧撑，需全身正面视角，默认关闭）
  3. 久坐提醒 + 语音播报

依赖安装:
    pip install opencv-python mediapipe numpy

用法:
    python3 pose_detect_mediapipe.py            # 等待 Pi 连接（默认端口 9999）
    python3 pose_detect_mediapipe.py --port 8888
    python3 pose_detect_mediapipe.py --source 0 # 用本地摄像头调试（不需要 Pi）

退出: 按 q
"""

import argparse
import socket
import struct
import subprocess
import time
import cv2
import mediapipe as mp
import numpy as np

# ══════════════════════════════════════════════════════════════
#  配置区（按需修改）
# ══════════════════════════════════════════════════════════════
CONFIG = {
    # ── 功能开关 ──────────────────────────────────────────────
    "enable_posture": True,  # 坐姿 / 驼背检测
    "enable_exercise": False,  # 运动计数（需全身正面视角，桌前请关闭）
    "enable_sitting": True,  # 久坐提醒
    # ── 网络 ──────────────────────────────────────────────────
    "host": "",  # 空字符串 = 监听所有网卡
    "port": 9999,
    # ── 视频旋转 ──────────────────────────────────────────────
    "video_rotation_angle": 180,  # 视频旋转角度（0/90/180/270 度）
    # ── 坐姿检测 ──────────────────────────────────────────────
    "posture_torso_threshold": 155,  # 躯干角 < 此值 → 驼背警告（度）。改为150° 更宽松
    "posture_head_forward_threshold": 0.05,  # 头部前倾阈值（鼻子相对肩膀的x位移 > 此值 → 头部前倾）
    "posture_alert_seconds": 10,  # 坐姿不良持续10秒才触发提醒
    # ── 运动计数（enable_exercise=False 时以下参数无效）────────
    "squat_down_angle": 100,  # 髋-膝-踝角度 < 此值 → 蹲下
    "squat_up_angle": 160,  # 髋-膝-踝角度 > 此值 → 站立
    "pushup_down_angle": 90,  # 肩-肘-腕角度 < 此值 → 下压
    "pushup_up_angle": 160,  # 肩-肘-腕角度 > 此值 → 撑起
    # ── 久坐提醒 ──────────────────────────────────────────────
    "sitting_alert_minutes": 20,  # 连续坐满多少分钟提醒（测试用0.2，正式用45）
    "sitting_stand_seconds": 60,  # 站立持续多少秒才算真正站起（≥60秒才重置计时器，避免误检测）
    "sitting_repeat_alert_minutes": 1.0,  # 如果没站起，每隔多少分钟重复提醒一次
    # ── 语音提醒 ──────────────────────────────────────────────
    "alert_voice": "Meijia",
    "alert_message": "你已经坐了很久了，站起来活动一下吧！",
    # ── 久坐坐/站判断阈值（根据你的摄像头位置校准）────────────
    # 实测参考：坐着 span≈0.215 hip_y≈0.537，站立 span≈0.287 hip_y≈0.458
    "sitting_torso_span_threshold": 0.25,  # 肩髋距离 < 此值 → 投坐姿票
    "sitting_hip_y_threshold": 0.48,  # 髋Y > 此值 → 投坐姿票
    "sitting_knee_angle_threshold": 130,  # 膝角 < 此值 → 投坐姿票（腿可见时）
}

# ── MediaPipe 关键点索引 ──────────────────────────────────────
KP = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
}


# ══════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════


def calc_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """三点角度，b 为顶点，返回 0~180°"""
    ba, bc = a - b, c - b
    cos = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def lm_xy(landmarks, idx: int) -> np.ndarray:
    p = landmarks[idx]
    return np.array([p.x, p.y])


def lm_vis(landmarks, idx: int, threshold=0.4) -> bool:
    return landmarks[idx].visibility > threshold


def all_vis(landmarks, *indices, threshold=0.4) -> bool:
    return all(lm_vis(landmarks, i, threshold) for i in indices)


def rotate_frame(frame: np.ndarray, angle: int) -> np.ndarray:
    """旋转视频帧（支持 0/90/180/270 度）"""
    angle = angle % 360
    if angle == 0:
        return frame
    elif angle == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif angle == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    elif angle == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    else:
        # 任意角度：使用仿射变换
        h, w = frame.shape[:2]
        center = (w / 2, h / 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(frame, rotation_matrix, (w, h))
        return rotated


# ══════════════════════════════════════════════════════════════
#  检测模块 1：坐姿 / 驼背
# ══════════════════════════════════════════════════════════════


class PostureDetector:
    """耳→肩→髋 夹角判断躯干前倾，左右取平均减少遮挡误差。
    同时检测头部前倾（鼻子相对肩膀的水平位移）。"""

    def __init__(
        self,
        torso_threshold: float,
        alert_seconds: float,
        head_forward_threshold: float = 0.05,
        repeat_alert_seconds: float = 5.0,
    ):
        self.torso_threshold = torso_threshold
        self.alert_seconds = alert_seconds
        self.head_forward_threshold = head_forward_threshold  # 头部前倾阈值
        self.repeat_alert_seconds = (
            repeat_alert_seconds  # 坐姿不良后，每隔多少秒重复提醒一次
        )
        self._bad_start: float | None = None
        self._last_alert_time: float | None = None  # 记录上次播放提醒的时间

    def update(self, landmarks) -> dict:
        result = {
            "status": "unknown",
            "torso_angle": None,
            "alert": False,
            "head_forward": None,
        }

        angles = []
        # 尽可能收集左右两侧的躯干角，只要有一侧可见就继续
        for ear, shoulder, hip in [
            (KP["left_ear"], KP["left_shoulder"], KP["left_hip"]),
            (KP["right_ear"], KP["right_shoulder"], KP["right_hip"]),
        ]:
            # 降低阈值到0.3，即使关键点部分遮挡也能检测
            if all_vis(landmarks, ear, shoulder, hip, threshold=0.3):
                angles.append(
                    calc_angle(
                        lm_xy(landmarks, ear),
                        lm_xy(landmarks, shoulder),
                        lm_xy(landmarks, hip),
                    )
                )

        if not angles:
            self._bad_start = None
            return result

        torso_angle = float(np.mean(angles))
        result["torso_angle"] = torso_angle

        # 检测头部前倾：鼻子-肩膀的水平距离
        head_forward_ratio = 0.0
        if lm_vis(landmarks, KP["nose"], threshold=0.3) and all_vis(
            landmarks, KP["left_shoulder"], KP["right_shoulder"], threshold=0.3
        ):
            nose_x = landmarks[KP["nose"]].x
            shoulder_left_x = landmarks[KP["left_shoulder"]].x
            shoulder_right_x = landmarks[KP["right_shoulder"]].x
            shoulder_mid_x = (shoulder_left_x + shoulder_right_x) / 2

            # 计算鼻子相对于肩膀中点的水平位移（正数表示头部前倾）
            head_forward_ratio = nose_x - shoulder_mid_x
            result["head_forward"] = head_forward_ratio

        now = time.time()
        # 判断坐姿是否良好：躯干角足够大 AND 头部不过度前倾
        is_posture_bad = (torso_angle < self.torso_threshold) or (
            head_forward_ratio > self.head_forward_threshold
        )

        if is_posture_bad:
            result["status"] = "bad"
            if self._bad_start is None:
                self._bad_start = now

            elapsed = now - self._bad_start
            # 首次提醒：坐姿不良持续超过 alert_seconds
            if elapsed >= self.alert_seconds and self._last_alert_time is None:
                result["alert"] = True
                self._last_alert_time = now
            # 重复提醒：每隔 repeat_alert_seconds 提醒一次
            elif (
                self._last_alert_time is not None
                and now - self._last_alert_time >= self.repeat_alert_seconds
            ):
                result["alert"] = True
                self._last_alert_time = now
        else:
            result["status"] = "good"
            self._bad_start = None
            self._last_alert_time = None  # 坐姿恢复，重置提醒记录

        return result


# ══════════════════════════════════════════════════════════════
#  检测模块 2：运动计数（深蹲 + 俯卧撑）
# ══════════════════════════════════════════════════════════════


class ExerciseCounter:
    """down → up 状态机计数，enable_exercise=False 时不会被调用。"""

    def __init__(self, cfg: dict):
        self.squat_count = 0
        self.pushup_count = 0
        self._squat_state = "up"
        self._pushup_state = "up"
        self.sq_down = cfg["squat_down_angle"]
        self.sq_up = cfg["squat_up_angle"]
        self.pu_down = cfg["pushup_down_angle"]
        self.pu_up = cfg["pushup_up_angle"]

    def update(self, landmarks) -> dict:
        result = {
            "squat_count": self.squat_count,
            "pushup_count": self.pushup_count,
            "squat_angle": None,
            "pushup_angle": None,
        }

        # 深蹲：髋-膝-踝
        if all_vis(landmarks, KP["left_hip"], KP["left_knee"], KP["left_ankle"]):
            sq_ang = calc_angle(
                lm_xy(landmarks, KP["left_hip"]),
                lm_xy(landmarks, KP["left_knee"]),
                lm_xy(landmarks, KP["left_ankle"]),
            )
            result["squat_angle"] = sq_ang
            if sq_ang < self.sq_down and self._squat_state == "up":
                self._squat_state = "down"
            elif sq_ang > self.sq_up and self._squat_state == "down":
                self._squat_state = "up"
                self.squat_count += 1
                result["squat_count"] = self.squat_count

        # 俯卧撑：肩-肘-腕
        if all_vis(landmarks, KP["left_shoulder"], KP["left_elbow"], KP["left_wrist"]):
            pu_ang = calc_angle(
                lm_xy(landmarks, KP["left_shoulder"]),
                lm_xy(landmarks, KP["left_elbow"]),
                lm_xy(landmarks, KP["left_wrist"]),
            )
            result["pushup_angle"] = pu_ang
            if pu_ang < self.pu_down and self._pushup_state == "up":
                self._pushup_state = "down"
            elif pu_ang > self.pu_up and self._pushup_state == "down":
                self._pushup_state = "up"
                self.pushup_count += 1
                result["pushup_count"] = self.pushup_count

        return result


# ══════════════════════════════════════════════════════════════
#  检测模块 3：久坐提醒（多特征投票）
# ══════════════════════════════════════════════════════════════


class SittingTimer:
    """
    三特征投票判断坐/站，多数决：
      特征1: 肩髋垂直距离（span）  — 坐着时小
      特征2: 髋关节Y绝对坐标       — 坐着时大
      特征3: 膝关节角度             — 腿被遮挡时自动弃权
    """

    def __init__(self, alert_minutes: float, stand_seconds: float, cfg: dict):
        self.alert_seconds = alert_minutes * 60
        self.stand_seconds = stand_seconds
        self.repeat_alert_seconds = cfg["sitting_repeat_alert_minutes"] * 60
        self.span_threshold = cfg["sitting_torso_span_threshold"]
        self.hip_y_thresh = cfg["sitting_hip_y_threshold"]
        self.knee_threshold = cfg["sitting_knee_angle_threshold"]

        self._sit_start: float | None = None
        self._stand_start: float | None = None
        self._last_is_sitting: bool = False
        self._alerted: bool = False
        self._last_alert_time: float | None = None  # 记录上次语音提醒的时间

    def update(self, landmarks) -> dict:
        result = {
            "sitting_minutes": 0.0,
            "is_sitting": False,
            "alert": False,
            "votes": "",
        }

        votes = []
        # debug_data = {}

        # 特征1：肩髋 span
        if all_vis(landmarks, KP["left_hip"], KP["left_shoulder"], threshold=0.3):
            span = landmarks[KP["left_hip"]].y - landmarks[KP["left_shoulder"]].y
            is_sitting_vote = span < self.span_threshold
            votes.append(("span", is_sitting_vote))
            # debug_data["span"] = f"{span:.3f} (阈值:{self.span_threshold})"

        # 特征2：髋Y绝对位置
        if lm_vis(landmarks, KP["left_hip"], threshold=0.3):
            hip_y = landmarks[KP["left_hip"]].y
            is_sitting_vote = hip_y > self.hip_y_thresh
            votes.append(("hip_y", is_sitting_vote))
            # debug_data["hip_y"] = f"{hip_y:.3f} (阈值:{self.hip_y_thresh})"

        # 特征3：膝关节角度（腿可见时才参与）
        if all_vis(
            landmarks, KP["left_hip"], KP["left_knee"], KP["left_ankle"], threshold=0.3
        ):
            knee_ang = calc_angle(
                lm_xy(landmarks, KP["left_hip"]),
                lm_xy(landmarks, KP["left_knee"]),
                lm_xy(landmarks, KP["left_ankle"]),
            )
            is_sitting_vote = knee_ang < self.knee_threshold
            votes.append(("knee", knee_ang < self.knee_threshold))
            # debug_data["knee"] = f"{knee_ang:.1f}° (阈值:{self.knee_threshold}°)"

        if not votes:
            is_sitting = self._last_is_sitting
            result["votes"] = "no_data"
        else:
            sitting_votes = sum(1 for _, v in votes if v)
            is_sitting = sitting_votes > len(votes) / 2
            result["votes"] = " ".join(f"{n}:{'S' if v else 'U'}" for n, v in votes)

        # # 调试信息：显示所有特征值
        # result["debug_info"] = " | ".join(f"{k}={v}" for k, v in debug_data.items())

        self._last_is_sitting = is_sitting
        result["is_sitting"] = is_sitting

        now = time.time()
        if is_sitting:
            self._stand_start = None
            if self._sit_start is None:
                self._sit_start = now
            elapsed = now - self._sit_start
            result["sitting_minutes"] = elapsed / 60

            # 首次提醒（超过初始警告时间）
            if elapsed >= self.alert_seconds and not self._alerted:
                result["alert"] = True
                self._alerted = True
                self._last_alert_time = now
            # 重复提醒（每隔 repeat_alert_seconds 提醒一次）
            elif self._alerted and self._last_alert_time is not None:
                if now - self._last_alert_time >= self.repeat_alert_seconds:
                    result["alert"] = True
                    self._last_alert_time = now
        else:
            if self._stand_start is None:
                self._stand_start = now
            elif now - self._stand_start >= self.stand_seconds:
                self._sit_start = None
                self._alerted = False
                self._last_alert_time = None
                self._stand_start = None

        return result


# ══════════════════════════════════════════════════════════════
#  显示层
# ══════════════════════════════════════════════════════════════


def draw_overlay(frame, posture, exercise, sitting, fps: float, cfg: dict):
    h, w = frame.shape[:2]

    def put(text, y, color=(255, 255, 255)):
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3)
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

    put(f"FPS: {fps:.1f}", 30)

    # 坐姿
    if cfg["enable_posture"] and posture["torso_angle"] is not None:
        ang = f"{posture['torso_angle']:.1f}"
        if posture["alert"]:
            put(f"[!] POSTURE BAD  {ang}deg", 70, (0, 0, 255))
        elif posture["status"] == "bad":
            put(f"Posture: slouching  {ang}deg", 70, (0, 165, 255))
        else:
            put(f"Posture: good  {ang}deg", 70, (0, 220, 0))

    # 运动计数
    if cfg["enable_exercise"]:
        put(f"Squats:  {exercise['squat_count']}", 110)
        put(f"Pushups: {exercise['pushup_count']}", 145)
        if exercise["squat_angle"] is not None:
            put(f"  knee:  {exercise['squat_angle']:.0f}deg", 175, (180, 180, 180))
        if exercise["pushup_angle"] is not None:
            put(f"  elbow: {exercise['pushup_angle']:.0f}deg", 200, (180, 180, 180))

    # 久坐
    if cfg["enable_sitting"]:
        mins = sitting["sitting_minutes"]
        if sitting["alert"]:
            put(f"[!] {mins:.0f}min - STAND UP!", h - 20, (0, 0, 255))
        elif sitting["is_sitting"]:
            put(f"Sitting: {mins:.1f} min", h - 20, (0, 220, 220))
        else:
            put("Standing", h - 20, (0, 220, 0))


# ══════════════════════════════════════════════════════════════
#  TCP 接收
# ══════════════════════════════════════════════════════════════


def receive_frames(host: str, port: int):
    """Generator：持续 yield BGR frames，来自 pi_stream.py，支持自动重连"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)

    while True:
        print(f"[INFO] 等待 Pi 连接 ({host or '0.0.0.0'}:{port})...")
        conn, addr = server.accept()
        print(f"[INFO] Pi 已连接: {addr}")

        header_size = struct.calcsize("Q")
        buf = b""
        try:
            while True:
                while len(buf) < header_size:
                    chunk = conn.recv(65536)
                    if not chunk:
                        # 连接断开，break 内层 while，外层 while 会重新等待连接
                        raise ConnectionResetError("Pi 连接已断开")
                    buf += chunk
                msg_size = struct.unpack("Q", buf[:header_size])[0]
                buf = buf[header_size:]

                while len(buf) < msg_size:
                    chunk = conn.recv(65536)
                    if not chunk:
                        raise ConnectionResetError("Pi 连接已断开")
                    buf += chunk
                frame_data = buf[:msg_size]
                buf = buf[msg_size:]

                np_arr = np.frombuffer(frame_data, dtype=np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    yield frame
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            print(f"[WARN] {e}，等待 Pi 重新连接...")
            conn.close()
        except Exception as e:
            print(f"[ERROR] 未预期的错误: {e}")
            conn.close()
            raise


def open_local_camera(source: int):
    """Generator：本地摄像头（调试用）"""
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开摄像头 {source}")
    try:
        while True:
            ret, frame = cap.read()
            if ret:
                yield frame
    finally:
        cap.release()


# ══════════════════════════════════════════════════════════════
#  主循环
# ══════════════════════════════════════════════════════════════


def main(args):
    cfg = CONFIG.copy()
    cfg["port"] = args.port

    posture_det = PostureDetector(
        cfg["posture_torso_threshold"],
        cfg["posture_alert_seconds"],
        cfg["posture_head_forward_threshold"],
    )
    exercise_ctr = ExerciseCounter(cfg)
    sitting_tmr = SittingTimer(
        cfg["sitting_alert_minutes"], cfg["sitting_stand_seconds"], cfg
    )

    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles

    fps_counter, fps_start, current_fps = 0, time.time(), 0.0
    _alert_proc = None  # 记录 say 进程，上一句播完才播下一句

    if args.source is not None:
        frame_gen = open_local_camera(int(args.source))
        print(f"[INFO] 使用本地摄像头 {args.source}")
    else:
        frame_gen = receive_frames(cfg["host"], cfg["port"])

    print("[INFO] 按 q 退出")

    with mp_pose.Pose(
        min_detection_confidence=0.35,
        min_tracking_confidence=0.35,
        model_complexity=1,
    ) as pose:
        for frame in frame_gen:
            # ── MediaPipe 推理 ────────────────────────────────
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = pose.process(rgb)
            rgb.flags.writeable = True

            # ── 骨骼绘制 ──────────────────────────────────────
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_styles.get_default_pose_landmarks_style(),
                )

            lms = results.pose_landmarks.landmark if results.pose_landmarks else None

            posture = (
                posture_det.update(lms)
                if (lms and cfg["enable_posture"])
                else {
                    "status": "unknown",
                    "torso_angle": None,
                    "alert": False,
                    "head_forward": None,
                }
            )
            exercise = (
                exercise_ctr.update(lms)
                if (lms and cfg["enable_exercise"])
                else {
                    "squat_count": 0,
                    "pushup_count": 0,
                    "squat_angle": None,
                    "pushup_angle": None,
                }
            )
            sitting = (
                sitting_tmr.update(lms)
                if (lms and cfg["enable_sitting"])
                else {
                    "sitting_minutes": 0.0,
                    "is_sitting": False,
                    "alert": False,
                    "votes": "",
                }
            )

            # ── FPS ───────────────────────────────────────────
            fps_counter += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                current_fps = fps_counter / elapsed
                fps_counter, fps_start = 0, time.time()

            # ── 命令行输出 ────────────────────────────────────
            torso_str = (
                f"{posture['torso_angle']:.1f}°" if posture["torso_angle"] else "n/a"
            )
            # head_forward_str = (
            #     f\"{posture['head_forward']:.3f}\"
            #     if posture[\"head_forward\"] is not None
            #     else \"n/a\"
            # )
            elapsed_sit = (
                (time.time() - sitting_tmr._sit_start)
                if sitting_tmr._sit_start
                else 0.0
            )
            sit_str = (
                f"{sitting['sitting_minutes']:.1f}min({elapsed_sit:.0f}s)"
                if sitting["is_sitting"]
                else "standing"
            )

            line = f"\r[FPS {current_fps:4.1f}] "
            if cfg["enable_posture"]:
                line += f"姿势:{posture['status']:7s}({torso_str})  "
            if cfg["enable_exercise"]:
                line += f"深蹲:{exercise_ctr.squat_count:3d}  俯卧撑:{exercise_ctr.pushup_count:3d}  "
            if cfg["enable_sitting"]:
                line += f"久坐:{sit_str}  "
            if posture["alert"]:
                line += "[!]驼背  "
            if sitting["alert"]:
                line += "[!]站起来!"
            print(line, end="", flush=True)

            # ── 语音提醒（非阻塞，上一句播完才播下一次）──────
            # 坐姿提醒（驼背超过10秒，之后每5秒重复提醒一次）
            if posture["alert"]:
                if _alert_proc is None or _alert_proc.poll() is not None:
                    _alert_proc = subprocess.Popen(
                        [
                            "say",
                            "-v",
                            cfg["alert_voice"],
                            "你的坐姿不对，请挺直腰背",
                        ]
                    )

            # 久坐提醒（久坐超过指定时间）
            if sitting["alert"]:
                if _alert_proc is None or _alert_proc.poll() is not None:
                    _alert_proc = subprocess.Popen(
                        ["say", "-v", cfg["alert_voice"], cfg["alert_message"]]
                    )
            # ── 视频旋转 ──────────────────────────────────────────
            frame = rotate_frame(frame, cfg["video_rotation_angle"])
            # ── 画面叠加 ──────────────────────────────────────
            draw_overlay(frame, posture, exercise, sitting, current_fps, cfg)
            cv2.imshow("Health Assistant", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cv2.destroyAllWindows()
    print("\n[INFO] 已退出")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Health Assistant - MediaPipe Pose")
    parser.add_argument(
        "--port", type=int, default=9999, help="TCP 监听端口（默认 9999）"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="本地摄像头索引（如 0），不填则等待 Pi 连接",
    )
    parser.add_argument(
        "--rotation",
        type=int,
        default=180,
        help="视频旋转角度：0/90/180/270 度（默认 180）",
    )
    args = parser.parse_args()
    CONFIG["video_rotation_angle"] = args.rotation
    main(args)
