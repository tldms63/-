"""
유튜브 영상에서 지정한 구간만 잘라 backend/static/videos/{id}.mp4 로 저장하는 헬퍼 스크립트.

selected_15_matches.md에서 검색으로 찾은 실제 유튜브 클립의 URL과, 우리가 원하는
경기 구간의 시작/종료 시각(초)만 알면 전체 영상을 내려받지 않고 해당 구간만 잘라
extract_pose.py가 바로 읽을 수 있는 mp4로 만들어 둔다.

동작 순서
--------
1. yt-dlp로 해당 구간(+양쪽 여유 구간)만 내려받는다
   (`download_ranges` + `force_keyframes_at_cuts`로 프레임 단위로 정확히 자른다).
2. ffmpeg-python으로 정확한 시작~종료 구간만 다시 한번 트리밍하면서, OpenCV/MediaPipe가
   문제없이 읽을 수 있도록 H.264/AAC mp4(+faststart)로 통일해 최종 파일을 만든다.
3. 중간 산출물은 정리한다.

필요 패키지: yt-dlp, ffmpeg-python (+ 시스템에 ffmpeg 실행 파일 필요)
  pip install yt-dlp ffmpeg-python
  ffmpeg가 PATH에 없다면 --ffmpeg-path로 직접 지정하거나 FFMPEG_PATH 환경변수를 설정한다.

사용법
------
  python download_clip.py 93 "https://www.youtube.com/watch?v=XXXXXXXX" 125 138
  python download_clip.py 93 "https://youtu.be/XXXXXXXX" 125 138 --ffmpeg-path "C:/tools/ffmpeg/bin/ffmpeg.exe"

주의: 저작권이 있는 방송 푸티지이므로, 실제로 사용해도 되는 클립인지(교육/공모전 목적의
허용 범위인지) 확인한 뒤 URL을 넣을 것. 이 스크립트는 사용자가 직접 지정한 URL만 받아
처리하며, URL을 자동으로 검색하거나 추측하지 않는다.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import ffmpeg
import yt_dlp
from yt_dlp.utils import download_range_func

BASE_DIR = Path(__file__).resolve().parent
VIDEOS_DIR = BASE_DIR / "static" / "videos"

# 시작/종료 구간 앞뒤로 이만큼(초) 더 받아둔다. yt-dlp가 키프레임 경계에서 자르기
# 때문에 정확히 start~end만 받으면 앞부분이 살짝 잘릴 수 있어, 여유를 두고 받은 뒤
# 2단계(ffmpeg-python)에서 정확한 지점으로 다시 자른다.
MARGIN_SEC = 2.0


def find_ffmpeg(explicit_path: str | None) -> str:
    """ffmpeg 실행 파일 경로를 찾는다: --ffmpeg-path > PATH > winget 기본 설치 경로 순."""
    if explicit_path:
        if not Path(explicit_path).exists():
            raise FileNotFoundError(f"지정한 ffmpeg 경로가 없습니다: {explicit_path}")
        return explicit_path

    found = shutil.which("ffmpeg")
    if found:
        return found

    # Windows에서 winget으로 설치한 경우 PATH가 새 터미널에서만 반영되므로 기본 설치
    # 위치도 한번 더 찾아본다.
    winget_root = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    if winget_root.exists():
        candidates = sorted(winget_root.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"))
        if candidates:
            return str(candidates[-1])

    raise FileNotFoundError(
        "ffmpeg 실행 파일을 찾을 수 없습니다. ffmpeg를 설치하거나 "
        "--ffmpeg-path로 경로를 직접 지정하세요."
    )


def ensure_ffmpeg_on_path(ffmpeg_path: str) -> None:
    """yt-dlp의 partial-download 가용성 체크(FFmpegFD.available)는 ffmpeg_location
    옵션을 무시하고 시스템 PATH만 검사하는 알려진 제약이 있어(yt-dlp #downloader/external.py
    참고), ffmpeg가 있는 폴더를 현재 프로세스의 PATH 맨 앞에 임시로 추가해 우회한다."""
    ffmpeg_dir = str(Path(ffmpeg_path).parent)
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")


def download_range(url: str, start_sec: float, end_sec: float, ffmpeg_path: str, tmp_path: Path) -> None:
    """yt-dlp로 [start-MARGIN, end+MARGIN] 구간만 내려받아 tmp_path에 저장한다."""
    range_start = max(0.0, start_sec - MARGIN_SEC)
    range_end = end_sec + MARGIN_SEC

    ydl_opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/mp4/best",
        "merge_output_format": "mp4",
        "outtmpl": str(tmp_path.with_suffix("")) + ".%(ext)s",
        "download_ranges": download_range_func(None, [(range_start, range_end)]),
        "force_keyframes_at_cuts": True,
        "ffmpeg_location": ffmpeg_path,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not tmp_path.exists():
        # 확장자가 mp4가 아니게 떨어진 경우를 대비해 같은 stem의 파일을 찾아본다.
        candidates = list(tmp_path.parent.glob(tmp_path.stem + ".*"))
        if not candidates:
            raise RuntimeError("yt-dlp 다운로드 결과 파일을 찾을 수 없습니다.")
        candidates[0].rename(tmp_path)


def trim_and_normalize(
    src_path: Path, dst_path: Path, start_sec: float, end_sec: float, ffmpeg_path: str
) -> None:
    """다운로드된 여유 구간에서 정확히 [start_sec, end_sec]만 잘라 H.264/AAC mp4로 정규화한다."""
    # 1단계에서 여유(MARGIN_SEC)를 두고 받았으므로, tmp 파일 안에서의 상대 시작 지점을 계산한다.
    trim_start = min(MARGIN_SEC, start_sec)
    duration = end_sec - start_sec

    stream = ffmpeg.input(str(src_path), ss=trim_start, t=duration)
    stream = ffmpeg.output(
        stream,
        str(dst_path),
        vcodec="libx264",
        acodec="aac",
        movflags="faststart",
        pix_fmt="yuv420p",
        loglevel="error",
    )
    ffmpeg.run(stream, cmd=ffmpeg_path, overwrite_output=True)


def download_clip(video_id: str, url: str, start_sec: float, end_sec: float, ffmpeg_path: str) -> Path:
    if end_sec <= start_sec:
        raise ValueError(f"end_sec({end_sec})는 start_sec({start_sec})보다 커야 합니다.")

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    final_path = VIDEOS_DIR / f"{video_id}.mp4"
    tmp_path = VIDEOS_DIR / f"{video_id}.raw_download.mp4"

    print(f"[{video_id}] 1/2 다운로드 중 (구간 {start_sec}s~{end_sec}s, 여유 {MARGIN_SEC}s 포함)...")
    download_range(url, start_sec, end_sec, ffmpeg_path, tmp_path)

    print(f"[{video_id}] 2/2 정확한 구간으로 트리밍 + mp4 정규화 중...")
    trim_and_normalize(tmp_path, final_path, start_sec, end_sec, ffmpeg_path)

    tmp_path.unlink(missing_ok=True)
    print(f"[{video_id}] 완료 -> {final_path}")
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="유튜브 URL의 특정 구간만 잘라 backend/static/videos/{id}.mp4로 저장합니다."
    )
    parser.add_argument("id", help="저장할 경기 id (예: 93). 결과 파일명은 static/videos/{id}.mp4")
    parser.add_argument("url", help="유튜브 영상 URL")
    parser.add_argument("start_sec", type=float, help="자를 구간의 시작 시각(초)")
    parser.add_argument("end_sec", type=float, help="자를 구간의 종료 시각(초)")
    parser.add_argument("--ffmpeg-path", default=None, help="ffmpeg 실행 파일 경로를 직접 지정")
    args = parser.parse_args()

    try:
        ffmpeg_path = find_ffmpeg(args.ffmpeg_path)
        ensure_ffmpeg_on_path(ffmpeg_path)
        download_clip(args.id, args.url, args.start_sec, args.end_sec, ffmpeg_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[{args.id}] 실패: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
