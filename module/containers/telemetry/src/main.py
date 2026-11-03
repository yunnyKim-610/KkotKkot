"""telemetry 컨테이너: ZoneStats → Supabase Edge Function(ingest-stats) → zone_stats 테이블

- 개인별 기록, 좌표, 영상은 받지도 보내지도 않는다. ZoneStats 외의 메시지는 버린다.
- 연결이 끊기면 /data/queue.jsonl 에 쌓아 두었다가 재전송한다.
- 기기 토큰은 이미지·저장소에 넣지 않고 기기별 환경변수(SUPABASE_URL, DEVICE_TOKEN)로 주입한다.
- service_role 키는 절대 기기에 두지 않는다. 기기는 Edge Function만 호출하고, 함수가 토큰을 검증한다.
"""
import json
import os
import urllib.request
from dataclasses import asdict

from shared.messages import ZoneStats

QUEUE = os.environ.get("QUEUE_FILE", "/data/queue.jsonl")
DEVICE_ID = os.environ.get("DEVICE_ID", "unknown-device")


def to_row(stats: ZoneStats) -> dict:
    d = asdict(stats)
    return {
        "device_id": DEVICE_ID,
        "zone": d["zone"],
        "period_start": d["period_start"],
        "period_end": d["period_end"],
        "observed_sec": d["observed_sec"],
        "bad_sec_by_reason": d["bad_sec_by_reason"],
        "alerts": d["alerts"],
    }


def post_rows(rows: list[dict]) -> bool:
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/functions/v1/ingest-stats"
    req = urllib.request.Request(url, data=json.dumps(rows).encode("utf-8"), method="POST", headers={
        "Content-Type": "application/json", "x-device-token": os.environ["DEVICE_TOKEN"]})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except OSError:
        return False


def main():
    # TODO: 소켓 서버 → ZoneStats 수신 → 큐에 쌓기 → 주기적으로 post_rows() 후 성공분 삭제
    raise NotImplementedError("telemetry 루프 구현 예정", QUEUE)


if __name__ == "__main__":
    main()
