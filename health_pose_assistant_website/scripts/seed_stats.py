"""Seed daily_stats with 30 days of mock data for every device."""

import argparse
import datetime
import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import get_db
from app.models import Device, DailyStat


def main():
    parser = argparse.ArgumentParser(description="Seed daily_stats with mock data")
    parser.add_argument("--days", type=int, default=30, help="Number of days to seed")
    args = parser.parse_args()

    db = next(get_db())
    devices = db.query(Device).all()
    if not devices:
        print("No devices found. Register at least one device first.")
        return

    today = datetime.date.today()
    created = 0
    skipped = 0

    for device in devices:
        for i in range(args.days):
            stat_date = today - datetime.timedelta(days=i)
            existing = (
                db.query(DailyStat)
                .filter(
                    DailyStat.device_id == device.id,
                    DailyStat.stat_date == stat_date,
                )
                .first()
            )
            if existing:
                skipped += 1
                continue

            stat = DailyStat(
                device_id=device.id,
                stat_date=stat_date,
                bad_posture_count=random.randint(0, 20),
                prolonged_alert_count=random.randint(0, 8),
                sitting_minutes=random.randint(60, 480),
                away_count=random.randint(0, 10),
            )
            db.add(stat)
            created += 1

    db.commit()
    print(
        f"Seeded {created} daily_stats records for {len(devices)} device(s) "
        f"({skipped} existing skipped)."
    )


if __name__ == "__main__":
    main()
