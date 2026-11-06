"""Create a separate local demo account and reports, preserving real records."""

import json
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def main():
    # Snapshot the existing local SQLite DB before table creation or demo inserts.
    database_path = Path(__file__).resolve().parent / "gubsin.db"
    if database_path.exists():
        backup_path = database_path.with_name(
            f"gubsin.before-demo-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
        )
        with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as backup:
            source.backup(backup)
        print(f"Backup: {backup_path.name}")

    import main as backend

    email = "demo@gubsin.example"
    device_id = "GUBSIN-DEMO-001"
    with backend.SessionLocal() as db:
        user = db.query(backend.User).filter_by(email=email).first()
        device = db.query(backend.UserDevice).filter_by(device_id=device_id).first()
        if device is not None and (user is None or device.user_id != user.id):
            raise RuntimeError("Demo device is already linked to another account.")
        user_exists = user is not None

    password = None
    if not user_exists:
        password = secrets.token_urlsafe(18)
        registration = backend.register_user(backend.UserRegisterInput(
            name="가상 리포트 체험", email=email, password=password,
        ))
        authorization = f"Bearer {registration['access_token']}"
    else:
        with backend.SessionLocal() as db:
            user = db.query(backend.User).filter_by(email=email).one()
            token = backend.create_auth_token(db, user.id)
            db.commit()
            authorization = f"Bearer {token.token}"

    if device is None:
        backend.connect_device(backend.DeviceConnectInput(
            device_id=device_id, device_name="가상 데이터 시연용 보호대",
        ), authorization)

    today = datetime.now().date()
    previous_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    days = max(30, (today - previous_month_start).days + 1)
    result = backend.seed_demo_history(
        backend.DemoSeedInput(days=days), device_id, authorization,
    )
    print(json.dumps({
        "email": email,
        "password": password or "Existing password preserved",
        **result,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
