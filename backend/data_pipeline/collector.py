"""
올림픽 아카이브(사진/동영상) 메타데이터 수집 스크립트.

서울올림픽기념국민체육진흥공단_올림픽자료실 사진동영상 정보 API
(공공데이터포털 SRVC_OD_API_PHOTO)를 호출해, TARGET_SPORTS에 지정한 종목별로
SPORT_KEYWORDS(선수명/세부종목명)에 가장 많이 매칭되는 경기 PER_SPORT건씩
(현재 5개 종목 x 3건 = 15건)을 골라 로컬 SQLite DB(olympics.db)에 저장한다.

선별 방식
---------
전체 페이지(최대 MAX_PAGES x PAGE_SIZE건)를 훑으면서 종목별로 후보를 모으고,
각 항목에 대해 SPORT_KEYWORDS(예: 김광선, 박시헌, 전병관 등 실제 선수명·핵심
세부종목명)와 BONUS_KEYWORDS(결승/금메달/시상식 등)가 제목·요약에 등장하는
개수로 점수를 매긴 뒤, 점수가 높은 순으로 종목당 PER_SPORT건을 뽑는다.
(score_item 참고) 키워드에 전혀 걸리지 않는 항목은 후보에서 제외한다.

호출 전략
---------
- 엔드포인트: 동영상(todz_api_movie_i)을 먼저 시도하고, 데이터가 없거나
  실패하면 사진(TODZ_API_PHOTO_I)으로 폴백한다.
- 서비스키: 1) urllib.parse.unquote로 디코딩해 params에 실어 requests가
  정확히 한 번만 인코딩하도록 호출하고, 실패하면 2) 이미 인코딩된 키를 URL
  문자열 끝에 직접 결합해 이중 인코딩을 피하는 방식으로 재시도한다.
- 결과 포맷 파라미터는 `_type`이 아니라 `resultType`이어야 정상 응답한다
  (`_type` 사용 시 INVALID_REQUEST_PARAMETER_ERROR[resultType] 발생 확인).
- 공공데이터포털 서버가 간헐적으로 연결을 끊는 경우가 있어 페이지 단위로
  재시도한다.

주의: 실제 영상 재생 URL은 API가 제공하지 않으므로 저장하지 않는다.
(item_url은 kspo.or.kr 내부 자료실 페이지 링크일 뿐, 스트리밍 링크가 아니다)
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

BASE_URL = "https://apis.data.go.kr/B551014/SRVC_OD_API_PHOTO"
ENDPOINTS = ["/todz_api_movie_i", "/TODZ_API_PHOTO_I"]
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "olympics.db")

# 웹에 노출할 5개 종목 x 종목별 3건 = 15건만 선별한다.
TARGET_SPORTS = ["복싱", "체조", "태권도", "펜싱", "역도"]
PER_SPORT = 3
PAGE_SIZE = 1000  # 이 API는 numOfRows를 1000건까지만 허용한다.
MAX_PAGES = 10  # 전체 데이터(약 9,752건)를 모두 훑어도 10페이지면 충분하다.

# 종목별로 우선 찾는 실제 선수명/핵심 세부종목명 (실제 데이터에서 대조 확인됨).
# 하나 매칭될 때마다 10점을 준다.
SPORT_KEYWORDS: dict[str, list[str]] = {
    "복싱": ["김광선", "박시헌"],
    "체조": ["박종훈", "임혜진", "도마"],
    "태권도": ["하태경"],
    "펜싱": ["에페", "플뢰레", "사브르"],
    "역도": ["전병관"],
}
# 종목 불문 가산점 키워드 (결승/시상식 장면을 우선하기 위함). 하나 매칭될 때마다 3점.
BONUS_KEYWORDS = ["결승", "금메달", "시상식"]

# 실제 응답 필드명(동영상 API 기준: title_kor_nm, game_kor_nm, fix_ymd, sc_txt_cn 등)을
# 최우선으로 탐색하고, 사진 API 등 다른 엔드포인트로 폴백될 경우를 대비해 자주 쓰이는
# 한글/영문 후보 키도 함께 순서대로 탐색해 매핑한다.
TITLE_KEYS = [
    "title_kor_nm", "제목명", "제목", "사진제목", "동영상제목", "titleNm", "title", "subject",
]
SPORT_KEYS = ["game_kor_nm", "종목명", "종목", "sportNm", "eventNm", "event"]
DATE_KEYS = [
    "fix_ymd", "날짜", "경기일자", "촬영일자", "등록일자", "regDate", "gameDate",
    "occurDate", "date",
]
SUMMARY_KEYS = ["sc_txt_cn", "내용요약", "내용", "설명", "content", "contents", "summary", "cn"]

# data.go.kr 원문은 선수 이름을 "성, 이니셜"로만 제공한다(예: "Lamour, J").
# 아래는 IOC 공식 결과(olympics.com/olympedia.org)로 대조 확인한 실제 전체 이름이며,
# 현재 TARGET_SPORTS로 선별된 15건(역도 3건, 펜싱 3건)에 등장하는 선수만 다룬다.
# 매칭 대상 표기가 "성, 이니셜"/"성 이니셜"/마침표 유무 등으로 들쭉날쭉해 정규식으로 흡수한다.
ATHLETE_NAME_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Delrieu,?\s*P\.?"), "Philippe Delrieu"),       # 프랑스, 펜싱 사브르
    (re.compile(r"Pogossov,?\s*G\.?"), "Georgy Pogosov"),         # 소련, 펜싱 사브르
    (re.compile(r"Lamour,?\s*J\.?"), "Jean-François Lamour"),     # 프랑스, 펜싱 사브르(금메달)
    (re.compile(r"Olech,?\s*Janus\.?"), "Janusz Olech"),          # 폴란드, 펜싱 사브르(은메달)
    (re.compile(r"Liao,?\s*Chin\s*Ming"), "Liao Chin-ming"),      # 대만(중화타이베이), 역도 100kg급
    (re.compile(r"Langthaler,?\s*F\.?"), "Franz Langthaler"),     # 오스트리아, 역도 100kg급
    (re.compile(r"Murillo,?\s*T\.?"), "Tolentino Murillo"),       # 콜롬비아, 역도 60kg급
    (re.compile(r"Suleymano\.?"), "Naim Süleymanoğlu"),           # 터키, 역도 60kg급 금메달(전설적 선수)
]


def expand_athlete_names(text: str) -> str:
    """원문의 축약된 선수 표기(성+이니셜)를 ATHLETE_NAME_MAP 기준 실제 전체 이름으로 치환한다."""
    for pattern, full_name in ATHLETE_NAME_MAP:
        text = pattern.sub(full_name, text)
    return text


def get_service_key() -> str:
    load_dotenv()
    raw_key = os.getenv("PHOTO_API_KEY")
    if not raw_key:
        print(".env 파일에 PHOTO_API_KEY 가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)
    return raw_key


def fetch_page_decoded(endpoint: str, service_key_encoded: str, page_no: int, num_of_rows: int) -> dict:
    """디코딩한 서비스키를 params로 전달 (requests가 1회만 인코딩).

    참고: 이 API는 결과 포맷 파라미터로 `_type`이 아니라 `resultType`을 요구한다.
    (`_type`으로 호출 시 `INVALID_REQUEST_PARAMETER_ERROR[resultType]` 에러가 발생함을 확인)
    """
    decoded_key = urllib.parse.unquote(service_key_encoded)
    params = {
        "serviceKey": decoded_key,
        "numOfRows": num_of_rows,
        "pageNo": page_no,
        "resultType": "json",
    }
    resp = requests.get(BASE_URL + endpoint, params=params, timeout=15)
    return parse_response(resp)


def fetch_page_raw_encoded(endpoint: str, service_key_encoded: str, page_no: int, num_of_rows: int) -> dict:
    """이미 인코딩된 서비스키를 URL 끝에 직접 결합 (이중 인코딩 방지 폴백)."""
    query = (
        f"?serviceKey={service_key_encoded}"
        f"&numOfRows={num_of_rows}"
        f"&pageNo={page_no}"
        f"&resultType=json"
    )
    resp = requests.get(BASE_URL + endpoint + query, timeout=15)
    return parse_response(resp)


def fetch_page(
    endpoint: str,
    service_key_encoded: str,
    page_no: int,
    num_of_rows: int,
    retries: int = 3,
) -> dict:
    """디코딩 키 호출을 우선 시도하고, 실패하면 인코딩 키 결합 방식으로 재시도한다.

    공공데이터포털 서버가 간헐적으로 연결을 끊는 경우(ConnectionResetError 등)가
    있어, 페이지 단위로 짧은 대기 후 재시도한다.
    """
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fetch_page_decoded(endpoint, service_key_encoded, page_no, num_of_rows)
        except Exception as decoded_exc:  # noqa: BLE001
            print(
                f"[{endpoint}] p{page_no} 디코딩 키 호출 실패(시도 {attempt}/{retries}), "
                f"인코딩 키 직접 결합 방식으로 재시도합니다: {decoded_exc}",
                file=sys.stderr,
            )
            try:
                return fetch_page_raw_encoded(endpoint, service_key_encoded, page_no, num_of_rows)
            except Exception as raw_exc:  # noqa: BLE001
                last_exc = raw_exc
                print(
                    f"[{endpoint}] p{page_no} 인코딩 키 방식도 실패(시도 {attempt}/{retries}): {raw_exc}",
                    file=sys.stderr,
                )
                time.sleep(1.0 * attempt)

    raise RuntimeError(f"[{endpoint}] p{page_no} 재시도 {retries}회 모두 실패: {last_exc}")


def parse_response(resp: requests.Response) -> dict:
    # 응답 헤더의 charset 선언이 부정확한 경우가 있어, 한글이 깨지지 않도록 명시적으로 강제한다.
    resp.encoding = "utf-8"
    text = resp.text.strip()
    if text.startswith("<"):
        # 에러 응답이나 XML 응답을 처리 (HTTP 상태코드가 4xx여도 본문에 상세 에러가 있음)
        return parse_xml_error_or_body(text)

    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise RuntimeError(f"알 수 없는 응답 형식입니다: {text[:200]}")

    # 공통 에러 포맷: {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {...}}}
    if "OpenAPI_ServiceResponse" in data:
        header = data["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        raise RuntimeError(
            f"API 에러 응답: {header.get('returnReasonCode')} - {header.get('errMsg')} "
            f"({header.get('returnAuthMsg')})"
        )

    return data


def parse_xml_error_or_body(text: str) -> dict:
    root = ET.fromstring(text)
    err_msg = root.findtext(".//errMsg")
    if err_msg:
        reason = root.findtext(".//returnReasonCode")
        auth_msg = root.findtext(".//returnAuthMsg")
        raise RuntimeError(f"API 에러 응답: {reason} - {err_msg} ({auth_msg})")

    # 정상 XML 바디를 dict 형태로 변환 (response > body > items > item)
    items = []
    for item_el in root.findall(".//items/item"):
        items.append({child.tag: (child.text or "") for child in item_el})

    result_code = root.findtext(".//resultCode")
    result_msg = root.findtext(".//resultMsg")
    total_count = root.findtext(".//totalCount")
    return {
        "response": {
            "header": {"resultCode": result_code, "resultMsg": result_msg},
            "body": {
                "items": {"item": items},
                "totalCount": int(total_count) if total_count else len(items),
            },
        }
    }


def extract_items(data: dict) -> tuple[list, int | None]:
    body = data.get("response", {}).get("body", {})

    header = data.get("response", {}).get("header", {})
    result_code = str(header.get("resultCode", "00"))
    if result_code not in ("00", "0"):
        raise RuntimeError(
            f"API 결과 코드 이상: {result_code} - {header.get('resultMsg')}"
        )

    items_field = body.get("items", [])
    if isinstance(items_field, dict):
        item = items_field.get("item", [])
    else:
        item = items_field

    if isinstance(item, dict):
        item = [item]
    elif item is None:
        item = []

    total_count = body.get("totalCount")
    try:
        total_count = int(total_count) if total_count is not None else None
    except (TypeError, ValueError):
        total_count = None

    return item, total_count


def pick(item: dict, keys: list[str]) -> str:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return str(item[key])
    return ""


def fix_known_date_typo(date_str: str) -> str:
    """서울올림픽(1988)인데 원본 fix_ymd가 '1998-'로 잘못 기재된 레코드가 실제로
    존재함을 확인했다 (예: 복싱 라이트미들급 시상식). 연도만 보정하고 나머지는 그대로 둔다."""
    if date_str.startswith("1998-"):
        return "1988-" + date_str[5:]
    return date_str


def score_item(item: dict, sport: str) -> int:
    """SPORT_KEYWORDS/BONUS_KEYWORDS 매칭 개수로 항목의 우선순위 점수를 매긴다."""
    haystack = " ".join(
        [
            str(item.get("title_kor_nm") or ""),
            str(item.get("sc_title_kor_nm") or ""),
            str(item.get("sc_txt_cn") or ""),
        ]
    )
    score = 0
    for kw in SPORT_KEYWORDS.get(sport, []):
        if kw in haystack:
            score += 10
    for kw in BONUS_KEYWORDS:
        if kw in haystack:
            score += 3
    return score


def build_row(item: dict) -> tuple[str, str, str, str, str]:
    """API 원본 item을 (title, sport, event_date, summary, raw_json)으로 변환한다."""
    sport = pick(item, SPORT_KEYS)
    base_title = pick(item, TITLE_KEYS)
    scene = str(item.get("sc_title_kor_nm") or "").strip()

    title_parts = [part for part in (sport, base_title) if part]
    title = " ".join(title_parts) if title_parts else "제목 미상"
    if scene and scene not in title:
        title = f"{title} - {scene}"
    title = expand_athlete_names(title)

    event_date = fix_known_date_typo(pick(item, DATE_KEYS))
    summary = expand_athlete_names(pick(item, SUMMARY_KEYS))
    # 참가국(country_kor_nm), 영상 길이(mv_time_len), 원본 링크(item_url)는
    # summary에 합치지 않고 raw_json에만 보존한다. API가 이를 별도 필드로 풀어서
    # 응답하므로(main.py의 country / duration_sec / source_url), 화면에서 중복 표시되지 않는다.

    return (title, sport, event_date, summary, json.dumps(item, ensure_ascii=False))


def setup_db(conn: sqlite3.Connection) -> None:
    # ID를 1부터 다시 깔끔하게 매기기 위해 테이블 자체를 새로 만든다
    # (DELETE만으로는 AUTOINCREMENT 카운터가 이전 최대값에서 이어짐).
    conn.execute("DROP TABLE IF EXISTS olympics")
    conn.execute(
        """
        CREATE TABLE olympics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            sport TEXT,
            event_date TEXT,
            summary TEXT,
            video_url TEXT,
            raw_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def collect_from_endpoint(endpoint: str, service_key_encoded: str) -> list[dict]:
    """전체 페이지를 훑어 종목별 후보를 모으고, score_item 점수가 높은 순으로
    종목당 PER_SPORT건씩 골라 모은다.

    같은 경기의 예선 조/장면이 title_kor_nm을 공유하는 경우가 많아(예: 역도
    "52KG급 (4)"의 여러 시도 장면, 체조 "개인 종목별 결승 (4)"의 서로 다른 선수/
    라운드 장면), 그룹별로 가장 점수가 높은 장면 하나만 남긴다 - "먼저 본 것"이
    아니라 "그룹 내 최고 점수"를 기준으로 고른다.

    그룹 키는 title_kor_nm 단독이 아니라 title_kor_nm + sc_title_kor_nm(장면 제목)의
    조합을 쓴다. title_kor_nm만 쓰면 "박종훈 1라운드(9.950점)"와 "박종훈 2라운드
    (10.000 만점)"처럼 서로 다른 라운드/선수의 장면이 같은 그룹으로 묶여 하나가
    통째로 버려지는 문제가 있었다.
    """
    best_by_group: dict[str, dict[str, tuple[int, dict]]] = {sport: {} for sport in TARGET_SPORTS}

    page_no = 1
    while page_no <= MAX_PAGES:
        data = fetch_page(endpoint, service_key_encoded, page_no, PAGE_SIZE)
        items, total_count = extract_items(data)
        if not items:
            break

        for item in items:
            sport = pick(item, SPORT_KEYS)
            if sport not in best_by_group:
                continue
            score = score_item(item, sport)
            if score <= 0:
                continue  # 키워드에 전혀 매칭되지 않으면 후보에서 제외

            group_key = (pick(item, TITLE_KEYS), str(item.get("sc_title_kor_nm") or ""))
            current_best = best_by_group[sport].get(group_key)
            if current_best is None or score > current_best[0]:
                best_by_group[sport][group_key] = (score, item)

        if total_count is not None and page_no * PAGE_SIZE >= total_count:
            break
        page_no += 1
        time.sleep(0.3)

    collected: list[dict] = []
    for sport in TARGET_SPORTS:
        ranked = sorted(best_by_group[sport].values(), key=lambda pair: pair[0], reverse=True)
        top = [item for _score, item in ranked[:PER_SPORT]]
        if len(top) < PER_SPORT:
            print(
                f"경고: '{sport}' 종목에서 키워드 매치 후보를 {PER_SPORT}건 채우지 못하고 "
                f"{len(top)}건만 찾았습니다.",
                file=sys.stderr,
            )
        collected.extend(top)
    return collected


