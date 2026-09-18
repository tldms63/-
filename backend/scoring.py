"""동작 유사도 점수를 '아케이드 게임' 감성으로 채점하는 로직.

정밀한 선수 코칭이 아니라 학생들이 88올림픽 동작을 따라 하며 즐기는 체감형
게임이 목표다. 그래서 화면에 감지되어 동작을 시도한 것만으로도 최소 점수를
보장하고(0점으로 좌절하지 않도록), 종목별로 가장 눈에 띄는 관절 몇 개만 골라
아주 너그러운 기준으로 채점한다.
"""
from __future__ import annotations

import math
import random
from typing import Optional

# MediaPipe Pose 33 랜드마크 인덱스 (extract_pose.py가 저장하는 순서와 동일하다).
NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16

BASE_SCORE = 40  # 화면에 감지되어 시도만 해도 보장하는 최저 점수 (0점 방지)
MIN_VISIBILITY = 0.3  # 이 미만이면 해당 관절은 안 보인다고 보고 무시한다

Point = tuple[float, float]
Landmark = dict  # {"x": float, "y": float, "z": float, "visibility": float}
Frame = Optional[list]  # list[Landmark] 또는 그 프레임에서 포즈를 못 찾았으면 None


def _point(frame: Frame, idx: int) -> Optional[Point]:
    if not frame or idx >= len(frame):
        return None
    lm = frame[idx]
    if lm is None:
        return None
    visibility = lm.get("visibility")
    if visibility is not None and visibility < MIN_VISIBILITY:
        return None
    return (lm["x"], lm["y"])


def _has_any_detection(frames: list[Frame]) -> bool:
    return any(frame for frame in frames)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _angle(a: Optional[Point], b: Optional[Point], c: Optional[Point]) -> Optional[float]:
    """세 점 a-b-c 중 b를 꼭짓점으로 하는 각도(도)를 구한다."""
    if a is None or b is None or c is None:
        return None
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    len1, len2 = math.hypot(*v1), math.hypot(*v2)
    if len1 < 1e-6 or len2 < 1e-6:
        return None
    cos_angle = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (len1 * len2)))
    return math.degrees(math.acos(cos_angle))


def _resample(points: list[Point], count: int) -> list[Point]:
    """포인트 시퀀스를 count개로 등간격 리샘플링한다.

    사용자 웹캠 프레임 수와 기준 영상 프레임 수가 서로 달라도(속도, 프레임레이트
    차이) 같은 길이로 맞춰서 지점별로 비교할 수 있게 해준다.
    """
    if not points:
        return []
    if len(points) == 1 or count == 1:
        return [points[0]] * count
    last_index = len(points) - 1
    resampled = []
    for i in range(count):
        pos = i / (count - 1) * last_index
        left = int(math.floor(pos))
        right = min(left + 1, last_index)
        ratio = pos - left
        x = points[left][0] * (1 - ratio) + points[right][0] * ratio
        y = points[left][1] * (1 - ratio) + points[right][1] * ratio
        resampled.append((x, y))
    return resampled


def _trajectory(frames: list[Frame], idx: int, origin_idx: Optional[int] = None) -> list[Point]:
    """특정 관절의 궤적을 추출한다.

    origin_idx(예: 어깨)를 주면 그 관절 기준 상대좌표로 변환해, 사용자가 화면
    어디에 서 있든/카메라와의 거리가 다르든 궤적 '모양'만 비교할 수 있게 한다.
    """
    points: list[Point] = []
    for frame in frames:
        p = _point(frame, idx)
        if p is None:
            continue
        if origin_idx is not None:
            origin = _point(frame, origin_idx)
            if origin is None:
                continue
            p = (p[0] - origin[0], p[1] - origin[1])
        points.append(p)
    return points


def _trajectory_score(
    user_frames: list[Frame], ref_frames: list[Frame], joint_idx: int, origin_idx: int, tolerance: float
) -> Optional[float]:
    """관절 하나의 궤적을 리샘플링해 평균 거리 오차를 점수로 환산한다.

    tolerance는 '이 정도 차이까지는 봐준다'는 아케이드용 허용 오차라, 실제
    스포츠 분석보다 훨씬 너그럽게 잡혀 있다.
    """
    user_pts = _trajectory(user_frames, joint_idx, origin_idx)
    ref_pts = _trajectory(ref_frames, joint_idx, origin_idx)
    if len(user_pts) < 2 or len(ref_pts) < 2:
        return None

    samples = 15
    u = _resample(user_pts, samples)
    r = _resample(ref_pts, samples)
    avg_dist = sum(math.hypot(ux - rx, uy - ry) for (ux, uy), (rx, ry) in zip(u, r)) / samples
    return _clamp(100 * (1 - avg_dist / tolerance))


