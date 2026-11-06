import calendar
import hashlib
import json
import os
import random
import secrets
import sys
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Column, Date, DateTime, Float, Integer, String, Text, UniqueConstraint, or_, text

from database import Base, SessionLocal, engine
from ui_contract import (
    AppSettingsReceipt, DailyStatusRecord, HandSettings,
    device_notification_preferences, get_notification_preferences,
    install_ui_routes, serialize_daily_status,
)

app = FastAPI(title="굽신굽신 백엔드")

frontend_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True)
    device_id = Column(String)
    angle = Column(Float)
    battery = Column(Integer)
    status = Column(String)
    measured_at = Column(DateTime)


class RomSettings(Base):
    __tablename__ = "rom_settings"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, unique=True)
    warning_angle = Column(Float)
    limit_angle = Column(Float)
    vibration_strength = Column(Integer)
    target_wear_minutes = Column(Integer)


class WearSession(Base):
    __tablename__ = "wear_sessions"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    started_at = Column(DateTime)
    last_sensor_at = Column(DateTime)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0)
    status = Column(String, default="ACTIVE")


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    sensor_data_id = Column(Integer, nullable=True)
    alert_type = Column(String)
    angle = Column(Float)
    vibration_strength = Column(Integer)
    occurred_at = Column(DateTime)
    is_read = Column(Integer, default=0)
    read_at = Column(DateTime, nullable=True)


class ContactEvent(Base):
    __tablename__ = "contact_events"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    occurred_at = Column(DateTime, index=True)
    hourly_contact_count = Column(Integer)
    is_overflexion = Column(Integer, default=0)


class OverflexionEvent(Base):
    __tablename__ = "overflexion_events"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    occurred_at = Column(DateTime, index=True)
    contact_count_in_last_hour = Column(Integer)


class SymptomRecord(Base):
    __tablename__ = "symptom_records"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    recorded_on = Column(Date, index=True)
    symptom_type = Column(String)
    body_area = Column(String)
    severity = Column(Integer)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class DeviceCommand(Base):
    __tablename__ = "device_commands"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    command_type = Column(String)
    payload = Column(Text)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime)
    delivered_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    password_salt = Column(String)
    created_at = Column(DateTime)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    token = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime)


class UserDevice(Base):
    __tablename__ = "user_devices"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    device_id = Column(String, unique=True, index=True)
    device_name = Column(String)
    paired_at = Column(DateTime)


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, unique=True, index=True)
    api_key_hash = Column(String)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class DeviceConnection(Base):
    __tablename__ = "device_connections"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, unique=True, index=True)
    last_seen_at = Column(DateTime)
    last_battery = Column(Integer, nullable=True)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    device_id = Column(String, index=True)
    report_type = Column(String)
    period_start = Column(Date)
    period_end = Column(Date)
    content = Column(Text)
    issued_at = Column(DateTime)


class DeviceSettingsSync(Base):
    __tablename__ = "device_settings_sync"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, unique=True, index=True)
    last_applied_command_id = Column(Integer)
    last_applied_at = Column(DateTime)


class DeviceVibrationSetting(Base):
    __tablename__ = "device_vibration_settings"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, unique=True, index=True)
    duration_ms = Column(Integer)
    updated_at = Column(DateTime)


class AngleViolation(Base):
    __tablename__ = "angle_violations"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    sensor_data_id = Column(Integer, nullable=True)
    violation_type = Column(String)
    threshold_angle = Column(Float)
    angle = Column(Float)
    excess_angle = Column(Float)
    occurred_at = Column(DateTime, index=True)


class PushToken(Base):
    __tablename__ = "push_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    platform = Column(String)
    token = Column(String, unique=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class DemoHistoryDay(Base):
    __tablename__ = "demo_history_days"
    __table_args__ = (UniqueConstraint("device_id", "recorded_on"),)

    id = Column(Integer, primary_key=True)
    device_id = Column(String, nullable=False, index=True)
    recorded_on = Column(Date, nullable=False)


Base.metadata.create_all(bind=engine)

SESSION_GAP = timedelta(minutes=5)
ALERT_COOLDOWN = timedelta(seconds=30)
OVERFLEXION_CONTACT_THRESHOLD = 10
WEAR_RECOMMENDATION_DELAY = timedelta(hours=1)
MAX_WEAR_RECOMMENDATIONS_PER_DAY = 5
TOKEN_LIFETIME = timedelta(days=7)

SYMPTOM_TYPES = {
    "PAIN": "통증",
    "STIFFNESS": "뻣뻣함",
    "NUMBNESS": "저림",
    "TINGLING": "따끔거림",
    "FATIGUE": "피로",
    "OTHER": "기타",
}
BODY_AREAS = {
    "NECK": "목",
    "SHOULDER": "어깨",
    "UPPER_BACK": "등",
    "LOWER_BACK": "허리",
    "ARM": "팔",
    "OTHER": "기타",
}
SEVERITY_LABELS = {
    1: "매우 약함",
    2: "약함",
    3: "보통",
    4: "심함",
    5: "매우 심함",
}


class SensorReading(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    angle: float = Field(ge=0, le=180)
    battery: int = Field(ge=0, le=100)


class RomSettingsInput(BaseModel):
    warning_angle: float = Field(ge=0, le=180)
    limit_angle: float = Field(ge=0, le=180)
    vibration_strength: int = Field(ge=0, le=100)
    vibration_duration_ms: int = Field(default=1000, ge=100, le=10000)
    target_wear_minutes: int = Field(gt=0, le=1440)
    delivery_mode: Literal["APP_DIRECT", "SERVER_POLL"] = "APP_DIRECT"

    @model_validator(mode="after")
    def validate_angles(self):
        if self.warning_angle >= self.limit_angle:
            raise ValueError("경고 각도는 제한 각도보다 작아야 합니다.")
        return self


class WearSessionStopInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)


class ContactEventInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)


class SymptomRecordInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    recorded_on: date = Field(default_factory=lambda: datetime.now().date())
    symptom_type: Literal["PAIN", "STIFFNESS", "NUMBNESS", "TINGLING", "FATIGUE", "OTHER"]
    body_area: Literal["NECK", "SHOULDER", "UPPER_BACK", "LOWER_BACK", "ARM", "OTHER"]
    severity: int = Field(ge=1, le=5)
    note: str | None = Field(default=None, max_length=1000)


class SymptomRecordUpdate(BaseModel):
    recorded_on: date | None = None
    symptom_type: Literal["PAIN", "STIFFNESS", "NUMBNESS", "TINGLING", "FATIGUE", "OTHER"] | None = None
    body_area: Literal["NECK", "SHOULDER", "UPPER_BACK", "LOWER_BACK", "ARM", "OTHER"] | None = None
    severity: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=1000)


