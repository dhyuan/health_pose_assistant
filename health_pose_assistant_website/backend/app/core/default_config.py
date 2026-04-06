"""Default pose/video configuration used by admin reset endpoints."""

from __future__ import annotations

DEFAULT_CONFIG: dict = {
    # Feature flags
    "enable_posture": True,
    "enable_exercise": False,
    "enable_sitting": True,
    # Video
    "video_rotation_angle": 180,
    # Posture detection
    "posture_torso_threshold": 145,
    "posture_head_forward_threshold": 0.05,
    "posture_alert_seconds": 10,
    # Exercise counting
    "squat_down_angle": 100,
    "squat_up_angle": 160,
    "pushup_down_angle": 90,
    "pushup_up_angle": 160,
    # Sitting reminders
    "sitting_alert_minutes": 20,
    "sitting_stand_seconds": 60,
    "sitting_repeat_alert_minutes": 1.0,
    # Voice
    "alert_voice": "Meijia",
    "alert_message": "你已经坐了很久了，站起来活动一下吧！",
    # Away / welcome messages
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
    # MediaPipe detection parameters
    "pose_min_detection_confidence": 0.5,
    "pose_min_tracking_confidence": 0.5,
    "pose_core_visibility_threshold": 0.5,
    "pose_presence_landmark_threshold": 0.35,
    "pose_presence_in_frame_margin": 0.02,
    "pose_min_core_visible_count": 3,
    "pose_min_head_visible_count": 1,
    "pose_require_same_side_torso": True,
    "pose_min_torso_span": 0.16,
    "pose_presence_confirm_frames": 3,
    # Sit/stand thresholds (desk-side calibrated)
    "sitting_torso_span_threshold": 0.27,
    "sitting_hip_y_threshold": 0.44,
    "sitting_knee_angle_threshold": 130,
    "sitting_torso_lean_threshold": 155,
    "sitting_knee_straight_threshold": 150,
    "sitting_knee_strong_threshold": 110,
    "sitting_frame_smoothing": 3,
}
