"""Tests for auth endpoints: POST /login, GET /me."""


class TestLogin:
    def test_login_success(self, client, admin_user):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": "testpass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, admin_user):
        resp = client.post(
            "/api/v1/auth/login", json={"email": "admin@test.com", "password": "wrong"}
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post(
            "/api/v1/auth/login", json={"email": "nobody@test.com", "password": "pass"}
        )
        assert resp.status_code == 401

    def test_login_invalid_email_format(self, client):
        resp = client.post(
            "/api/v1/auth/login", json={"email": "not-an-email", "password": "pass"}
        )
        assert resp.status_code == 422


class TestMe:
    def test_me_success(self, client, admin_headers, admin_user):
        resp = client.get("/api/v1/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "admin@test.com"
        assert data["is_admin"] is True
        assert "id" in data

    def test_me_no_token(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)

    def test_me_invalid_token(self, client):
        resp = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.value"}
        )
        assert resp.status_code == 401

    def test_me_normal_user(self, client, normal_user, normal_token):
        resp = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {normal_token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is False
