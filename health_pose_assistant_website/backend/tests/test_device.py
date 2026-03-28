"""Tests for device endpoints: GET /config, POST /events, POST /heartbeat."""

import pytest

from app.models import DeviceConfigBinding


class TestDeviceConfig:
    def test_config_no_profile(self, client, device_headers):
        """No config profile exists → version=0, empty config."""
        resp = client.get("/api/v1/device/config", headers=device_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 0
        assert data["config_json"] == {}

    def test_config_with_active_profile_no_binding(
        self, client, device_headers, active_config
    ):
        """Active profile exists but device has no binding → falls back to active profile."""
        resp = client.get("/api/v1/device/config", headers=device_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 1
        assert data["config_json"]["bad_posture_threshold"] == 0.5

    def test_config_with_binding(
        self, client, device_headers, device_with_token, active_config, db
    ):
        """Device bound to a profile → returns that profile's config."""
        device, _ = device_with_token
        binding = DeviceConfigBinding(device_id=device.id, profile_id=active_config.id)
        db.add(binding)
        db.commit()

        resp = client.get("/api/v1/device/config", headers=device_headers)
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

    def test_config_invalid_token(self, client):
        resp = client.get(
            "/api/v1/device/config", headers={"X-Device-Token": "bad-token"}
        )
        assert resp.status_code == 401

    def test_config_missing_token(self, client):
        resp = client.get("/api/v1/device/config")
        assert resp.status_code == 422  # missing required header


class TestDeviceEvents:
    def test_report_event(self, client, device_headers):
        resp = client.post(
            "/api/v1/device/events",
            json={"event_type": "bad_posture", "payload": {"score": 0.3}},
            headers=device_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ok"
        assert "event_id" in data

    def test_report_event_minimal(self, client, device_headers):
        """payload defaults to empty dict."""
        resp = client.post(
            "/api/v1/device/events",
            json={"event_type": "prolonged_sitting"},
            headers=device_headers,
        )
        assert resp.status_code == 201

    def test_report_event_no_auth(self, client):
        resp = client.post(
            "/api/v1/device/events",
            json={"event_type": "test"},
        )
        assert resp.status_code == 422  # missing X-Device-Token

    def test_report_event_missing_type(self, client, device_headers):
        resp = client.post(
            "/api/v1/device/events",
            json={"payload": {}},
            headers=device_headers,
        )
        assert resp.status_code == 422


class TestHeartbeat:
    def test_heartbeat(self, client, device_headers, device_with_token, db):
        device, _ = device_with_token
        assert device.last_seen_at is None

        resp = client.post("/api/v1/device/heartbeat", headers=device_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        db.refresh(device)
        assert device.last_seen_at is not None

    def test_heartbeat_invalid_token(self, client):
        resp = client.post(
            "/api/v1/device/heartbeat",
            headers={"X-Device-Token": "invalid"},
        )
        assert resp.status_code == 401
