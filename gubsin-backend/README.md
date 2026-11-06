# 굽신굽신 백엔드

FastAPI 기반 자세 보조기 백엔드입니다. 앱 사용자는 로그인 후 자신의 기기를 연결하고, 아두이노는 기기 인증키로 센서·접촉 이벤트를 전송합니다.

## 실행

Python 3.14 기준입니다. 압축을 푼 프로젝트 폴더에서 먼저 가상환경과 라이브러리를 설치합니다.

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

macOS / Linux:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Docker를 사용하는 경우에는 아래 명령으로 실행합니다.

```powershell
docker compose up --build
```

Docker 실행 시 SQLite 데이터는 `data/gubsin.db`에 유지됩니다.

API 문서는 서버 실행 후 `http://127.0.0.1:8000/docs`에서 확인할 수 있습니다.

다른 컴퓨터나 휴대폰에서 연결할 때는 같은 네트워크에서 서버 PC의 IP를 사용하세요. 예를 들어 `http://192.168.0.15:8000`입니다. 프론트 주소를 CORS 허용 목록에 설정하고, 개발 서버 포트의 로컬 방화벽 허용 여부도 확인하세요.

기본 DB는 프로젝트 폴더의 SQLite(`gubsin.db`)입니다. 배포 시에는 `DATABASE_URL` 환경 변수로 PostgreSQL 등의 DB 주소를 지정할 수 있습니다.

환경변수 예시는 [`.env.example`](.env.example)에 있습니다. 값은 서버 실행 환경에 설정해 사용합니다.

`.env` 파일은 자동으로 읽지 않습니다. 셸 환경변수로 지정하거나, `.env.example`을 복사해 값을 채운 뒤 `python -m uvicorn main:app --env-file .env --host 0.0.0.0 --port 8000`으로 실행하세요.

## 테스트

가상환경에 라이브러리를 설치한 뒤 프로젝트 폴더에서 실행합니다.

```sh
python -m unittest discover -s tests -v
```

테스트는 별도 임시 SQLite DB를 사용합니다. 앱에 사용하는 DB를 수정하지 않습니다.

## GitHub 업로드

압축을 푼 `gubsin-backend` 폴더의 파일을 저장소에 업로드하세요. 숨김 파일인 `.gitignore`, `.dockerignore`, `.env.example`도 포함합니다. 새 저장소에는 DB·계정·측정값이 포함되지 않으며 최초 서버 실행 시 DB 테이블이 생성됩니다.

실제 DB와 백업, 비밀 환경설정, 가상환경은 `.gitignore`로 제외합니다. 가상 측정 데이터와 리포트는 아래 안내대로 `python setup_demo.py`를 실행해 새로 만들 수 있습니다. 데모 계정 비밀번호는 실행 시 생성되며 저장소에는 포함하지 않습니다.

## 앱 인증

1. `POST /auth/register` 또는 `POST /auth/login`으로 토큰을 받습니다.
2. 앱 요청에는 `Authorization: Bearer <access_token>` 헤더를 보냅니다.
3. `POST /devices/connect`로 기기를 연결합니다.

기기를 처음 연결하면 응답의 `device_api_key`가 한 번만 표시됩니다. 이 값을 아두이노에 저장해야 합니다.

## 아두이노 인증

아두이노는 다음 헤더를 포함합니다.

```text
X-Device-Key: <device_api_key>
```

- 센서 데이터: `POST /sensor/readings`
- 아랫판 접촉 시작: `POST /sensor/contact-events`
- 연결 상태 유지: `POST /devices/{device_id}/heartbeat?battery=...`
- 대기 명령 수신: `GET /devices/{device_id}/commands/next`
- 명령 적용 확인: `POST /devices/{device_id}/commands/{command_id}/ack`

ROM·진동 설정은 기본적으로 앱 직접 전달 방식입니다. `PUT` 또는 `PATCH /settings/rom` 응답의 `hardware_payload`를 앱에서 하드웨어로 보내고, 적용 응답을 받은 뒤 서버에 결과를 기록합니다. 기기 폴링 개발용 경로는 `PUT /settings/rom`에 `delivery_mode: "SERVER_POLL"`을 명시하면 사용할 수 있습니다. 과굴곡 진동 명령 대기열도 기존 기기 개발용으로 유지합니다.

앱은 `GET /devices/{device_id}/status`로 기기 연결 상태·배터리·대기 명령 수를 확인합니다. 앱이 보고한 적용 상태는 `APP_REPORTED_APPLIED`, 기기 인증키로 적용을 확인한 상태는 `SYNCED`입니다. `device_verified`로 두 상태를 구분합니다.