def collect() -> int:
    service_key_encoded = get_service_key()

    conn = sqlite3.connect(DB_PATH)
    setup_db(conn)

    collected: list[dict] = []
    used_endpoint = None
    last_error: Exception | None = None

    for endpoint in ENDPOINTS:
        try:
            print(f"엔드포인트 시도: {endpoint}")
            collected = collect_from_endpoint(endpoint, service_key_encoded)
            if collected:
                used_endpoint = endpoint
                break
            print(f"[{endpoint}] 응답에 데이터가 없습니다. 다음 엔드포인트로 폴백합니다.", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"[{endpoint}] 호출 실패: {exc}", file=sys.stderr)

    if not collected:
        conn.close()
        raise RuntimeError(
            f"모든 엔드포인트({', '.join(ENDPOINTS)})에서 데이터를 가져오지 못했습니다. "
            f"마지막 에러: {last_error}"
        )

    print(f"'{used_endpoint}' 엔드포인트에서 {len(collected)}건을 수집했습니다.")

    rows = [build_row(item) for item in collected]

    conn.executemany(
        """
        INSERT INTO olympics (title, sport, event_date, summary, raw_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    # id가 1부터 순서대로 부여된 뒤에야 video_url(/static/videos/{id}.mp4)을 채울 수 있다.
    conn.execute("UPDATE olympics SET video_url = '/static/videos/' || id || '.mp4'")
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM olympics").fetchone()[0]
    all_rows = conn.execute(
        "SELECT id, title, sport, event_date, summary FROM olympics ORDER BY id"
    ).fetchall()
    conn.close()

    expected = len(TARGET_SPORTS) * PER_SPORT
    if count < expected:
        print(
            f"경고: 목표한 {expected}건({len(TARGET_SPORTS)}개 종목 x {PER_SPORT}건)에 "
            f"못 미치는 {count}건만 저장되었습니다.",
            file=sys.stderr,
        )

    print(f"olympics.db에 총 {count}건의 메타데이터를 저장했습니다.")
    print("=== 선별된 경기 목록 [ID / 종목 / 제목 / 상세 설명] ===")
    for row_id, title, sport, event_date, summary in all_rows:
        print(f"[{row_id}] {sport} | {title} ({event_date})")
        print(f"    {summary}")

    return count


if __name__ == "__main__":
    try:
        collect()
    except Exception as exc:  # noqa: BLE001
        print(f"수집 실패: {exc}", file=sys.stderr)
        sys.exit(1)
