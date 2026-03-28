"""Tests for scheduled aggregation and today_sitting_minutes in config."""

import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import DailyStat, Device, PostureEvent
from app.tasks import aggregate_daily_stats_for_date


class TestAggregation:
    """Test aggregate_daily_stats_for_date."""

    def _today_utc(self):
        return datetime.datetime.now(datetime.timezone.utc).date()

    def _make_event(
        self,
        db: Session,
        device_id: int,
        event_type: str,
        payload: dict | None = None,
        created_at=None,
    ):
        ev = PostureEvent(
            device_id=device_id,
            event_type=event_type,
            payload=payload or {},
        )
        db.add(ev)
        db.flush()
        if created_at is not None:
            db.execute(
                PostureEvent.__table__.update()
                .where(PostureEvent.__table__.c.id == ev.id)
                .values(created_at=created_at)
            )
        db.commit()
        return ev

    def test_aggregate_basic(self, db, device_with_token):
        """Events of different types are counted correctly."""
        device, _ = device_with_token
        today = self._today_utc()

        self._make_event(db, device.id, "bad_posture")
        self._make_event(db, device.id, "bad_posture")
        self._make_event(db, device.id, "prolonged_sitting")
        self._make_event(db, device.id, "leave")
        self._make_event(db, device.id, "leave")
        self._make_event(db, device.id, "leave")
        self._make_event(db, device.id, "sitting_summary", {"sitting_minutes": 30})
        self._make_event(db, device.id, "sitting_summary", {"sitting_minutes": 45})

        aggregate_daily_stats_for_date(db, today)

        stat = (
            db.query(DailyStat)
            .filter(
                DailyStat.device_id == device.id,
                DailyStat.stat_date == today,
            )
            .first()
        )
        assert stat is not None
        assert stat.bad_posture_count == 2
        assert stat.prolonged_alert_count == 1
        assert stat.away_count == 3
        assert stat.sitting_minutes == 45  # MAX

    def test_aggregate_upsert(self, db, device_with_token):
        """Running aggregation twice updates (not duplicates) the row."""
        device, _ = device_with_token
        today = self._today_utc()

        self._make_event(db, device.id, "bad_posture")
        aggregate_daily_stats_for_date(db, today)

        stat = (
            db.query(DailyStat)
            .filter(
                DailyStat.device_id == device.id,
                DailyStat.stat_date == today,
            )
            .first()
        )
        assert stat.bad_posture_count == 1

        # Add another event, re-aggregate
        self._make_event(db, device.id, "bad_posture")
        aggregate_daily_stats_for_date(db, today)

        db.refresh(stat)
        assert stat.bad_posture_count == 2
        # Still one row
        count = (
            db.query(DailyStat)
            .filter(
                DailyStat.device_id == device.id,
                DailyStat.stat_date == today,
            )
            .count()
        )
        assert count == 1

    def test_aggregate_no_events(self, db, device_with_token):
        """No events → no daily_stats row created."""
        device, _ = device_with_token
        today = self._today_utc()
        aggregate_daily_stats_for_date(db, today)

        count = (
            db.query(DailyStat)
            .filter(
                DailyStat.device_id == device.id,
                DailyStat.stat_date == today,
            )
            .count()
        )
        assert count == 0

    def test_aggregate_ignores_other_dates(self, db, device_with_token):
        """Events from another day are not counted."""
        device, _ = device_with_token
        today = self._today_utc()
        yesterday = today - datetime.timedelta(days=1)

        yesterday_dt = datetime.datetime.combine(
            yesterday, datetime.time(12, 0), tzinfo=datetime.timezone.utc
        )
        self._make_event(db, device.id, "bad_posture", created_at=yesterday_dt)
        self._make_event(db, device.id, "bad_posture")  # today

        aggregate_daily_stats_for_date(db, today)

        stat = (
            db.query(DailyStat)
            .filter(
                DailyStat.device_id == device.id,
                DailyStat.stat_date == today,
            )
            .first()
        )
        assert stat is not None
        assert stat.bad_posture_count == 1

    def test_aggregate_welcome_back_ignored(self, db, device_with_token):
        """welcome_back events are not counted in any aggregation column."""
        device, _ = device_with_token
        today = self._today_utc()

        self._make_event(db, device.id, "welcome_back")

        aggregate_daily_stats_for_date(db, today)

        # welcome_back doesn't cause a daily_stats row with non-zero counts
        # but the query groups by device_id, so a row IS created with zeros
        stat = (
            db.query(DailyStat)
            .filter(
                DailyStat.device_id == device.id,
                DailyStat.stat_date == today,
            )
            .first()
        )
        if stat is not None:
            assert stat.bad_posture_count == 0
            assert stat.prolonged_alert_count == 0
            assert stat.away_count == 0
            assert stat.sitting_minutes == 0


class TestTodaySittingMinutes:
    """GET /device/config should include today_sitting_minutes."""

    def test_config_includes_today_sitting_zero(self, client, device_headers):
        """No sitting_summary events → today_sitting_minutes=0."""
        resp = client.get("/api/v1/device/config", headers=device_headers)
        assert resp.status_code == 200
        assert resp.json()["today_sitting_minutes"] == 0

    def test_config_includes_today_sitting(
        self, client, device_headers, device_with_token, db
    ):
        """Sitting summary events → MAX value returned."""
        device, _ = device_with_token

        # Report two sitting_summary events
        for mins in (20, 35):
            ev = PostureEvent(
                device_id=device.id,
                event_type="sitting_summary",
                payload={"sitting_minutes": mins},
            )
            db.add(ev)
        db.commit()

        resp = client.get("/api/v1/device/config", headers=device_headers)
        assert resp.status_code == 200
        assert resp.json()["today_sitting_minutes"] == 35

    def test_config_today_sitting_with_profile(
        self, client, device_headers, device_with_token, active_config, db
    ):
        """today_sitting_minutes returned alongside config."""
        device, _ = device_with_token

        ev = PostureEvent(
            device_id=device.id,
            event_type="sitting_summary",
            payload={"sitting_minutes": 12},
        )
        db.add(ev)
        db.commit()

        resp = client.get("/api/v1/device/config", headers=device_headers)
        data = resp.json()
        assert data["version"] == 1
        assert data["today_sitting_minutes"] == 12
