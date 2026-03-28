"""Scheduled tasks — aggregate posture_events into daily_stats."""

import datetime
import logging

from sqlalchemy import Integer, case, cast, func
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models import DailyStat, PostureEvent

logger = logging.getLogger(__name__)


def aggregate_daily_stats_for_date(db: Session, target_date: datetime.date):
    """Aggregate posture_events → daily_stats for *target_date*."""
    start_dt = datetime.datetime.combine(
        target_date, datetime.time.min, tzinfo=datetime.timezone.utc
    )
    end_dt = datetime.datetime.combine(
        target_date + datetime.timedelta(days=1),
        datetime.time.min,
        tzinfo=datetime.timezone.utc,
    )

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


def run_aggregation():
    """Aggregate today + yesterday (called periodically by APScheduler)."""
    db = SessionLocal()
    try:
        today = datetime.datetime.now(datetime.timezone.utc).date()
        yesterday = today - datetime.timedelta(days=1)
        aggregate_daily_stats_for_date(db, yesterday)
        aggregate_daily_stats_for_date(db, today)
        logger.info("Aggregation completed for %s and %s", yesterday, today)
    except Exception:
        logger.exception("Aggregation failed")
        db.rollback()
    finally:
        db.close()
