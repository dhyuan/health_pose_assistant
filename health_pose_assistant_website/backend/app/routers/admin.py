import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
import zoneinfo
from fastapi.responses import StreamingResponse
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.core.security import generate_device_token
from app.db.session import get_db
from app.deps import require_admin
from app.models import (
    User,
    Device,
    DeviceToken,
    ConfigProfile,
    DeviceConfigBinding,
    DailyStat,
    PostureEvent,
)
from app.schemas.schemas import (
    ConfigOut,
    ConfigUpdate,
    DailyStatOut,
    DashboardOut,
    DeviceCreate,
    DeviceOut,
    DeviceUpdate,
    DeviceWithToken,
    SittingSessionOut,
    SittingSessionsResponse,
    TodaySummary,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ---- Devices ----


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(Device).all()


@router.post("/devices", response_model=DeviceWithToken, status_code=201)
def register_device(
    body: DeviceCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(Device).filter(Device.device_code == body.device_code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Device code already exists"
        )

    device = Device(device_code=body.device_code, name=body.name, owner_id=admin.id)
    db.add(device)
    db.flush()

    plain_token, token_hash = generate_device_token()
    dt = DeviceToken(device_id=device.id, token_hash=token_hash)
    db.add(dt)

    # Create default config binding if an active profile exists
    active_profile = (
        db.query(ConfigProfile).filter(ConfigProfile.is_active.is_(True)).first()
    )
    if active_profile:
        binding = DeviceConfigBinding(device_id=device.id, profile_id=active_profile.id)
        db.add(binding)

    db.commit()
    db.refresh(device)
    return DeviceWithToken(
        device=DeviceOut.model_validate(device), plain_token=plain_token
    )


@router.put("/devices/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    body: DeviceUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.name = body.name
    db.commit()
    db.refresh(device)
    return device


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(
    device_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()


@router.post("/devices/{device_id}/regenerate-token", response_model=DeviceWithToken)
def regenerate_device_token(
    device_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    # Delete all existing tokens for this device
    db.query(DeviceToken).filter(DeviceToken.device_id == device.id).delete()

    # Generate new token
    plain_token, token_hash = generate_device_token()
    dt = DeviceToken(device_id=device.id, token_hash=token_hash)
    db.add(dt)
    db.commit()
    db.refresh(device)
    return DeviceWithToken(
        device=DeviceOut.model_validate(device), plain_token=plain_token
    )


# ---- Config ----


@router.get("/config", response_model=ConfigOut)
def get_config(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    profile = db.query(ConfigProfile).filter(ConfigProfile.is_active.is_(True)).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="No active config profile")
    return profile


@router.put("/config", response_model=ConfigOut)
def update_config(
    body: ConfigUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    profile = db.query(ConfigProfile).filter(ConfigProfile.is_active.is_(True)).first()
    if profile is None:
        # Create first profile
        profile = ConfigProfile(
            name="default", version=1, config_json=body.config_json, is_active=True
        )
        db.add(profile)
    else:
        profile.config_json = body.config_json
        profile.version += 1
    db.commit()
    db.refresh(profile)
    return profile


# ---- Stats ----


@router.get("/stats", response_model=list[DailyStatOut])
def get_stats(
    device_id: int | None = Query(None),
    from_date: datetime.date | None = Query(None, alias="from"),
    to_date: datetime.date | None = Query(None, alias="to"),
    tz: str = Query("UTC"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # 仅做透传，实际聚合时区逻辑在聚合任务中实现
    q = db.query(DailyStat)
    if device_id is not None:
        q = q.filter(DailyStat.device_id == device_id)
    if from_date is not None:
        q = q.filter(DailyStat.stat_date >= from_date)
    if to_date is not None:
        q = q.filter(DailyStat.stat_date <= to_date)
    return q.order_by(DailyStat.stat_date.desc()).all()


# ---- Sitting Sessions ----


@router.get("/sitting-sessions", response_model=SittingSessionsResponse)
def get_sitting_sessions(
    date: datetime.date = Query(...),
    device_id: int | None = Query(None),
    tz: str = Query("UTC"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # 计算本地时区对应的UTC区间
    try:
        tzinfo = zoneinfo.ZoneInfo(tz)
    except Exception:
        tzinfo = datetime.timezone.utc
    local_start = datetime.datetime.combine(date, datetime.time.min, tzinfo=tzinfo)
    local_end = local_start + datetime.timedelta(days=1)
    start_dt = local_start.astimezone(datetime.timezone.utc)
    end_dt = local_end.astimezone(datetime.timezone.utc)

    q = db.query(PostureEvent).filter(
        PostureEvent.event_type == "sitting_session",
        PostureEvent.created_at >= start_dt,
        PostureEvent.created_at < end_dt,
    )
    if device_id is not None:
        q = q.filter(PostureEvent.device_id == device_id)

    events = q.order_by(PostureEvent.created_at.asc()).all()

    # Get sitting_alert_minutes from active config
    profile = db.query(ConfigProfile).filter(ConfigProfile.is_active.is_(True)).first()
    alert_mins = 20
    if profile and profile.config_json:
        alert_mins = profile.config_json.get("sitting_alert_minutes", 20)

    sessions = [
        SittingSessionOut(
            id=e.id,
            device_id=e.device_id,
            start_time=e.payload.get("start_time", ""),
            end_time=e.payload.get("end_time", ""),
            duration_seconds=e.payload.get("duration_seconds", 0),
        )
        for e in events
    ]

    # 查询 device_status 区间
    device_status_spans = []
    if device_id is not None:
        from app.models import DeviceStatus

        latest_before_start = (
            db.query(DeviceStatus)
            .filter(
                DeviceStatus.device_id == device_id,
                DeviceStatus.changed_at < start_dt,
            )
            .order_by(DeviceStatus.changed_at.desc())
            .first()
        )
        status_q = (
            db.query(DeviceStatus)
            .filter(
                DeviceStatus.device_id == device_id,
                DeviceStatus.changed_at >= start_dt,
                DeviceStatus.changed_at < end_dt,
            )
            .order_by(DeviceStatus.changed_at.asc())
        )
        status_rows = status_q.all()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        visible_end = min(end_dt, now_utc)

        current_status = latest_before_start.status if latest_before_start else None
        current_start = start_dt if latest_before_start else None

        for row in status_rows:
            if current_status is not None and current_start is not None:
                span_end = min(row.changed_at, end_dt)
                if current_start < span_end:
                    device_status_spans.append(
                        {
                            "start": current_start.isoformat(),
                            "end": span_end.isoformat(),
                            "status": current_status,
                        }
                    )

            current_status = row.status
            current_start = max(row.changed_at, start_dt)

        if (
            current_status is not None
            and current_start is not None
            and current_start < visible_end
        ):
            device_status_spans.append(
                {
                    "start": current_start.isoformat(),
                    "end": visible_end.isoformat(),
                    "status": current_status,
                }
            )

    return SittingSessionsResponse(
        sitting_alert_minutes=alert_mins,
        sessions=sessions,
        device_status_spans=device_status_spans,
    )


# ---- Dashboard ----


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_devices = db.query(sa_func.count(Device.id)).scalar() or 0
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(minutes=5)
    online_devices = (
        db.query(sa_func.count(Device.id))
        .filter(Device.last_seen_at >= cutoff)
        .scalar()
        or 0
    )

    today = datetime.date.today()
    row = (
        db.query(
            sa_func.coalesce(sa_func.sum(DailyStat.bad_posture_count), 0),
            sa_func.coalesce(sa_func.sum(DailyStat.prolonged_alert_count), 0),
            sa_func.coalesce(sa_func.sum(DailyStat.sitting_minutes), 0),
            sa_func.coalesce(sa_func.sum(DailyStat.away_count), 0),
        )
        .filter(DailyStat.stat_date == today)
        .one()
    )

    return DashboardOut(
        total_devices=total_devices,
        online_devices=online_devices,
        today=TodaySummary(
            bad_posture_count=row[0],
            prolonged_alert_count=row[1],
            sitting_minutes=row[2],
            away_count=row[3],
        ),
    )


# ---- Video Stream Proxy ----


@router.get("/devices/{device_id}/stream")
async def stream_device_video(
    device_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.stream_url:
        raise HTTPException(status_code=404, detail="Device has no stream URL")

    # Validate that stream_url points to expected MJPEG path
    url = device.stream_url
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid stream URL scheme")

    async def _proxy_stream():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, timeout=None) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    yield chunk

    return StreamingResponse(
        _proxy_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
