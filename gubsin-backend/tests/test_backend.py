import asyncio
import json
import os
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_DIRECTORY = tempfile.mkdtemp(prefix="gubsin-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(TEMP_DIRECTORY) / 'test.db'}"
sys.path.insert(0, str(PROJECT_ROOT))

import main  # noqa: E402


def request_json(method, path, *, authorization=None, body=None):
    """Exercise HTTP routing, validation and auth without extra test dependencies."""
    path, _, query = path.partition("?")
    headers = [(b"content-type", b"application/json")]
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    payload = json.dumps(body).encode() if body is not None else b""
    messages = []

    async def run():
        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        async def send(message):
            messages.append(message)

        await main.app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": query.encode(),
            "headers": headers, "client": ("127.0.0.1", 1234), "server": ("test", 80),
            "root_path": "",
        }, receive, send)

    asyncio.run(run())
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    data = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(data)


class DemoClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 6, 8, 0, 0)


class BackendFlowTest(unittest.TestCase):
    def create_user_and_device(self):
        unique = uuid.uuid4().hex
        registration = main.register_user(
            main.UserRegisterInput(
                name="테스트 사용자",
                email=f"user-{unique}@example.com",
                password="password123",
            )
        )
        authorization = f"Bearer {registration['access_token']}"
        device_id = f"TEST-{unique[:8]}"
        device = main.connect_device(
            main.DeviceConnectInput(device_id=device_id, device_name="테스트 보호대"),
            authorization,
        )
        return authorization, device_id, device["device_api_key"]

    def test_rom_command_is_acknowledged_by_device(self):
        authorization, device_id, device_key = self.create_user_and_device()
        main.update_rom_settings(
            main.RomSettingsInput(
                warning_angle=50,
                limit_angle=65,
                vibration_strength=80,
                vibration_duration_ms=1500,
                target_wear_minutes=120,
                delivery_mode="SERVER_POLL",
            ),
            device_id,
            authorization,
        )

        command = main.get_next_device_command(device_id, device_key)["command"]
        self.assertEqual(command["type"], "ROM_SETTINGS")
        self.assertEqual(command["payload"]["vibration_duration_ms"], 1500)
        main.acknowledge_device_command(device_id, command["id"], device_key)

        settings = main.get_rom_settings(device_id, authorization)
        self.assertEqual(settings["hardware_sync"]["status"], "SYNCED")

    def test_contact_threshold_and_hourly_statistics(self):
        authorization, device_id, device_key = self.create_user_and_device()
        warning = main.receive_sensor_data(
            main.SensorReading(device_id=device_id, angle=60, battery=90),
            device_key,
        )
        self.assertEqual(warning["excess_angle"], 5)

        for _ in range(10):
            main.receive_contact_event(
                main.ContactEventInput(device_id=device_id),
                device_key,
            )

        hourly = main.get_hourly_overflexion_statistics(
            device_id,
            None,
            authorization,
        )
        self.assertEqual(
            sum(item["overflexion_count"] for item in hourly["hourly"]),
            1,
        )

    def test_symptom_analysis_and_daily_report(self):
        authorization, device_id, device_key = self.create_user_and_device()
        main.receive_sensor_data(
            main.SensorReading(device_id=device_id, angle=30, battery=90),
            device_key,
        )
        main.create_symptom_record(
            main.SymptomRecordInput(
                device_id=device_id,
                symptom_type="PAIN",
                body_area="NECK",
                severity=4,
                note="테스트 기록",
            ),
            authorization,
        )

        analysis = main.analyze_symptoms(device_id, None, None, authorization)
        self.assertEqual(analysis["record_count"], 1)
        self.assertEqual(analysis["high_severity_count"], 1)

        report = main.issue_daily_report(device_id, None, authorization)
        self.assertEqual(report["report_type"], "DAILY")

    @patch.object(main, "datetime", DemoClock)
    def test_demo_reports_are_complete_and_repeatable(self):
        authorization, device_id, _ = self.create_user_and_device()
        first = main.seed_demo_history(main.DemoSeedInput(days=37), device_id, authorization)
        weekly = main.get_report(first["weekly_report_id"], authorization)
        monthly = main.get_report(first["previous_month_report_id"], authorization)
        self.assertEqual(len(weekly["content"]["daily"]), 7)
        self.assertEqual(weekly["content"]["summary"]["total_readings"], 28)
        self.assertEqual(len(monthly["content"]["daily"]), 31)
        self.assertEqual(monthly["content"]["summary"]["total_readings"], 124)
        self.assertTrue(monthly["content"]["is_demo"])
        self.assertEqual(first["created_days"], 37)
        second = main.seed_demo_history(main.DemoSeedInput(days=37), device_id, authorization)
        self.assertEqual(second["created_days"], 0)
        self.assertEqual(second["reading_count"], 0)
        self.assertEqual(second["weekly_report_id"], first["weekly_report_id"])
        with main.SessionLocal() as db:
            latest = db.query(main.SensorData).filter_by(device_id=device_id).order_by(
                main.SensorData.measured_at.desc()
            ).first()
            self.assertLessEqual(latest.measured_at, DemoClock.now())

    @patch.object(main, "datetime", DemoClock)
    def test_live_angle_updates_today_and_reports_without_touching_other_days(self):
        authorization, device_id, key = self.create_user_and_device()
        main.seed_demo_history(main.DemoSeedInput(days=7), device_id, authorization)
        before = main.get_daily_summary(device_id, authorization)
        yesterday = DemoClock.now().date() - timedelta(days=1)
        yesterday_before = main.get_sensor_history(device_id, 200, None, authorization, yesterday)
        main.receive_sensor_data(main.SensorReading(device_id=device_id, angle=72, battery=89), key)
        after = main.get_daily_summary(device_id, authorization)
        self.assertEqual(after["total_readings"], before["total_readings"] + 1)
        self.assertTrue(any(row["angle"] == 72 for row in after["measurements"]))
        self.assertEqual(main.get_sensor_history(device_id, 200, None, authorization, yesterday), yesterday_before)
        self.assertEqual(main.get_weekly_statistics(device_id, None, authorization)["summary"]["total_readings"], 29)
        self.assertEqual(main.get_monthly_statistics(device_id, None, None, authorization)["summary"]["total_readings"], 25)
        issued = main.issue_daily_report(device_id, None, authorization)
        self.assertEqual(issued["content"]["summary"]["total_readings"], after["total_readings"])

    @patch.object(main, "datetime", DemoClock)
    def test_seed_preserves_days_with_real_measurements(self):
        authorization, device_id, key = self.create_user_and_device()
        main.receive_sensor_data(main.SensorReading(device_id=device_id, angle=41, battery=89), key)
        seeded = main.seed_demo_history(main.DemoSeedInput(days=7), device_id, authorization)
        self.assertEqual(seeded["created_days"], 6)
        self.assertEqual(main.get_daily_summary(device_id, authorization)["total_readings"], 1)

    def test_hand_selection_persists_and_requires_ownership(self):
        auth, device, _ = self.create_user_and_device()
        path = f"/settings/hand?device_id={device}"
        self.assertEqual(request_json("GET", path)[0], 401)
        self.assertFalse(request_json("GET", path, authorization=auth)[1]["is_configured"])
        status, saved = request_json("PUT", path, authorization=auth, body={"hand": "RIGHT", "fingers": [4, 2]})
        self.assertEqual(status, 200)
        self.assertEqual(saved["fingers"], [2, 4])
        self.assertEqual(request_json("GET", path, authorization=auth)[1]["hand"], "RIGHT")
        self.assertEqual(request_json("PUT", path, authorization=auth, body={"hand": "LEFT", "fingers": [6]})[0], 422)
        self.assertEqual(request_json("PUT", path, authorization=auth, body={"hand": "LEFT", "fingers": [2, 2]})[0], 422)
        other_auth, _, _ = self.create_user_and_device()
        self.assertEqual(request_json("GET", path, authorization=other_auth)[0], 403)

    def test_daily_status_matches_video_and_calendar(self):
        auth, device, _ = self.create_user_and_device()
        today = main.datetime.now().date().isoformat()
        path = f"/daily-records/{today}?device_id={device}"
        data = {"condition": "NORMAL", "symptoms": ["STIFFNESS", "SWELLING"], "activities": ["TYPING", "EXERCISE"], "note": "가" * 1000}
        self.assertIsNone(request_json("GET", path, authorization=auth)[1]["record"])
        status, saved = request_json("PUT", path, authorization=auth, body=data)
        self.assertEqual(status, 200)
        self.assertEqual(saved["symptoms"], data["symptoms"])
        self.assertEqual(len(saved["note"]), 1000)
        analysis = request_json("GET", f"/daily-records/analysis?device_id={device}", authorization=auth)
        self.assertEqual(analysis[0], 200)
        self.assertEqual(analysis[1]["symptom_counts"]["SWELLING"], 1)
        self.assertEqual(analysis[1]["activity_counts"]["EXERCISE"], 1)
        updated = request_json("PUT", path, authorization=auth, body={**data, "condition": "GOOD", "symptoms": ["NONE"]})[1]
        self.assertEqual(updated["id"], saved["id"])
        monthly = main.get_monthly_statistics(device, None, None, auth)
        self.assertEqual(monthly["daily"][-1]["status_record"]["condition"], "GOOD")
        self.assertTrue(monthly["daily"][-1]["has_status_record"])
        self.assertFalse(monthly["daily"][-1]["is_worn"])
        self.assertEqual(main.get_dashboard_overview(device, auth)["status_record"]["id"], saved["id"])
        self.assertEqual(main.get_daily_summary(device, auth)["status_record"]["id"], saved["id"])
        daily_report = main.issue_daily_report(device, None, auth)
        self.assertEqual(daily_report["content"]["daily"][0]["status_record"]["symptoms"], ["NONE"])
        self.assertEqual(request_json("PUT", path, authorization=auth, body={**data, "symptoms": ["NONE", "PAIN"]})[0], 422)
        self.assertEqual(request_json("PUT", path, authorization=auth, body={**data, "note": "가" * 1001})[0], 422)
        other_auth, _, _ = self.create_user_and_device()
        self.assertEqual(request_json("DELETE", path, authorization=other_auth)[0], 403)
        self.assertEqual(request_json("DELETE", path, authorization=auth)[0], 200)
        self.assertIsNone(request_json("GET", path, authorization=auth)[1]["record"])

    def test_notification_preferences_suppress_alerts_but_keep_measurements(self):
        auth, device, key = self.create_user_and_device()
        defaults = request_json("GET", "/settings/notifications", authorization=auth)[1]
        self.assertEqual(defaults["wear_reminder_after_minutes"], 60)
        self.assertEqual(defaults["overflexion_contact_threshold"], 10)
        self.assertEqual(defaults["max_wear_reminders_per_day"], 5)
        self.assertEqual(request_json("PUT", "/settings/notifications", authorization=auth, body={"wear_recommendation_enabled": False, "overuse_enabled": False})[0], 200)
        self.assertEqual(main.check_wear_recommendation(device, auth)["reason"], "DISABLED")
        result = main.receive_sensor_data(main.SensorReading(device_id=device, angle=75, battery=80), key)
        self.assertFalse(result["alert_created"])
        for _ in range(10):
            main.receive_contact_event(main.ContactEventInput(device_id=device), key)
        with main.SessionLocal() as db:
            self.assertEqual(db.query(main.AlertHistory).filter_by(device_id=device).count(), 0)
            self.assertEqual(db.query(main.OverflexionEvent).filter_by(device_id=device).count(), 1)
        self.assertEqual(main.get_daily_summary(device, auth)["total_readings"], 1)
        request_json("PUT", "/settings/notifications", authorization=auth, body={"wear_recommendation_enabled": True, "overuse_enabled": True})
        result = main.receive_sensor_data(main.SensorReading(device_id=device, angle=75, battery=80), key)
        self.assertTrue(result["alert_created"])

    def test_direct_rom_application_and_stale_result(self):
        auth, device, key = self.create_user_and_device()
        rom = {"warning_angle": 25, "limit_angle": 30, "vibration_strength": 70, "vibration_duration_ms": 7000, "target_wear_minutes": 240}
        status, saved = request_json("PUT", f"/settings/rom?device_id={device}", authorization=auth, body=rom)
        self.assertEqual(status, 200)
        self.assertEqual(saved["delivery_mode"], "APP_DIRECT")
        self.assertEqual(saved["hardware_payload"]["vibration_duration_ms"], 7000)
        self.assertIsNone(main.get_next_device_command(device, key)["command"])
        path = f"/settings/rom/{saved['command_id']}/application"
        failed = request_json("POST", path, authorization=auth, body={"success": False, "error_message": "기기 응답 없음"})[1]
        self.assertEqual(failed["hardware_sync"]["status"], "APP_FAILED")
        applied = request_json("POST", path, authorization=auth, body={"success": True})[1]
        self.assertEqual(applied["hardware_sync"]["status"], "APP_REPORTED_APPLIED")
        self.assertFalse(applied["hardware_sync"]["device_verified"])
        main.acknowledge_device_command(device, saved["command_id"], key)
        self.assertTrue(main.get_rom_settings(device, auth)["hardware_sync"]["device_verified"])
        newer = request_json("PUT", f"/settings/rom?device_id={device}", authorization=auth, body={**rom, "limit_angle": 45})[1]
        self.assertNotEqual(newer["command_id"], saved["command_id"])
        self.assertEqual(request_json("POST", path, authorization=auth, body={"success": True})[0], 409)
        with self.assertRaises(main.HTTPException) as stale_ack:
            main.acknowledge_device_command(device, saved["command_id"], key)
        self.assertEqual(stale_ack.exception.status_code, 409)
        other_auth, _, _ = self.create_user_and_device()
        self.assertEqual(request_json("POST", f"/settings/rom/{newer['command_id']}/application", authorization=other_auth, body={"success": True})[0], 403)

    def test_video_rom_slider_partial_update(self):
        auth, device, _ = self.create_user_and_device()
        status, result = request_json("PATCH", f"/settings/rom?device_id={device}", authorization=auth, body={"limit_angle": 15, "vibration_duration_ms": 5000, "target_wear_minutes": 240})
        self.assertEqual(status, 200)
        self.assertEqual(result["hardware_payload"]["warning_angle"], 10)
        self.assertEqual(result["hardware_payload"]["limit_angle"], 15)
        self.assertEqual(result["delivery_mode"], "APP_DIRECT")
        request_json("PATCH", f"/settings/rom?device_id={device}", authorization=auth, body={"vibration_duration_ms": 7000})
        current = main.get_rom_settings(device, auth)
        self.assertEqual(current["limit_angle"], 15)
        self.assertEqual(current["target_wear_minutes"], 240)
        self.assertEqual(current["vibration_duration_ms"], 7000)
        self.assertEqual(request_json("PATCH", f"/settings/rom?device_id={device}", authorization=auth, body={"limit_angle": None})[0], 422)
        self.assertEqual(request_json("PATCH", f"/settings/rom?device_id={device}", authorization=auth, body={"limit_angle": 17})[0], 422)

    @patch.object(main, "datetime", DemoClock)
    def test_cross_midnight_wear_is_consistent_across_screens(self):
        auth, device, _ = self.create_user_and_device()
        with main.SessionLocal() as db:
            db.add(main.WearSession(
                device_id=device, started_at=datetime(2026, 11, 5, 23, 50),
                last_sensor_at=datetime(2026, 11, 6, 0, 10), ended_at=datetime(2026, 11, 6, 0, 10),
                duration_seconds=1200, status="COMPLETED",
            ))
            db.commit()
        self.assertEqual(main.get_daily_summary(device, auth)["wear_minutes"], 10)
        self.assertEqual(main.get_dashboard_overview(device, auth)["today"]["wear_minutes"], 10)
        self.assertEqual(main.get_today_wear_summary(device, auth)["wear_seconds"], 600)


if __name__ == "__main__":
    unittest.main()
