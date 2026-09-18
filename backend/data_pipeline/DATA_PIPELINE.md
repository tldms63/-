# 데이터 파이프라인 문서

`backend/`에는 FastAPI 웹 서버(`main.py`)가, `backend/data_pipeline/`에는 그
서버가 서빙할 데이터를 준비하는 **데이터 파이프라인 스크립트**가 들어있다.
이 문서는 데이터 파이프라인 부분만 따로 정리한 것이다 (공모전 제출 / 포트폴리오
정리용).

## 전체 흐름

```
[1] 수집 (Collect)          [2] 가공 (Process)              [3] 추출 (Extract)
                                                                    │
공공데이터포털 API              유튜브 원본 영상                    MediaPipe
      │                            │                                │
      ▼                            ▼                                ▼
collector.py   ─────▶  olympics.db   download_clip.py  ─────▶  extract_pose.py
(메타데이터 수집)      (id, title,    (구간 컷팅 +           (33개 관절
                        sport, ...)    mp4 정규화)             키포인트 추출)
                                          │                          │
                                          ▼                          ▼
                              static/videos/{id}.mp4       static/poses/{id}.json
                                          │                          │
                                          └──────────┬───────────────┘
                                                      ▼
                                              main.py (FastAPI)
                                     GET /api/olympics/search        → DB 조회
                                     GET /api/olympics/{id}/keypoints → poses/{id}.json 반환
```

실행 순서: **collector.py → (사람이 수동으로 유튜브 영상 검색) → download_clip.py → extract_pose.py**
그 다음 `main.py`가 결과물(DB + poses JSON)을 읽어서 API로 서빙한다.

---

## 1. `collector.py` — 메타데이터 수집

- **역할**: 서울올림픽기념국민체육진흥공단 공공데이터 API(`SRVC_OD_API_PHOTO`)를
  호출해 종목별(복싱/체조/태권도/펜싱/역도) 후보 영상·사진 메타데이터를 모으고,
  선수명/결승·금메달 키워드로 점수를 매겨 종목당 3건(총 15건)을 선별한다.
- **입력**:
  - 외부: 공공데이터포털 API 응답 (네트워크 호출)
  - 로컬: `.env`의 `PHOTO_API_KEY`
- **출력**: `olympics.db`의 `olympics` 테이블 (`id, title, sport, event_date, summary,
  video_url, raw_json, created_at`). `video_url`은 `/static/videos/{id}.mp4`로
  미리 채워지지만, 실제 파일은 아직 없다 (2단계에서 생성됨).
- **실행**: `python data_pipeline/collector.py` (backend/ 기준)
- **비고**: 실행할 때마다 `olympics` 테이블을 `DROP`하고 새로 만든다 (재실행 시
  id가 1부터 다시 매겨짐). 실제 영상 재생 URL은 API가 제공하지 않으므로,
  `matches_for_youtube.md` / `selected_15_matches.md`를 참고해 사람이 직접
  유튜브에서 해당 경기 영상을 찾아야 한다 (수동 개입 단계).

## 2. `download_clip.py` — 영상 클립 수집 및 구간 컷팅

- **역할**: 사람이 찾은 유튜브 URL과 원하는 구간(시작~종료 초)을 받아, 전체
  영상을 내려받지 않고 해당 구간만 잘라 MediaPipe가 바로 읽을 수 있는
  H.264/AAC mp4로 정규화한다.
- **처리 방식**: `yt-dlp`로 여유(±2초)를 두고 구간만 다운로드 →
  `ffmpeg-python`으로 정확한 구간으로 재트리밍 + 코덱 정규화 → 중간 파일 삭제.
- **입력**: 유튜브 URL, 시작/종료 시각(초), (1단계에서 정해진) 경기 `id`.
- **출력**: `static/videos/{id}.mp4`
- **실행**: `python data_pipeline/download_clip.py <id> "<youtube_url>" <start_sec> <end_sec>` (backend/ 기준)
- **의존성**: 시스템에 `ffmpeg` 실행 파일 필요 (`--ffmpeg-path`로 직접 지정 가능).
- **비고**: 저작권이 있는 방송 푸티지이므로 URL은 스크립트가 자동 검색하지 않고
  사용자가 직접 지정한 것만 처리한다.

## 3. `extract_pose.py` — 포즈 키포인트 추출

- **역할**: `static/videos/{id}.mp4`를 프레임 단위로 순회하며 MediaPipe Pose
  Landmarker(Tasks API)로 33개 관절 좌표를 추출해 캐시 파일로 저장한다.
  '동작 유사도 측정' 기능이 매 요청마다 영상을 재분석하지 않도록, 미리 한 번만
  실행해 두는 전처리 스크립트다.
- **좌표 정규화**: `x, y`는 프레임 해상도에 대한 비율(0~1, 해상도 무관),
  `z`는 hip 기준 상대 깊이, `visibility`는 관절이 보이는지에 대한 신뢰도(0~1).
  별도 스케일링 없이 MediaPipe 원본 값을 그대로 저장한다.
