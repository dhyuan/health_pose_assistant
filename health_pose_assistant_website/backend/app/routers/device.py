import datetime as _dt

from fastapi import APIRouter, Depends
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_device_by_token
from app.models import Device, PostureEvent, DeviceConfigBinding, ConfigProfile
from app.schemas.schemas import (
    DeviceConfigResponse,
    EventCreate,
    HeartbeatRequest,
    HeartbeatResponse,
)

router = APIRouter(prefix="/api/v1/device", tags=["device"])


def _today_sitting_minutes(db: Session, device_id: int) -> int:
    """MAX sitting_minutes from today's sitting_summary events for this device."""
    today_start = _dt.datetime.combine(
        _dt.datetime.now(_dt.timezone.utc).date(),
        _dt.time.min,
        tzinfo=_dt.timezone.utc,
    )
    val = (
        db.query(
            func.coalesce(
                func.max(cast(PostureEvent.payload["sitting_minutes"].astext, Integer)),
                0,
            )
        )
        .filter(
            PostureEvent.device_id == device_id,
            PostureEvent.event_type == "sitting_summary",
            PostureEvent.created_at >= today_start,
        )
        .scalar()
    )
    return int(val) if val else 0


@router.get("/config", response_model=DeviceConfigResponse)
def get_config(
    device: Device = Depends(get_device_by_token),
    db: Session = Depends(get_db),
):
    sitting = _today_sitting_minutes(db, device.id)

    binding = (
        db.query(DeviceConfigBinding)
        .filter(DeviceConfigBinding.device_id == device.id)
        .first()
    )
    if binding is not None and binding.profile is not None:
        profile = binding.profile
        return DeviceConfigResponse(
            version=profile.version,
            config_json=profile.config_json,
            today_sitting_minutes=sitting,
        )
    # Fallback: no binding yet, try active profile
    active = db.query(ConfigProfile).filter(ConfigProfile.is_active.is_(True)).first()
    if active is not None:
        return DeviceConfigResponse(
            version=active.version,
            config_json=active.config_json,
            today_sitting_minutes=sitting,
        )
    return DeviceConfigResponse(
        version=0, config_json={}, today_sitting_minutes=sitting
    )


@router.post("/events", status_code=201)
def report_event(
    body: EventCreate,
    device: Device = Depends(get_device_by_token),
    db: Session = Depends(get_db),
):
    event = PostureEvent(
        device_id=device.id,
        event_type=body.event_type,
        payload=body.payload,
    )
    db.add(event)
    db.commit()
    return {"status": "ok", "event_id": event.id}


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    body: HeartbeatRequest = HeartbeatRequest(),
    device: Device = Depends(get_device_by_token),
    db: Session = Depends(get_db),
):
    device.last_seen_at = _dt.datetime.now(_dt.timezone.utc)
    if body.stream_url is not None:
        device.stream_url = body.stream_url
    db.commit()
    return HeartbeatResponse()
