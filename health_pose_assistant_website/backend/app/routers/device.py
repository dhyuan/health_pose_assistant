from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_device_by_token
from app.models import Device, PostureEvent, DeviceConfigBinding, ConfigProfile
from app.schemas.schemas import DeviceConfigResponse, EventCreate, HeartbeatResponse

router = APIRouter(prefix="/api/v1/device", tags=["device"])


@router.get("/config", response_model=DeviceConfigResponse)
def get_config(
    device: Device = Depends(get_device_by_token),
    db: Session = Depends(get_db),
):
    binding = (
        db.query(DeviceConfigBinding)
        .filter(DeviceConfigBinding.device_id == device.id)
        .first()
    )
    if binding is not None and binding.profile is not None:
        profile = binding.profile
        return DeviceConfigResponse(
            version=profile.version, config_json=profile.config_json
        )
    # Fallback: no binding yet, try active profile
    active = db.query(ConfigProfile).filter(ConfigProfile.is_active.is_(True)).first()
    if active is not None:
        return DeviceConfigResponse(
            version=active.version, config_json=active.config_json
        )
    return DeviceConfigResponse(version=0, config_json={})


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
    device: Device = Depends(get_device_by_token),
    db: Session = Depends(get_db),
):
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return HeartbeatResponse()
