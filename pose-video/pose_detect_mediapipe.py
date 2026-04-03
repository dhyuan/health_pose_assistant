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
import logging
import random
import socket
import struct
import subprocess
import threading
import time
import warnings
from enum import Enum, auto
import cv2

warnings.filterwarnings(
    "ignore",
    message=r"SymbolDatabase\.GetPrototype\(\) is deprecated.*",
    category=UserWarning,
    module=r"google\.protobuf\.symbol_database",
)

import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── 中文字体（用于 PIL 绘制） ──
try:
    _FONT_NORMAL = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 20)
    _FONT_SMALL = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 14)
except OSError:
    _FONT_NORMAL = ImageFont.load_default()
    _FONT_SMALL = ImageFont.load_default()

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
    # ── MediaPipe 检测参数 ────────────────────────────────────
    "pose_min_detection_confidence": 0.5,
    "pose_min_tracking_confidence": 0.3,
    "pose_core_visibility_threshold": 0.33,
    # ── 坐姿检测 ──────────────────────────────────────────────
    "posture_torso_threshold": 145,  # 躯干角 < 此值 → 驼背警告（度）。
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
#  检测模块 1：运动计数（深蹲 + 俯卧撑）
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
#  检测模块 2：姿态状态机（融合坐姿检测 + 久坐提醒 + 离开/回来检测）
# ══════════════════════════════════════════════════════════════


class PoseState(Enum):
    """六状态：离开 / 检测失败 / 站立 / 坐姿良好 / 坐姿不良 / 久坐"""

    AWAY = auto()
    DETECT_FAILED = auto()
    STANDING = auto()
    SITTING_GOOD = auto()
    SITTING_BAD = auto()
    SITTING_PROLONGED = auto()


