# 영상 시안 프론트 연동

모든 사용자 API에 `Authorization: Bearer <access_token>`을 보냅니다. 기기 API는 `X-Device-Key`를 사용합니다. 데이터가 없는 경우 각도를 `0`으로 꾸미지 말고 `null` 또는 빈 기록을 그대로 처리해 `--°`, '기록 없음'을 표시하세요.

## 화면별 연결

| 화면 | API | 사용하는 값 |
| --- | --- | --- |
| 홈 | `GET /dashboard/overview?device_id=...` | `realtime`, `today`, `hand_settings`, `status_record` |
| 왼손/오른손·손가락 선택 | `GET`, `PUT /settings/hand?device_id=...` | `hand`, `fingers` |
| 오늘 상태 기록 | `GET`, `PUT`, `DELETE /daily-records/2026-11-06?device_id=...` | `condition`, `symptoms`, `activities`, `note` |
| 기록 선택지 | `GET /daily-records/options` | 서버의 코드와 한국어 라벨 |
| 기록 목록 | `GET /daily-records?device_id=...&start_date=2026-11-01&end_date=2026-11-30` | 날짜별 상태 기록 |
| 상태·사용 패턴 분석 | `GET /daily-records/analysis?device_id=...` | 상태·증상·활동 분포, 사용 통계, 날짜별 기록. 기본 최근 30일 |
| 통신 | `GET /devices/{device_id}/status` | 최근 서버 통신 기준 `is_connected`, 배터리, `rom_settings_sync` |
| 하루 리포트 | `GET /dashboard/daily?device_id=...&target_date=2026-11-06` | 착용 시간·과굴곡·최대 초과 각도·목표 달성·상태 기록 |
| 시간대 그래프 | `GET /dashboard/overflexion/hourly?device_id=...&target_date=2026-11-06` | 24시간 데이터. 영상의 3시간 눈금은 프론트에서 합산 |
| 주간 | `GET /dashboard/weekly?device_id=...&end_date=2026-11-06` | 기준일 포함 7일의 `daily`와 `summary` |
| 월간 캘린더 | `GET /dashboard/monthly?device_id=...&year=2026&month=11` | 날짜별 `is_worn`, `has_status_record`, `status_record` |
| 알림 설정 | `GET`, `PUT /settings/notifications` | 두 토글과 서버 알림 조건 |
| 알림 이력 | `GET /alerts?device_id=...` | 알림 목록·읽음 여부 |
| 기기 설정 | `GET`, `PATCH /settings/rom?device_id=...` | 허용 ROM·진동·목표 착용 시간 |

새 기능 적용 후 서버를 재시작하면 필요한 새 테이블이 생성됩니다. 기존 테이블·측정 기록은 삭제하지 않습니다.

## 초기 손 설정

```json
{"hand": "RIGHT", "fingers": [2, 4]}
```

`hand`는 `LEFT` 또는 `RIGHT`, `fingers`는 화면의 1~5 번호를 그대로 사용합니다. 적어도 하나를 선택해야 하고 중복 번호는 허용하지 않습니다. 기기별로 저장하며, 다시 PUT하면 초기 설정을 수정합니다. 처음 GET하면 `is_configured: false`, `hand: null`, `fingers: []`입니다.

## 오늘 상태 저장·수정

`PUT /daily-records/2026-11-06?device_id=...`

```json
{
  "condition": "NORMAL",
  "symptoms": ["STIFFNESS", "SWELLING"],
  "activities": ["TYPING", "EXERCISE"],
  "note": "가상 시연용 상태 기록"
}
```

- 상태: `GOOD`(좋음), `NORMAL`(보통), `UNCOMFORTABLE`(불편), `SEVERE`(심함), `VERY_SEVERE`(매우 심함).
- 증상: `PAIN`, `STIFFNESS`, `SWELLING`, `NUMBNESS`, `OTHER`, `NONE`. 복수 선택이 가능하며 `NONE`은 단독으로만 선택합니다.
- 활동: `TYPING`, `HOUSEWORK`, `EXERCISE`, `OTHER`. 복수 선택 또는 빈 배열이 가능합니다.
- 메모: 최대 1,000자. 빈 문자열이면 메모를 지웁니다.

같은 사용자·기기·날짜의 PUT은 같은 기록을 수정합니다. GET 응답은 `{"record": {...}}`이며 기록이 없으면 `{"record": null}`입니다. 미래 상태 저장은 422입니다. 다른 사용자의 기기 데이터에는 접근할 수 없습니다.

월간 `daily[].is_worn`은 측정·착용 기록 여부, `has_status_record`는 사용자가 상태를 작성했는지를 나타냅니다. 상태만 작성해도 착용한 날로 표시하지 않습니다. 캘린더에서 날짜를 선택하면 해당 날짜의 `status_record`를 보여주고 PUT으로 수정합니다. 현재 월 데이터는 오늘까지만 반환하므로 미래 날짜 셀은 프론트에서 그립니다.

