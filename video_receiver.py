#!/usr/bin/env python3
"""
video_receiver.py
=================
Mac 端接收 Pi 视频流，使用 MediaPipe Pose 实时检测：
  1. 坐姿 / 驼背
  2. 深蹲 / 俯卧撑计数
  3. 久坐提醒

依赖安装:
    pip install opencv-python mediapipe numpy

用法:
    python3 video_receiver.py             # 默认监听 0.0.0.0:9999
    python3 video_receiver.py --port 8888
    python3 video_receiver.py --source 0  # 直接用本地摄像头调试（不需要Pi）

退出: 按 q
"""

import argparse
import socket
import struct
import time
import cv2
import mediapipe as mp
import numpy as np

# ══════════════════════════════════════════════════════════════
#  配置区（按需修改）
# ══════════════════════════════════════════════════════════════
CONFIG = {
    # 网络
    "host": "",  # 空字符串 = 监听所有网卡
    "port": 9999,
    # 坐姿检测
    "posture_torso_threshold": 150,  # 躯干角 < 此值 → 驼背警告（度）
    "posture_alert_seconds": 3,  # 持续多少秒才触发警告，避免误报
    # 运动计数
    "squat_down_angle": 100,  # 髋-膝-踝角度 < 此值 → 判定为蹲下
    "squat_up_angle": 160,  # 髋-膝-踝角度 > 此值 → 判定为站立
    "pushup_down_angle": 90,  # 肩-肘-腕角度 < 此值 → 判定为下压
    "pushup_up_angle": 160,  # 肩-肘-腕角度 > 此值 → 判定为撑起
    # 久坐提醒
    "sitting_alert_minutes": 45,  # 连续坐满多少分钟提醒
    "sitting_stand_seconds": 10,  # 检测到站立多少秒才重置计时器
}

# MoveNet 17点 → MediaPipe 33点，常用关键点索引
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


def angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """三点角度，b 为顶点，返回 0~180°"""
    ba, bc = a - b, c - b
    cos = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def lm_xy(landmarks, idx: int) -> np.ndarray:
    """取关键点 (x, y)，归一化坐标"""
    p = landmarks[idx]
    return np.array([p.x, p.y])


def lm_visible(landmarks, idx: int, threshold=0.4) -> bool:
    """关键点可见性是否足够"""
    return landmarks[idx].visibility > threshold


def both_visible(landmarks, *indices, threshold=0.4) -> bool:
    return all(lm_visible(landmarks, i, threshold) for i in indices)


# ══════════════════════════════════════════════════════════════
#  检测模块 1：坐姿 / 驼背
# ══════════════════════════════════════════════════════════════


class PostureDetector:
    """
    检测逻辑：
      - 耳朵→肩→髋 的夹角（躯干角）
        正常坐直 ≈ 170°，驼背前倾时角度变小
      - 使用左右两侧平均值，减少单侧遮挡误差
    """

    def __init__(self, torso_threshold: float, alert_seconds: float):
        self.torso_threshold = torso_threshold
        self.alert_seconds = alert_seconds
        self._bad_start: float | None = None  # 开始驼背的时间戳

    def update(self, landmarks) -> dict:
        result = {"status": "unknown", "torso_angle": None, "alert": False}

        angles = []
        # 左侧：左耳→左肩→左髋
        if both_visible(landmarks, KP["left_ear"], KP["left_shoulder"], KP["left_hip"]):
            a = angle(
                lm_xy(landmarks, KP["left_ear"]),
                lm_xy(landmarks, KP["left_shoulder"]),
                lm_xy(landmarks, KP["left_hip"]),
            )
            angles.append(a)
        # 右侧：右耳→右肩→右髋
        if both_visible(
            landmarks, KP["right_ear"], KP["right_shoulder"], KP["right_hip"]
        ):
            a = angle(
                lm_xy(landmarks, KP["right_ear"]),
                lm_xy(landmarks, KP["right_shoulder"]),
                lm_xy(landmarks, KP["right_hip"]),
            )
            angles.append(a)

        if not angles:
            self._bad_start = None
            return result

        torso_angle = float(np.mean(angles))
        result["torso_angle"] = torso_angle

        if torso_angle < self.torso_threshold:
            result["status"] = "bad"
            if self._bad_start is None:
                self._bad_start = time.time()
            elif time.time() - self._bad_start >= self.alert_seconds:
                result["alert"] = True
        else:
            result["status"] = "good"
            self._bad_start = None

        return result