- **입력**: `static/videos/{id}.mp4`, `models/pose_landmarker_lite.task` (최초
  1회 공식 URL에서 직접 다운로드해 두어야 하는 모델 파일).
- **출력**: `static/poses/{id}.json`
  (`video_id, fps, width, height, frame_count, num_landmarks,
  detected_frame_count, coordinate_space, frames[]`)
- **실행** (backend/ 기준):
  - `python data_pipeline/extract_pose.py <id>` (단일 영상)
  - `python data_pipeline/extract_pose.py --all` (`static/videos/` 안의 모든 mp4 일괄 처리)

## 4. `olympics.db` — 데이터셋 저장소

- **역할**: `collector.py`가 적재한 15건의 경기 메타데이터를 담는 SQLite 파일.
  `main.py`가 검색 API(`/api/olympics/search`, `/api/olympics/sports`)에서
  그대로 읽어 응답한다.
- **생성/갱신 주체**: `collector.py` (전체 재생성), 이후 `collector.py`의
  `collect()` 마지막 단계에서 `video_url` 컬럼만 갱신.

## 5. `static/poses/*.json` — 최종 추출된 모션 데이터셋

- **역할**: `extract_pose.py`의 최종 산출물. `main.py`의
  `GET /api/olympics/{id}/keypoints`가 이 파일을 그대로 읽어 응답한다
  (파일이 없으면 404 + "extract_pose.py로 먼저 추출해야 합니다" 안내).
- **소비자**: 프런트엔드의 '동작 유사도 측정' 기능.

---

## 구조 리팩토링: `backend/data_pipeline/`로 분리 완료

세 스크립트(`collector.py`, `download_clip.py`, `extract_pose.py`)는
`main.py`가 **import하지 않는 독립 실행 CLI 스크립트**다 (`python collector.py`
식으로 직접 실행되고, `main.py`에서 이들을 참조하는 코드는 없음). 따라서
이동해도 Python import 경로(`sys.path`) 문제는 발생하지 않는다.

데이터 수집/가공 관련 파일 전부(`collector.py`, `download_clip.py`,
`extract_pose.py`, `matches_for_youtube.md`, `selected_15_matches.md`,
`DATA_PIPELINE.md`, `olympics.db`)를 `backend/data_pipeline/`로 옮기고,
`static/`, `models/`는 서버(`main.py`)가 직접 서빙/참조하는 대상이므로
`backend/` 루트에 그대로 두었다.

이동에 맞춰 각 스크립트의 "내 위치 기준 상대경로" 계산을 아래처럼 보정했다.

| 파일 | 옮기기 전 | 옮긴 뒤 |
|---|---|---|
| `collector.py` | `os.path.dirname(os.path.abspath(__file__))/olympics.db` | 동일 (스크립트와 DB가 함께 이동했으므로 수정 불필요) |
| `download_clip.py` | `BASE_DIR = Path(__file__).resolve().parent` | `BACKEND_DIR = Path(__file__).resolve().parent.parent` (한 단계 위 `backend/`를 가리키도록 보정) |
| `extract_pose.py` | `BASE_DIR = Path(__file__).resolve().parent` | `BACKEND_DIR = Path(__file__).resolve().parent.parent` (`models/`, `static/videos/`, `static/poses/` 모두 `backend/` 기준으로 보정) |
| `main.py` | `DB_PATH = BASE_DIR/olympics.db` | `DB_PATH = BASE_DIR/data_pipeline/olympics.db` (DB가 `data_pipeline/`로 이동했으므로 반영). `POSES_DIR`은 `static/`이 그대로 `backend/`에 남아 있어 수정 불필요. |

`.env`(`PHOTO_API_KEY`)는 `python-dotenv`의 `load_dotenv()`가 호출부 파일
위치부터 상위 폴더로 올라가며 `.env`를 찾으므로(`usecwd=False` 기본값),
`collector.py`가 `backend/data_pipeline/`로 이동해도 `backend/.env`를 그대로
잘 찾는다 (수정 불필요).

실행 명령어는 아래처럼 바뀐다:

```
python data_pipeline/collector.py
python data_pipeline/download_clip.py <id> "<youtube_url>" <start_sec> <end_sec>
python data_pipeline/extract_pose.py <id>
python data_pipeline/extract_pose.py --all
```

(단, 현재 `main.py`에는 `/static/...` 경로를 서빙하는 `StaticFiles` 마운트가
없다 — `video_url`은 DB에 `/static/videos/{id}.mp4`로 저장돼 있지만 FastAPI가
그 경로를 직접 서빙하고 있지 않다. 이번 리팩토링과는 별개의 기존 이슈이니,
정적 파일 서빙을 실제로 붙일 계획이라면 함께 확인이 필요하다.)
