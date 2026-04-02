"""Scheduled tasks — aggregate posture_events into daily_stats."""

import datetime
import logging

from sqlalchemy import Integer, case, cast, func
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models import DailyStat, Device, DeviceStatus, PostureEvent

logger = logging.getLogger(__name__)

HEARTBEAT_OFFLINE_TIMEOUT = datetime.timedelta(minutes=5)


import zoneinfo


def aggregate_daily_stats_for_date(
    db: Session, target_date: datetime.date, tz: str = "UTC"
):
    """Aggregate posture_events → daily_stats for *target_date* in given timezone."""
    try:
        tzinfo = zoneinfo.ZoneInfo(tz)
    except Exception:
        tzinfo = datetime.timezone.utc
    local_start = datetime.datetime.combine(
        target_date, datetime.time.min, tzinfo=tzinfo
    )
    local_end = local_start + datetime.timedelta(days=1)
    start_dt = local_start.astimezone(datetime.timezone.utc)
    end_dt = local_end.astimezone(datetime.timezone.utc)

    rows = (
        db.query(
            PostureEvent.device_id,
            func.coalesce(
                func.sum(case((PostureEvent.event_type == "bad_posture", 1), else_=0)),
                0,
            ).label("bad_posture_count"),
            func.coalesce(
                func.sum(
                    case((PostureEvent.event_type == "prolonged_sitting", 1), else_=0)
                ),
                0,
            ).label("prolonged_alert_count"),
            func.coalesce(
                func.sum(case((PostureEvent.event_type == "leave", 1), else_=0)),
                0,
            ).label("away_count"),
            func.coalesce(
                func.max(
                    case(
                        (
                            PostureEvent.event_type == "sitting_summary",
                            cast(
                                PostureEvent.payload["sitting_minutes"].astext,
                                Integer,
                            ),
                        ),
                        else_=None,
                    )
                ),
                0,
            ).label("sitting_minutes"),
        )
        .filter(
            PostureEvent.created_at >= start_dt,
            PostureEvent.created_at < end_dt,
        )
        .group_by(PostureEvent.device_id)
        .all()
    )

    for row in rows:
        stat = (
            db.query(DailyStat)
            .filter(
                DailyStat.device_id == row.device_id,
                DailyStat.stat_date == target_date,
            )
            .first()
        )
        if stat is None:
            stat = DailyStat(device_id=row.device_id, stat_date=target_date)
            db.add(stat)
        stat.bad_posture_count = row.bad_posture_count
        stat.prolonged_alert_count = row.prolonged_alert_count
        stat.sitting_minutes = row.sitting_minutes
        stat.away_count = row.away_count

    db.commit()


def run_aggregation(tz: str = "Pacific/Auckland"):
    """Aggregate today + yesterday (called periodically by APScheduler)."""
    db = SessionLocal()
    try:
        now = datetime.datetime.now(zoneinfo.ZoneInfo(tz))
        today = now.date()
        yesterday = today - datetime.timedelta(days=1)
        aggregate_daily_stats_for_date(db, yesterday, tz)
        aggregate_daily_stats_for_date(db, today, tz)
        logger.info(f"Aggregation completed for {yesterday} and {today} in tz {tz}")
    except Exception:
        logger.exception("Aggregation failed")
        db.rollback()
    finally:
        db.close()


def mark_stale_devices_offline():
    """Mark devices as offline if heartbeat is stale for more than timeout."""
    db = SessionLocal()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now_utc - HEARTBEAT_OFFLINE_TIMEOUT
    inserted = 0
    try:
        stale_devices = (
            db.query(Device)
            .filter(Device.last_seen_at.is_not(None), Device.last_seen_at < cutoff)
            .all()
        )
        for device in stale_devices:
            latest_status = (
                db.query(DeviceStatus)
                .filter(DeviceStatus.device_id == device.id)
                .order_by(DeviceStatus.changed_at.desc())
                .first()
            )
            if latest_status is None or latest_status.status != "offline":
                db.add(
                    DeviceStatus(
                        device_id=device.id,
                        status="offline",
                        changed_at=now_utc,
                        extra={"reason": "heartbeat_timeout"},
                    )
                )
                inserted += 1
        if inserted:
            logger.info("Marked %s devices offline due to heartbeat timeout", inserted)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to mark stale devices offline")
    finally:
        db.close()