# ══════════════════════════════════════════════════════════════
#  检测模块 2：运动计数（深蹲 + 俯卧撑）
# ══════════════════════════════════════════════════════════════


class ExerciseCounter:
    """
    状态机计数：
      down → up 算一次完整动作
    支持深蹲和俯卧撑，通过不同关节角度区分。
    """

    def __init__(self, cfg: dict):
        self.squat_count = 0
        self.pushup_count = 0
        self._squat_state = "up"  # "up" | "down"
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

        # ── 深蹲：髋-膝-踝 ───────────────────────────────────
        if both_visible(landmarks, KP["left_hip"], KP["left_knee"], KP["left_ankle"]):
            sq_angle = angle(
                lm_xy(landmarks, KP["left_hip"]),
                lm_xy(landmarks, KP["left_knee"]),
                lm_xy(landmarks, KP["left_ankle"]),
            )
            result["squat_angle"] = sq_angle

            if sq_angle < self.sq_down and self._squat_state == "up":
                self._squat_state = "down"
            elif sq_angle > self.sq_up and self._squat_state == "down":
                self._squat_state = "up"
                self.squat_count += 1
                result["squat_count"] = self.squat_count

        # ── 俯卧撑：肩-肘-腕 ─────────────────────────────────
        if both_visible(
            landmarks, KP["left_shoulder"], KP["left_elbow"], KP["left_wrist"]
        ):
            pu_angle = angle(
                lm_xy(landmarks, KP["left_shoulder"]),
                lm_xy(landmarks, KP["left_elbow"]),
                lm_xy(landmarks, KP["left_wrist"]),
            )
            result["pushup_angle"] = pu_angle

            if pu_angle < self.pu_down and self._pushup_state == "up":
                self._pushup_state = "down"
            elif pu_angle > self.pu_up and self._pushup_state == "down":
                self._pushup_state = "up"
                self.pushup_count += 1
                result["pushup_count"] = self.pushup_count

        return result


# ══════════════════════════════════════════════════════════════
#  检测模块 3：久坐提醒
# ══════════════════════════════════════════════════════════════