def _finish_arm_angle(frames: list[Frame]) -> Optional[float]:
    """마지막으로 포즈가 잡힌 프레임(피니시 동작)의 양팔 평균 각도를 구한다."""
    for frame in reversed(frames):
        if not frame:
            continue
        left = _angle(_point(frame, LEFT_SHOULDER), _point(frame, LEFT_ELBOW), _point(frame, LEFT_WRIST))
        right = _angle(_point(frame, RIGHT_SHOULDER), _point(frame, RIGHT_ELBOW), _point(frame, RIGHT_WRIST))
        angles = [a for a in (left, right) if a is not None]
        if angles:
            return sum(angles) / len(angles)
    return None


def _score_boxing(user_frames: list[Frame], ref_frames: Optional[list[Frame]]) -> Optional[float]:
    """복싱: 손목/팔꿈치 궤적 위주 (손목 비중을 더 크게 둔다)."""
    if not ref_frames:
        return None

    wrist_scores, elbow_scores = [], []
    for wrist_idx, elbow_idx, shoulder_idx in (
        (LEFT_WRIST, LEFT_ELBOW, LEFT_SHOULDER),
        (RIGHT_WRIST, RIGHT_ELBOW, RIGHT_SHOULDER),
    ):
        s = _trajectory_score(user_frames, ref_frames, wrist_idx, shoulder_idx, tolerance=0.5)
        if s is not None:
            wrist_scores.append(s)
        s = _trajectory_score(user_frames, ref_frames, elbow_idx, shoulder_idx, tolerance=0.4)
        if s is not None:
            elbow_scores.append(s)

    if not wrist_scores and not elbow_scores:
        return None

    wrist_avg = sum(wrist_scores) / len(wrist_scores) if wrist_scores else None
    elbow_avg = sum(elbow_scores) / len(elbow_scores) if elbow_scores else None
    if wrist_avg is None:
        return elbow_avg
    if elbow_avg is None:
        return wrist_avg
    return wrist_avg * 0.65 + elbow_avg * 0.35


def _score_weightlifting(user_frames: list[Frame]) -> Optional[float]:
    """역도: 양손의 y좌표(머리 위로 들어 올렸는지)만 본다.

    기준 영상 궤적과 정밀 비교하지 않는다 - 역도의 핵심은 '들어 올렸는가'이지
    타이밍/궤적의 정밀함이 아니기 때문에, 기준 데이터가 없어도 채점 가능하다.
    """
    best_margin = None
    for frame in user_frames:
        nose = _point(frame, NOSE)
        if nose is None:
            continue
        wrist_ys = [p[1] for p in (_point(frame, LEFT_WRIST), _point(frame, RIGHT_WRIST)) if p is not None]
        if not wrist_ys:
            continue
        # 이미지 좌표계는 y가 아래로 갈수록 커지므로, 손목이 코보다 위에 있으면 양수.
        margin = nose[1] - min(wrist_ys)
        if best_margin is None or margin > best_margin:
            best_margin = margin

    if best_margin is None:
        return None
    # margin == 0(손목이 딱 머리 높이) → 60점(GOOD). 화면 높이의 5%만 더 올려도
    # 만점에 가까워지는 매우 후한 곡선이다.
    return _clamp(60 + best_margin * 800)


def _score_gymnastics(user_frames: list[Frame], ref_frames: Optional[list[Frame]]) -> Optional[float]:
    """체조: 착지 피니시 순간의 양팔 각도만 비교한다 (동작 전체 타이밍은 안 본다)."""
    user_angle = _finish_arm_angle(user_frames)
    if user_angle is None:
        return None

    ref_angle = _finish_arm_angle(ref_frames) if ref_frames else None
    if ref_angle is None:
        # 기준 영상의 포즈 데이터가 아직 추출되지 않았다면, 체조 피니시 자세의
        # 전형적인 '양팔을 곧게 편' 각도(약 170도)를 대신 기준으로 삼는다.
        ref_angle = 170.0

    diff = abs(user_angle - ref_angle)
    tolerance = 60.0  # 이만큼 차이 나야 0점에 가까워지는 매우 너그러운 허용 오차
    return _clamp(100 * (1 - diff / tolerance))