class UserRegisterInput(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class DeviceConnectInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    device_name: str = Field(min_length=1, max_length=50)


class ProfileUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    current_password: str | None = Field(default=None, min_length=8, max_length=128)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class PushTokenInput(BaseModel):
    platform: Literal["IOS", "ANDROID", "WEB"]
    token: str = Field(min_length=1, max_length=500)


class DemoSeedInput(BaseModel):
    days: int = Field(default=30, ge=7, le=93)
    issue_reports: bool = True


def get_or_create_settings(db, device_id):
    settings = (
        db.query(RomSettings)
        .filter(RomSettings.device_id == device_id)
        .first()
    )

    if settings is None:
        settings = RomSettings(
            device_id=device_id,
            warning_angle=55,
            limit_angle=65,
            vibration_strength=70,
            target_wear_minutes=120,
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return settings


def get_or_create_vibration_setting(db, device_id):
    setting = (
        db.query(DeviceVibrationSetting)
        .filter(DeviceVibrationSetting.device_id == device_id)
        .first()
    )
    if setting is None:
        setting = DeviceVibrationSetting(
            device_id=device_id,
            duration_ms=1000,
            updated_at=datetime.now(),
        )
        db.add(setting)
        db.flush()
    return setting


def normalize_email(email):
    return email.strip().lower()


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        600_000,
    ).hex()


def hash_device_key(device_key):
    return hashlib.sha256(device_key.encode("utf-8")).hexdigest()


def create_device_key(db, device_id):
    device_key = secrets.token_urlsafe(32)
    now = datetime.now()
    credential = DeviceCredential(
        device_id=device_id,
        api_key_hash=hash_device_key(device_key),
        created_at=now,
        updated_at=now,
    )
    db.add(credential)
    return device_key


def create_auth_token(db, user_id):
    now = datetime.now()
    token = AuthToken(
        user_id=user_id,
        token=secrets.token_urlsafe(32),
        created_at=now,
        expires_at=now + TOKEN_LIFETIME,
    )
    db.add(token)
    db.flush()
    return token


def get_authenticated_user(db, authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    token_value = authorization.removeprefix("Bearer ").strip()
    token = (
        db.query(AuthToken)
        .filter(
            AuthToken.token == token_value,
            AuthToken.expires_at > datetime.now(),
        )
        .first()
    )
    if token is None:
        raise HTTPException(status_code=401, detail="로그인이 만료되었거나 유효하지 않습니다.")

    user = db.query(User).filter(User.id == token.user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    return user


def authenticate_device(db, device_id, device_key):
    if not device_key:
        raise HTTPException(status_code=401, detail="기기 인증키가 필요합니다.")
    credential = (
        db.query(DeviceCredential)
        .filter(DeviceCredential.device_id == device_id)
        .first()
    )
    if credential is None or not secrets.compare_digest(
        credential.api_key_hash,
        hash_device_key(device_key),
    ):
        raise HTTPException(status_code=401, detail="기기 인증키가 올바르지 않습니다.")


def touch_device_connection(db, device_id, battery=None):
    connection = (
        db.query(DeviceConnection)
        .filter(DeviceConnection.device_id == device_id)
        .first()
    )
    if connection is None:
        connection = DeviceConnection(
            device_id=device_id,
            last_seen_at=datetime.now(),
            last_battery=battery,
        )
        db.add(connection)
    else:
        connection.last_seen_at = datetime.now()
        if battery is not None:
            connection.last_battery = battery
    return connection


def get_rom_sync_info(db, device_id):
    latest_command = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.device_id == device_id,
            DeviceCommand.command_type == "ROM_SETTINGS",
        )
        .order_by(DeviceCommand.id.desc())
        .first()
    )
    sync = (
        db.query(DeviceSettingsSync)
        .filter(DeviceSettingsSync.device_id == device_id)
        .first()
    )
    if latest_command is None:
        return {"status": "NOT_SENT", "last_applied_at": None, "device_verified": False}
    if (
        sync is not None
        and sync.last_applied_command_id == latest_command.id
        and latest_command.status == "ACKNOWLEDGED"
    ):
        return {
            "status": "SYNCED",
            "last_applied_at": sync.last_applied_at.isoformat(),
            "device_verified": True,
        }
    receipt = db.get(AppSettingsReceipt, latest_command.id)
    return {
        "status": latest_command.status,
        "last_applied_at": sync.last_applied_at.isoformat() if sync else None,
        "device_verified": False,
        "app_reported_at": receipt.reported_at.isoformat() if receipt else None,
        "app_error_message": receipt.error_message if receipt else None,
    }


def require_owned_device(db, authorization, device_id):
    user = get_authenticated_user(db, authorization)
    device = (
        db.query(UserDevice)
        .filter(UserDevice.user_id == user.id, UserDevice.device_id == device_id)
        .first()
    )
    if device is None:
        raise HTTPException(status_code=403, detail="접근 권한이 없는 기기입니다.")
    return user, device


def update_wear_session(db, device_id, measured_at):
    active_session = (
        db.query(WearSession)
        .filter(
            WearSession.device_id == device_id,
            WearSession.status == "ACTIVE",
        )
        .order_by(WearSession.started_at.desc())
        .first()
    )

    started = False
    if (
        active_session is not None
        and measured_at - active_session.last_sensor_at > SESSION_GAP
    ):
        active_session.ended_at = active_session.last_sensor_at
        active_session.duration_seconds = max(
            0,
            int((active_session.ended_at - active_session.started_at).total_seconds()),
        )
        active_session.status = "COMPLETED"
        active_session = None

    if active_session is None:
        active_session = WearSession(
            device_id=device_id,
            started_at=measured_at,
            last_sensor_at=measured_at,
            status="ACTIVE",
        )
        db.add(active_session)
        started = True
    else:
        active_session.last_sensor_at = measured_at

    return active_session, started


def session_duration_seconds(session, now):
    ended_at = session.ended_at or min(
        now,
        session.last_sensor_at + SESSION_GAP,
    )
    return max(0, int((ended_at - session.started_at).total_seconds()))


def queue_device_command(db, device_id, command_type, payload):
    command = DeviceCommand(
        device_id=device_id,
        command_type=command_type,
        payload=json.dumps(payload),
        status="PENDING",
        created_at=datetime.now(),
    )
    db.add(command)
    db.flush()
    return command


def serialize_symptom_record(record):
    return {
        "id": record.id,
        "device_id": record.device_id,
        "recorded_on": record.recorded_on.isoformat(),
        "symptom_type": record.symptom_type,
        "body_area": record.body_area,
        "severity": record.severity,
        "note": record.note,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def wear_seconds_in_period(sessions, period_start, period_end, now):
    total_seconds = 0
    for session in sessions:
        session_end = session.ended_at or min(
            now,
            session.last_sensor_at + SESSION_GAP,
        )
        overlap_start = max(session.started_at, period_start)
        overlap_end = min(session_end, period_end)
        if overlap_end > overlap_start:
            total_seconds += int((overlap_end - overlap_start).total_seconds())
    return total_seconds


def add_demo_history(db, device_id, days):
    """프론트 시연용 일별 착용·각도·과굴곡 데이터를 추가한다."""
    settings = get_or_create_settings(db, device_id)
    now = datetime.now()
    today = now.date()
    randomizer = random.Random(f"{device_id}-{today.isoformat()}")
    reading_count = 0
    contact_count = 0
    overflexion_count = 0
    created_days = 0
    skipped_days = 0

    for offset in range(days):
        record_date = today - timedelta(days=days - offset - 1)
        day_start = datetime.combine(record_date, time.min)
        day_end = day_start + timedelta(days=1)
        already_seeded = db.query(DemoHistoryDay).filter_by(
            device_id=device_id, recorded_on=record_date
        ).first()
        existing_reading = db.query(SensorData.id).filter(
            SensorData.device_id == device_id,
            SensorData.measured_at >= day_start,
            SensorData.measured_at < day_end,
        ).first()
        existing_session = db.query(WearSession.id).filter(
            WearSession.device_id == device_id,
            WearSession.started_at < day_end,
            or_(WearSession.ended_at.is_(None), WearSession.ended_at > day_start),
        ).first()
        if already_seeded or existing_reading or existing_session:
            skipped_days += 1
            continue
        db.add(DemoHistoryDay(device_id=device_id, recorded_on=record_date))
        created_days += 1
        started_at = day_start + timedelta(hours=9)
        wear_minutes = 75 + (offset * 13) % 95
        ended_at = started_at + timedelta(minutes=wear_minutes)
        if record_date == today:
            ended_at = min(ended_at, now)
            started_at = min(started_at, max(day_start, ended_at - timedelta(minutes=wear_minutes)))
        duration = ended_at - started_at
        db.add(
            WearSession(
                device_id=device_id,
                started_at=started_at,
                last_sensor_at=ended_at,
                ended_at=ended_at,
                duration_seconds=max(0, int(duration.total_seconds())),
                status="COMPLETED",
            )
        )

        angles = [
            round(randomizer.uniform(25, 48), 1),
            round(randomizer.uniform(38, 58), 1),
            round(randomizer.uniform(45, 70), 1),
            round(randomizer.uniform(30, 75), 1),
        ]
        for index, angle in enumerate(angles):
            measured_at = started_at + duration * (index / 3)
            if angle >= settings.limit_angle:
                status = "LIMIT_EXCEEDED"
                threshold_angle = settings.limit_angle
            elif angle >= settings.warning_angle:
                status = "WARNING"
                threshold_angle = settings.warning_angle
            else:
                status = "SAFE"
                threshold_angle = None
            sensor_data = SensorData(
                device_id=device_id,
                angle=angle,
                battery=max(65, 100 - offset),
                status=status,
                measured_at=measured_at,
            )
            db.add(sensor_data)
            db.flush()
            reading_count += 1
            if threshold_angle is not None:
                db.add(
                    AngleViolation(
                        device_id=device_id,
                        sensor_data_id=sensor_data.id,
                        violation_type=status,
                        threshold_angle=threshold_angle,
                        angle=angle,
                        excess_angle=round(angle - threshold_angle, 1),
                        occurred_at=measured_at,
                    )
                )

        daily_contacts = 5 + (offset * 3) % 9
        for contact_index in range(daily_contacts):
            occurred_at = started_at + min(duration, timedelta(minutes=3 * contact_index))
            is_overflexion = contact_index == 9
            db.add(
                ContactEvent(
                    device_id=device_id,
                    occurred_at=occurred_at,
                    hourly_contact_count=contact_index + 1,
                    is_overflexion=int(is_overflexion),
                )
            )
            contact_count += 1
            if is_overflexion:
                db.add(
                    OverflexionEvent(
                        device_id=device_id,
                        occurred_at=occurred_at,
                        contact_count_in_last_hour=contact_index + 1,
                    )
                )
                overflexion_count += 1

    return {
        "days": days,
        "created_days": created_days,
        "skipped_days": skipped_days,
        "reading_count": reading_count,
        "contact_count": contact_count,
        "overflexion_count": overflexion_count,
    }


def build_statistics(db, device_id, period_start, period_end):
    now = datetime.now()
    settings = get_or_create_settings(db, device_id)
    readings = (
        db.query(SensorData)
        .filter(
            SensorData.device_id == device_id,
            SensorData.measured_at >= period_start,
            SensorData.measured_at < period_end,
        )
        .all()
    )
    sessions = (
        db.query(WearSession)
        .filter(
            WearSession.device_id == device_id,
            WearSession.started_at < period_end,
            or_(WearSession.ended_at.is_(None), WearSession.ended_at > period_start),
        )
        .all()
    )
    contact_events = (
        db.query(ContactEvent)
        .filter(
            ContactEvent.device_id == device_id,
            ContactEvent.occurred_at >= period_start,
            ContactEvent.occurred_at < period_end,
        )
        .all()
    )
    overflexion_events = (
        db.query(OverflexionEvent)
        .filter(
            OverflexionEvent.device_id == device_id,
            OverflexionEvent.occurred_at >= period_start,
            OverflexionEvent.occurred_at < period_end,
        )
        .all()
    )
    angle_violations = (
        db.query(AngleViolation)
        .filter(
            AngleViolation.device_id == device_id,
            AngleViolation.occurred_at >= period_start,
            AngleViolation.occurred_at < period_end,
        )
        .all()
    )

    owner = db.query(UserDevice).filter_by(device_id=device_id).first()
    status_records = (
        db.query(DailyStatusRecord).filter(
            DailyStatusRecord.user_id == owner.user_id,
            DailyStatusRecord.device_id == device_id,
            DailyStatusRecord.recorded_on >= period_start.date(),
            DailyStatusRecord.recorded_on < period_end.date(),
        ).all() if owner else []
    )
    status_by_date = {record.recorded_on: serialize_daily_status(record) for record in status_records}
    daily = []
    current_day = period_start.date()
    while current_day < period_end.date():
        day_start = datetime.combine(current_day, time.min)
        day_end = day_start + timedelta(days=1)
        day_readings = [
            reading for reading in readings if reading.measured_at.date() == current_day
        ]
        day_contacts = [
            contact for contact in contact_events if contact.occurred_at.date() == current_day
        ]
        day_violations = [
            violation
            for violation in angle_violations
            if violation.occurred_at.date() == current_day
        ]
        wear_seconds = wear_seconds_in_period(sessions, day_start, day_end, now)
        warning_count = sum(
            1 for reading in day_readings if reading.status == "WARNING"
        )
        limit_count = sum(
            1 for reading in day_readings if reading.status == "LIMIT_EXCEEDED"
        )
        overflexion_count = sum(
            1
            for event in overflexion_events
            if event.occurred_at.date() == current_day
        )
        daily.append(
            {
                "date": current_day.isoformat(),
                "status_record": status_by_date.get(current_day),
                "has_status_record": current_day in status_by_date,
                "wear_seconds": wear_seconds,
                "wear_minutes": round(wear_seconds / 60, 1),
                "progress_percent": round(
                    min(100, wear_seconds / (settings.target_wear_minutes * 60) * 100),
                    1,
                ),
                "total_readings": len(day_readings),
                "contact_count": len(day_contacts),
                "warning_count": warning_count,
                "limit_exceeded_count": limit_count,
                "overflexion_count": overflexion_count,
                "max_excess_angle": max(
                    (violation.excess_angle for violation in day_violations), default=0
                ),
                "is_worn": wear_seconds > 0 or bool(day_readings) or bool(day_contacts),
                "max_angle": max(
                    (reading.angle for reading in day_readings), default=None
                ),
            }
        )
        current_day += timedelta(days=1)

    total_wear_seconds = sum(day["wear_seconds"] for day in daily)
    warning_count = sum(1 for reading in readings if reading.status == "WARNING")
    limit_count = sum(
        1 for reading in readings if reading.status == "LIMIT_EXCEEDED"
    )
    return {
        "device_id": device_id,
        "target_wear_minutes_per_day": settings.target_wear_minutes,
        "summary": {
            "wear_seconds": total_wear_seconds,
            "wear_minutes": round(total_wear_seconds / 60, 1),
            "average_wear_minutes": round(total_wear_seconds / 60 / len(daily), 1),
            "progress_percent": round(min(100, total_wear_seconds / (settings.target_wear_minutes * 60 * len(daily)) * 100), 1),
            "target_wear_minutes": settings.target_wear_minutes * len(daily),
            "total_readings": len(readings),
            "contact_count": len(contact_events),
            "warning_count": warning_count,
            "limit_exceeded_count": limit_count,
            "overflexion_count": len(overflexion_events),
            "max_excess_angle": max(
                (violation.excess_angle for violation in angle_violations), default=0
            ),
            "average_excess_angle": round(
                sum(violation.excess_angle for violation in angle_violations)
                / len(angle_violations),
                1,
            ) if angle_violations else 0,
            "max_angle": max((reading.angle for reading in readings), default=None),
        },
        "daily": daily,
    }


def issue_report_snapshot(
    db,
    user_id,
    device_id,
    report_type,
    period_start,
    period_end,
):
    content = build_statistics(db, device_id, period_start, period_end)
    report = Report(
        user_id=user_id,
        device_id=device_id,
        report_type=report_type,
        period_start=period_start.date(),
        period_end=(period_end - timedelta(days=1)).date(),
        content=json.dumps(content, ensure_ascii=False),
        issued_at=datetime.now(),
    )
    db.add(report)
    db.flush()
    return report, content


def create_alert_if_needed(db, sensor_data, settings, measured_at):
    if sensor_data.status == "SAFE":
        return None
    if not device_notification_preferences(db, sys.modules[__name__], sensor_data.device_id)["overuse_enabled"]:
        return None

    previous_alert = (
        db.query(AlertHistory)
        .filter(
            AlertHistory.device_id == sensor_data.device_id,
            AlertHistory.alert_type == sensor_data.status,
        )
        .order_by(AlertHistory.occurred_at.desc())
        .first()
    )
    if (
        previous_alert is not None
        and measured_at - previous_alert.occurred_at < ALERT_COOLDOWN
    ):
        return None

    alert = AlertHistory(
        device_id=sensor_data.device_id,
        sensor_data_id=sensor_data.id,
        alert_type=sensor_data.status,
        angle=sensor_data.angle,
        vibration_strength=settings.vibration_strength,
        occurred_at=measured_at,
    )
    db.add(alert)
    return alert


latest_reading = {
    "device_id": "GUBSIN-001",
    "angle": 0,
    "status": "SAFE",
    "battery": 0,
    "measured_at": None,
}


@app.get("/")
def home():
    return {"message": "굽신굽신 백엔드 서버가 실행 중입니다!"}


@app.get("/health")
def health_check():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="데이터베이스에 연결할 수 없습니다.",
        ) from error
    finally:
        db.close()
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/auth/register", status_code=201)
def register_user(user_input: UserRegisterInput):
    email = normalize_email(user_input.email)
    if "@" not in email:
        raise HTTPException(status_code=422, detail="올바른 이메일 주소를 입력해 주세요.")

    db = SessionLocal()
    if db.query(User).filter(User.email == email).first() is not None:
        db.close()
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    salt = secrets.token_hex(16)
    user = User(
        name=user_input.name.strip(),
        email=email,
        password_salt=salt,
        password_hash=hash_password(user_input.password, salt),
        created_at=datetime.now(),
    )
    db.add(user)
    db.flush()
    token = create_auth_token(db, user.id)
    db.commit()
    result = {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "access_token": token.token,
        "token_type": "bearer",
        "expires_at": token.expires_at.isoformat(),
    }
    db.close()
    return result


@app.post("/auth/login")
def login(login_input: LoginInput):
    email = normalize_email(login_input.email)
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not secrets.compare_digest(
        user.password_hash,
        hash_password(login_input.password, user.password_salt) if user else "",
    ):
        db.close()
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    token = create_auth_token(db, user.id)
    db.commit()
    result = {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "access_token": token.token,
        "token_type": "bearer",
        "expires_at": token.expires_at.isoformat(),
    }
    db.close()
    return result


@app.get("/auth/me")
def get_my_profile(authorization: str | None = Header(default=None)):
    db = SessionLocal()
    user = get_authenticated_user(db, authorization)
    result = {"id": user.id, "name": user.name, "email": user.email}
    db.close()
    return result


@app.patch("/auth/me")
def update_my_profile(
    profile_input: ProfileUpdateInput,
    authorization: str | None = Header(default=None),
):
    if profile_input.name is None and profile_input.new_password is None:
        raise HTTPException(status_code=422, detail="수정할 항목을 입력해 주세요.")
    if profile_input.new_password is not None and profile_input.current_password is None:
        raise HTTPException(status_code=422, detail="현재 비밀번호를 입력해 주세요.")

    db = SessionLocal()
    user = get_authenticated_user(db, authorization)
    if profile_input.name is not None:
        user.name = profile_input.name.strip()
    if profile_input.new_password is not None:
        if not secrets.compare_digest(
            user.password_hash,
            hash_password(profile_input.current_password, user.password_salt),
        ):
            db.close()
            raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")
        salt = secrets.token_hex(16)
        user.password_salt = salt
        user.password_hash = hash_password(profile_input.new_password, salt)
    db.commit()
    result = {"id": user.id, "name": user.name, "email": user.email}
    db.close()
    return result


@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    db = SessionLocal()
    get_authenticated_user(db, authorization)
    token_value = authorization.removeprefix("Bearer ").strip()
    db.query(AuthToken).filter(AuthToken.token == token_value).delete()
    db.commit()
    db.close()
    return {"message": "로그아웃 완료"}


@app.post("/push-tokens", status_code=201)
def register_push_token(
    push_token_input: PushTokenInput,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    user = get_authenticated_user(db, authorization)
    push_token = (
        db.query(PushToken)
        .filter(PushToken.token == push_token_input.token)
        .first()
    )
    now = datetime.now()
    if push_token is None:
        push_token = PushToken(
            user_id=user.id,
            platform=push_token_input.platform,
            token=push_token_input.token,
            is_active=1,
            created_at=now,
            updated_at=now,
        )
        db.add(push_token)
    else:
        push_token.user_id = user.id
        push_token.platform = push_token_input.platform
        push_token.is_active = 1
        push_token.updated_at = now
    db.commit()
    result = {"push_token_id": push_token.id, "platform": push_token.platform}
    db.close()
    return result


@app.delete("/push-tokens/{push_token_id}")
def unregister_push_token(
    push_token_id: int,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    user = get_authenticated_user(db, authorization)
    push_token = (
        db.query(PushToken)
        .filter(PushToken.id == push_token_id, PushToken.user_id == user.id)
        .first()
    )
    if push_token is None:
        db.close()
        raise HTTPException(status_code=404, detail="푸시 토큰을 찾을 수 없습니다.")
    push_token.is_active = 0
    push_token.updated_at = datetime.now()
    db.commit()
    db.close()
    return {"message": "푸시 토큰 등록 해제 완료", "push_token_id": push_token_id}


@app.post("/devices/connect", status_code=201)
def connect_device(
    device_input: DeviceConnectInput,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    user = get_authenticated_user(db, authorization)
    device = (
        db.query(UserDevice)
        .filter(UserDevice.device_id == device_input.device_id)
        .first()
    )
    if device is not None and device.user_id != user.id:
        db.close()
        raise HTTPException(status_code=409, detail="이미 다른 사용자와 연결된 기기입니다.")

    if device is None:
        device = UserDevice(
            user_id=user.id,
            device_id=device_input.device_id,
            device_name=device_input.device_name,
            paired_at=datetime.now(),
        )
        db.add(device)
    else:
        device.device_name = device_input.device_name
    credential = (
        db.query(DeviceCredential)
        .filter(DeviceCredential.device_id == device_input.device_id)
        .first()
    )
    device_key = None
    if credential is None:
        device_key = create_device_key(db, device_input.device_id)
    db.commit()
    result = {
        "device_id": device.device_id,
        "device_name": device.device_name,
        "paired_at": device.paired_at.isoformat(),
        "device_api_key": device_key,
        "device_api_key_notice": (
            "아두이노에 한 번만 저장하세요. 이후에는 다시 표시되지 않습니다."
            if device_key
            else None
        ),
    }
    db.close()
    return result


@app.post("/devices/{device_id}/credentials/regenerate")
def regenerate_device_credential(
    device_id: str,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    user = get_authenticated_user(db, authorization)
    device = (
        db.query(UserDevice)
        .filter(UserDevice.device_id == device_id, UserDevice.user_id == user.id)
        .first()
    )
    if device is None:
        db.close()
        raise HTTPException(status_code=404, detail="연결된 기기를 찾을 수 없습니다.")

    device_key = secrets.token_urlsafe(32)
    credential = (
        db.query(DeviceCredential)
        .filter(DeviceCredential.device_id == device_id)
        .first()
    )
    if credential is None:
        now = datetime.now()
        db.add(
            DeviceCredential(
                device_id=device_id,
                api_key_hash=hash_device_key(device_key),
                created_at=now,
                updated_at=now,
            )
        )
    else:
        credential.api_key_hash = hash_device_key(device_key)
        credential.updated_at = datetime.now()
    db.commit()
    db.close()
    return {
        "device_id": device_id,
        "device_api_key": device_key,
        "notice": "이전 키는 즉시 무효화되었습니다. 새 키를 아두이노에 저장하세요.",
    }


@app.get("/devices")
def get_my_devices(authorization: str | None = Header(default=None)):
    db = SessionLocal()
    user = get_authenticated_user(db, authorization)
    devices = db.query(UserDevice).filter(UserDevice.user_id == user.id).all()
    now = datetime.now()
    result = []
    for device in devices:
        latest_reading = (
            db.query(SensorData)
            .filter(SensorData.device_id == device.device_id)
            .order_by(SensorData.measured_at.desc())
            .first()
        )
        latest_contact = (
            db.query(ContactEvent)
            .filter(ContactEvent.device_id == device.device_id)
            .order_by(ContactEvent.occurred_at.desc())
            .first()
        )
        connection = (
            db.query(DeviceConnection)
            .filter(DeviceConnection.device_id == device.device_id)
            .first()
        )
        activity_times = [
            latest_reading.measured_at if latest_reading else None,
            latest_contact.occurred_at if latest_contact else None,
            connection.last_seen_at if connection else None,
        ]
        last_activity_at = max(time for time in activity_times if time is not None) if any(activity_times) else None
        result.append(
            {
                "device_id": device.device_id,
                "device_name": device.device_name,
                "paired_at": device.paired_at.isoformat(),
                "is_connected": bool(
                    last_activity_at and now - last_activity_at <= SESSION_GAP
                ),
                "last_activity_at": (
                    last_activity_at.isoformat() if last_activity_at else None
                ),
                "battery": (
                    connection.last_battery
                    if connection and connection.last_battery is not None
                    else latest_reading.battery if latest_reading else None
                ),
            }
        )
    db.close()
    return {"devices": result}


@app.get("/devices/{device_id}/commands")
def get_device_command_history(
    device_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    commands = (
        db.query(DeviceCommand)
        .filter(DeviceCommand.device_id == device_id)
        .order_by(DeviceCommand.id.desc())
        .limit(limit)
        .all()
    )
    result = [
        {
            "id": command.id,
            "type": command.command_type,
            "payload": json.loads(command.payload),
            "status": command.status,
            "created_at": command.created_at.isoformat(),
            "delivered_at": (
                command.delivered_at.isoformat() if command.delivered_at else None
            ),
            "acknowledged_at": (
                command.acknowledged_at.isoformat()
                if command.acknowledged_at
                else None
            ),
        }
        for command in commands
    ]
    db.close()
    return {"device_id": device_id, "count": len(result), "commands": result}


@app.get("/devices/{device_id}/status")
def get_device_status(
    device_id: str,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    _, device = require_owned_device(db, authorization, device_id)
    connection = (
        db.query(DeviceConnection)
        .filter(DeviceConnection.device_id == device_id)
        .first()
    )
    latest_reading = (
        db.query(SensorData)
        .filter(SensorData.device_id == device_id)
        .order_by(SensorData.measured_at.desc())
        .first()
    )
    pending_command_count = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.device_id == device_id,
            DeviceCommand.status.in_(["PENDING", "SENT"]),
        )
        .count()
    )
    now = datetime.now()
    last_seen_at = connection.last_seen_at if connection else None
    result = {
        "device_id": device_id,
        "device_name": device.device_name,
        "is_connected": bool(
            last_seen_at and now - last_seen_at <= SESSION_GAP
        ),
        "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
        "battery": connection.last_battery if connection else None,
        "latest_angle": latest_reading.angle if latest_reading else None,
        "pending_command_count": pending_command_count,
        "rom_settings_sync": get_rom_sync_info(db, device_id),
    }
    db.close()
    return result


@app.delete("/devices/{device_id}")
def disconnect_device(
    device_id: str,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    _, device = require_owned_device(db, authorization, device_id)
    db.delete(device)
    db.query(DeviceCredential).filter(
        DeviceCredential.device_id == device_id
    ).delete()
    db.commit()
    db.close()
    return {
        "message": "기기 연결 해제 완료",
        "device_id": device_id,
        "notice": "기기 인증키가 무효화되었습니다.",
    }


@app.get("/settings/rom")
def get_rom_settings(
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    settings = get_or_create_settings(db, device_id)
    vibration_setting = get_or_create_vibration_setting(db, device_id)

    result = {
        "device_id": settings.device_id,
        "warning_angle": settings.warning_angle,
        "limit_angle": settings.limit_angle,
        "vibration_strength": settings.vibration_strength,
        "vibration_duration_ms": vibration_setting.duration_ms,
        "target_wear_minutes": settings.target_wear_minutes,
        "hardware_sync": get_rom_sync_info(db, device_id),
    }
    db.commit()
    db.close()

    return result


@app.put("/settings/rom")
def update_rom_settings(
    new_settings: RomSettingsInput,
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    settings = get_or_create_settings(db, device_id)

    settings.warning_angle = new_settings.warning_angle
    settings.limit_angle = new_settings.limit_angle
    settings.vibration_strength = new_settings.vibration_strength
    settings.target_wear_minutes = new_settings.target_wear_minutes
    vibration_setting = get_or_create_vibration_setting(db, device_id)
    vibration_setting.duration_ms = new_settings.vibration_duration_ms
    vibration_setting.updated_at = datetime.now()

    (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.device_id == device_id,
            DeviceCommand.command_type == "ROM_SETTINGS",
            DeviceCommand.status.in_(["PENDING", "SENT", "APP_PENDING", "APP_FAILED", "APP_REPORTED_APPLIED"]),
        )
        .update({"status": "SUPERSEDED"}, synchronize_session=False)
    )
    command = queue_device_command(
        db,
        device_id,
        "ROM_SETTINGS",
        {
            "warning_angle": settings.warning_angle,
            "limit_angle": settings.limit_angle,
            "vibration_strength": settings.vibration_strength,
            "vibration_duration_ms": vibration_setting.duration_ms,
            "target_wear_minutes": settings.target_wear_minutes,
        },
    )
    if new_settings.delivery_mode == "APP_DIRECT":
        command.status = "APP_PENDING"
    db.commit()
    command_id = command.id
    payload = json.loads(command.payload)
    db.close()

    return {
        "message": "ROM 설정 저장 완료",
        "command_id": command_id,
        "delivery_mode": new_settings.delivery_mode,
        "hardware_payload": payload,
    }


@app.post("/sensor/readings")
def receive_sensor_data(
    reading: SensorReading,
    x_device_key: str | None = Header(default=None),
):
    db = SessionLocal()
    authenticate_device(db, reading.device_id, x_device_key)
    touch_device_connection(db, reading.device_id, reading.battery)
    settings = get_or_create_settings(db, reading.device_id)

    if reading.angle >= settings.limit_angle:
        status = "LIMIT_EXCEEDED"
    elif reading.angle >= settings.warning_angle:
        status = "WARNING"
    else:
        status = "SAFE"

    measured_at = datetime.now()

    sensor_data = SensorData(
        device_id=reading.device_id,
        angle=reading.angle,
        battery=reading.battery,
        status=status,
        measured_at=measured_at,
    )
    db.add(sensor_data)
    db.flush()
    excess_angle = 0.0
    if status != "SAFE":
        threshold_angle = (
            settings.limit_angle
            if status == "LIMIT_EXCEEDED"
            else settings.warning_angle
        )
        excess_angle = round(reading.angle - threshold_angle, 1)
        db.add(
            AngleViolation(
                device_id=reading.device_id,
                sensor_data_id=sensor_data.id,
                violation_type=status,
                threshold_angle=threshold_angle,
                angle=reading.angle,
                excess_angle=excess_angle,
                occurred_at=measured_at,
            )
        )
    _, session_started = update_wear_session(db, reading.device_id, measured_at)
    alert = create_alert_if_needed(db, sensor_data, settings, measured_at)
    db.commit()
    db.close()

    latest_reading["device_id"] = reading.device_id
    latest_reading["angle"] = reading.angle
    latest_reading["status"] = status
    latest_reading["battery"] = reading.battery
    latest_reading["measured_at"] = measured_at.isoformat()

    return {
        "message": "센서 데이터 저장 완료",
        "status": status,
        "excess_angle": excess_angle,
        "wear_session_started": session_started,
        "alert_created": alert is not None,
    }


@app.post("/sensor/contact-events")
def receive_contact_event(
    contact_input: ContactEventInput,
    x_device_key: str | None = Header(default=None),
):
    """아랫판 접촉 시작 이벤트를 기록하고, 최근 1시간 과굴곡을 판정한다."""
    db = SessionLocal()
    authenticate_device(db, contact_input.device_id, x_device_key)
    touch_device_connection(db, contact_input.device_id)
    occurred_at = datetime.now()
    window_start = occurred_at - timedelta(hours=1)
    settings = get_or_create_settings(db, contact_input.device_id)
    vibration_setting = get_or_create_vibration_setting(db, contact_input.device_id)
    previous_contact_count = (
        db.query(ContactEvent)
        .filter(
            ContactEvent.device_id == contact_input.device_id,
            ContactEvent.occurred_at >= window_start,
        )
        .count()
    )
    hourly_contact_count = previous_contact_count + 1
    overflexion_in_window = (
        db.query(OverflexionEvent)
        .filter(
            OverflexionEvent.device_id == contact_input.device_id,
            OverflexionEvent.occurred_at >= window_start,
        )
        .first()
    )
    is_new_overflexion = (
        hourly_contact_count >= OVERFLEXION_CONTACT_THRESHOLD
        and overflexion_in_window is None
    )
    contact_event = ContactEvent(
        device_id=contact_input.device_id,
        occurred_at=occurred_at,
        hourly_contact_count=hourly_contact_count,
        is_overflexion=int(is_new_overflexion),
    )
    db.add(contact_event)
    update_wear_session(db, contact_input.device_id, occurred_at)

    command_id = None
    if is_new_overflexion:
        db.add(
            OverflexionEvent(
                device_id=contact_input.device_id,
                occurred_at=occurred_at,
                contact_count_in_last_hour=hourly_contact_count,
            )
        )
        if device_notification_preferences(db, sys.modules[__name__], contact_input.device_id)["overuse_enabled"]:
            db.add(
                AlertHistory(
                    device_id=contact_input.device_id,
                    alert_type="OVERFLEXION",
                    angle=None,
                    vibration_strength=settings.vibration_strength,
                    occurred_at=occurred_at,
                )
            )
        command = queue_device_command(
            db,
            contact_input.device_id,
            "VIBRATE",
            {
                "strength": settings.vibration_strength,
                "duration_ms": vibration_setting.duration_ms,
                "reason": "OVERFLEXION",
            },
        )
        command_id = command.id

    db.commit()
    db.close()

    return {
        "device_id": contact_input.device_id,
        "hourly_contact_count": hourly_contact_count,
        "is_overflexion": is_new_overflexion,
        "vibration_command_id": command_id,
    }


@app.get("/dashboard/realtime")
def get_realtime_data(
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    reading = (
        db.query(SensorData)
        .filter(SensorData.device_id == device_id)
        .order_by(SensorData.measured_at.desc())
        .first()
    )
    db.close()

    if reading is None:
        if latest_reading["device_id"] == device_id:
            return latest_reading
        raise HTTPException(status_code=404, detail="센서 데이터가 없습니다.")

    return {
        "device_id": reading.device_id,
        "angle": reading.angle,
        "status": reading.status,
        "battery": reading.battery,
        "measured_at": reading.measured_at.isoformat(),
    }


@app.get("/dashboard/overview")
def get_dashboard_overview(
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
):
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    db = SessionLocal()
    user, _ = require_owned_device(db, authorization, device_id)
    settings = get_or_create_settings(db, device_id)
    latest_reading = (
        db.query(SensorData)
        .filter(SensorData.device_id == device_id)
        .order_by(SensorData.measured_at.desc())
        .first()
    )
    sessions = (
        db.query(WearSession)
        .filter(
            WearSession.device_id == device_id,
            WearSession.started_at < today_start + timedelta(days=1),
            or_(WearSession.ended_at.is_(None), WearSession.ended_at > today_start),
        )
        .all()
    )
    wear_seconds = wear_seconds_in_period(sessions, today_start, today_start + timedelta(days=1), now)
    today_overflexion_count = (
        db.query(OverflexionEvent)
        .filter(
            OverflexionEvent.device_id == device_id,
            OverflexionEvent.occurred_at >= today_start,
        )
        .count()
    )
    unread_alert_count = (
        db.query(AlertHistory)
        .filter(
            AlertHistory.device_id == device_id,
            AlertHistory.is_read == 0,
        )
        .count()
    )
    active_session = next(
        (
            session
            for session in sessions
            if session.status == "ACTIVE"
            and now - session.last_sensor_at <= SESSION_GAP
        ),
        None,
    )
    yesterday_start = today_start - timedelta(days=1)
    yesterday_overflexion_count = db.query(OverflexionEvent).filter(
        OverflexionEvent.device_id == device_id,
        OverflexionEvent.occurred_at >= yesterday_start,
        OverflexionEvent.occurred_at < today_start,
    ).count()
    has_yesterday_data = db.query(SensorData.id).filter(
        SensorData.device_id == device_id,
        SensorData.measured_at >= yesterday_start,
        SensorData.measured_at < today_start,
    ).first() is not None or db.query(ContactEvent.id).filter(
        ContactEvent.device_id == device_id,
        ContactEvent.occurred_at >= yesterday_start,
        ContactEvent.occurred_at < today_start,
    ).first() is not None
    status_record = db.query(DailyStatusRecord).filter_by(
        user_id=user.id, device_id=device_id, recorded_on=now.date(),
    ).first()
    hand_settings = db.query(HandSettings).filter_by(user_id=user.id, device_id=device_id).first()
    result = {
        "device_id": device_id,
        "status_record": serialize_daily_status(status_record) if status_record else None,
        "hand_settings": {"hand": hand_settings.hand, "fingers": json.loads(hand_settings.fingers)} if hand_settings else None,
        "realtime": (
            {
                "angle": latest_reading.angle,
                "status": latest_reading.status,
                "battery": latest_reading.battery,
                "measured_at": latest_reading.measured_at.isoformat(),
            }
            if latest_reading
            else None
        ),
        "today": {
            "wear_minutes": round(wear_seconds / 60, 1),
            "target_wear_minutes": settings.target_wear_minutes,
            "progress_percent": round(
                min(100, wear_seconds / (settings.target_wear_minutes * 60) * 100),
                1,
            ),
            "is_wearing": active_session is not None,
            "overflexion_count": today_overflexion_count,
            "yesterday_overflexion_count": yesterday_overflexion_count,
            "has_yesterday_data": has_yesterday_data,
            "overflexion_change_from_yesterday": today_overflexion_count - yesterday_overflexion_count if has_yesterday_data else None,
            "unread_alert_count": unread_alert_count,
        },
    }
    db.close()
    return result


@app.get("/dashboard/daily")
def get_daily_summary(
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
    target_date: date | None = None,
):
    selected_date = target_date or datetime.now().date()
    if selected_date > datetime.now().date():
        raise HTTPException(422, detail="미래 날짜의 기록은 조회할 수 없습니다.")
    today_start = datetime.combine(selected_date, time.min)
    today_end = today_start + timedelta(days=1)
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    readings = (
        db.query(SensorData)
        .filter(
            SensorData.device_id == device_id,
            SensorData.measured_at >= today_start,
            SensorData.measured_at < today_end,
        )
        .all()
    )
    statistics = build_statistics(db, device_id, today_start, today_end)
    db.close()

    warning_count = sum(
        1 for reading in readings if reading.status == "WARNING"
    )
    limit_count = sum(
        1 for reading in readings if reading.status == "LIMIT_EXCEEDED"
    )

    return {
        "device_id": device_id,
        "date": today_start.date().isoformat(),
        "wear_minutes": statistics["summary"]["wear_minutes"],
        "overflexion_count": statistics["summary"]["overflexion_count"],
        "max_excess_angle": statistics["summary"]["max_excess_angle"],
        "progress_percent": statistics["summary"]["progress_percent"],
        "status_record": statistics["daily"][0]["status_record"],
        "total_readings": len(readings),
        "max_angle": max((reading.angle for reading in readings), default=None),
        "average_angle": round(sum(reading.angle for reading in readings) / len(readings), 1) if readings else None,
        "warning_count": warning_count,
        "limit_exceeded_count": limit_count,
        "safe_count": len(readings) - warning_count - limit_count,
        "measurements": [
            {
                "id": reading.id,
                "angle": reading.angle,
                "battery": reading.battery,
                "status": reading.status,
                "measured_at": reading.measured_at.isoformat(),
            }
            for reading in sorted(
                readings,
                key=lambda reading: reading.measured_at,
                reverse=True,
            )[:20]
        ],
    }


@app.get("/dashboard/overflexion/hourly")
def get_hourly_overflexion_statistics(
    device_id: str = "GUBSIN-001",
    target_date: date | None = None,
    authorization: str | None = Header(default=None),
):
    selected_date = target_date or datetime.now().date()
    day_start = datetime.combine(selected_date, time.min)
    day_end = day_start + timedelta(days=1)
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    contacts = (
        db.query(ContactEvent)
        .filter(
            ContactEvent.device_id == device_id,
            ContactEvent.occurred_at >= day_start,
            ContactEvent.occurred_at < day_end,
        )
        .all()
    )
    overflexion_events = (
        db.query(OverflexionEvent)
        .filter(
            OverflexionEvent.device_id == device_id,
            OverflexionEvent.occurred_at >= day_start,
            OverflexionEvent.occurred_at < day_end,
        )
        .all()
    )
    violations = (
        db.query(AngleViolation)
        .filter(
            AngleViolation.device_id == device_id,
            AngleViolation.occurred_at >= day_start,
            AngleViolation.occurred_at < day_end,
        )
        .all()
    )
    db.close()

    hourly = []
    for hour in range(24):
        hour_contacts = [event for event in contacts if event.occurred_at.hour == hour]
        hour_overflexion = [
            event for event in overflexion_events if event.occurred_at.hour == hour
        ]
        hour_violations = [
            event for event in violations if event.occurred_at.hour == hour
        ]
        hourly.append(
            {
                "hour": hour,
                "contact_count": len(hour_contacts),
                "overflexion_count": len(hour_overflexion),
                "violation_count": len(hour_violations),
                "max_excess_angle": max(
                    (event.excess_angle for event in hour_violations), default=0
                ),
            }
        )
    return {"device_id": device_id, "date": selected_date.isoformat(), "hourly": hourly}


@app.get("/dashboard/weekly")
def get_weekly_statistics(
    device_id: str = "GUBSIN-001",
    end_date: date | None = None,
    authorization: str | None = Header(default=None),
):
    selected_end_date = end_date or datetime.now().date()
    if selected_end_date > datetime.now().date():
        raise HTTPException(status_code=422, detail="미래 날짜의 통계는 조회할 수 없습니다.")

    period_start = datetime.combine(
        selected_end_date - timedelta(days=6),
        time.min,
    )
    period_end = datetime.combine(selected_end_date + timedelta(days=1), time.min)
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    result = build_statistics(db, device_id, period_start, period_end)
    db.close()

    return {
        "period_type": "WEEKLY",
        "start_date": period_start.date().isoformat(),
        "end_date": selected_end_date.isoformat(),
        **result,
    }


@app.get("/dashboard/monthly")
def get_monthly_statistics(
    device_id: str = "GUBSIN-001",
    year: int | None = Query(default=None, ge=2020, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    authorization: str | None = Header(default=None),
):
    today = datetime.now().date()
    selected_year = year or today.year
    selected_month = month or today.month
    month_start_date = date(selected_year, selected_month, 1)
    if month_start_date > today:
        raise HTTPException(status_code=422, detail="미래 월의 통계는 조회할 수 없습니다.")

    days_in_month = calendar.monthrange(selected_year, selected_month)[1]
    next_month_date = month_start_date + timedelta(days=days_in_month)
    period_start = datetime.combine(month_start_date, time.min)
    full_period_end = datetime.combine(next_month_date, time.min)
    period_end = min(
        full_period_end,
        datetime.combine(today + timedelta(days=1), time.min),
    )

    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    result = build_statistics(db, device_id, period_start, period_end)
    db.close()

    return {
        "period_type": "MONTHLY",
        "year": selected_year,
        "month": selected_month,
        "start_date": period_start.date().isoformat(),
        "end_date": (period_end - timedelta(days=1)).date().isoformat(),
        **result,
    }


@app.post("/demo/seed-history", status_code=201)
def seed_demo_history(
    demo_input: DemoSeedInput,
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
):
    """프론트 시연 전용: 최근 일별 가상 기록과 리포트를 만든다."""
    with SessionLocal() as db:
        user, _ = require_owned_device(db, authorization, device_id)
        seed_result = add_demo_history(db, device_id, demo_input.days)
        db.flush()
        report_ids = {}
        if demo_input.issue_reports:
            today = datetime.now().date()
            tomorrow = datetime.combine(today + timedelta(days=1), time.min)
            month_start = datetime.combine(today.replace(day=1), time.min)
            periods = [
                ("weekly_report_id", "WEEKLY", tomorrow - timedelta(days=7), tomorrow),
                ("monthly_report_id", "MONTHLY", month_start, tomorrow),
            ]
            previous_month_end = month_start
            previous_month_start = (month_start - timedelta(days=1)).replace(day=1)
            if today - timedelta(days=demo_input.days - 1) <= previous_month_start.date():
                periods.append((
                    "previous_month_report_id", "MONTHLY",
                    previous_month_start, previous_month_end,
                ))
            for key, report_type, start, end in periods:
                # Reuse only demo snapshots, leaving manually issued reports intact.
                candidates = db.query(Report).filter_by(
                    user_id=user.id, device_id=device_id, report_type=report_type,
                    period_start=start.date(), period_end=(end - timedelta(days=1)).date(),
                ).all()
                report = next((
                    item for item in candidates
                    if json.loads(item.content).get("is_demo") is True
                ), None)
                if report is None:
                    report, content = issue_report_snapshot(
                        db, user.id, device_id, report_type, start, end,
                    )
                else:
                    content = build_statistics(db, device_id, start, end)
                content["is_demo"] = True
                report.content = json.dumps(content, ensure_ascii=False)
                report_ids[key] = report.id
        db.commit()
        return {
            "message": "가상 사용 기록 생성 완료",
            "device_id": device_id,
            "is_demo": True,
            **seed_result,
            **report_ids,
        }


@app.post("/reports/weekly", status_code=201)
def issue_weekly_report(
    device_id: str = "GUBSIN-001",
    end_date: date | None = None,
    authorization: str | None = Header(default=None),
):
    selected_end_date = end_date or datetime.now().date()
    if selected_end_date > datetime.now().date():
        raise HTTPException(status_code=422, detail="미래 날짜의 리포트는 발행할 수 없습니다.")

    period_start = datetime.combine(selected_end_date - timedelta(days=6), time.min)
    period_end = datetime.combine(selected_end_date + timedelta(days=1), time.min)
    db = SessionLocal()
    user, _ = require_owned_device(db, authorization, device_id)
    report, content = issue_report_snapshot(
        db,
        user.id,
        device_id,
        "WEEKLY",
        period_start,
        period_end,
    )
    db.commit()
    result = {
        "report_id": report.id,
        "report_type": report.report_type,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "issued_at": report.issued_at.isoformat(),
        "content": content,
    }
    db.close()
    return result


@app.post("/reports/daily", status_code=201)
def issue_daily_report(
    device_id: str = "GUBSIN-001",
    target_date: date | None = None,
    authorization: str | None = Header(default=None),
):
    selected_date = target_date or datetime.now().date()
    if selected_date > datetime.now().date():
        raise HTTPException(status_code=422, detail="미래 날짜의 리포트는 발행할 수 없습니다.")

    period_start = datetime.combine(selected_date, time.min)
    period_end = period_start + timedelta(days=1)
    db = SessionLocal()
    user, _ = require_owned_device(db, authorization, device_id)
    report, content = issue_report_snapshot(
        db,
        user.id,
        device_id,
        "DAILY",
        period_start,
        period_end,
    )
    db.commit()
    result = {
        "report_id": report.id,
        "report_type": report.report_type,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "issued_at": report.issued_at.isoformat(),
        "content": content,
    }
    db.close()
    return result


@app.post("/reports/monthly", status_code=201)
def issue_monthly_report(
    device_id: str = "GUBSIN-001",
    year: int | None = Query(default=None, ge=2020, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    authorization: str | None = Header(default=None),
):
    today = datetime.now().date()
    selected_year = year or today.year
    selected_month = month or today.month
    month_start_date = date(selected_year, selected_month, 1)
    if month_start_date > today:
        raise HTTPException(status_code=422, detail="미래 월의 리포트는 발행할 수 없습니다.")

    days_in_month = calendar.monthrange(selected_year, selected_month)[1]
    period_start = datetime.combine(month_start_date, time.min)
    full_period_end = period_start + timedelta(days=days_in_month)
    period_end = min(
        full_period_end,
        datetime.combine(today + timedelta(days=1), time.min),
    )
    db = SessionLocal()
    user, _ = require_owned_device(db, authorization, device_id)
    report, content = issue_report_snapshot(
        db,
        user.id,
        device_id,
        "MONTHLY",
        period_start,
        period_end,
    )
    db.commit()
    result = {
        "report_id": report.id,
        "report_type": report.report_type,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "issued_at": report.issued_at.isoformat(),
        "content": content,
    }
    db.close()
    return result


@app.get("/reports")
def get_report_history(
    device_id: str = "GUBSIN-001",
    limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    user, _ = require_owned_device(db, authorization, device_id)
    reports = (
        db.query(Report)
        .filter(Report.user_id == user.id, Report.device_id == device_id)
        .order_by(Report.issued_at.desc())
        .limit(limit)
        .all()
    )
    result = [
        {
            "report_id": report.id,
            "report_type": report.report_type,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "issued_at": report.issued_at.isoformat(),
        }
        for report in reports
    ]
    db.close()
    return {"device_id": device_id, "count": len(result), "reports": result}


@app.get("/reports/{report_id}")
def get_report(report_id: int, authorization: str | None = Header(default=None)):
    db = SessionLocal()
    user = get_authenticated_user(db, authorization)
    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.user_id == user.id)
        .first()
    )
    if report is None:
        db.close()
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    result = {
        "report_id": report.id,
        "report_type": report.report_type,
        "device_id": report.device_id,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "issued_at": report.issued_at.isoformat(),
        "content": json.loads(report.content),
    }
    db.close()
    return result


@app.get("/sensor/readings")
def get_sensor_history(
    device_id: str = "GUBSIN-001",
    limit: int = Query(default=50, ge=1, le=200),
    status: Literal["SAFE", "WARNING", "LIMIT_EXCEEDED"] | None = None,
    authorization: str | None = Header(default=None),
    target_date: date | None = None,
):
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    query = db.query(SensorData).filter(SensorData.device_id == device_id)
    if target_date is not None:
        day_start = datetime.combine(target_date, time.min)
        query = query.filter(
            SensorData.measured_at >= day_start,
            SensorData.measured_at < day_start + timedelta(days=1),
        )
    if status is not None:
        query = query.filter(SensorData.status == status)
    readings = query.order_by(SensorData.measured_at.desc()).limit(limit).all()
    reading_ids = [reading.id for reading in readings]
    violations = (
        db.query(AngleViolation)
        .filter(AngleViolation.sensor_data_id.in_(reading_ids))
        .all()
        if reading_ids
        else []
    )
    violations_by_reading_id = {
        violation.sensor_data_id: violation for violation in violations
    }
    db.close()

    return {
        "device_id": device_id,
        "count": len(readings),
        "readings": [
            {
                "id": reading.id,
                "angle": reading.angle,
                "battery": reading.battery,
                "status": reading.status,
                "threshold_angle": (
                    violations_by_reading_id[reading.id].threshold_angle
                    if reading.id in violations_by_reading_id
                    else None
                ),
                "excess_angle": (
                    violations_by_reading_id[reading.id].excess_angle
                    if reading.id in violations_by_reading_id
                    else 0
                ),
                "measured_at": reading.measured_at.isoformat(),
            }
            for reading in readings
        ],
    }


@app.post("/wear-sessions/stop")
def stop_wear_session(
    session_input: WearSessionStopInput,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, session_input.device_id)
    session = (
        db.query(WearSession)
        .filter(
            WearSession.device_id == session_input.device_id,
            WearSession.status == "ACTIVE",
        )
        .order_by(WearSession.started_at.desc())
        .first()
    )

    if session is None:
        db.close()
        raise HTTPException(status_code=404, detail="진행 중인 착용 세션이 없습니다.")

    ended_at = min(datetime.now(), session.last_sensor_at + SESSION_GAP)
    session.ended_at = ended_at
    session.duration_seconds = session_duration_seconds(session, ended_at)
    session.status = "COMPLETED"
    db.commit()
    duration_seconds = session.duration_seconds
    db.close()

    return {
        "message": "착용 세션 종료 완료",
        "device_id": session_input.device_id,
        "duration_seconds": duration_seconds,
        "duration_minutes": round(duration_seconds / 60, 1),
    }


@app.get("/wear-sessions/today")
def get_today_wear_summary(
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
):
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    today_end = datetime.combine(now.date(), time.max)
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    settings = get_or_create_settings(db, device_id)
    sessions = (
        db.query(WearSession)
        .filter(
            WearSession.device_id == device_id,
            WearSession.started_at <= today_end,
            or_(WearSession.ended_at.is_(None), WearSession.ended_at > today_start),
        )
        .order_by(WearSession.started_at.desc())
        .all()
    )

    total_seconds = wear_seconds_in_period(sessions, today_start, today_start + timedelta(days=1), now)
    target_seconds = settings.target_wear_minutes * 60
    active_session = next(
        (
            session
            for session in sessions
            if session.status == "ACTIVE"
            and now - session.last_sensor_at <= SESSION_GAP
        ),
        None,
    )
    db.close()

    return {
        "device_id": device_id,
        "date": now.date().isoformat(),
        "target_wear_minutes": settings.target_wear_minutes,
        "wear_seconds": total_seconds,
        "wear_minutes": round(total_seconds / 60, 1),
        "progress_percent": round(min(100, total_seconds / target_seconds * 100), 1),
        "is_wearing": active_session is not None,
        "session_count": len(sessions),
    }


@app.get("/alerts")
def get_alert_history(
    device_id: str = "GUBSIN-001",
    limit: int = Query(default=50, ge=1, le=200),
    is_read: bool | None = None,
    alert_type: Literal[
        "WARNING",
        "LIMIT_EXCEEDED",
        "OVERFLEXION",
        "WEAR_RECOMMENDATION",
    ] | None = None,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    query = db.query(AlertHistory).filter(AlertHistory.device_id == device_id)
    if is_read is not None:
        query = query.filter(AlertHistory.is_read == int(is_read))
    if alert_type is not None:
        query = query.filter(AlertHistory.alert_type == alert_type)
    alerts = query.order_by(AlertHistory.occurred_at.desc()).limit(limit).all()
    db.close()

    return {
        "device_id": device_id,
        "count": len(alerts),
        "alerts": [
            {
                "id": alert.id,
                "alert_type": alert.alert_type,
                "angle": alert.angle,
                "vibration_strength": alert.vibration_strength,
                "occurred_at": alert.occurred_at.isoformat(),
                "is_read": bool(alert.is_read),
                "read_at": alert.read_at.isoformat() if alert.read_at else None,
            }
            for alert in alerts
        ],
    }


@app.patch("/alerts/{alert_id}/read")
def mark_alert_as_read(
    alert_id: int,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    alert = db.query(AlertHistory).filter(AlertHistory.id == alert_id).first()
    if alert is None:
        db.close()
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
    require_owned_device(db, authorization, alert.device_id)

    alert.is_read = 1
    alert.read_at = datetime.now()
    db.commit()
    db.close()

    return {"message": "알림 읽음 처리 완료", "alert_id": alert_id}


@app.patch("/alerts/read-all")
def mark_all_alerts_as_read(
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    now = datetime.now()
    updated_count = (
        db.query(AlertHistory)
        .filter(
            AlertHistory.device_id == device_id,
            AlertHistory.is_read == 0,
        )
        .update({"is_read": 1, "read_at": now}, synchronize_session=False)
    )
    db.commit()
    db.close()
    return {"message": "모든 알림 읽음 처리 완료", "updated_count": updated_count}


@app.get("/symptoms/options")
def get_symptom_options():
    return {
        "symptom_types": [
            {"value": value, "label": label}
            for value, label in SYMPTOM_TYPES.items()
        ],
        "body_areas": [
            {"value": value, "label": label}
            for value, label in BODY_AREAS.items()
        ],
        "severity": [
            {"value": value, "label": label}
            for value, label in SEVERITY_LABELS.items()
        ],
    }


@app.post("/symptoms", status_code=201)
def create_symptom_record(
    symptom_input: SymptomRecordInput,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, symptom_input.device_id)
    now = datetime.now()
    record = SymptomRecord(
        device_id=symptom_input.device_id,
        recorded_on=symptom_input.recorded_on,
        symptom_type=symptom_input.symptom_type,
        body_area=symptom_input.body_area,
        severity=symptom_input.severity,
        note=symptom_input.note,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    result = serialize_symptom_record(record)
    db.close()
    return result


@app.get("/symptoms")
def get_symptom_records(
    device_id: str = "GUBSIN-001",
    limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    records = (
        db.query(SymptomRecord)
        .filter(SymptomRecord.device_id == device_id)
        .order_by(SymptomRecord.recorded_on.desc(), SymptomRecord.id.desc())
        .limit(limit)
        .all()
    )
    result = [serialize_symptom_record(record) for record in records]
    db.close()
    return {"device_id": device_id, "count": len(result), "records": result}


@app.get("/symptoms/analysis")
def analyze_symptoms(
    device_id: str = "GUBSIN-001",
    start_date: date | None = None,
    end_date: date | None = None,
    authorization: str | None = Header(default=None),
):
    selected_end_date = end_date or datetime.now().date()
    selected_start_date = start_date or selected_end_date - timedelta(days=29)
    if selected_start_date > selected_end_date:
        raise HTTPException(status_code=422, detail="시작일은 종료일보다 늦을 수 없습니다.")

    period_start = datetime.combine(selected_start_date, time.min)
    period_end = datetime.combine(selected_end_date + timedelta(days=1), time.min)
    db = SessionLocal()
    require_owned_device(db, authorization, device_id)
    records = (
        db.query(SymptomRecord)
        .filter(
            SymptomRecord.device_id == device_id,
            SymptomRecord.recorded_on >= selected_start_date,
            SymptomRecord.recorded_on <= selected_end_date,
        )
        .all()
    )
    overflexion_dates = {
        event.occurred_at.date()
        for event in db.query(OverflexionEvent)
        .filter(
            OverflexionEvent.device_id == device_id,
            OverflexionEvent.occurred_at >= period_start,
            OverflexionEvent.occurred_at < period_end,
        )
        .all()
    }
    db.close()

    symptom_type_counts = {
        symptom_type: sum(
            1 for record in records if record.symptom_type == symptom_type
        )
        for symptom_type in SYMPTOM_TYPES
    }
    body_area_counts = {
        body_area: sum(1 for record in records if record.body_area == body_area)
        for body_area in BODY_AREAS
    }
    records_on_overflexion_days = sum(
        1 for record in records if record.recorded_on in overflexion_dates
    )
    return {
        "device_id": device_id,
        "start_date": selected_start_date.isoformat(),
        "end_date": selected_end_date.isoformat(),
        "record_count": len(records),
        "average_severity": round(
            sum(record.severity for record in records) / len(records), 1
        ) if records else 0,
        "high_severity_count": sum(1 for record in records if record.severity >= 4),
        "symptom_type_counts": symptom_type_counts,
        "body_area_counts": body_area_counts,
        "records_on_overflexion_days": records_on_overflexion_days,
        "overflexion_day_count": len(overflexion_dates),
    }


@app.patch("/symptoms/{record_id}")
def update_symptom_record(
    record_id: int,
    update_input: SymptomRecordUpdate,
    authorization: str | None = Header(default=None),
):
    update_values = update_input.model_dump(exclude_unset=True)
    if not update_values:
        raise HTTPException(status_code=422, detail="수정할 항목을 입력해 주세요.")

    db = SessionLocal()
    record = db.query(SymptomRecord).filter(SymptomRecord.id == record_id).first()
    if record is None:
        db.close()
        raise HTTPException(status_code=404, detail="증상 기록을 찾을 수 없습니다.")
    require_owned_device(db, authorization, record.device_id)

    for field, value in update_values.items():
        setattr(record, field, value)
    record.updated_at = datetime.now()
    db.commit()
    db.refresh(record)
    result = serialize_symptom_record(record)
    db.close()
    return result


@app.delete("/symptoms/{record_id}")
def delete_symptom_record(
    record_id: int,
    authorization: str | None = Header(default=None),
):
    db = SessionLocal()
    record = db.query(SymptomRecord).filter(SymptomRecord.id == record_id).first()
    if record is None:
        db.close()
        raise HTTPException(status_code=404, detail="증상 기록을 찾을 수 없습니다.")
    require_owned_device(db, authorization, record.device_id)

    db.delete(record)
    db.commit()
    db.close()
    return {"message": "증상 기록 삭제 완료", "record_id": record_id}


@app.post("/wear-recommendations/check")
def check_wear_recommendation(
    device_id: str = "GUBSIN-001",
    authorization: str | None = Header(default=None),
):
    """앱이 주기적으로 호출해 미착용 권장 알림을 대기열에 추가한다."""
    db = SessionLocal()
    user, _ = require_owned_device(db, authorization, device_id)
    if not get_notification_preferences(db, user.id)["wear_recommendation_enabled"]:
        db.close()
        return {"queued": False, "reason": "DISABLED"}
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    latest_reading = (
        db.query(SensorData)
        .filter(SensorData.device_id == device_id)
        .order_by(SensorData.measured_at.desc())
        .first()
    )
    latest_contact = (
        db.query(ContactEvent)
        .filter(ContactEvent.device_id == device_id)
        .order_by(ContactEvent.occurred_at.desc())
        .first()
    )
    activity_times = [
        item.measured_at if isinstance(item, SensorData) else item.occurred_at
        for item in (latest_reading, latest_contact)
        if item is not None
    ]
    if not activity_times:
        db.close()
        return {"queued": False, "reason": "NO_DEVICE_ACTIVITY"}

    last_activity_at = max(activity_times)
    if now - last_activity_at < WEAR_RECOMMENDATION_DELAY:
        db.close()
        return {"queued": False, "reason": "RECENTLY_WORN"}

    recommendations = (
        db.query(AlertHistory)
        .filter(
            AlertHistory.device_id == device_id,
            AlertHistory.alert_type == "WEAR_RECOMMENDATION",
            AlertHistory.occurred_at >= today_start,
        )
        .order_by(AlertHistory.occurred_at.desc())
        .all()
    )
    if len(recommendations) >= MAX_WEAR_RECOMMENDATIONS_PER_DAY:
        db.close()
        return {"queued": False, "reason": "DAILY_LIMIT_REACHED"}
    if recommendations and now - recommendations[0].occurred_at < WEAR_RECOMMENDATION_DELAY:
        db.close()
        return {"queued": False, "reason": "RECOMMENDATION_COOLDOWN"}

    alert = AlertHistory(
        device_id=device_id,
        alert_type="WEAR_RECOMMENDATION",
        angle=None,
        vibration_strength=0,
        occurred_at=now,
    )
    db.add(alert)
    db.commit()
    alert_id = alert.id
    db.close()
    return {
        "queued": True,
        "alert_id": alert_id,
        "recommendation_count_today": len(recommendations) + 1,
    }


@app.get("/devices/{device_id}/commands/next")
def get_next_device_command(
    device_id: str,
    x_device_key: str | None = Header(default=None),
):
    """아두이노가 폴링하여 설정·진동 명령을 받아가는 엔드포인트다."""
    db = SessionLocal()
    authenticate_device(db, device_id, x_device_key)
    touch_device_connection(db, device_id)
    command = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.device_id == device_id,
            DeviceCommand.status.in_(["PENDING", "SENT"]),
        )
        .order_by(DeviceCommand.id.asc())
        .first()
    )
    if command is None:
        db.close()
        return {"command": None}

    if command.status == "PENDING":
        command.status = "SENT"
        command.delivered_at = datetime.now()
        db.commit()

    result = {
        "command": {
            "id": command.id,
            "type": command.command_type,
            "payload": json.loads(command.payload),
        }
    }
    db.close()
    return result


@app.post("/devices/{device_id}/commands/{command_id}/ack")
def acknowledge_device_command(
    device_id: str,
    command_id: int,
    x_device_key: str | None = Header(default=None),
):
    db = SessionLocal()
    authenticate_device(db, device_id, x_device_key)
    touch_device_connection(db, device_id)
    command = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.id == command_id,
            DeviceCommand.device_id == device_id,
        )
        .first()
    )
    if command is None:
        db.close()
        raise HTTPException(status_code=404, detail="기기 명령을 찾을 수 없습니다.")

    if command.status == "SUPERSEDED":
        db.close()
        raise HTTPException(status_code=409, detail="최신 설정으로 다시 적용해 주세요.")
    if command.command_type == "ROM_SETTINGS":
        latest_settings_command = db.query(DeviceCommand).filter_by(
            device_id=device_id, command_type="ROM_SETTINGS",
        ).order_by(DeviceCommand.id.desc()).first()
        if latest_settings_command.id != command.id:
            db.close()
            raise HTTPException(status_code=409, detail="이전 설정의 적용 확인은 사용할 수 없습니다.")

    command.status = "ACKNOWLEDGED"
    command.acknowledged_at = datetime.now()
    if command.command_type == "ROM_SETTINGS":
        sync = (
            db.query(DeviceSettingsSync)
            .filter(DeviceSettingsSync.device_id == device_id)
            .first()
        )
        if sync is None:
            sync = DeviceSettingsSync(
                device_id=device_id,
                last_applied_command_id=command.id,
                last_applied_at=command.acknowledged_at,
            )
            db.add(sync)
        else:
            sync.last_applied_command_id = command.id
            sync.last_applied_at = command.acknowledged_at
    db.commit()
    db.close()
    return {"message": "기기 명령 확인 완료", "command_id": command_id}


@app.post("/devices/{device_id}/heartbeat")
def device_heartbeat(
    device_id: str,
    battery: int | None = Query(default=None, ge=0, le=100),
    x_device_key: str | None = Header(default=None),
):
    db = SessionLocal()
    authenticate_device(db, device_id, x_device_key)
    connection = touch_device_connection(db, device_id, battery)
    db.commit()
    result = {
        "device_id": device_id,
        "last_seen_at": connection.last_seen_at.isoformat(),
        "battery": connection.last_battery,
    }
    db.close()
    return result


ui_routes = install_ui_routes(app, sys.modules[__name__])