class SittingTimer:
    """
    逻辑：
      - 检测髋关节可见且膝关节角度接近 90° → 判定为坐姿
      - 连续坐满 N 分钟 → 触发提醒
      - 检测到站立（膝关节伸直）持续 10 秒 → 重置计时器
    """

    def __init__(self, alert_minutes: float, stand_seconds: float):
        self.alert_seconds = alert_minutes * 60
        self.stand_seconds = stand_seconds
        self._sit_start: float | None = None
        self._stand_start: float | None = None
        self._alerted = False  # 已提醒，避免重复报警

    def update(self, landmarks) -> dict:
        result = {
            "sitting_minutes": 0.0,
            "is_sitting": False,
            "alert": False,
        }

        # 用髋-膝-踝角度判断坐/站
        # 坐姿：膝关节约 80°~110°；站立：膝关节 > 160°
        if not both_visible(
            landmarks, KP["left_hip"], KP["left_knee"], KP["left_ankle"]
        ):
            return result

        # knee_ang = angle(
        #     lm_xy(landmarks, KP["left_hip"]),
        #     lm_xy(landmarks, KP["left_knee"]),
        #     lm_xy(landmarks, KP["left_ankle"]),
        # )
        # is_sitting = knee_ang < 130   # 小于 130° 视为坐姿

        hip_y = landmarks[KP["left_hip"]].y
        shoulder_y = landmarks[KP["left_shoulder"]].y
        torso_span = hip_y - shoulder_y  # 坐着≈0.215，站立≈0.287

        # 髋肩垂直距离（归一化）
        # 站立时两者距离大；坐着时躯干压缩，距离相对小
        # 更直接的：髋关节Y绝对位置——坐着时髋在画面中间偏上
        # is_sitting = hip_y < 0.75  # 髋关节在画面上75%以上位置 → 坐着

        # 坐着时肩髋距离更小，这个规律更稳定。把阈值设在两者中间 0.25：
        is_sitting = torso_span < 0.25  # 阈值取两者中间

        result["is_sitting"] = is_sitting

        now = time.time()

        if is_sitting:
            self._stand_start = None  # 重置站立计时
            if self._sit_start is None:
                self._sit_start = now
            elapsed = now - self._sit_start
            result["sitting_minutes"] = elapsed / 60
            if elapsed >= self.alert_seconds and not self._alerted:
                result["alert"] = True
                self._alerted = True
        else:
            # 站立逻辑：需要持续站立才重置（防误触）
            if self._stand_start is None:
                self._stand_start = now
            elif now - self._stand_start >= self.stand_seconds:
                self._sit_start = None
                self._alerted = False
                self._stand_start = None

        return result


# ══════════════════════════════════════════════════════════════
#  显示层：在帧上叠加信息
# ══════════════════════════════════════════════════════════════


def draw_overlay(frame, posture, exercise, sitting, fps: float):
    h, w = frame.shape[:2]

    def put(text, y, color=(255, 255, 255)):
        cv2.putText(
            frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3
        )  # 黑色描边
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

    # FPS
    put(f"FPS: {fps:.1f}", 30)

    # ── 坐姿 ──────────────────────────────────────────────────
    if posture["torso_angle"] is not None:
        status = posture["status"]
        ang_str = f"{posture['torso_angle']:.1f}"
        if posture["alert"]:
            put(f"[!] POSTURE BAD  {ang_str}deg", 70, (0, 0, 255))
        elif status == "bad":
            put(f"Posture: slouching  {ang_str}deg", 70, (0, 165, 255))
        else:
            put(f"Posture: good  {ang_str}deg", 70, (0, 220, 0))

    # ── 运动计数 ───────────────────────────────────────────────
    put(f"Squats:  {exercise['squat_count']}", 110)
    put(f"Pushups: {exercise['pushup_count']}", 145)
    if exercise["squat_angle"] is not None:
        put(f"  knee: {exercise['squat_angle']:.0f}deg", 175, (180, 180, 180))
    if exercise["pushup_angle"] is not None:
        put(f"  elbow: {exercise['pushup_angle']:.0f}deg", 200, (180, 180, 180))

    # ── 久坐 ───────────────────────────────────────────────────
    mins = sitting["sitting_minutes"]
    if sitting["alert"]:
        put(f"[!] SIT {mins:.0f}min - STAND UP!", h - 20, (0, 0, 255))
    elif sitting["is_sitting"]:
        put(f"Sitting: {mins:.1f} min", h - 20, (0, 220, 220))
    else:
        put("Standing", h - 20, (0, 220, 0))


# ══════════════════════════════════════════════════════════════
#  TCP 接收（来自 Pi 的自定义帧协议）
# ══════════════════════════════════════════════════════════════


