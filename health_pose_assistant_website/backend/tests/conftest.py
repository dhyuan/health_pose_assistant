"""Shared test fixtures — uses a separate test DB to avoid touching dev data."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password, generate_device_token, hash_device_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import User, Device, DeviceToken, ConfigProfile, DeviceConfigBinding

from fastapi.testclient import TestClient

# Use a dedicated test database (same server, different db name)
_settings = get_settings()
_base_url = _settings.DATABASE_URL.rsplit("/", 1)[0]
TEST_DB_URL = f"{_base_url}/health_video_test"

engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="session", autouse=True)
def create_test_db():
    """Ensure test DB is reachable. Create manually if needed:
    createdb health_video_test
    psql health_video_test -c "GRANT ALL ON SCHEMA public TO hva_user;"
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    yield


@pytest.fixture(autouse=True)
def setup_tables():
    """Recreate all tables before each test for full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_user(db) -> User:
    user = User(
        email="admin@test.com",
        hashed_password=hash_password("testpass"),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def normal_user(db) -> User:
    user = User(
        email="user@test.com",
        hashed_password=hash_password("testpass"),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_token(client, admin_user) -> str:
    resp = client.post(
        "/api/v1/auth/login", json={"email": "admin@test.com", "password": "testpass"}
    )
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def normal_token(client, normal_user) -> str:
    resp = client.post(
        "/api/v1/auth/login", json={"email": "user@test.com", "password": "testpass"}
    )
    return resp.json()["access_token"]


@pytest.fixture
def device_with_token(db, admin_user) -> tuple[Device, str]:
    """Create a device and return (device, plain_token)."""
    device = Device(device_code="TEST-001", name="Test Device", owner_id=admin_user.id)
    db.add(device)
    db.flush()
    plain, hashed = generate_device_token()
    dt = DeviceToken(device_id=device.id, token_hash=hashed)
    db.add(dt)
    db.commit()
    db.refresh(device)
    return device, plain


@pytest.fixture
def device_headers(device_with_token) -> dict:
    _, plain_token = device_with_token
    return {"X-Device-Token": plain_token}


@pytest.fixture
def active_config(db) -> ConfigProfile:
    profile = ConfigProfile(
        name="default",
        version=1,
        config_json={"bad_posture_threshold": 0.5, "alert_interval": 30},
        is_active=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