class PoseStateMachine:
    """
    统一状态机：融合坐姿检测、久坐提醒、离开/回来检测。

    状态转换:
      AWAY ──(人出现)──→ STANDING / SITTING_*
      DETECT_FAILED ──(关节点恢复)──→ 恢复之前的检测流程
      STANDING ──(坐下)──→ SITTING_GOOD / SITTING_BAD
      SITTING_GOOD ──(驼背)──→ SITTING_BAD
      SITTING_GOOD ──(久坐)──→ SITTING_PROLONGED
      SITTING_BAD ──(恢复)──→ SITTING_GOOD
      SITTING_BAD ──(久坐)──→ SITTING_PROLONGED
      SITTING_PROLONGED ──(站起)──→ STANDING
      任何状态 ──(关节点丢失)──→ DETECT_FAILED（暂停计时）
      任何状态 ──(人消失)──→ AWAY
    """

    def __init__(self, cfg: dict):
        # ── 阈值 ──
        self.posture_threshold = cfg["posture_torso_threshold"]
        self.head_forward_threshold = cfg["posture_head_forward_threshold"]
        self.posture_alert_seconds = cfg["posture_alert_seconds"]
        self.posture_repeat_seconds = 5.0
        self.sitting_alert_seconds = cfg["sitting_alert_minutes"] * 60
        self.sitting_repeat_seconds = cfg["sitting_repeat_alert_minutes"] * 60
        self.stand_clear_seconds = cfg["sitting_stand_seconds"]
        self.away_reset_seconds = 10  # 离开超过10秒→视为主动休息，清零当前坐时
        self.away_clear_seconds = 5 * 60  # 离开超过5分钟→清零当前坐时
        self.span_threshold = cfg["sitting_torso_span_threshold"]
        self.hip_y_thresh = cfg["sitting_hip_y_threshold"]
        self.knee_threshold = cfg["sitting_knee_angle_threshold"]
        self.frame_smoothing = cfg["sitting_frame_smoothing"]

        # ── 状态 ──
        self.state = PoseState.AWAY

        # ── 计时器 ──
        self._sit_start: float | None = None
        self._stand_start: float | None = None
        self._away_start: float | None = time.time()
        self._detect_failed_start: float | None = None
        self._accumulated_sitting: float = 0.0
        self._current_session_elapsed: float = 0.0  # 暂停坐计时器时保存的已坐时长
        self._bad_posture_start: float | None = None
        self._last_posture_alert_time: float | None = None
        self._last_sitting_alert_time: float | None = None

        # ── 坐立会话追踪 ──
        self._session_wall_start: datetime.datetime | None = None
        self._pending_session: dict | None = None

        # ── 帧平滑 ──
        self._sit_frame_count: int = 0
        self._stand_frame_count: int = 0
        self._last_raw_sitting: bool = False

        # ── 显示缓存 ──
        self._last_current_minutes: float = 0.0
        self._last_accumulated_minutes: float = 0.0

        # ── 语音互锁（leave / welcome_back 各只播一次）──
        self._leave_voice_played: bool = False
        self._welcome_voice_played: bool = False

        # ── 午夜重置 ──
        self._last_date: str = datetime.datetime.now().strftime("%Y-%m-%d")

    # ─────────────────────── 内部检测方法 ───────────────────────

    def _detect_torso_angle(self, landmarks) -> float | None:
        """耳→肩→髋 夹角（左右取平均）"""
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
        return float(np.mean(angles)) if angles else None

    def _detect_head_forward(self, landmarks) -> float:
        """鼻子相对肩膀中点的水平位移（正数=头部前倾）"""
        if lm_vis(landmarks, KP["nose"], threshold=0.3) and all_vis(
            landmarks, KP["left_shoulder"], KP["right_shoulder"], threshold=0.3
        ):
            nose_x = landmarks[KP["nose"]].x
            mid_x = (
                landmarks[KP["left_shoulder"]].x + landmarks[KP["right_shoulder"]].x
            ) / 2
            return nose_x - mid_x
        return 0.0

    def _is_posture_bad(self, torso_angle: float | None, head_forward: float) -> bool:
        if torso_angle is None:
            return False
        return (
            torso_angle < self.posture_threshold
            or head_forward > self.head_forward_threshold
        )

    def _detect_sitting_raw(self, landmarks) -> tuple:
        """
        多特征投票判断坐/站。
        返回 (is_sitting, votes_str, debug_str, torso_angle)。
        """
        votes = []
        debug_data = {}

        torso_angle = self._detect_torso_angle(landmarks)
        if torso_angle is not None:
            debug_data["torso"] = f"{torso_angle:.1f}°"

        knee_ang = None
        if all_vis(
            landmarks,
            KP["left_hip"],
            KP["left_knee"],
            KP["left_ankle"],
            threshold=0.3,
        ):
            knee_ang = calc_angle(
                lm_xy(landmarks, KP["left_hip"]),
                lm_xy(landmarks, KP["left_knee"]),
                lm_xy(landmarks, KP["left_ankle"]),
            )

        # ═══ 强制站立条件 ═══
        if torso_angle is not None and torso_angle < 140:
            ds = " | ".join(f"{k}={v}" for k, v in debug_data.items())
            return False, "BENDING(TORSO<140°)→U", ds, torso_angle

        if (
            torso_angle is not None
            and 140 <= torso_angle <= 160
            and knee_ang is not None
            and knee_ang > 140
        ):
            ds = " | ".join(f"{k}={v}" for k, v in debug_data.items())
            return (
                False,
                f"MID-STAND(TORSO{torso_angle:.0f}°)∩KNEE({knee_ang:.0f}°)>140→U",
                ds,
                torso_angle,
            )

        if (
            torso_angle is not None
            and torso_angle > 160
            and knee_ang is not None
            and knee_ang > 140
        ):
            ds = " | ".join(f"{k}={v}" for k, v in debug_data.items())
            return (
                False,
                f"TORSO({torso_angle:.0f}°)>160∩KNEE({knee_ang:.0f}°)>140→U",
                ds,
                torso_angle,
            )

        # ═══ 特征投票 ═══
        if all_vis(landmarks, KP["left_hip"], KP["left_shoulder"], threshold=0.3):
            span = landmarks[KP["left_hip"]].y - landmarks[KP["left_shoulder"]].y
            votes.append(("span", span < self.span_threshold))
            debug_data["span"] = f"{span:.3f}(阈值:{self.span_threshold})"

        if lm_vis(landmarks, KP["left_hip"], threshold=0.3):
            hip_y = landmarks[KP["left_hip"]].y
            votes.append(("hip_y", hip_y > self.hip_y_thresh))
            debug_data["hip_y"] = f"{hip_y:.3f}(阈值:{self.hip_y_thresh})"

        if knee_ang is not None:
            votes.append(("knee", knee_ang < self.knee_threshold))
            debug_data["knee"] = f"{knee_ang:.1f}°(阈值:{self.knee_threshold}°)"

        line1_keys = ("torso", "span")
        line2_keys = ("hip_y", "knee")
        ds1 = " | ".join(f"{k}={v}" for k, v in debug_data.items() if k in line1_keys)
        ds2 = " | ".join(f"{k}={v}" for k, v in debug_data.items() if k in line2_keys)
        ds = ds1 + "\n" + ds2 if ds2 else ds1

        if not votes:
            return self._last_raw_sitting, "no_data", ds, torso_angle

        sitting_votes = sum(1 for _, v in votes if v)
        is_sitting = sitting_votes > len(votes) / 2
        vs = " ".join(f"{n}:{'S' if v else 'U'}" for n, v in votes)
        return is_sitting, vs, ds, torso_angle

    # ─────────────────────── 状态转换辅助 ───────────────────────

    def _enter_away(self, now: float):
        """进入 AWAY 状态：暂停坐计时器"""
        if self._sit_start is not None:
            self._current_session_elapsed = now - self._sit_start
            self._sit_start = None
        self.state = PoseState.AWAY
        self._away_start = now

    def _return_from_away(self, now: float):
        """从 AWAY 返回：补偿暂停期间的时间偏移"""
        if self._away_start is not None:
            pause_duration = now - self._away_start

            # 离开时间 >= away_reset_seconds → 视为主动休息，清零当前坐时
            if pause_duration >= self.away_reset_seconds:
                if self._current_session_elapsed > 0:
                    self._finalize_session(self._current_session_elapsed)
                    self._accumulated_sitting += self._current_session_elapsed
                    self._current_session_elapsed = 0
                self._sit_start = None
                self._stand_start = None
                self._bad_posture_start = None
                self._last_posture_alert_time = None
                self._last_sitting_alert_time = None
                self._last_current_minutes = 0.0
                self._away_start = None
                return

            if self._stand_start is not None:
                self._stand_start += pause_duration
            if self._bad_posture_start is not None:
                self._bad_posture_start += pause_duration
            if self._last_posture_alert_time is not None:
                self._last_posture_alert_time += pause_duration
            if self._last_sitting_alert_time is not None:
                self._last_sitting_alert_time += pause_duration
            self._away_start = None
        # 恢复之前保存的坐计时（仅短暂离开时）
        if self._current_session_elapsed > 0:
            self._sit_start = now - self._current_session_elapsed
            self._current_session_elapsed = 0

    def _can_detect(self, landmarks) -> bool:
        """检查最少需要的关节点是否可见（至少一侧肩膀 + 一侧髋部）"""
        has_shoulder = lm_vis(landmarks, KP["left_shoulder"], threshold=0.3) or lm_vis(
            landmarks, KP["right_shoulder"], threshold=0.3
        )
        has_hip = lm_vis(landmarks, KP["left_hip"], threshold=0.3) or lm_vis(
            landmarks, KP["right_hip"], threshold=0.3
        )
        return has_shoulder and has_hip

    def _enter_detect_failed(self, now: float):
        """进入 DETECT_FAILED 状态：暂停所有计时器"""
        if self._sit_start is not None:
            self._current_session_elapsed = now - self._sit_start
            self._sit_start = None
        self.state = PoseState.DETECT_FAILED
        self._detect_failed_start = now

    def _return_from_detect_failed(self, now: float):
        """从 DETECT_FAILED 返回：补偿暂停期间的时间偏移"""
        if self._detect_failed_start is not None:
            pause_duration = now - self._detect_failed_start

            # 检测失败时间 >= away_reset_seconds → 视为离开，清零当前坐时
            if pause_duration >= self.away_reset_seconds:
                if self._current_session_elapsed > 0:
                    self._finalize_session(self._current_session_elapsed)
                    self._accumulated_sitting += self._current_session_elapsed
                    self._current_session_elapsed = 0
                self._sit_start = None
                self._stand_start = None
                self._bad_posture_start = None
                self._last_posture_alert_time = None
                self._last_sitting_alert_time = None
                self._last_current_minutes = 0.0
                self._detect_failed_start = None
                return

            if self._stand_start is not None:
                self._stand_start += pause_duration
            if self._bad_posture_start is not None:
                self._bad_posture_start += pause_duration
            if self._last_posture_alert_time is not None:
                self._last_posture_alert_time += pause_duration
            if self._last_sitting_alert_time is not None:
                self._last_sitting_alert_time += pause_duration
            self._detect_failed_start = None
        # 恢复之前保存的坐计时（仅短暂检测失败时）
        if self._current_session_elapsed > 0:
            self._sit_start = now - self._current_session_elapsed
            self._current_session_elapsed = 0

    def _handle_standing(self, now: float, was_sitting: bool, result: dict):
        """处理 STANDING 状态逻辑"""
        if was_sitting:
            # 坐→站：保存当前坐时长
            if self._sit_start is not None:
                self._current_session_elapsed = now - self._sit_start
                self._sit_start = None
            self._bad_posture_start = None
            self._last_posture_alert_time = None

        if self._stand_start is None:
            self._stand_start = now

        self.state = PoseState.STANDING
        result["is_sitting"] = False

        stand_elapsed = now - self._stand_start
        if stand_elapsed >= self.stand_clear_seconds:
            # 站立足够久→清零当前坐时，累计保留
            if self._current_session_elapsed > 0:
                self._finalize_session(self._current_session_elapsed)
                self._accumulated_sitting += self._current_session_elapsed
                self._current_session_elapsed = 0
            self._last_current_minutes = 0.0
            self._last_sitting_alert_time = None

        result["current_sitting_minutes"] = self._last_current_minutes
        result["accumulated_sitting_minutes"] = self._last_accumulated_minutes

    def _handle_sitting(self, now: float, torso_angle, head_forward, result: dict):
        """处理 SITTING_GOOD / SITTING_BAD / SITTING_PROLONGED 逻辑"""
        self._stand_start = None

        # 恢复坐计时
        if self._sit_start is None:
            if self._current_session_elapsed > 0:
                self._sit_start = now - self._current_session_elapsed
                self._current_session_elapsed = 0
            else:
                self._sit_start = now
                self._session_wall_start = datetime.datetime.now(datetime.timezone.utc)

        current_elapsed = now - self._sit_start
        total_sitting = self._accumulated_sitting + current_elapsed
        current_minutes = current_elapsed / 60
        accumulated_minutes = total_sitting / 60

        result["is_sitting"] = True
        result["current_sitting_minutes"] = current_minutes
        result["accumulated_sitting_minutes"] = accumulated_minutes
        self._last_current_minutes = current_minutes
        self._last_accumulated_minutes = accumulated_minutes

        # 检查是否久坐（以本次连续坐的时长为准，站起来超过 stand_clear_seconds 后从零计算）
        if current_elapsed >= self.sitting_alert_seconds:
            self._handle_prolonged(now, result)
        elif self._is_posture_bad(torso_angle, head_forward):
            self._handle_bad_posture(now, result)
        else:
            self._handle_good_posture(result)

    def _handle_prolonged(self, now: float, result: dict):
        """SITTING_PROLONGED: 久坐提醒（不区分坐姿好坏）"""
        if self.state != PoseState.SITTING_PROLONGED:
            result["alert_sitting"] = True
            self._last_sitting_alert_time = now
        elif (
            self._last_sitting_alert_time is not None
            and now - self._last_sitting_alert_time >= self.sitting_repeat_seconds
        ):
            result["alert_sitting"] = True
            self._last_sitting_alert_time = now
        self.state = PoseState.SITTING_PROLONGED
        if result["alert_sitting"] and result.get("voice_event") is None:
            result["voice_event"] = "prolonged_sitting"

    def _handle_bad_posture(self, now: float, result: dict):
        """SITTING_BAD: 坐姿不良 → 超过10秒后每5秒提醒"""
        self.state = PoseState.SITTING_BAD
        if self._bad_posture_start is None:
            self._bad_posture_start = now
        bad_elapsed = now - self._bad_posture_start
        if bad_elapsed >= self.posture_alert_seconds:
            if self._last_posture_alert_time is None:
                result["alert_posture"] = True
                self._last_posture_alert_time = now
            elif now - self._last_posture_alert_time >= self.posture_repeat_seconds:
                result["alert_posture"] = True
                self._last_posture_alert_time = now
        if result["alert_posture"] and result.get("voice_event") is None:
            result["voice_event"] = "bad_posture"

    def _handle_good_posture(self, result: dict):
        """SITTING_GOOD: 坐姿良好"""
        self.state = PoseState.SITTING_GOOD
        self._bad_posture_start = None
        self._last_posture_alert_time = None

    def _finalize_session(self, session_seconds: float):
        """记录已结束的坐立会话，供事件上报使用。"""
        if self._session_wall_start is not None and session_seconds > 0:
            end_time = datetime.datetime.now(datetime.timezone.utc)
            self._pending_session = {
                "start_time": self._session_wall_start.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": round(session_seconds),
            }
            self._session_wall_start = None

    # ─────────────────────── 主更新入口 ───────────────────────

    def update(self, landmarks) -> dict:
        """
        每帧调用一次。传入 landmarks（检测不到人时传 None）。
        返回包含状态、计时、提醒事件的 dict。
        """
        now = time.time()
        result = {
            "state": self.state,
            "state_name": self.state.name,
            "torso_angle": None,
            "head_forward": None,
            "is_sitting": False,
            "current_sitting_minutes": 0.0,
            "accumulated_sitting_minutes": 0.0,
            "alert_posture": False,
            "alert_sitting": False,
            "votes": "",
            "debug_info": "",
            "voice_event": None,  # leave / welcome_back / bad_posture / prolonged_sitting
            "session_ended": None,  # 坐立会话结束时的信息
        }

        # ── 午夜重置 ──
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if current_date != self._last_date:
            # 跨日时结束当前坐立会话
            if self._sit_start is not None:
                self._finalize_session(now - self._sit_start)
                self._sit_start = now
                self._session_wall_start = datetime.datetime.now(datetime.timezone.utc)
            elif self._current_session_elapsed > 0:
                self._finalize_session(self._current_session_elapsed)
                self._current_session_elapsed = 0
            self._accumulated_sitting = 0.0
            self._last_date = current_date

        # ═══ AWAY：检测不到人 ═══
        if landmarks is None:
            if self.state != PoseState.AWAY:
                self._enter_away(now)
                if not self._leave_voice_played:
                    result["voice_event"] = "leave"
            # 离开超过 5 分钟 → 清零当前坐时
            if self._away_start and (now - self._away_start) > self.away_clear_seconds:
                if self._current_session_elapsed > 0:
                    self._finalize_session(self._current_session_elapsed)
                    self._accumulated_sitting += self._current_session_elapsed
                    self._current_session_elapsed = 0
                self._sit_start = None
                self._bad_posture_start = None
                self._last_posture_alert_time = None
                self._last_current_minutes = 0.0
            result["state"] = self.state
            result["state_name"] = self.state.name
            result["current_sitting_minutes"] = self._last_current_minutes
            result["accumulated_sitting_minutes"] = self._last_accumulated_minutes
            result["debug_info"] = "⏸ 检测中断(暂停计时)"
            if self._pending_session is not None:
                result["session_ended"] = self._pending_session
                self._pending_session = None
            return result

        # ═══ 从 AWAY 返回 ═══
        if self.state == PoseState.AWAY:
            self._return_from_away(now)
            if not self._welcome_voice_played:
                result["voice_event"] = "welcome_back"

        # ═══ DETECT_FAILED：关键关节点不可见 ═══
        if not self._can_detect(landmarks):
            if self.state != PoseState.DETECT_FAILED:
                self._enter_detect_failed(now)
            result["state"] = self.state
            result["state_name"] = self.state.name
            result["current_sitting_minutes"] = self._last_current_minutes
            result["accumulated_sitting_minutes"] = self._last_accumulated_minutes
            result["debug_info"] = "⚠ 关节点不可见(暂停计时)"
            if self._pending_session is not None:
                result["session_ended"] = self._pending_session
                self._pending_session = None
            return result

        # ═══ 从 DETECT_FAILED 返回 ═══
        if self.state == PoseState.DETECT_FAILED:
            self._return_from_detect_failed(now)

        # ═══ 坐/站检测 ═══
        is_sitting_raw, votes_str, debug_str, torso_angle = self._detect_sitting_raw(
            landmarks
        )
        self._last_raw_sitting = is_sitting_raw
        head_forward = self._detect_head_forward(landmarks)
        result["torso_angle"] = torso_angle
        result["head_forward"] = head_forward
        result["votes"] = votes_str
        result["debug_info"] = debug_str

        # 帧平滑
        if is_sitting_raw:
            self._sit_frame_count += 1
            self._stand_frame_count = 0
        else:
            self._stand_frame_count += 1
            self._sit_frame_count = 0

        was_sitting = self.state in (
            PoseState.SITTING_GOOD,
            PoseState.SITTING_BAD,
            PoseState.SITTING_PROLONGED,
        )

        if was_sitting:
            want_stand = self._stand_frame_count >= self.frame_smoothing
            want_sit = not want_stand
        elif self.state == PoseState.STANDING:
            want_sit = self._sit_frame_count >= self.frame_smoothing
            want_stand = not want_sit
        else:
            # 从 AWAY / DETECT_FAILED 进入，直接取原始结果
            want_sit = is_sitting_raw
            want_stand = not want_sit

        # ═══ 状态更新 ═══
        if want_stand:
            self._handle_standing(now, was_sitting, result)
        else:
            self._handle_sitting(now, torso_angle, head_forward, result)

        result["state"] = self.state
        result["state_name"] = self.state.name
        if self._pending_session is not None:
            result["session_ended"] = self._pending_session
            self._pending_session = None
        return result


