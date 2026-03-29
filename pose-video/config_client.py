"""
config_client.py
================
Background threads for communicating with the Health Pose Assistant backend:
  - ConfigClient: polls config every N seconds, hot-patches thresholds
  - EventReporter: non-blocking event submission + heartbeat

Usage (from pose_detect_mediapipe.py):
    from config_client import ConfigClient, EventReporter

    reporter = EventReporter(api_url, device_token)
    config_cl = ConfigClient(api_url, device_token,
                             state_machine, exercise_ctr, cfg)
    config_cl.start()

When --api-url / --device-token are omitted the module is never imported
and pose-video runs in standalone local mode.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

logger = logging.getLogger("config_client")

# ── CONFIG key → PoseStateMachine attribute mapping ──────────
_SM_ATTR_MAP = {
    "posture_torso_threshold": "posture_threshold",
    "posture_head_forward_threshold": "head_forward_threshold",
    "posture_alert_seconds": "posture_alert_seconds",
    "sitting_alert_minutes": ("sitting_alert_seconds", lambda v: v * 60),
    "sitting_repeat_alert_minutes": ("sitting_repeat_seconds", lambda v: v * 60),
    "sitting_stand_seconds": "stand_clear_seconds",
    "sitting_torso_span_threshold": "span_threshold",
    "sitting_hip_y_threshold": "hip_y_thresh",
    "sitting_knee_angle_threshold": "knee_threshold",
    "sitting_frame_smoothing": "frame_smoothing",
}

# ── CONFIG key → ExerciseCounter attribute mapping ───────────
_EC_ATTR_MAP = {
    "squat_down_angle": "sq_down",
    "squat_up_angle": "sq_up",
    "pushup_down_angle": "pu_down",
    "pushup_up_angle": "pu_up",
}

# ── Keys that should update the runtime CONFIG dict directly ─
_CFG_DIRECT_KEYS = {
    "enable_posture",
    "enable_exercise",
    "enable_sitting",
    "alert_voice",
    "alert_message",
    "leave_messages",
    "welcome_back_messages",
    "video_rotation_angle",
}


# ══════════════════════════════════════════════════════════════
#  ConfigClient
# ══════════════════════════════════════════════════════════════


class ConfigClient:
    """Daemon thread that polls GET /device/config and hot-patches thresholds."""

    def __init__(
        self,
        api_url,
        device_token,
        state_machine,
        exercise_counter,
        config_dict,
        interval=10,
    ):
        self._api_url = api_url.rstrip("/")
        self._headers = {"X-Device-Token": device_token}
        self._sm = state_machine
        self._ec = exercise_counter
        self._cfg = config_dict
        self._interval = interval
        self._version = 0
        self._stop = threading.Event()

    def start(self):
        t = threading.Thread(target=self._loop, name="config-client", daemon=True)
        t.start()
        return t

    def stop(self):
        self._stop.set()

    # ──────────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._poll()
            except Exception:
                logger.warning("Config poll failed", exc_info=True)
            self._stop.wait(self._interval)

    def _poll(self):
        resp = requests.get(
            f"{self._api_url}/api/v1/device/config",
            headers=self._headers,
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()

        new_version = data.get("version", 0)
        today_sitting = data.get("today_sitting_minutes", 0)
        config_json = data.get("config_json", {})

        # First poll: restore accumulated sitting from server (recovery on restart)
        if self._version == 0 and today_sitting > 0:
            current_mins = self._sm._accumulated_sitting / 60
            if today_sitting > current_mins:
                self._sm._accumulated_sitting = today_sitting * 60
                logger.info(
                    "Restored today_sitting_minutes=%d from server", today_sitting
                )

        if new_version <= self._version:
            return

        # Hot-patch PoseStateMachine thresholds
        for cfg_key, mapping in _SM_ATTR_MAP.items():
            if cfg_key in config_json:
                if isinstance(mapping, tuple):
                    attr_name, transform = mapping
                    setattr(self._sm, attr_name, transform(config_json[cfg_key]))
                else:
                    setattr(self._sm, mapping, config_json[cfg_key])

        # Hot-patch ExerciseCounter thresholds
        for cfg_key, attr_name in _EC_ATTR_MAP.items():
            if cfg_key in config_json:
                setattr(self._ec, attr_name, config_json[cfg_key])

        # Update runtime CONFIG dict (voice messages, feature flags, etc.)
        for key in _CFG_DIRECT_KEYS:
            if key in config_json:
                self._cfg[key] = config_json[key]

        self._version = new_version
        logger.info("Config updated to version %d", new_version)


# ══════════════════════════════════════════════════════════════
#  EventReporter
# ══════════════════════════════════════════════════════════════


class EventReporter:
    """Non-blocking event submission via ThreadPoolExecutor."""

    def __init__(self, api_url, device_token, max_workers=2, stream_url=None):
        self._api_url = api_url.rstrip("/")
        self._headers = {
            "X-Device-Token": device_token,
            "Content-Type": "application/json",
        }
        self._stream_url = stream_url
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="event-rpt"
        )

    def report_event(self, event_type, payload=None):
        """Submit a posture event (fire-and-forget)."""
        self._pool.submit(self._post_event, event_type, payload or {})

    def heartbeat(self):
        """Submit a heartbeat (fire-and-forget)."""
        self._pool.submit(self._post_heartbeat)

    # ──────────────────────────────────────────────────────────

    def _post_event(self, event_type, payload):
        try:
            requests.post(
                f"{self._api_url}/api/v1/device/events",
                json={"event_type": event_type, "payload": payload},
                headers=self._headers,
                timeout=5,
            )
        except Exception:
            logger.warning("Event report failed (%s)", event_type, exc_info=True)

    def _post_heartbeat(self):
        try:
            body = {}
            if self._stream_url:
                body["stream_url"] = self._stream_url
            requests.post(
                f"{self._api_url}/api/v1/device/heartbeat",
                json=body if body else None,
                headers=self._headers,
                timeout=5,
            )
        except Exception:
            logger.warning("Heartbeat failed", exc_info=True)

    def shutdown(self):
        self._pool.shutdown(wait=False)
