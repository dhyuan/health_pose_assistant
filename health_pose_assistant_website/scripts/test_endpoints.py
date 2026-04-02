"""Quick smoke test for all Phase 1 endpoints."""

import json
import os
import urllib.request
import urllib.error

BASE = "http://localhost:8001"
ADMIN_PASSWORD = os.environ.get("HPA_ADMIN_PASS")


def require_admin_password():
    if not ADMIN_PASSWORD:
        raise RuntimeError("Set HPA_ADMIN_PASS before running this smoke test.")


def req(method, path, data=None, headers=None):
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(
        f"{BASE}{path}", data=body, headers=headers, method=method
    )
    try:
        resp = urllib.request.urlopen(r)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test():
    require_admin_password()
    print("=" * 60)
    print("Phase 1 Endpoint Smoke Test")
    print("=" * 60)

    # 1. Health check
    status, body = req("GET", "/health")
    print(f"\n[{status}] GET /health -> {body}")
    assert status == 200

    # 2. Login (admin)
    status, body = req(
        "POST",
        "/api/v1/auth/login",
        {"email": "admin@example.com", "password": ADMIN_PASSWORD},
    )
    print(
        f"[{status}] POST /api/v1/auth/login -> token={body.get('access_token', '')[:20]}..."
    )
    assert status == 200
    token = body["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    # 3. GET /auth/me
    status, body = req("GET", "/api/v1/auth/me", headers=auth)
    print(f"[{status}] GET /api/v1/auth/me -> {body}")
    assert status == 200
    assert body["email"] == "admin@example.com"

    # 4. POST /admin/devices (register device)
    status, body = req(
        "POST",
        "/api/v1/admin/devices",
        {"device_code": "PI-001", "name": "Test Pi"},
        headers=auth,
    )
    print(
        f"[{status}] POST /admin/devices -> device_id={body.get('device', {}).get('id')}, token={body.get('plain_token', '')[:20]}..."
    )
    assert status == 201
    device_token = body["plain_token"]

    # 5. GET /admin/devices
    status, body = req("GET", "/api/v1/admin/devices", headers=auth)
    print(f"[{status}] GET /admin/devices -> {len(body)} device(s)")
    assert status == 200

    # 6. PUT /admin/config (create initial config)
    config_data = {"config_json": {"bad_posture_threshold": 0.5, "alert_interval": 30}}
    status, body = req("PUT", "/api/v1/admin/config", config_data, headers=auth)
    print(f"[{status}] PUT /admin/config -> version={body.get('version')}")
    assert status == 200

    # 7. GET /admin/config
    status, body = req("GET", "/api/v1/admin/config", headers=auth)
    print(
        f"[{status}] GET /admin/config -> version={body.get('version')}, config={body.get('config_json')}"
    )
    assert status == 200

    # 8. PUT /admin/config again (version should increment)
    config_data = {"config_json": {"bad_posture_threshold": 0.6, "alert_interval": 20}}
    status, body = req("PUT", "/api/v1/admin/config", config_data, headers=auth)
    print(
        f"[{status}] PUT /admin/config -> version={body.get('version')} (should be 2)"
    )
    assert status == 200 and body["version"] == 2

    # 9. GET /admin/stats
    status, body = req("GET", "/api/v1/admin/stats", headers=auth)
    print(f"[{status}] GET /admin/stats -> {len(body)} stat(s)")
    assert status == 200

    # ---- Device endpoints ----
    dev_auth = {"X-Device-Token": device_token}

    # 10. GET /device/config
    status, body = req("GET", "/api/v1/device/config", headers=dev_auth)
    print(
        f"[{status}] GET /device/config -> version={body.get('version')}, config={body.get('config_json')}"
    )
    assert status == 200

    # 11. POST /device/events
    status, body = req(
        "POST",
        "/api/v1/device/events",
        {"event_type": "bad_posture", "payload": {"score": 0.3}},
        headers=dev_auth,
    )
    print(f"[{status}] POST /device/events -> {body}")
    assert status == 201

    # 12. POST /device/heartbeat
    status, body = req("POST", "/api/v1/device/heartbeat", headers=dev_auth)
    print(f"[{status}] POST /device/heartbeat -> {body}")
    assert status == 200

    # ---- Negative tests ----

    # 13. Unauthorized access (no token)
    status, body = req("GET", "/api/v1/auth/me")
    print(f"\n[{status}] GET /auth/me (no token) -> {body.get('detail')}")
    assert status in (401, 403)

    # 14. Invalid device token
    status, body = req(
        "GET", "/api/v1/device/config", headers={"X-Device-Token": "invalid-token"}
    )
    print(f"[{status}] GET /device/config (bad token) -> {body.get('detail')}")
    assert status == 401

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    test()