# ══════════════════════════════════════════════════════════════
#  显示层
# ══════════════════════════════════════════════════════════════


def draw_overlay(frame, sm_result: dict, exercise: dict, fps: float, cfg: dict):
    h, w = frame.shape[:2]

    # 使用 PIL 绘制（支持中文）
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    def put(text, y, color=(255, 255, 255)):
        rgb = (color[2], color[1], color[0])  # BGR → RGB
        py = y - 16
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)]:
            draw.text((10 + dx, py + dy), text, font=_FONT_NORMAL, fill=(0, 0, 0))
        draw.text((10, py), text, font=_FONT_NORMAL, fill=rgb)

    def put_small(text, y, color=(180, 180, 180)):
        rgb = (color[2], color[1], color[0])
        py = y - 11
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            draw.text((10 + dx, py + dy), text, font=_FONT_SMALL, fill=(0, 0, 0))
        draw.text((10, py), text, font=_FONT_SMALL, fill=rgb)

    put(f"FPS: {fps:.1f}", 30)

    state_name = sm_result.get("state_name", "AWAY")
    torso_angle = sm_result.get("torso_angle")

    # 坐姿状态 + 躯干角
    if cfg["enable_posture"] and torso_angle is not None:
        ang = f"{torso_angle:.1f}"
        if sm_result["alert_posture"]:
            put(f"[!] POSTURE BAD  {ang}deg", 70, (0, 0, 255))
        elif state_name == "SITTING_BAD":
            put(f"Posture: slouching  {ang}deg", 70, (0, 165, 255))
        else:
            put(f"Posture: good  {ang}deg", 70, (0, 220, 0))
        put_small(f"  State: {state_name}  Torso={ang}deg", 95)

    # 运动计数
    if cfg["enable_exercise"]:
        put(f"Squats:  {exercise['squat_count']}", 110)
        put(f"Pushups: {exercise['pushup_count']}", 145)
        if exercise["squat_angle"] is not None:
            put(f"  knee:  {exercise['squat_angle']:.0f}deg", 175, (180, 180, 180))
        if exercise["pushup_angle"] is not None:
            put(f"  elbow: {exercise['pushup_angle']:.0f}deg", 200, (180, 180, 180))

    # 久坐信息
    if cfg["enable_sitting"]:
        current_mins = sm_result.get("current_sitting_minutes", 0.0)
        accumulated_mins = sm_result.get("accumulated_sitting_minutes", 0.0)

        if sm_result["alert_sitting"]:
            put(
                f"[!] STAND UP! Now: {current_mins:.1f}min | Total: {accumulated_mins:.1f}min",
                h - 60,
                (0, 0, 255),
            )
        elif sm_result["is_sitting"]:
            put(
                f"Sitting - Now: {current_mins:.1f}min | Total: {accumulated_mins:.1f}min",
                h - 60,
                (0, 220, 220),
            )
        elif state_name == "DETECT_FAILED":
            put(
                f"检测中断 | Total: {accumulated_mins:.1f}min",
                h - 60,
                (0, 165, 255),
            )
        elif state_name == "AWAY":
            put(
                f"离开 | Total: {accumulated_mins:.1f}min",
                h - 60,
                (180, 180, 180),
            )
        else:
            put(f"Standing | Total: {accumulated_mins:.1f}min", h - 60, (0, 220, 0))

        votes_str = sm_result.get("votes", "")
        if votes_str:
            put_small(f"  Votes: {votes_str}", h - 50)

        debug_info = sm_result.get("debug_info", "")
        if debug_info:
            lines = debug_info.split("\n")
            put_small(f"  Features: {lines[0]}", h - 30)
            if len(lines) > 1 and lines[1]:
                put_small(f"  Features: {lines[1]}", h - 10)

    # 写回 frame
    frame[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


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
#  MJPEG 流服务器（浏览器可通过 <img> 直接显示）
# ══════════════════════════════════════════════════════════════

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class MJPEGStreamHandler(BaseHTTPRequestHandler):
    """Serves the latest annotated frame as a multipart MJPEG stream."""

    # Class-level shared state (set by MJPEGServer)
    _latest_frame: bytes = b""
    _lock = threading.Lock()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path != "/stream":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            while True:
                with MJPEGStreamHandler._lock:
                    jpeg = MJPEGStreamHandler._latest_frame
                if not jpeg:
                    time.sleep(0.05)
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                time.sleep(0.033)  # ~30 fps cap
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, format, *args):
        pass  # suppress request logging


