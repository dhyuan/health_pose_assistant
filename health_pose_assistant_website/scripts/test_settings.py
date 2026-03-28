"""Quick smoke test for Settings page API flow via Next.js proxy."""

import urllib.request
import json
import http.cookiejar

BASE = "http://localhost:3000"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method=method
    )
    try:
        resp = opener.open(req)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


# 1. Login
status, data = api(
    "POST", "/api/auth/login", {"email": "admin@example.com", "password": "admin123"}
)
print(f"1. Login: {status} -> {data}")
assert status == 200

# 2. Get config
status, data = api("GET", "/api/admin/config")
print(f"2. Get config: {status}")

# 3. Create/update config with default values
config = {
    "enable_posture": True,
    "enable_exercise": False,
    "enable_sitting": True,
    "video_rotation_angle": 180,
    "posture_torso_threshold": 145,
    "sitting_alert_minutes": 20,
}
status, data = api("PUT", "/api/admin/config", {"config_json": config})
print(f"3. PUT config: {status} -> version={data.get('version')}")
v1 = data.get("version")
assert status == 200

# 4. Update again -> version should increment
config["sitting_alert_minutes"] = 30
status, data = api("PUT", "/api/admin/config", {"config_json": config})
v2 = data.get("version")
print(
    f"4. PUT config: {status} -> version={v2}, sitting_alert_minutes={data['config_json']['sitting_alert_minutes']}"
)
assert status == 200
assert v2 == v1 + 1
assert data["config_json"]["sitting_alert_minutes"] == 30

print("\nAll checks passed!")