## 프론트 연동

영상 시안에 맞춘 손·손가락 선택, 날짜별 상태 기록, 알림 토글, 직접 ROM 전달 예시는 [UI_API.md](UI_API.md)를 참고하세요. 기존 `/symptoms` API는 호환용으로 유지되며, 영상의 '오늘 기록 저장'은 `/daily-records/{날짜}`에 연결합니다.

기본 허용 주소는 `http://localhost:3000`, `http://localhost:5173`입니다. 다른 프론트 주소는 실행 전 `FRONTEND_ORIGINS` 환경 변수에 쉼표로 구분해 지정합니다.

대시보드 첫 화면에는 `GET /dashboard/overview?device_id=...`를 사용하면 실시간 상태, 오늘 착용 현황, 과굴곡 수, 미확인 알림 수를 한 번에 받을 수 있습니다.

주간·월간 리포트는 각각 `POST /reports/weekly`, `POST /reports/monthly`로 발행합니다. 발행된 리포트 목록은 `GET /reports`, 개별 스냅샷은 `GET /reports/{report_id}`에서 조회합니다.

일간 리포트는 `POST /reports/daily`로 발행합니다. 시간대별 과굴곡·접촉·초과 각도 데이터는 `GET /dashboard/overflexion/hourly`에서 조회합니다.

ROM 설정에는 진동 강도와 `vibration_duration_ms`(100~10,000ms)를 함께 지정합니다. 앱 푸시 토큰은 `POST /push-tokens`로 등록하며, 실제 FCM/APNs 발송 연동은 발송 서비스 결정 후 연결합니다.

## 가상 사용 기록과 리포트

로컬 시연 계정은 `demo@gubsin.example`, 기기는 `GUBSIN-DEMO-001`입니다. 비밀번호는 최초 `python setup_demo.py` 실행 결과에 표시됩니다. 기존 계정으로 다시 실행하면 비밀번호는 변경되지 않습니다. 실행 전 기존 `gubsin.db`는 타임스탬프가 붙은 백업 파일로 보존됩니다.

생성되는 기록은 최근 30일 이상(지난달 1일부터 오늘까지 포함)의 가상 각도·배터리·착용 세션·접촉·과굴곡 데이터입니다. 최근 7일, 이번 달 오늘까지, 지난달 전체 리포트도 함께 발행합니다. 데모 리포트의 `content.is_demo`는 `true`입니다.

다시 실행하면 이미 생성한 날짜는 건너뛰며, 같은 기간의 데모 리포트만 갱신합니다. 기존 측정 기록이 있는 날짜도 건너뜁니다. 실제 데이터를 사용하는 기기와 구분하여 시연용 기기를 사용하세요.

로그인 후 아래 API를 호출하면 그래프와 캘린더에 사용할 데이터를 받을 수 있습니다.

```text
GET /dashboard/weekly?device_id=GUBSIN-DEMO-001
GET /dashboard/monthly?device_id=GUBSIN-DEMO-001
GET /reports?device_id=GUBSIN-DEMO-001
GET /reports/{report_id}
```

다른 시연용 계정·기기에는 로그인 후 `POST /demo/seed-history?device_id=...`에 `{"days": 30, "issue_reports": true}`를 보내 생성할 수 있습니다. `days`는 7~93일입니다. 지난달 전체 리포트는 생성 범위가 지난달 1일을 포함할 때 함께 발행합니다.

## 오늘 실제 측정값 반영

인증된 기기의 `POST /sensor/readings` 요청은 서버 수신 시각으로 SQLite에 저장됩니다. 현재 개발 서버는 한국 시각을 사용합니다. 배포 서버에서도 같은 날짜 기준을 사용하도록 시스템 시간대를 `Asia/Seoul`로 설정해야 합니다.

- `GET /dashboard/daily?device_id=...`: 오늘 총 측정 횟수·상태 횟수·최대/평균 각도와 최신 20개 `measurements`를 반환합니다.
- `GET /sensor/readings?device_id=...&target_date=2026-11-06&limit=200`: 선택 날짜의 측정 이력만 반환합니다.
- 주간·월간 대시보드는 호출할 때마다 DB에서 집계하므로 새 측정값이 즉시 반영됩니다. 프론트에서는 측정 후 다시 조회하거나 주기적으로 새로고침하세요.
- 이미 발행한 `/reports/{report_id}`는 발행 시점의 저장된 리포트입니다. 새 측정값을 포함한 리포트는 다시 발행하면 됩니다.