class MJPEGServer:
    """Runs an MJPEG HTTP server in a daemon thread."""

    def __init__(self, port: int):
        self._port = port
        self._server: HTTPServer | None = None

    def start(self):
        self._server = _ThreadingHTTPServer(("0.0.0.0", self._port), MJPEGStreamHandler)
        t = threading.Thread(
            target=self._server.serve_forever, name="mjpeg-server", daemon=True
        )
        t.start()
        logger.info("MJPEG stream server started on port %d", self._port)

    def update_frame(self, frame: np.ndarray):
        """Encode and store the latest frame for streaming."""
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        with MJPEGStreamHandler._lock:
            MJPEGStreamHandler._latest_frame = buf.tobytes()


# ══════════════════════════════════════════════════════════════
#  主循环
# ══════════════════════════════════════════════════════════════


def _total_sitting_minutes(sm) -> int:
    """Calculate total sitting minutes from PoseStateMachine internal state."""
    total = sm._accumulated_sitting
    if sm._sit_start is not None:
        total += time.time() - sm._sit_start
    elif sm._current_session_elapsed > 0:
        total += sm._current_session_elapsed
    return int(total / 60)


def main(args):
    cfg = CONFIG.copy()
    cfg["port"] = args.port

    if args.production:
        # 生产模式使用已验证稳定参数，并默认关闭诊断日志。
        args.diagnostics = False
        if args.pose_detection_conf is None:
            args.pose_detection_conf = 0.5
        if args.pose_tracking_conf is None:
            args.pose_tracking_conf = 0.3
        if args.pose_core_vis_threshold is None:
            args.pose_core_vis_threshold = 0.33

    if args.pose_detection_conf is not None:
        cfg["pose_min_detection_confidence"] = args.pose_detection_conf
    if args.pose_tracking_conf is not None:
        cfg["pose_min_tracking_confidence"] = args.pose_tracking_conf
    if args.pose_core_vis_threshold is not None:
        cfg["pose_core_visibility_threshold"] = args.pose_core_vis_threshold

    state_machine = PoseStateMachine(cfg)
    exercise_ctr = ExerciseCounter(cfg)

    # ── 后端集成（仅当 --api-url 和 --device-token 都提供时启用）──
    event_reporter = None
    _last_sitting_report: float = time.time()

    # ── MJPEG 流服务器 ──
    mjpeg_server = None
    stream_url = None
    if args.stream_port:
        mjpeg_server = MJPEGServer(args.stream_port)
        mjpeg_server.start()
        # Build URL using hostname for heartbeat reporting
        import socket as _sock

        _hostname = _sock.gethostname()
        stream_url = f"http://{_hostname}.local:{args.stream_port}/stream"

    if args.api_url and args.device_token:
        from config_client import ConfigClient, EventReporter

        config_client = ConfigClient(
            args.api_url,
            args.device_token,
            state_machine,
            exercise_ctr,
            cfg,
            interval=args.config_interval,
        )
        config_client.start()

        event_reporter = EventReporter(
            args.api_url, args.device_token, stream_url=stream_url
        )

        # Heartbeat thread (every 30s)
        def _heartbeat_loop():
            while True:
                event_reporter.heartbeat()
                time.sleep(30)

        threading.Thread(target=_heartbeat_loop, name="heartbeat", daemon=True).start()

        logger.info("已连接后端 %s", args.api_url)

    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    landmark_spec = mp_drawing.DrawingSpec(
        color=(0, 255, 255), thickness=2, circle_radius=2
    )
    connection_spec = mp_drawing.DrawingSpec(
        color=(0, 255, 0), thickness=2, circle_radius=2
    )

    fps_counter, fps_start, current_fps = 0, time.time(), 0.0
    _alert_proc = None  # 记录 say 进程，上一句播完才播下一句
    _last_voice_time: float = 0.0  # 任意两条语音之间的最小冷却时间
    _diag_total_frames = 0
    _diag_pose_detected_frames = 0
    _diag_fallback_detected_frames = 0
    _diag_core_filtered_frames = 0
    _diag_last_ts = time.time()
    _diag_luma_sum = 0.0

    if args.source is not None:
        frame_gen = open_local_camera(int(args.source))
        print(f"[INFO] 使用本地摄像头 {args.source}")
    else:
        frame_gen = receive_frames(cfg["host"], cfg["port"])

    print("[INFO] 按 q 退出")

    with mp_pose.Pose(
        min_detection_confidence=cfg["pose_min_detection_confidence"],
        min_tracking_confidence=cfg["pose_min_tracking_confidence"],
        model_complexity=1,
    ) as pose:
        for frame in frame_gen:
            _diag_total_frames += 1
            # 先旋转再推理，避免相机倒置导致检测率接近 0。
            frame = rotate_frame(frame, cfg["video_rotation_angle"])
            # ── MediaPipe 推理 ────────────────────────────────
            _diag_luma_sum += float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = pose.process(rgb)
            rgb.flags.writeable = True

            # 某些 Pi 流可能出现通道顺序异常：首轮失败时回退再试一次。
            used_fallback = False
            if not results.pose_landmarks:
                frame.flags.writeable = False
                fallback_results = pose.process(frame)
                frame.flags.writeable = True
                if fallback_results.pose_landmarks:
                    results = fallback_results
                    used_fallback = True

            if results.pose_landmarks:
                _diag_pose_detected_frames += 1
                if used_fallback:
                    _diag_fallback_detected_frames += 1

            # ── 骨骼绘制 ──────────────────────────────────────
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=landmark_spec,
                    connection_drawing_spec=connection_spec,
                )

            lms = results.pose_landmarks.landmark if results.pose_landmarks else None

            # ── 过滤低可见度的误检测（物体被误识为人）──
            if lms is not None:
                _core = [
                    KP["left_shoulder"],
                    KP["right_shoulder"],
                    KP["left_hip"],
                    KP["right_hip"],
                ]
                avg_vis = sum(lms[i].visibility for i in _core) / len(_core)
                if avg_vis < cfg["pose_core_visibility_threshold"]:
                    _diag_core_filtered_frames += 1
                    lms = None

            if args.diagnostics:
                now_diag = time.time()
                if now_diag - _diag_last_ts >= args.diag_interval:
                    detect_rate = _diag_pose_detected_frames / max(
                        _diag_total_frames, 1
                    )
                    filtered_rate = _diag_core_filtered_frames / max(
                        _diag_pose_detected_frames, 1
                    )
                    logger.info(
                        "Diag: frames=%d detect_rate=%.1f%% fallback_hits=%d core_filtered=%.1f%% avg_luma=%.1f conf(det=%.2f, track=%.2f, vis=%.2f)",
                        _diag_total_frames,
                        detect_rate * 100,
                        _diag_fallback_detected_frames,
                        filtered_rate * 100,
                        _diag_luma_sum / max(_diag_total_frames, 1),
                        cfg["pose_min_detection_confidence"],
                        cfg["pose_min_tracking_confidence"],
                        cfg["pose_core_visibility_threshold"],
                    )
                    _diag_total_frames = 0
                    _diag_pose_detected_frames = 0
                    _diag_fallback_detected_frames = 0
                    _diag_core_filtered_frames = 0
                    _diag_luma_sum = 0.0
                    _diag_last_ts = now_diag

            # ── 状态机更新（始终调用，传 None 表示检测不到人）──
            sm_result = state_machine.update(lms)

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

            # ── FPS ───────────────────────────────────────────
            fps_counter += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                current_fps = fps_counter / elapsed
                fps_counter, fps_start = 0, time.time()

            # ── 久坐汇报（每 10 分钟上报一次 sitting_summary）──
            if event_reporter:
                now_rpt = time.time()
                if now_rpt - _last_sitting_report >= 600:
                    sit_mins = _total_sitting_minutes(state_machine)
                    event_reporter.report_event(
                        "sitting_summary", {"sitting_minutes": sit_mins}
                    )
                    _last_sitting_report = now_rpt

                # 上报坐立会话结束事件
                session_ended = sm_result.get("session_ended")
                if session_ended:
                    event_reporter.report_event("sitting_session", session_ended)

            # ── 语音提醒（非阻塞，上一句播完且冷却5秒后才播下一句）──
            voice_event = sm_result.get("voice_event")
            now_t = time.time()
            if (
                voice_event
                and (_alert_proc is None or _alert_proc.poll() is not None)
                and (now_t - _last_voice_time >= 5.0)
            ):
                voice_msg = None
                if voice_event == "bad_posture":
                    voice_msg = "你的坐姿不对，请挺直腰背"
                elif voice_event == "prolonged_sitting":
                    voice_msg = cfg["alert_message"]
                elif voice_event == "leave":
                    voice_msg = random.choice(cfg["leave_messages"])
                elif voice_event == "welcome_back":
                    voice_msg = random.choice(cfg["welcome_back_messages"])
                if voice_msg:
                    _alert_proc = subprocess.Popen(
                        ["say", "-v", cfg["alert_voice"], voice_msg]
                    )
                    _last_voice_time = now_t
                    # 上报事件到后端
                    if event_reporter:
                        event_reporter.report_event(voice_event)
                    if voice_event == "leave":
                        state_machine._leave_voice_played = True
                        state_machine._welcome_voice_played = False
                    elif voice_event == "welcome_back":
                        state_machine._welcome_voice_played = True
                        state_machine._leave_voice_played = False

            # ── 画面叠加 ──────────────────────────────────────
            draw_overlay(frame, sm_result, exercise, current_fps, cfg)

            # ── MJPEG 推流 ────────────────────────────────────
            if mjpeg_server is not None:
                mjpeg_server.update_frame(frame)

            if not args.headless:
                cv2.imshow("Health Assistant", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            else:
                time.sleep(0.001)  # yield to MJPEG server threads

    if not args.headless:
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
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="后端 API 地址（如 http://localhost:8000），不填则纯本地模式",
    )
    parser.add_argument(
        "--device-token",
        type=str,
        default=None,
        help="设备 Token（从后端管理页获取）",
    )
    parser.add_argument(
        "--config-interval",
        type=int,
        default=10,
        help="配置轮询间隔秒数（默认 10）",
    )
    parser.add_argument(
        "--stream-port",
        type=int,
        default=8080,
        help="MJPEG 流服务端口（默认 8080，设为 0 禁用）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无窗口模式（不打开 OpenCV 窗口，仅通过 MJPEG 流输出）",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="生产模式：关闭诊断日志并应用稳定阈值",
    )
    parser.add_argument(
        "--pose-detection-conf",
        type=float,
        default=None,
        help="覆盖姿态初检置信度（默认使用内置配置 0.5）",
    )
    parser.add_argument(
        "--pose-tracking-conf",
        type=float,
        default=None,
        help="覆盖姿态跟踪置信度（默认使用内置配置 0.3）",
    )
    parser.add_argument(
        "--pose-core-vis-threshold",
        type=float,
        default=None,
        help="覆盖肩髋核心点平均可见度阈值（默认使用内置配置 0.33）",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="打印姿态检测诊断日志（检测命中率/过滤率）",
    )
    parser.add_argument(
        "--diag-interval",
        type=float,
        default=5.0,
        help="诊断日志输出间隔秒数（默认 5.0）",
    )
    args = parser.parse_args()
    CONFIG["video_rotation_angle"] = args.rotation
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    main(args)
