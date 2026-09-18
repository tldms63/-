"""
영상에서 선수 관절(Keypoint) 좌표를 추출해 미리 캐싱하는 전처리 스크립트.

'동작 유사도 측정' 기능이 매 요청마다 영상을 다시 분석하지 않도록, 이 스크립트를
미리 한 번 돌려서 프레임별 포즈 랜드마크를 backend/static/poses/{id}.json 으로
저장해 둔다. main.py의 GET /api/olympics/{id}/keypoints 는 이 캐시 파일만 읽는다.

입력: backend/static/videos/{id}.mp4  (경기 영상. 직접 다운로드해서 넣어야 함)
출력: backend/static/poses/{id}.json

사용법
------
  python extract_pose.py 93          # static/videos/93.mp4 하나만 처리
  python extract_pose.py --all       # static/videos/ 안의 모든 .mp4를 일괄 처리
  python extract_pose.py 93 --video "C:/clips/my_clip.mp4"   # 임의 경로 지정

필요 패키지: opencv-python, mediapipe
  pip install opencv-python mediapipe

필요 모델 파일: backend/models/pose_landmarker_lite.task
  최신 mediapipe(Tasks API)는 모델을 pip 패키지에 포함하지 않으므로 최초 1회
  아래 공식 URL에서 받아 위 경로에 저장해야 한다.
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task

좌표 정규화
-----------
MediaPipe Pose Landmarker가 반환하는 x, y는 프레임 너비/높이에 대한 비율(0~1
정규화 좌표)이라, 원본 영상의 해상도가 얼마든 상관없이 그대로 비교할 수 있다.
z는 엉덩이(hip) 중심 기준 상대 깊이, visibility는 해당 관절이 화면에 보이는지에
대한 신뢰도(0~1)다. 원본 좌표를 그대로 저장하며 별도 스케일링을 하지 않는다.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "pose_landmarker_lite.task"
VIDEOS_DIR = BASE_DIR / "static" / "videos"
POSES_DIR = BASE_DIR / "static" / "poses"

NUM_LANDMARKS = 33
MODEL_DOWNLOAD_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)


def build_landmarker() -> PoseLandmarker:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"포즈 모델 파일이 없습니다: {MODEL_PATH}\n"
            f"{MODEL_DOWNLOAD_URL} 에서 다운로드해 위 경로에 저장하세요."
        )
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return PoseLandmarker.create_from_options(options)


def extract_video(video_path: Path, video_id: str, landmarker: PoseLandmarker) -> dict:
    """영상 하나를 프레임 단위로 순회하며 포즈 랜드마크 시퀀스를 만든다."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frames = []
    frame_index = 0
    detected_count = 0

    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break

        # detect_for_video는 타임스탬프가 프레임마다 단조 증가해야 한다.
        timestamp_ms = int((frame_index / fps) * 1000)
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        result = landmarker.detect_for_video(mp_image, timestamp_ms)

        if result.pose_landmarks:
            detected_count += 1
            landmarks = [
                {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
                for lm in result.pose_landmarks[0]
            ]
        else:
            # 선수가 화면 밖이거나 장면 전환 등으로 포즈를 못 찾은 프레임
            landmarks = None

        frames.append(
            {
                "frame_index": frame_index,
                "timestamp_ms": timestamp_ms,
                "landmarks": landmarks,
            }
        )
        frame_index += 1

    cap.release()

    return {
        "video_id": video_id,
        "fps": fps,
        "width": width,
        "height": height,
        "frame_count": frame_index,
        "num_landmarks": NUM_LANDMARKS,
        "detected_frame_count": detected_count,
        "coordinate_space": "normalized (0~1, 해상도 무관)",
        "frames": frames,
    }


def process_one(video_path: Path, video_id: str, landmarker: PoseLandmarker) -> Path:
    POSES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = POSES_DIR / f"{video_id}.json"

    print(f"[{video_id}] 처리 시작: {video_path.name}")
    started = time.time()
    data = extract_video(video_path, video_id, landmarker)
    elapsed = time.time() - started

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    print(
        f"[{video_id}] 완료: 총 {data['frame_count']}프레임 중 "
        f"{data['detected_frame_count']}프레임에서 포즈 검출 "
        f"({elapsed:.1f}초) -> {output_path}"
    )
    return output_path


def process_all(landmarker: PoseLandmarker) -> None:
    if not VIDEOS_DIR.exists():
        print(f"영상 폴더가 없습니다: {VIDEOS_DIR}", file=sys.stderr)
        return

    video_paths = sorted(VIDEOS_DIR.glob("*.mp4"))
    if not video_paths:
        print(f"{VIDEOS_DIR} 안에 .mp4 파일이 없습니다.", file=sys.stderr)
        return

    print(f"총 {len(video_paths)}개 영상을 처리합니다.")
    for video_path in video_paths:
        video_id = video_path.stem
        try:
            process_one(video_path, video_id, landmarker)
        except Exception as exc:  # noqa: BLE001
            print(f"[{video_id}] 처리 실패: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="영상에서 MediaPipe Pose로 관절 좌표를 추출해 static/poses/{id}.json에 캐싱합니다."
    )
    parser.add_argument("id", nargs="?", help="처리할 경기 id (예: 93). --all과 함께는 쓰지 않는다.")
    parser.add_argument(
        "--video",
        help="id에 대응하는 영상 파일 경로를 직접 지정 (기본값: static/videos/{id}.mp4)",
    )
    parser.add_argument("--all", action="store_true", help="static/videos/ 안의 모든 .mp4를 일괄 처리")
    args = parser.parse_args()

    if not args.all and not args.id:
        parser.error("id를 지정하거나 --all 옵션을 사용하세요.")

    landmarker = build_landmarker()
    try:
        if args.all:
            process_all(landmarker)
        else:
            video_path = Path(args.video) if args.video else VIDEOS_DIR / f"{args.id}.mp4"
            if not video_path.exists():
                print(f"영상 파일을 찾을 수 없습니다: {video_path}", file=sys.stderr)
                sys.exit(1)
            process_one(video_path, args.id, landmarker)
    finally:
        landmarker.close()


if __name__ == "__main__":
    main()