`/symptoms`는 이전 단일 증상·신체 부위 기록 API입니다. 새 화면은 `/daily-records`를 사용하며, 두 종류의 기록을 자동 병합하지 않습니다.

## 알림 설정

`PUT /settings/notifications`

```json
{"wear_recommendation_enabled": true, "overuse_enabled": false}
```

설정은 사용자별로 저장합니다. 착용 권장 토글을 끄면 권장 알림을 생성하지 않습니다. 과사용 토글을 끄면 각도·과굴곡 앱 알림 이력을 생성하지 않습니다. 측정·과굴곡 통계 및 기기 진동 로직은 계속 유지되며 기존 알림도 보존합니다.

확정 조건은 미착용 60분 후, 하루 최대 5회이며 과굴곡은 최근 60분 접촉 시작 10회 기준입니다. 응답의 `wear_reminder_after_minutes`, `max_wear_reminders_per_day`, `overflexion_window_minutes`, `overflexion_contact_threshold`로 문구를 표시하세요. 영상의 '2시간', '5회' 고정 문구는 이 값으로 변경해야 합니다. `contact_count`는 접촉 횟수이고 `overflexion_count`는 기준 도달로 생성된 과굴곡 기록 수입니다.

실제 푸시 발송은 보류되어 있어 `push_delivery_available: false`입니다. 앱이 `/wear-recommendations/check`를 호출할 때 권장 여부를 평가하며, 백그라운드 자동 푸시를 보장하는 스케줄러는 아직 없습니다.

## ROM·진동 설정 직접 전달

`PATCH /settings/rom?device_id=...`

```json
{"limit_angle": 30, "vibration_duration_ms": 5000, "target_wear_minutes": 240}
```

PATCH에서 `limit_angle`은 영상 슬라이더의 15/30/45/60/75/90도 중 하나입니다. ROM을 바꾸면 진동 시작 기준인 `warning_angle`을 ROM보다 5도 작은 값으로 계산합니다. 진동 지속 시간은 밀리초이므로 영상의 3/5/7초는 3000/5000/7000입니다. 부분 수정하지 않은 강도·목표 시간·ROM은 유지합니다. 하루 착용 목표는 분 단위이므로 4시간은 240입니다.

응답:

```json
{
  "command_id": 42,
  "delivery_mode": "APP_DIRECT",
  "hardware_payload": {
    "warning_angle": 25,
    "limit_angle": 30,
    "vibration_strength": 70,
    "vibration_duration_ms": 5000,
    "target_wear_minutes": 240
  }
}
```

실제 값은 저장된 설정에 따라 달라집니다. 앱은 이 값을 실제 하드웨어 통신 규격에 맞게 변환해 직접 전송해야 합니다. 블루투스 특성 UUID·Wi-Fi 장치 주소·펌웨어 명령 형식은 앱/기기 쪽에서 맞춰야 합니다.

하드웨어의 적용 응답을 받으면 `POST /settings/rom/42/application`에 `{"success": true}`를 보냅니다. 전송 실패 시 `{"success": false, "error_message": "기기 응답 없음"}`을 보냅니다.

상태는 `APP_PENDING` → `APP_REPORTED_APPLIED` 또는 `APP_FAILED`입니다. 앱 보고는 `device_verified: false`이고, 기기가 인증키로 기존 `/devices/{device_id}/commands/{command_id}/ack`를 보내 확인하면 `SYNCED`, `device_verified: true`가 됩니다. 이전 설정의 적용 결과는 409로 거부하므로 최신 설정을 다시 전달하세요. 앱 직접 전달용 ROM은 기기 폴링 API에서 반환하지 않습니다.

기존 개발용 폴링은 전체 `PUT /settings/rom`에서 `delivery_mode: "SERVER_POLL"`을 명시하면 사용할 수 있습니다. PUT 기본값도 이제 `APP_DIRECT`입니다.

## 저장 시점과 통신 표시

홈의 `today.has_yesterday_data`가 false면 '어제 기록 없음'을 표시하고, true면 `overflexion_change_from_yesterday`를 사용해 비교합니다. 휴대폰 자체 Wi-Fi 상태는 앱에서 확인하고, 서버의 `is_connected`는 기기의 최근 서버 통신 여부를 표시하는 데 사용하세요.

대시보드는 조회할 때 최신 측정·상태 기록을 집계합니다. 저장 후 화면을 다시 조회해야 합니다. 이미 발행한 `/reports/{id}`는 저장된 리포트이므로, 수정된 상태까지 포함하려면 새로 발행하세요. 실제 하드웨어 전송과 진동은 실기기 연결 검증이 필요합니다.
