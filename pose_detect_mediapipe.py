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
import datetime
import random
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
    "posture_torso_threshold": 150,  # 躯干角 < 此值 → 驼背警告（度）。改为150° 更宽松
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
    # ── 人离开画面的消息 ──────────────────────────────────────
    "leave_messages": [
        "是的，应该多站起来活动一下。有很多比工作更有意思的事可以做哦。",
        "去休息一下吧，身体比工作更重要。",
        "站起来伸伸懒腰，让眼睛放松一下。",
        "出去走走吧，呼吸一下新鲜空气。",
        "劳逸结合最重要，别太拼了。",
        "放松放松，生活不只有工作。",
        "去喝杯水，活动下筋骨。",
        "给自己一个休息的机会吧。",
    ],
    # ── 人回到画面的消息 ──────────────────────────────────────
    "welcome_back_messages": [
        "准备回来学习工作了啊，加油！",
        "欢迎回来，我们继续加油吧！",
        "休息好了吗？继续冲吧！",
        "回来了，让我们继续努力。",
        "充电完成，准备继续战斗！",
        "状态调整好了，继续来吧！",
        "一起加油，你可以的！",
        "新的开始，让我们再来！",
        "精神焕发了吧，冲起来！",
    ],
    # ── 久坐坐/站判断阈值（根据你的摄像头位置校准）────────────
    # 实测参考：坐着 span≈0.215 hip_y≈0.537，站立 span≈0.287 hip_y≈0.458
    "sitting_torso_span_threshold": 0.25,  # 肩髋距离 < 此值 → 投坐姿票
    "sitting_hip_y_threshold": 0.48,  # 髋Y > 此值 → 投坐姿票
    "sitting_knee_angle_threshold": 130,  # 膝角 < 此值 → 投坐姿票（腿可见时）
    "sitting_torso_lean_threshold": 155,  # 躯干倾角 < 此值 → 明显前倾（弯腰）
    "sitting_knee_straight_threshold": 150,  # 膝角 > 此值 → 腿伸直（弯腰特征）
    "sitting_frame_smoothing": 3,  # 连续N帧判断为同一状态才切换（避免抖动）
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
        self.torso_lean_thresh = cfg["sitting_torso_lean_threshold"]
        self.knee_straight_thresh = cfg["sitting_knee_straight_threshold"]
        self.frame_smoothing = cfg["sitting_frame_smoothing"]
        self.stand_clear_seconds = 120  # 站立2分钟后清零当前坐着时间
        self.leave_messages = cfg.get(
            "leave_messages", ["休息一下吧。"]
        )  # 人离开的提醒语
        self.welcome_back_messages = cfg.get(
            "welcome_back_messages", ["欢迎回来。"]
        )  # 人回来的欢迎语

        self._sit_start: float | None = None
        self._stand_start: float | None = None
        self._last_is_sitting: bool = False
        self._alerted: bool = False
        self._last_alert_time: float | None = None  # 记录上次语音提醒的时间
        self._sitting_frame_count = 0  # 连续判定为坐着的帧数
        self._accumulated_sitting: float = 0.0  # 累计坐着时间（秒）
        self._last_date: str = self._get_date_str()  # 用于检测午夜重置
        self._last_current_sitting_minutes: float = 0.0  # 站立时保持上一帧的current值
        self._last_accumulated_sitting_minutes: float = (
            0.0  # 站立时保持上一帧的accumulated值
        )
        self._pause_start: float | None = (
            None  # 暂停开始时间（检测不到人时），用于补偿暂停期间
        )
        self._pause_accumulated: float = 0.0  # 累计暂停时长（秒）
        self._was_paused: bool = False  # 追踪上一帧是否处于暂停状态

    def update(self, landmarks) -> dict:
        result = {
            "current_sitting_minutes": 0.0,
            "accumulated_sitting_minutes": 0.0,
            "is_sitting": False,
            "alert": False,
            "votes": "",
            "debug_info": "",
            "on_leave": False,  # 人离开画面
            "on_welcome_back": False,  # 人回到画面
        }

        now = time.time()

        # ═══ 检测中断处理：暂停所有计时直到人回到画面 ═══
        if landmarks is None:
            # 检测不到人，开始暂停
            if self._pause_start is None:
                self._pause_start = now  # 记录暂停开始时间
                self._was_paused = True
                result["on_leave"] = True  # 标记人离开事件
            # 返回上一帧的状态（显示暂停前的最后状态）
            result["current_sitting_minutes"] = self._last_current_sitting_minutes
            result["accumulated_sitting_minutes"] = (
                self._last_accumulated_sitting_minutes
            )
            result["debug_info"] = "⏸ 检测中断(暂停计时)"
            return result
        else:
            # 人回到画面，补偿暂停期间
            if self._pause_start is not None:
                pause_duration = now - self._pause_start
                # 所有开始时间向后移动（相当于把暂停时间"删除"掉）
                if self._sit_start is not None:
                    self._sit_start += pause_duration
                if self._stand_start is not None:
                    self._stand_start += pause_duration
                if self._last_alert_time is not None:
                    self._last_alert_time += pause_duration
                # 清除暂停记录
                self._pause_start = None
                # 标记人回来事件（只在暂停后恢复时触发一次）
                if self._was_paused:
                    result["on_welcome_back"] = True
                    self._was_paused = False

        votes = []
        debug_data = {}

        # ═══ 躯干角+膝角联合判断：强制站立的条件 ═══
        # 只有当躯干>160° 且 膝角>140° 时才直接判定为站立
        angles = []
        for ear, shoulder, hip in [
            (KP["left_ear"], KP["left_shoulder"], KP["left_hip"]),
            (KP["right_ear"], KP["right_shoulder"], KP["right_hip"]),
        ]:
            if all_vis(landmarks, ear, shoulder, hip, threshold=0.3):
                angles.append(
                    calc_angle(
                        lm_xy(landmarks, ear),
                        lm_xy(landmarks, shoulder),
                        lm_xy(landmarks, hip),
                    )
                )

        torso_angle = float(np.mean(angles)) if angles else None
        if torso_angle is not None:
            debug_data["torso"] = f"{torso_angle:.1f}°"

        # 膝角检测（先计算，用于联合判断）
        knee_ang_for_constraint = None
        if all_vis(
            landmarks, KP["left_hip"], KP["left_knee"], KP["left_ankle"], threshold=0.3
        ):
            knee_ang_for_constraint = calc_angle(
                lm_xy(landmarks, KP["left_hip"]),
                lm_xy(landmarks, KP["left_knee"]),
                lm_xy(landmarks, KP["left_ankle"]),
            )

        # ═══ 弯腰强制站立：躯干 < 140° → 直接判定为站立 ═══
        if torso_angle is not None and torso_angle < 140:
            is_sitting = False
            result["votes"] = f"BENDING(TORSO<140°)→U"
            result["debug_info"] = " | ".join(f"{k}={v}" for k, v in debug_data.items())
            self._last_is_sitting = is_sitting
            result["is_sitting"] = is_sitting

            # ── 午夜重置检测 ──────────────────────────────
            current_date = self._get_date_str(now)
            if current_date != self._last_date:
                self._accumulated_sitting = 0.0
                self._last_date = current_date

            # 站立状态：保持上一帧的current和accumulated
            if self._stand_start is None:
                self._stand_start = now

            result["current_sitting_minutes"] = self._last_current_sitting_minutes
            result["accumulated_sitting_minutes"] = (
                self._last_accumulated_sitting_minutes
            )
            return result

        # ═══ 中间姿态（140-160°）：膝角伸直 → 判定为站立 ═══
        if (
            torso_angle is not None
            and 140 <= torso_angle <= 160
            and knee_ang_for_constraint is not None
            and knee_ang_for_constraint > 140
        ):
            is_sitting = False
            result["votes"] = (
                f"MID-STAND(140°<TORSO<160°) ∩ KNEE({knee_ang_for_constraint:.0f}°)>140→U"
            )
            result["debug_info"] = " | ".join(f"{k}={v}" for k, v in debug_data.items())
            self._last_is_sitting = is_sitting
            result["is_sitting"] = is_sitting

            # ── 午夜重置检测 ──────────────────────────────
            current_date = self._get_date_str(now)
            if current_date != self._last_date:
                self._accumulated_sitting = 0.0
                self._last_date = current_date

            # 站立状态：保持上一帧的current和accumulated
            if self._stand_start is None:
                self._stand_start = now

            result["current_sitting_minutes"] = self._last_current_sitting_minutes
            result["accumulated_sitting_minutes"] = (
                self._last_accumulated_sitting_minutes
            )
            return result

        # 强制站立条件：躯干>160° AND 膝角>140°
        if (
            torso_angle is not None
            and torso_angle > 160
            and knee_ang_for_constraint is not None
            and knee_ang_for_constraint > 140
        ):
            is_sitting = False
            result["votes"] = (
                f"TORSO({torso_angle:.0f}°)>160 ∩ KNEE({knee_ang_for_constraint:.0f}°)>140→U"
            )
            result["debug_info"] = " | ".join(f"{k}={v}" for k, v in debug_data.items())
            self._last_is_sitting = is_sitting
            result["is_sitting"] = is_sitting

            # ── 午夜重置检测 ──────────────────────────────
            current_date = self._get_date_str(now)
            if current_date != self._last_date:
                self._accumulated_sitting = 0.0
                self._last_date = current_date

            # 直立状态：保持上一帧的current和accumulated
            if self._stand_start is None:
                self._stand_start = now

            result["current_sitting_minutes"] = self._last_current_sitting_minutes
            result["accumulated_sitting_minutes"] = (
                self._last_accumulated_sitting_minutes
            )
            return result

        # 特征1：肩髋 span
        if all_vis(landmarks, KP["left_hip"], KP["left_shoulder"], threshold=0.3):
            span = landmarks[KP["left_hip"]].y - landmarks[KP["left_shoulder"]].y
            is_sitting_vote = span < self.span_threshold
            votes.append(("span", is_sitting_vote))
            debug_data["span"] = f"{span:.3f} (阈值:{self.span_threshold})"

        # 特征2：髋Y绝对位置
        if lm_vis(landmarks, KP["left_hip"], threshold=0.3):
            hip_y = landmarks[KP["left_hip"]].y
            is_sitting_vote = hip_y > self.hip_y_thresh
            votes.append(("hip_y", is_sitting_vote))
            debug_data["hip_y"] = f"{hip_y:.3f} (阈值:{self.hip_y_thresh})"

        # 特征3：膝关节角度（腿可见时才参与）
        if all_vis(
            landmarks, KP["left_hip"], KP["left_knee"], KP["left_ankle"], threshold=0.3
        ):
            # 如果已经计算过膝角（用于强制站立判断），直接使用该值
            if knee_ang_for_constraint is None:
                knee_ang_for_constraint = calc_angle(
                    lm_xy(landmarks, KP["left_hip"]),
                    lm_xy(landmarks, KP["left_knee"]),
                    lm_xy(landmarks, KP["left_ankle"]),
                )
            knee_ang = knee_ang_for_constraint
            is_sitting_vote = knee_ang < self.knee_threshold
            votes.append(("knee", is_sitting_vote))
            debug_data["knee"] = f"{knee_ang:.1f}° (阈值:{self.knee_threshold}°)"

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
        result["debug_info"] = " | ".join(f"{k}={v}" for k, v in debug_data.items())

        # ── 午夜重置检测 ──────────────────────────────────────────────
        current_date = self._get_date_str(now)
        if current_date != self._last_date:
            # 跨过午夜，重置累计时间
            self._accumulated_sitting = 0.0
            self._last_date = current_date
        if is_sitting:
            # ── 坐着状态 ──────────────────────────────────────────────
            self._stand_start = None
            if self._sit_start is None:
                self._sit_start = now

            current_elapsed = now - self._sit_start
            current_minutes = current_elapsed / 60
            accumulated_minutes = (self._accumulated_sitting + current_elapsed) / 60

            result["current_sitting_minutes"] = current_minutes
            result["accumulated_sitting_minutes"] = accumulated_minutes

            # 保存这一帧的值，站立时会用到
            self._last_current_sitting_minutes = current_minutes
            self._last_accumulated_sitting_minutes = accumulated_minutes

            # 提醒逻辑改为基于累计时间
            total_time = self._accumulated_sitting + current_elapsed
            if total_time >= self.alert_seconds and not self._alerted:
                result["alert"] = True
                self._alerted = True
                self._last_alert_time = now
            elif self._alerted and self._last_alert_time is not None:
                if now - self._last_alert_time >= self.repeat_alert_seconds:
                    result["alert"] = True
                    self._last_alert_time = now
        else:
            # ── 站立状态 ──────────────────────────────────────────────
            if self._stand_start is None:
                self._stand_start = now

            stand_elapsed = now - self._stand_start

            if stand_elapsed < self.stand_clear_seconds:
                # 站立 < 2分钟：保持上一帧的current和accumulated（不变）
                result["current_sitting_minutes"] = self._last_current_sitting_minutes
                result["accumulated_sitting_minutes"] = (
                    self._last_accumulated_sitting_minutes
                )
            else:
                # 站立 >= 2分钟：current清零，accumulated保持
                result["current_sitting_minutes"] = 0.0
                result["accumulated_sitting_minutes"] = self._accumulated_sitting / 60

                # 清除坐着记录
                self._sit_start = None
                self._alerted = False
                self._last_alert_time = None
                self._stand_start = None

        return result

    def _get_date_str(self, timestamp: float | None = None) -> str:
        """获取指定时间戳（或当前时间）的日期字符串（YYYY-MM-DD）"""
        if timestamp is None:
            timestamp = time.time()
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


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
        # Debug: 显示躯干角
        put(f"  Debug: Torso={ang}deg", 95, (180, 180, 180))

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
        current_mins = sitting.get("current_sitting_minutes", 0.0)
        accumulated_mins = sitting.get("accumulated_sitting_minutes", 0.0)

        if sitting["alert"]:
            put(
                f"[!] STAND UP! Now: {current_mins:.1f}min | Total: {accumulated_mins:.1f}min",
                h - 60,
                (0, 0, 255),
            )
        elif sitting["is_sitting"]:
            put(
                f"Sitting - Now: {current_mins:.1f}min | Total: {accumulated_mins:.1f}min",
                h - 60,
                (0, 220, 220),
            )
        else:
            put(f"Standing | Total: {accumulated_mins:.1f}min", h - 60, (0, 220, 0))

        # Debug: 显示投票信息
        votes_str = sitting.get("votes", "")
        if votes_str:
            put(f"  Votes: {votes_str}", h - 35, (180, 180, 180))

        # Debug: 显示特征值
        debug_info = sitting.get("debug_info", "")
        if debug_info:
            put(f"  Features: {debug_info}", h - 10, (180, 180, 180))


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
                    "current_sitting_minutes": 0.0,
                    "accumulated_sitting_minutes": 0.0,
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
                f"Now:{sitting.get('current_sitting_minutes', 0):.1f}m Acc:{sitting.get('accumulated_sitting_minutes', 0):.1f}m"
                if sitting["is_sitting"]
                else f"Acc:{sitting.get('accumulated_sitting_minutes', 0):.1f}m"
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
            # 注释掉console的debug输出，改为显示在视频上
            # print(line, end="", flush=True)

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

            # 人离开画面提醒
            if sitting.get("on_leave", False):
                if _alert_proc is None or _alert_proc.poll() is not None:
                    leave_msg = random.choice(cfg["leave_messages"])
                    _alert_proc = subprocess.Popen(
                        ["say", "-v", cfg["alert_voice"], leave_msg]
                    )

            # 人回到画面欢迎
            if sitting.get("on_welcome_back", False):
                if _alert_proc is None or _alert_proc.poll() is not None:
                    welcome_msg = random.choice(cfg["welcome_back_messages"])
                    _alert_proc = subprocess.Popen(
                        ["say", "-v", cfg["alert_voice"], welcome_msg]
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
