"""올림픽 아카이브 검색 백엔드 (FastAPI)."""
import json
import os
import sqlite3
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "olympics.db")
POSES_DIR = os.path.join(BASE_DIR, "static", "poses")

app = FastAPI(title="Olympics Archive Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/olympics/sports")
def list_sports() -> list[str]:
    """DB에 존재하는 종목명을 중복 없이 정렬해 반환한다 (검색 필터용)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT sport
            FROM olympics
            WHERE sport IS NOT NULL AND sport != ''
            ORDER BY sport
            """
        ).fetchall()
    finally:
        conn.close()

    return [row["sport"] for row in rows]


def _with_raw_fields(row: sqlite3.Row) -> dict:
    """DB에 저장된 raw_json(원본 공공데이터)에서 화면 표시에 쓸 수 있는
    추가 정보(참가국, 영상 길이, 원본 출처 링크)를 꺼내 응답에 덧붙인다."""
    record = dict(row)
    raw = record.pop("raw_json", None)

    record["country"] = None
    record["duration_sec"] = None
    record["source_url"] = None

    if raw:
        try:
            raw_obj = json.loads(raw)
        except (TypeError, ValueError):
            raw_obj = {}

        record["country"] = raw_obj.get("country_kor_nm") or None

        duration = raw_obj.get("mv_time_len")
        try:
            record["duration_sec"] = int(duration) if duration not in (None, "") else None
        except (TypeError, ValueError):
            record["duration_sec"] = None

        record["source_url"] = raw_obj.get("item_url") or None

    return record


@app.get("/api/olympics/search")
def search_olympics(keyword: Optional[str] = None, sport: Optional[str] = None) -> list[dict]:
    """title/summary를 keyword로, sport를 sport로 부분 일치 검색한다 (둘 다 선택값, AND 결합)."""
    query = "SELECT id, title, sport, event_date, summary, video_url, raw_json FROM olympics WHERE 1=1"
    params: list[str] = []

    if keyword:
        query += " AND (title LIKE ? OR summary LIKE ?)"
        like = f"%{keyword}%"
        params.extend([like, like])

    if sport:
        query += " AND sport LIKE ?"
        params.append(f"%{sport}%")

    query += " ORDER BY id"

    conn = get_connection()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return [_with_raw_fields(row) for row in rows]


@app.get("/api/olympics/{match_id}/keypoints")
def get_keypoints(match_id: int) -> FileResponse:
    """extract_pose.py가 미리 추출해 둔 관절 좌표 시퀀스를 반환한다.

    static/poses/{id}.json이 아직 없으면(추출 전이면) 404를 반환한다.
    """
    pose_path = os.path.join(POSES_DIR, f"{match_id}.json")
    if not os.path.isfile(pose_path):
        raise HTTPException(
            status_code=404,
            detail=(
                f"id={match_id}에 대한 포즈 데이터가 없습니다. "
                "extract_pose.py로 먼저 추출해야 합니다."
            ),
        )
    return FileResponse(pose_path, media_type="application/json")
