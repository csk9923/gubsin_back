import json
import os
import random
import time
from urllib.request import Request, urlopen

API_URL = "http://127.0.0.1:8000/sensor/readings"
DEVICE_API_KEY = os.environ.get("DEVICE_API_KEY")

if not DEVICE_API_KEY:
    raise RuntimeError("DEVICE_API_KEY 환경 변수를 설정해 주세요.")

while True:
    angle = round(random.uniform(20, 75), 1)

    data = {
        "device_id": "GUBSIN-001",
        "angle": angle,
        "battery": random.randint(70, 100),
    }

    request = Request(
        API_URL,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Device-Key": DEVICE_API_KEY,
        },
        method="POST",
    )

    with urlopen(request) as response:
        result = json.loads(response.read().decode("utf-8"))

    print(f"각도: {angle}° / 상태: {result['status']}")
    time.sleep(2)
