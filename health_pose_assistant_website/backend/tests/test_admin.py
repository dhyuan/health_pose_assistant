"""Tests for admin endpoints: devices, config, stats, dashboard."""

import datetime

from app.models import DailyStat, Device, DeviceStatus, PostureEvent


class TestAdminDevices:
    def test_list_devices_empty(self, client, admin_headers):
        resp = client.get("/api/v1/admin/devices", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_register_device(self, client, admin_headers):
        resp = client.post(
            "/api/v1/admin/devices",
            json={"device_code": "PI-100", "name": "Living Room"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["device"]["device_code"] == "PI-100"
        assert data["device"]["name"] == "Living Room"
        assert len(data["plain_token"]) > 20

    def test_register_device_then_list(self, client, admin_headers):
        client.post(
            "/api/v1/admin/devices",
            json={"device_code": "PI-200", "name": "Bedroom"},
            headers=admin_headers,
        )
        resp = client.get("/api/v1/admin/devices", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_register_duplicate_device_code(self, client, admin_headers):
        client.post(
            "/api/v1/admin/devices",
            json={"device_code": "DUP", "name": "First"},
            headers=admin_headers,
        )
        resp = client.post(
            "/api/v1/admin/devices",
            json={"device_code": "DUP", "name": "Second"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_register_device_auto_binds_config(
        self, client, admin_headers, active_config
    ):
        """If an active profile exists, new device gets auto-bound."""
        resp = client.post(
            "/api/v1/admin/devices",
            json={"device_code": "AUTO-BIND", "name": "AutoBind"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        # Verify the device can fetch config via device token
        token = resp.json()["plain_token"]
        cfg_resp = client.get(
            "/api/v1/device/config", headers={"X-Device-Token": token}
        )
        assert cfg_resp.status_code == 200
        assert cfg_resp.json()["version"] == 1

    def test_non_admin_cannot_list(self, client, normal_token):
        resp = client.get(
            "/api/v1/admin/devices",
            headers={"Authorization": f"Bearer {normal_token}"},
        )
        assert resp.status_code == 403

    def test_no_auth_cannot_register(self, client):
        resp = client.post(
            "/api/v1/admin/devices",
            json={"device_code": "X", "name": "Y"},
        )
        assert resp.status_code in (401, 403)


class TestAdminConfig:
    def test_get_config_none(self, client, admin_headers):
        resp = client.get("/api/v1/admin/config", headers=admin_headers)
        assert resp.status_code == 404

    def test_put_config_creates(self, client, admin_headers):
        resp = client.put(
            "/api/v1/admin/config",
            json={"config_json": {"threshold": 0.5}},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 1
        assert data["config_json"]["threshold"] == 0.5
        assert data["is_active"] is True

    def test_put_config_increments_version(self, client, admin_headers, active_config):
        resp = client.put(
            "/api/v1/admin/config",
            json={"config_json": {"threshold": 0.8}},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    def test_get_config_after_create(self, client, admin_headers, active_config):
        resp = client.get("/api/v1/admin/config", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

    def test_put_config_replaces_json(self, client, admin_headers, active_config):
        client.put(
            "/api/v1/admin/config",
            json={"config_json": {"new_key": "value"}},
            headers=admin_headers,
        )
        resp = client.get("/api/v1/admin/config", headers=admin_headers)
        data = resp.json()
        assert "new_key" in data["config_json"]
        # old keys should be gone (full replace, not merge)
        assert "bad_posture_threshold" not in data["config_json"]


class TestAdminStats:
    def test_stats_empty(self, client, admin_headers):
        resp = client.get("/api/v1/admin/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_stats_with_data(self, client, admin_headers, device_with_token, db):
        device, _ = device_with_token
        stat = DailyStat(
            device_id=device.id,
            stat_date=datetime.date(2026, 3, 28),
            bad_posture_count=5,
            prolonged_alert_count=2,
            sitting_minutes=120,
            away_count=3,
        )
        db.add(stat)
        db.commit()

        resp = client.get("/api/v1/admin/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["bad_posture_count"] == 5


class TestAdminUpdateDevice:
    def test_update_device_name(self, client, admin_headers, device_with_token, db):
        device, _ = device_with_token
        resp = client.put(
            f"/api/v1/admin/devices/{device.id}",
            json={"name": "New Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_update_nonexistent_device(self, client, admin_headers):
        resp = client.put(
            "/api/v1/admin/devices/9999",
            json={"name": "No Such"},
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestAdminDeleteDevice:
    def test_delete_device(self, client, admin_headers, device_with_token, db):
        device, _ = device_with_token
        resp = client.delete(
            f"/api/v1/admin/devices/{device.id}", headers=admin_headers
        )
        assert resp.status_code == 204

        # Verify device is gone
        assert db.query(Device).filter(Device.id == device.id).first() is None

    def test_delete_nonexistent_device(self, client, admin_headers):
        resp = client.delete("/api/v1/admin/devices/9999", headers=admin_headers)
        assert resp.status_code == 404


class TestAdminRegenerateToken:
    def test_regenerate_token(self, client, admin_headers, device_with_token):
        device, old_plain = device_with_token
        resp = client.post(
            f"/api/v1/admin/devices/{device.id}/regenerate-token",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        new_token = data["plain_token"]
        assert len(new_token) > 20
        assert new_token != old_plain

        # Old token should no longer work
        resp_old = client.get(
            "/api/v1/device/config", headers={"X-Device-Token": old_plain}
        )
        assert resp_old.status_code == 401

        # New token should work
        resp_new = client.get(
            "/api/v1/device/config", headers={"X-Device-Token": new_token}
        )
        assert resp_new.status_code == 200

    def test_regenerate_token_nonexistent(self, client, admin_headers):
        resp = client.post(
            "/api/v1/admin/devices/9999/regenerate-token", headers=admin_headers
        )
        assert resp.status_code == 404


class TestAdminDashboard:
    def test_dashboard_empty(self, client, admin_headers):
        resp = client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_devices"] == 0
        assert data["online_devices"] == 0
        assert data["today"]["bad_posture_count"] == 0

    def test_dashboard_with_data(self, client, admin_headers, device_with_token, db):
        device, _ = device_with_token
        # Mark device as online (last_seen_at within 5 min)
        device.last_seen_at = datetime.datetime.now(datetime.timezone.utc)
        db.add(device)

        # Add today's stats
        stat = DailyStat(
            device_id=device.id,
            stat_date=datetime.date.today(),
            bad_posture_count=7,
            prolonged_alert_count=3,
            sitting_minutes=200,
            away_count=4,
        )
        db.add(stat)
        db.commit()

        resp = client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_devices"] == 1
        assert data["online_devices"] == 1
        assert data["today"]["bad_posture_count"] == 7
        assert data["today"]["sitting_minutes"] == 200

    def test_dashboard_excludes_stale_device_after_5_minutes(
        self, client, admin_headers, device_with_token, db
    ):
        device, _ = device_with_token
        device.last_seen_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(minutes=6)
        db.add(device)
        db.commit()

        resp = client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["online_devices"] == 0

    def test_stats_filter_by_device(self, client, admin_headers, device_with_token, db):
        device, _ = device_with_token
        db.add(
            DailyStat(
                device_id=device.id,
                stat_date=datetime.date(2026, 3, 27),
                bad_posture_count=1,
                prolonged_alert_count=0,
                sitting_minutes=60,
                away_count=0,
            )
        )
        db.commit()

        resp = client.get(
            f"/api/v1/admin/stats?device_id={device.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = client.get(
            "/api/v1/admin/stats?device_id=9999",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_stats_filter_by_date(self, client, admin_headers, device_with_token, db):
        device, _ = device_with_token
        for day in (25, 26, 27, 28):
            db.add(
                DailyStat(
                    device_id=device.id,
                    stat_date=datetime.date(2026, 3, day),
                    bad_posture_count=day,
                    prolonged_alert_count=0,
                    sitting_minutes=0,
                    away_count=0,
                )
            )
        db.commit()

        resp = client.get(
            "/api/v1/admin/stats?from=2026-03-26&to=2026-03-27",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_stats_non_admin_forbidden(self, client, normal_token):
        resp = client.get(
            "/api/v1/admin/stats",
            headers={"Authorization": f"Bearer {normal_token}"},
        )
        assert resp.status_code == 403


class TestDeviceStreamUrl:
    def test_device_list_includes_stream_url(self, client, admin_headers, db):
        from app.models import Device

        # Register a device
        resp = client.post(
            "/api/v1/admin/devices",
            json={"device_code": "STREAM-01", "name": "Stream Test"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["device"]["stream_url"] is None

        # Set stream_url directly
        device = db.query(Device).filter(Device.device_code == "STREAM-01").first()
        device.stream_url = "http://mac.local:8080/stream"
        db.commit()

        # List should show stream_url
        resp = client.get("/api/v1/admin/devices", headers=admin_headers)
        devices = resp.json()
        assert devices[0]["stream_url"] == "http://mac.local:8080/stream"

    def test_stream_device_not_found(self, client, admin_headers):
        resp = client.get("/api/v1/admin/devices/9999/stream", headers=admin_headers)
        assert resp.status_code == 404

    def test_stream_device_no_url(self, client, admin_headers):
        # Register device without stream_url
        resp = client.post(
            "/api/v1/admin/devices",
            json={"device_code": "NO-STREAM", "name": "No Stream"},
            headers=admin_headers,
        )
        device_id = resp.json()["device"]["id"]

        resp = client.get(
            f"/api/v1/admin/devices/{device_id}/stream",
            headers=admin_headers,
        )
        assert resp.status_code == 404
        assert "no stream" in resp.json()["detail"].lower()


class TestSittingSessions:
    def test_sitting_sessions_empty(self, client, admin_headers):
        resp = client.get(
            "/api/v1/admin/sitting-sessions?date=2026-03-29",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions"] == []
        assert data["sitting_alert_minutes"] == 20  # default

    def test_sitting_sessions_with_data(
        self, client, admin_headers, device_with_token, db
    ):
        device, _ = device_with_token
        target_date = datetime.date(2026, 3, 29)
        ts = datetime.datetime(2026, 3, 29, 9, 0, 0, tzinfo=datetime.timezone.utc)

        db.add(
            PostureEvent(
                device_id=device.id,
                event_type="sitting_session",
                payload={
                    "start_time": "2026-03-29T09:00:00+00:00",
                    "end_time": "2026-03-29T09:45:00+00:00",
                    "duration_seconds": 2700,
                },
                created_at=ts,
            )
        )
        db.add(
            PostureEvent(
                device_id=device.id,
                event_type="sitting_session",
                payload={
                    "start_time": "2026-03-29T14:00:00+00:00",
                    "end_time": "2026-03-29T14:15:00+00:00",
                    "duration_seconds": 900,
                },
                created_at=datetime.datetime(
                    2026, 3, 29, 14, 15, 0, tzinfo=datetime.timezone.utc
                ),
            )
        )
        db.commit()

        resp = client.get(
            f"/api/v1/admin/sitting-sessions?date=2026-03-29",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 2
        assert data["sessions"][0]["duration_seconds"] == 2700
        assert data["sessions"][1]["duration_seconds"] == 900

    def test_sitting_sessions_filter_by_device(
        self, client, admin_headers, device_with_token, db
    ):
        device, _ = device_with_token
        ts = datetime.datetime(2026, 3, 29, 10, 0, 0, tzinfo=datetime.timezone.utc)
        db.add(
            PostureEvent(
                device_id=device.id,
                event_type="sitting_session",
                payload={
                    "start_time": "2026-03-29T10:00:00+00:00",
                    "end_time": "2026-03-29T10:30:00+00:00",
                    "duration_seconds": 1800,
                },
                created_at=ts,
            )
        )
        db.commit()

        # Matching device
        resp = client.get(
            f"/api/v1/admin/sitting-sessions?date=2026-03-29&device_id={device.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["sessions"]) == 1

        # Non-existing device
        resp = client.get(
            "/api/v1/admin/sitting-sessions?date=2026-03-29&device_id=9999",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["sessions"]) == 0

    def test_sitting_sessions_alert_from_config(
        self, client, admin_headers, active_config, db
    ):
        # Update config to include sitting_alert_minutes
        active_config.config_json = {"sitting_alert_minutes": 30}
        db.commit()

        resp = client.get(
            "/api/v1/admin/sitting-sessions?date=2026-03-29",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["sitting_alert_minutes"] == 30

    def test_sitting_sessions_date_required(self, client, admin_headers):
        resp = client.get(
            "/api/v1/admin/sitting-sessions",
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_sitting_sessions_include_carry_over_status_from_previous_day(
        self, client, admin_headers, device_with_token, db
    ):
        device, _ = device_with_token
        db.add(
            DeviceStatus(
                device_id=device.id,
                status="online",
                changed_at=datetime.datetime(
                    2026, 3, 28, 23, 30, 0, tzinfo=datetime.timezone.utc
                ),
                extra=None,
            )
        )
        db.commit()

        resp = client.get(
            f"/api/v1/admin/sitting-sessions?date=2026-03-29&device_id={device.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        spans = resp.json()["device_status_spans"]
        assert spans == [
            {
                "start": "2026-03-29T00:00:00+00:00",
                "end": "2026-03-30T00:00:00+00:00",
                "status": "online",
            }
        ]

    def test_sitting_sessions_extend_last_offline_status_to_day_end(
        self, client, admin_headers, device_with_token, db
    ):
        device, _ = device_with_token
        db.add_all(
            [
                DeviceStatus(
                    device_id=device.id,
                    status="online",
                    changed_at=datetime.datetime(
                        2026, 3, 29, 8, 0, 0, tzinfo=datetime.timezone.utc
                    ),
                    extra=None,
                ),
                DeviceStatus(
                    device_id=device.id,
                    status="offline",
                    changed_at=datetime.datetime(
                        2026, 3, 29, 12, 0, 0, tzinfo=datetime.timezone.utc
                    ),
                    extra=None,
                ),
            ]
        )
        db.commit()

        resp = client.get(
            f"/api/v1/admin/sitting-sessions?date=2026-03-29&device_id={device.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        spans = resp.json()["device_status_spans"]
        assert spans == [
            {
                "start": "2026-03-29T08:00:00+00:00",
                "end": "2026-03-29T12:00:00+00:00",
                "status": "online",
            },
            {
                "start": "2026-03-29T12:00:00+00:00",
                "end": "2026-03-30T00:00:00+00:00",
                "status": "offline",
            },
        ]
