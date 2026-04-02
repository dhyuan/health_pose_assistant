"""Tests for scheduled task behaviors."""

import datetime

from app.models import DeviceStatus
from app.tasks import mark_stale_devices_offline


class TestMarkStaleDevicesOffline:
    def test_marks_stale_device_offline(self, device_with_token, db):
        device, _ = device_with_token
        device.last_seen_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(minutes=6)
        db.add(device)
        db.commit()

        mark_stale_devices_offline()

        latest = (
            db.query(DeviceStatus)
            .filter(DeviceStatus.device_id == device.id)
            .order_by(DeviceStatus.changed_at.desc())
            .first()
        )
        assert latest is not None
        assert latest.status == "offline"
        assert (latest.extra or {}).get("reason") == "heartbeat_timeout"

    def test_does_not_duplicate_offline_status(self, device_with_token, db):
        device, _ = device_with_token
        now = datetime.datetime.now(datetime.timezone.utc)
        device.last_seen_at = now - datetime.timedelta(minutes=6)
        db.add(device)
        db.add(
            DeviceStatus(
                device_id=device.id,
                status="offline",
                changed_at=now - datetime.timedelta(minutes=1),
                extra=None,
            )
        )
        db.commit()

        mark_stale_devices_offline()

        offline_count = (
            db.query(DeviceStatus)
            .filter(
                DeviceStatus.device_id == device.id, DeviceStatus.status == "offline"
            )
            .count()
        )
        assert offline_count == 1

    def test_keeps_recent_device_online(self, device_with_token, db):
        device, _ = device_with_token
        device.last_seen_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(minutes=2)
        db.add(device)
        db.commit()

        mark_stale_devices_offline()

        latest = (
            db.query(DeviceStatus)
            .filter(DeviceStatus.device_id == device.id)
            .order_by(DeviceStatus.changed_at.desc())
            .first()
        )
        assert latest is None
