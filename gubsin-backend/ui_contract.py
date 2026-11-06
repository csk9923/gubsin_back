"""Persistence and app endpoints matching the mobile prototype."""

import json
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Column, Date, DateTime, Integer, String, Text, UniqueConstraint

from database import Base, SessionLocal


class HandSettings(Base):
    __tablename__ = "hand_settings"
    __table_args__ = (UniqueConstraint("user_id", "device_id"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    device_id = Column(String, nullable=False, index=True)
    hand = Column(String, nullable=False)
    fingers = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class DailyStatusRecord(Base):
    __tablename__ = "daily_status_records"
    __table_args__ = (UniqueConstraint("user_id", "device_id", "recorded_on"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    device_id = Column(String, nullable=False, index=True)
    recorded_on = Column(Date, nullable=False, index=True)
    condition = Column(String, nullable=False)
    symptoms = Column(Text, nullable=False)
    activities = Column(Text, nullable=False)
    note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class NotificationPreferences(Base):
    __tablename__ = "notification_preferences"
    user_id = Column(Integer, primary_key=True)
    wear_recommendation_enabled = Column(Integer, nullable=False, default=1)
    overuse_enabled = Column(Integer, nullable=False, default=1)


class AppSettingsReceipt(Base):
    __tablename__ = "app_settings_receipts"
    command_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    success = Column(Integer, nullable=False)
    error_message = Column(Text, nullable=True)
    reported_at = Column(DateTime, nullable=False)


SYMPTOM_OPTIONS = {
    "PAIN": "통증", "STIFFNESS": "뻣뻣함", "SWELLING": "붓기",
    "NUMBNESS": "저림", "OTHER": "기타", "NONE": "없음",
}
ACTIVITY_OPTIONS = {"TYPING": "타이핑", "HOUSEWORK": "집안일", "EXERCISE": "운동", "OTHER": "기타"}
CONDITION_OPTIONS = {
    "GOOD": "좋음", "NORMAL": "보통", "UNCOMFORTABLE": "불편",
    "SEVERE": "심함", "VERY_SEVERE": "매우 심함",
}


class HandSettingsInput(BaseModel):
    hand: Literal["LEFT", "RIGHT"]
    fingers: list[Annotated[int, Field(strict=True, ge=1, le=5)]] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_fingers(self):
        if len(set(self.fingers)) != len(self.fingers):
            raise ValueError("손가락을 중복 선택할 수 없습니다.")
        self.fingers.sort()
        return self


class DailyStatusInput(BaseModel):
    condition: Literal["GOOD", "NORMAL", "UNCOMFORTABLE", "SEVERE", "VERY_SEVERE"]
    symptoms: list[Literal["PAIN", "STIFFNESS", "SWELLING", "NUMBNESS", "OTHER", "NONE"]] = Field(min_length=1, max_length=6)
    activities: list[Literal["TYPING", "HOUSEWORK", "EXERCISE", "OTHER"]] = Field(default_factory=list, max_length=4)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_selections(self):
        if "NONE" in self.symptoms and len(self.symptoms) > 1:
            raise ValueError("증상 '없음'은 다른 증상과 함께 선택할 수 없습니다.")
        if len(set(self.symptoms)) != len(self.symptoms) or len(set(self.activities)) != len(self.activities):
            raise ValueError("중복 선택은 허용되지 않습니다.")
        return self


class NotificationInput(BaseModel):
    wear_recommendation_enabled: bool = Field(strict=True)
    overuse_enabled: bool = Field(strict=True)


class AppSettingsResultInput(BaseModel):
    success: bool = Field(strict=True)
    error_message: str | None = Field(default=None, max_length=500)


class RomSettingsPatchInput(BaseModel):
    limit_angle: float | None = Field(default=None, ge=15, le=90, multiple_of=15)
    vibration_duration_ms: int | None = Field(default=None, ge=100, le=10000)
    vibration_strength: int | None = Field(default=None, ge=0, le=100)
    target_wear_minutes: int | None = Field(default=None, gt=0, le=1440)

    @model_validator(mode="after")
    def require_changes(self):
        values = self.model_dump(exclude_unset=True)
        if not values or any(value is None for value in values.values()):
            raise ValueError("수정할 값을 입력해 주세요. null 값은 사용할 수 없습니다.")
        return self


def serialize_daily_status(record):
    return {
        "id": record.id, "device_id": record.device_id,
        "recorded_on": record.recorded_on.isoformat(), "condition": record.condition,
        "symptoms": json.loads(record.symptoms), "activities": json.loads(record.activities),
        "note": record.note, "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def get_notification_preferences(db, user_id):
    preferences = db.get(NotificationPreferences, user_id) if user_id is not None else None
    return {
        "wear_recommendation_enabled": bool(preferences.wear_recommendation_enabled) if preferences else True,
        "overuse_enabled": bool(preferences.overuse_enabled) if preferences else True,
        "wear_reminder_after_minutes": 60,
        "max_wear_reminders_per_day": 5,
        "overflexion_window_minutes": 60,
        "overflexion_contact_threshold": 10,
        "push_delivery_available": False,
    }


def device_notification_preferences(db, backend, device_id):
    owner = db.query(backend.UserDevice).filter_by(device_id=device_id).first()
    return get_notification_preferences(db, owner.user_id if owner else None)


def install_ui_routes(app, backend):
    # All device records require both login and device ownership.
    @app.get("/settings/hand")
    def get_hand_settings(device_id: str, authorization: str | None = Header(default=None)):
        with SessionLocal() as db:
            user, _ = backend.require_owned_device(db, authorization, device_id)
            record = db.query(HandSettings).filter_by(user_id=user.id, device_id=device_id).first()
            return {
                "device_id": device_id, "hand": record.hand if record else None,
                "fingers": json.loads(record.fingers) if record else [],
                "is_configured": record is not None,
            }

    @app.put("/settings/hand")
    def save_hand_settings(settings: HandSettingsInput, device_id: str, authorization: str | None = Header(default=None)):
        with SessionLocal() as db:
            user, _ = backend.require_owned_device(db, authorization, device_id)
            record = db.query(HandSettings).filter_by(user_id=user.id, device_id=device_id).first()
            if record is None:
                record = HandSettings(user_id=user.id, device_id=device_id)
                db.add(record)
            record.hand = settings.hand
            record.fingers = json.dumps(settings.fingers)
            record.updated_at = backend.datetime.now()
            db.commit()
            return {"device_id": device_id, "hand": record.hand, "fingers": json.loads(record.fingers), "is_configured": True}

    @app.get("/daily-records/options")
    def get_daily_record_options():
        return {
            "conditions": [{"value": key, "label": value} for key, value in CONDITION_OPTIONS.items()],
            "symptoms": [{"value": key, "label": value} for key, value in SYMPTOM_OPTIONS.items()],
            "activities": [{"value": key, "label": value} for key, value in ACTIVITY_OPTIONS.items()],
            "max_note_length": 1000,
        }

    @app.get("/daily-records")
    def list_daily_records(
        device_id: str, start_date: date | None = None, end_date: date | None = None,
        limit: int = Query(default=50, ge=1, le=366), authorization: str | None = Header(default=None),
    ):
        if start_date and end_date and start_date > end_date:
            raise HTTPException(422, "시작일은 종료일보다 늦을 수 없습니다.")
        with SessionLocal() as db:
            user, _ = backend.require_owned_device(db, authorization, device_id)
            query = db.query(DailyStatusRecord).filter_by(user_id=user.id, device_id=device_id)
            if start_date:
                query = query.filter(DailyStatusRecord.recorded_on >= start_date)
            if end_date:
                query = query.filter(DailyStatusRecord.recorded_on <= end_date)
            records = query.order_by(DailyStatusRecord.recorded_on.desc()).limit(limit).all()
            return {"device_id": device_id, "count": len(records), "records": [serialize_daily_status(item) for item in records]}

    @app.get("/daily-records/analysis")
    def analyze_daily_records(
        device_id: str, start_date: date | None = None, end_date: date | None = None,
        authorization: str | None = Header(default=None),
    ):
        selected_end = end_date or backend.datetime.now().date()
        selected_start = start_date or selected_end - timedelta(days=29)
        if selected_start > selected_end or (selected_end - selected_start).days > 365:
            raise HTTPException(422, "조회 기간은 시작일 이후 최대 366일이어야 합니다.")
        if selected_end > backend.datetime.now().date():
            raise HTTPException(422, "미래 날짜의 분석은 조회할 수 없습니다.")
        with SessionLocal() as db:
            user, _ = backend.require_owned_device(db, authorization, device_id)
            records = db.query(DailyStatusRecord).filter(
                DailyStatusRecord.user_id == user.id, DailyStatusRecord.device_id == device_id,
                DailyStatusRecord.recorded_on >= selected_start,
                DailyStatusRecord.recorded_on <= selected_end,
            ).all()
            statistics = backend.build_statistics(
                db, device_id, datetime.combine(selected_start, time.min),
                datetime.combine(selected_end + timedelta(days=1), time.min),
            )
            return {
                "device_id": device_id, "start_date": selected_start.isoformat(), "end_date": selected_end.isoformat(),
                "recorded_days": len(records),
                "condition_counts": {key: sum(item.condition == key for item in records) for key in CONDITION_OPTIONS},
                "symptom_counts": {key: sum(key in json.loads(item.symptoms) for item in records) for key in SYMPTOM_OPTIONS},
                "activity_counts": {key: sum(key in json.loads(item.activities) for item in records) for key in ACTIVITY_OPTIONS},
                "usage_summary": statistics["summary"], "daily": statistics["daily"],
            }

    @app.get("/daily-records/{recorded_on}")
    def get_daily_record(recorded_on: date, device_id: str, authorization: str | None = Header(default=None)):
        with SessionLocal() as db:
            user, _ = backend.require_owned_device(db, authorization, device_id)
            record = db.query(DailyStatusRecord).filter_by(user_id=user.id, device_id=device_id, recorded_on=recorded_on).first()
            return {"record": serialize_daily_status(record) if record else None}

    @app.put("/daily-records/{recorded_on}")
    def save_daily_record(recorded_on: date, record_input: DailyStatusInput, device_id: str, authorization: str | None = Header(default=None)):
        if recorded_on > backend.datetime.now().date():
            raise HTTPException(422, "미래 날짜의 상태는 기록할 수 없습니다.")
        with SessionLocal() as db:
            user, _ = backend.require_owned_device(db, authorization, device_id)
            record = db.query(DailyStatusRecord).filter_by(user_id=user.id, device_id=device_id, recorded_on=recorded_on).first()
            now = backend.datetime.now()
            if record is None:
                record = DailyStatusRecord(user_id=user.id, device_id=device_id, recorded_on=recorded_on, created_at=now)
                db.add(record)
            record.condition = record_input.condition
            record.symptoms = json.dumps(record_input.symptoms)
            record.activities = json.dumps(record_input.activities)
            record.note = record_input.note
            record.updated_at = now
            db.commit()
            return serialize_daily_status(record)

    @app.delete("/daily-records/{recorded_on}")
    def delete_daily_record(recorded_on: date, device_id: str, authorization: str | None = Header(default=None)):
        with SessionLocal() as db:
            user, _ = backend.require_owned_device(db, authorization, device_id)
            record = db.query(DailyStatusRecord).filter_by(user_id=user.id, device_id=device_id, recorded_on=recorded_on).first()
            if record is None:
                raise HTTPException(404, "상태 기록을 찾을 수 없습니다.")
            db.delete(record)
            db.commit()
            return {"message": "상태 기록 삭제 완료"}

    @app.get("/settings/notifications")
    def get_notifications(authorization: str | None = Header(default=None)):
        with SessionLocal() as db:
            user = backend.get_authenticated_user(db, authorization)
            return get_notification_preferences(db, user.id)

    @app.put("/settings/notifications")
    def save_notifications(settings: NotificationInput, authorization: str | None = Header(default=None)):
        with SessionLocal() as db:
            user = backend.get_authenticated_user(db, authorization)
            preferences = db.get(NotificationPreferences, user.id)
            if preferences is None:
                preferences = NotificationPreferences(user_id=user.id)
                db.add(preferences)
            preferences.wear_recommendation_enabled = int(settings.wear_recommendation_enabled)
            preferences.overuse_enabled = int(settings.overuse_enabled)
            db.commit()
            return get_notification_preferences(db, user.id)

    @app.patch("/settings/rom")
    def patch_rom_settings(settings: RomSettingsPatchInput, device_id: str, authorization: str | None = Header(default=None)):
        with SessionLocal() as db:
            backend.require_owned_device(db, authorization, device_id)
            current = backend.get_or_create_settings(db, device_id)
            vibration = backend.get_or_create_vibration_setting(db, device_id)
            values = {
                "warning_angle": current.warning_angle, "limit_angle": current.limit_angle,
                "vibration_strength": current.vibration_strength,
                "target_wear_minutes": current.target_wear_minutes,
                "vibration_duration_ms": vibration.duration_ms,
            }
        changes = settings.model_dump(exclude_unset=True)
        values.update(changes)
        if "limit_angle" in changes:
            values["warning_angle"] = changes["limit_angle"] - 5
        return backend.update_rom_settings(backend.RomSettingsInput(**values), device_id, authorization)

    @app.post("/settings/rom/{command_id}/application")
    def report_direct_application(command_id: int, result: AppSettingsResultInput, authorization: str | None = Header(default=None)):
        with SessionLocal() as db:
            command = db.get(backend.DeviceCommand, command_id)
            if command is None or command.command_type != "ROM_SETTINGS":
                raise HTTPException(404, "ROM 설정을 찾을 수 없습니다.")
            user, _ = backend.require_owned_device(db, authorization, command.device_id)
            latest = db.query(backend.DeviceCommand).filter_by(device_id=command.device_id, command_type="ROM_SETTINGS").order_by(backend.DeviceCommand.id.desc()).first()
            if latest.id != command.id or command.status == "SUPERSEDED":
                raise HTTPException(409, "새 설정이 있습니다. 최신 설정을 다시 전달해 주세요.")
            if command.status in ("ACKNOWLEDGED", "APP_REPORTED_APPLIED"):
                return {"command_id": command.id, "hardware_sync": backend.get_rom_sync_info(db, command.device_id)}
            if command.status not in ("APP_PENDING", "APP_FAILED"):
                raise HTTPException(409, "앱 직접 전달용 설정이 아닙니다.")
            receipt = db.get(AppSettingsReceipt, command.id)
            if receipt is None:
                receipt = AppSettingsReceipt(command_id=command.id, user_id=user.id)
                db.add(receipt)
            receipt.success = int(result.success)
            receipt.error_message = result.error_message if not result.success else None
            receipt.reported_at = backend.datetime.now()
            command.status = "APP_REPORTED_APPLIED" if result.success else "APP_FAILED"
            db.commit()
            return {"command_id": command.id, "hardware_sync": backend.get_rom_sync_info(db, command.device_id)}

    return {
        "get_hand_settings": get_hand_settings, "save_hand_settings": save_hand_settings,
        "get_daily_record_options": get_daily_record_options, "list_daily_records": list_daily_records,
        "analyze_daily_records": analyze_daily_records,
        "get_daily_record": get_daily_record, "save_daily_record": save_daily_record,
        "delete_daily_record": delete_daily_record,
        "get_notifications": get_notifications, "save_notifications": save_notifications,
        "report_direct_application": report_direct_application,
        "patch_rom_settings": patch_rom_settings,
    }
