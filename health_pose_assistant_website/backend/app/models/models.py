import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Date,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    devices: Mapped[list["Device"]] = relationship(back_populates="owner")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    stream_url: Mapped[str | None] = mapped_column(String(512))

    owner: Mapped["User"] = relationship(back_populates="devices")
    tokens: Mapped[list["DeviceToken"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    config_binding: Mapped["DeviceConfigBinding | None"] = relationship(
        back_populates="device", uselist=False
    )
    events: Mapped[list["PostureEvent"]] = relationship(back_populates="device")
    daily_stats: Mapped[list["DailyStat"]] = relationship(back_populates="device")
    status: Mapped["DeviceStatus"] = relationship(back_populates="device")


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    device: Mapped["Device"] = relationship(back_populates="tokens")


class ConfigProfile(Base):
    __tablename__ = "config_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bindings: Mapped[list["DeviceConfigBinding"]] = relationship(
        back_populates="profile"
    )


class DeviceConfigBinding(Base):
    __tablename__ = "device_config_bindings"

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("config_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    device: Mapped["Device"] = relationship(back_populates="config_binding")
    profile: Mapped["ConfigProfile"] = relationship(back_populates="bindings")


class PostureEvent(Base):
    __tablename__ = "posture_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    device: Mapped["Device"] = relationship(back_populates="events")


class DailyStat(Base):
    __tablename__ = "daily_stats"
    __table_args__ = (
        UniqueConstraint("device_id", "stat_date", name="uq_device_stat_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stat_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    bad_posture_count: Mapped[int] = mapped_column(Integer, default=0)
    prolonged_alert_count: Mapped[int] = mapped_column(Integer, default=0)
    sitting_minutes: Mapped[int] = mapped_column(Integer, default=0)
    away_count: Mapped[int] = mapped_column(Integer, default=0)

    device: Mapped["Device"] = relationship(back_populates="daily_stats")


class DeviceStatus(Base):
    __tablename__ = "device_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    device: Mapped["Device"] = relationship("Device")
