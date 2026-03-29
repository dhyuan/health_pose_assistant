import datetime
from pydantic import BaseModel, EmailStr


# ---- Auth ----


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    is_admin: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---- Device (admin side) ----


class DeviceCreate(BaseModel):
    device_code: str
    name: str


class DeviceUpdate(BaseModel):
    name: str


class DeviceOut(BaseModel):
    id: int
    device_code: str
    name: str
    owner_id: int
    last_seen_at: datetime.datetime | None
    stream_url: str | None = None

    model_config = {"from_attributes": True}


class DeviceWithToken(BaseModel):
    device: DeviceOut
    plain_token: str


# ---- Config ----


class ConfigOut(BaseModel):
    id: int
    name: str
    version: int
    config_json: dict
    is_active: bool
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class ConfigUpdate(BaseModel):
    config_json: dict


# ---- Device-side schemas ----


class DeviceConfigResponse(BaseModel):
    version: int
    config_json: dict
    today_sitting_minutes: int = 0


class EventCreate(BaseModel):
    event_type: str
    payload: dict = {}


class HeartbeatRequest(BaseModel):
    stream_url: str | None = None


class HeartbeatResponse(BaseModel):
    status: str = "ok"


# ---- Stats ----


class DailyStatOut(BaseModel):
    id: int
    device_id: int
    stat_date: datetime.date
    bad_posture_count: int
    prolonged_alert_count: int
    sitting_minutes: int
    away_count: int

    model_config = {"from_attributes": True}


# ---- Dashboard ----


class TodaySummary(BaseModel):
    bad_posture_count: int
    prolonged_alert_count: int
    sitting_minutes: int
    away_count: int


class DashboardOut(BaseModel):
    total_devices: int
    online_devices: int
    today: TodaySummary
