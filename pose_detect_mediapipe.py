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
from enum import Enum, auto
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
    """五状态：离开 / 站立 / 坐姿良好 / 坐姿不良 / 久坐"""

    AWAY = auto()
    STANDING = auto()
    SITTING_GOOD = auto()
    SITTING_BAD = auto()
    SITTING_PROLONGED = auto()


class PoseStateMachine:
    """
    统一状态机：融合坐姿检测、久坐提醒、离开/回来检测。

    状态转换:
      AWAY ──(人出现)──→ STANDING / SITTING_*
      STANDING ──(坐下)──→ SITTING_GOOD / SITTING_BAD
      SITTING_GOOD ──(驼背)──→ SITTING_BAD
      SITTING_GOOD ──(久坐)──→ SITTING_PROLONGED
      SITTING_BAD ──(恢复)──→ SITTING_GOOD
      SITTING_BAD ──(久坐)──→ SITTING_PROLONGED
      SITTING_PROLONGED ──(站起)──→ STANDING
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
        self._accumulated_sitting: float = 0.0
        self._current_session_elapsed: float = 0.0  # 暂停坐计时器时保存的已坐时长
        self._bad_posture_start: float | None = None
        self._last_posture_alert_time: float | None = None
        self._last_sitting_alert_time: float | None = None

        # ── 帧平滑 ──
        self._sit_frame_count: int = 0
        self._stand_frame_count: int = 0
        self._last_raw_sitting: bool = False

        # ── 显示缓存 ──
        self._last_current_minutes: float = 0.0
        self._last_accumulated_minutes: float = 0.0

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

        ds = " | ".join(f"{k}={v}" for k, v in debug_data.items())

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

            # 离开时间 >= stand_clear_seconds → 视为充分休息，清零当前坐时
            if pause_duration >= self.stand_clear_seconds:
                if self._current_session_elapsed > 0:
                    self._accumulated_sitting += self._current_session_elapsed
                    self._current_session_elapsed = 0
                self._sit_start = None
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
        }

        # ── 午夜重置 ──
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if current_date != self._last_date:
            self._accumulated_sitting = 0.0
            self._last_date = current_date

        # ═══ AWAY：检测不到人 ═══
        if landmarks is None:
            if self.state != PoseState.AWAY:
                self._enter_away(now)
                result["voice_event"] = "leave"
            # 离开超过 5 分钟 → 清零当前坐时
            if self._away_start and (now - self._away_start) > self.away_clear_seconds:
                if self._current_session_elapsed > 0:
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
            return result

        # ═══ 从 AWAY 返回 ═══
        if self.state == PoseState.AWAY:
            self._return_from_away(now)
            result["voice_event"] = "welcome_back"

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
            # 从 AWAY 进入，直接取原始结果
            want_sit = is_sitting_raw
            want_stand = not want_sit

        # ═══ 状态更新 ═══
        if want_stand:
            self._handle_standing(now, was_sitting, result)
        else:
            self._handle_sitting(now, torso_angle, head_forward, result)

        result["state"] = self.state
        result["state_name"] = self.state.name
        return result


# ══════════════════════════════════════════════════════════════
#  显示层
# ══════════════════════════════════════════════════════════════


def draw_overlay(frame, sm_result: dict, exercise: dict, fps: float, cfg: dict):
    h, w = frame.shape[:2]

    def put(text, y, color=(255, 255, 255)):
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3)
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

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
        put(f"  State: {state_name}  Torso={ang}deg", 95, (180, 180, 180))

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
        else:
            put(f"Standing | Total: {accumulated_mins:.1f}min", h - 60, (0, 220, 0))

        votes_str = sm_result.get("votes", "")
        if votes_str:
            put(f"  Votes: {votes_str}", h - 35, (180, 180, 180))

        debug_info = sm_result.get("debug_info", "")
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

    state_machine = PoseStateMachine(cfg)
    exercise_ctr = ExerciseCounter(cfg)

    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles

    fps_counter, fps_start, current_fps = 0, time.time(), 0.0
    _alert_proc = None  # 记录 say 进程，上一句播完才播下一句
    _last_voice_time: float = 0.0  # 任意两条语音之间的最小冷却时间

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

            # ── 视频旋转 ──────────────────────────────────────────
            frame = rotate_frame(frame, cfg["video_rotation_angle"])
            # ── 画面叠加 ──────────────────────────────────────
            draw_overlay(frame, sm_result, exercise, current_fps, cfg)
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