def _score_generic(user_frames: list[Frame], ref_frames: Optional[list[Frame]]) -> Optional[float]:
    """복싱/역도/체조 외 종목이거나 기준 데이터가 애매한 경우를 위한 기본 채점.

    기준 포즈가 있으면 팔 관절 궤적을 종합 비교하고, 없으면 '동작을 크게
    움직였는지'만 보고 후하게 점수를 준다 (움직이기만 해도 재밌어야 하므로).
    """
    if ref_frames:
        scores = []
        for idx, shoulder_idx, tolerance in (
            (LEFT_WRIST, LEFT_SHOULDER, 0.5),
            (RIGHT_WRIST, RIGHT_SHOULDER, 0.5),
            (LEFT_ELBOW, LEFT_SHOULDER, 0.4),
            (RIGHT_ELBOW, RIGHT_SHOULDER, 0.4),
        ):
            s = _trajectory_score(user_frames, ref_frames, idx, shoulder_idx, tolerance)
            if s is not None:
                scores.append(s)
        if scores:
            return sum(scores) / len(scores)

    movement, samples = 0.0, 0
    for idx in (LEFT_WRIST, RIGHT_WRIST):
        pts = _trajectory(user_frames, idx)
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            movement += math.hypot(x2 - x1, y2 - y1)
            samples += 1
    if samples == 0:
        return None
    return _clamp(60 + (movement / samples) * 400)


_SPORT_SCORERS = {
    "복싱": lambda user, ref: _score_boxing(user, ref),
    "역도": lambda user, ref: _score_weightlifting(user),
    "체조": lambda user, ref: _score_gymnastics(user, ref),
}

# (임계점수, 판정 텍스트, 응원 멘트 후보) - 리듬 게임처럼 점수 구간별로 다르게 반응한다.
_GRADE_TIERS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (90, "PERFECT", (
        "완벽해요! 88 서울의 전설이 따로 없네요!",
        "지금 이 순간, 당신이 챔피언입니다!",
    )),
    (75, "GREAT", (
        "훌륭해요! 선수 못지않은 움직임이에요!",
        "멋진데요? 계속 이 느낌으로 가봐요!",
    )),
    (60, "GOOD", (
        "좋아요! 감각을 잘 잡고 있어요!",
        "괜찮은데요! 조금만 더 다듬어볼까요?",
    )),
    (0, "KEEP GOING", (
        "괜찮아요, 다시 한번 도전해봐요!",
        "포기하지 마세요! 다음엔 더 잘할 수 있어요!",
    )),
)


def _grade_for(score: float) -> tuple[str, str]:
    for threshold, grade, messages in _GRADE_TIERS:
        if score >= threshold:
            return grade, random.choice(messages)
    grade, messages = _GRADE_TIERS[-1][1], _GRADE_TIERS[-1][2]
    return grade, random.choice(messages)


def evaluate_pose(sport: str, user_frames: list[Frame], ref_frames: Optional[list[Frame]]) -> dict:
    """종목에 맞는 채점 함수를 골라 실행하고, 최저 점수 보장 + 판정/응원 멘트를 붙인다."""
    if not _has_any_detection(user_frames):
        return {
            "score": 0,
            "grade": "KEEP GOING",
            "message": "화면에 잘 보이도록 서주세요! 카메라 앞에서 다시 도전해봐요.",
            "sport": sport,
        }

    scorer = _SPORT_SCORERS.get(sport)
    raw_score = scorer(user_frames, ref_frames) if scorer else None
    if raw_score is None:
        raw_score = _score_generic(user_frames, ref_frames)
    if raw_score is None:
        # 사람은 감지됐지만 핵심 관절이 전부 가려진 경우 - 그래도 시도했으니 기본 점수만.
        raw_score = BASE_SCORE

    final_score = round(_clamp(max(raw_score, BASE_SCORE)))
    grade, message = _grade_for(final_score)

    return {
        "score": final_score,
        "grade": grade,
        "message": message,
        "sport": sport,
    }