def receive_frames(host: str, port: int):
    """Generator：持续 yield BGR frames"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    print(f"[INFO] 等待 Pi 连接 ({host or '0.0.0.0'}:{port})...")
    conn, addr = server.accept()
    print(f"[INFO] Pi 已连接: {addr}")

    header_size = struct.calcsize("Q")
    buf = b""

    try:
        while True:
            # 读帧头（8字节长度）
            while len(buf) < header_size:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
            msg_size = struct.unpack("Q", buf[:header_size])[0]
            buf = buf[header_size:]

            # 读帧数据
            while len(buf) < msg_size:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
            frame_data = buf[:msg_size]
            buf = buf[msg_size:]

            # JPEG 解码
            np_arr = np.frombuffer(frame_data, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is not None:
                yield frame
    finally:
        conn.close()
        server.close()


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

    # 初始化检测模块
    posture_det = PostureDetector(
        cfg["posture_torso_threshold"], cfg["posture_alert_seconds"]
    )
    exercise_ctr = ExerciseCounter(cfg)
    sitting_tmr = SittingTimer(
        cfg["sitting_alert_minutes"], cfg["sitting_stand_seconds"]
    )

    # 初始化 MediaPipe
    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles

    # FPS
    fps_counter, fps_start, current_fps = 0, time.time(), 0.0

    # 帧来源
    if args.source is not None:
        frame_gen = open_local_camera(int(args.source))
        print(f"[INFO] 使用本地摄像头 {args.source}")
    else:
        frame_gen = receive_frames(cfg["host"], cfg["port"])

    print("[INFO] 按 q 退出")

    with mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=1,  # 0=快, 1=均衡, 2=最准
    ) as pose:
        for frame in frame_gen:
            # ── MediaPipe 推理 ───────────────────────────────
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = pose.process(rgb)
            rgb.flags.writeable = True

            # ── 骨骼绘制 ─────────────────────────────────────
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_styles.get_default_pose_landmarks_style(),
                )

            # 在主循环里临时加一行调试输出，观察关键点数据（每秒打印一次）
            if results.pose_landmarks:
                lms = results.pose_landmarks.landmark
                if int(time.time() * 2) % 2 == 0:  # 每秒打一次
                    print(f"髋Y: {lms[23].y:.3f}  肩Y: {lms[11].y:.3f}")

            # ── 检测模块更新 ─────────────────────────────────
            lms = results.pose_landmarks.landmark if results.pose_landmarks else None

            posture = (
                posture_det.update(lms)
                if lms
                else {"status": "unknown", "torso_angle": None, "alert": False}
            )
            exercise = (
                exercise_ctr.update(lms)
                if lms
                else {
                    "squat_count": exercise_ctr.squat_count,
                    "pushup_count": exercise_ctr.pushup_count,
                    "squat_angle": None,
                    "pushup_angle": None,
                }
            )
            sitting = (
                sitting_tmr.update(lms)
                if lms
                else {"sitting_minutes": 0.0, "is_sitting": False, "alert": False}
            )

            # ── FPS ──────────────────────────────────────────
            fps_counter += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                current_fps = fps_counter / elapsed
                fps_counter, fps_start = 0, time.time()

            # ── 命令行输出 ────────────────────────────────────
            torso_str = (
                f"{posture['torso_angle']:.1f}°" if posture["torso_angle"] else "n/a"
            )
            sit_str = (
                f"{sitting['sitting_minutes']:.1f}min"
                if sitting["is_sitting"]
                else "standing"
            )
            print(
                f"\r[FPS {current_fps:4.1f}] "
                f"姿势:{posture['status']:7s}({torso_str})  "
                f"深蹲:{exercise_ctr.squat_count:3d}  "
                f"俯卧撑:{exercise_ctr.pushup_count:3d}  "
                f"久坐:{sit_str}  "
                + ("[!]驼背" if posture["alert"] else "")
                + ("[!]站起来!" if sitting["alert"] else ""),
                end="",
                flush=True,
            )

            # ── 画面叠加 ─────────────────────────────────────
            draw_overlay(frame, posture, exercise, sitting, current_fps)
            cv2.imshow("Health Assistant", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cv2.destroyAllWindows()
    print("\n[INFO] 已退出")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port", type=int, default=9999, help="TCP 监听端口（默认 9999）"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="本地摄像头索引（如 0），不填则等待 Pi 连接",
    )
    main(parser.parse_args())
