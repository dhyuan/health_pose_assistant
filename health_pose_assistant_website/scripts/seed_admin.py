"""Seed an admin user into the database."""

import argparse
import sys
import os

# Allow running from project root or scripts/ dir
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.security import hash_password
from app.db.session import get_db
from app.models import User


def main():
    parser = argparse.ArgumentParser(description="Seed admin user")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="admin123")
    args = parser.parse_args()

    db = next(get_db())
    existing = db.query(User).filter(User.email == args.email).first()
    if existing:
        print(f"Admin user '{args.email}' already exists, skipping.")
        return

    user = User(
        email=args.email,
        hashed_password=hash_password(args.password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    print(f"Admin user '{args.email}' created.")


if __name__ == "__main__":
    main()
