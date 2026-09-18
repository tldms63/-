import { PoseLandmarker, FilesetResolver, DrawingUtils }
  from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.12";

const MP_WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.12/wasm";
const MP_MODEL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task";
const DETECT_INTERVAL_MS = 130; // 인식 주기(약 8fps). 저사양 PC에서 멈춤 방지.

let poseLandmarker = null;
let drawingUtils = null;
let lastVideoTime = -1;
let lastDetect = 0;

// 공공데이터 기반 샘플 클립
const CLIPS = [
  {
    id: "clip_01",
    sport: "레슬링",
    category: "그레코로만형 48kg",
    country: "대한민국",
    title: "1988 서울올림픽 레슬링 결승",
    athlete: "김영남 선수",
    desc: "홈 관중의 응원 속에 투혼을 발휘해 값진 금메달을 획득한 명승부.",
    tags: ["금메달", "투혼"]
  },
  {
    id: "clip_02",
    sport: "양궁",
    category: "여자 단체전",
    country: "대한민국",
    title: "1988 서울올림픽 양궁 결승",
    athlete: "김수녕 선수",
    desc: "신궁의 집중력으로 올림픽 최초 2관왕에 오른 경기.",
    tags: ["금메달", "정적동작"]
  },
  {
    id: "clip_03",
    sport: "복싱",
    category: "라이트미들급",
    country: "대한민국",
    title: "1988 서울올림픽 복싱 결승",
    athlete: "박시헌 선수",
    desc: "치열한 펀치 공방과 빠른 풋워크가 돋보인 결승전.",
    tags: ["난타전", "풋워크"]
  },
  {
    id: "clip_04",
    sport: "육상",
    category: "남자 100m",
    country: "미국",
    title: "1988 서울올림픽 육상 100m",
    athlete: "칼 루이스",
    desc: "폭발적인 가속도로 트랙을 질주한 세기의 대결.",
    tags: ["스피드", "질주"]
  }
];

let currentClip = CLIPS[0];
let isPlaying = false;
let sessionTimer = null;
let scores = [];
let camReady = false;       // 카메라가 켜졌는지
let renderStarted = false;  // 스켈레톤 루프가 이미 돌고 있는지
let lastDetectedPoses = []; // 이번 프레임에 감지된 포즈들
let lockedPlayers = null;   // 게임 시작 시 고정된 플레이어들([{center}]) — null이면 미고정(미리보기)
const PLAYER_COLORS = ["#00e5ff", "#ff9f1c"]; // 1P 하늘색, 2P 주황

// DOM 요소
const archiveVideo = document.getElementById("archiveVideo");
const webcamVideo = document.getElementById("webcamVideo");
const webcamCanvas = document.getElementById("webcamCanvas");
const accValue = document.getElementById("accValue");
const videoNotice = document.getElementById("videoNotice");
const camNotice = document.getElementById("camNotice");
const startBtn = document.getElementById("startBtn");
const pauseBtn = document.getElementById("pauseBtn");
const resetBtn = document.getElementById("resetBtn");
const resultModal = document.getElementById("resultModal");

// UI 반영
function setClip(clip) {
  currentClip = clip;
  document.getElementById("metaTitle").textContent = clip.title;
  document.getElementById("metaAthlete").textContent = `${clip.athlete} (${clip.country}) · ${clip.category}`;
  document.getElementById("metaDesc").textContent = clip.desc;
  renderRecommendations();
  resetSession();
}

// 추천 로직: 같은 종목 또는 같은 국가 우선
function renderRecommendations() {
  const recomList = document.getElementById("recomList");
  const related = CLIPS
    .filter(c => c.id !== currentClip.id)
    .sort((a, b) => {
      let scoreA = (a.sport === currentClip.sport ? 2 : 0) + (a.country === currentClip.country ? 1 : 0);
      let scoreB = (b.sport === currentClip.sport ? 2 : 0) + (b.country === currentClip.country ? 1 : 0);
      return scoreB - scoreA;
    })
    .slice(0, 3);

  recomList.innerHTML = related.map(c => `
    <div class="recom-card" onclick="selectClipById('${c.id}')">
      <div class="recom-card-title">${c.title}</div>
      <div class="recom-card-info">${c.sport} · ${c.athlete}</div>
    </div>
  `).join("");
}

window.selectClipById = (id) => {
  const target = CLIPS.find(c => c.id === id);
  if (target) setClip(target);
};

// 포즈 추정 모델 로딩 (웹캠 영상을 서버로 보내지 않고 브라우저에서 직접 실행)
async function initPose() {
  try {
    const vision = await FilesetResolver.forVisionTasks(MP_WASM);
    // GPU delegate가 일부 PC(구형 내장그래픽)에서 탭을 멈추게 해서 CPU 전용으로 고정.
    poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: MP_MODEL, delegate: "CPU" },
      runningMode: "IMAGE",  // 매 호출마다 새로 감지 (VIDEO 추적 모드가 0만 반환하는 문제 회피)
      numPoses: 3,           // 최대 3명까지 감지(그중 큰 2명 사용) — 새로 들어온 사람 무시 로직에 필요
      minPoseDetectionConfidence: 0.3,
      minPosePresenceConfidence: 0.3,
    });
    drawingUtils = new DrawingUtils(webcamCanvas.getContext("2d"));
  } catch (e) {
    console.error("MediaPipe 로딩 실패:", e);
  }
}

// 카메라 연결
async function initWebcam() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 480 }, height: { ideal: 360 } }, audio: false,
    });
    webcamVideo.srcObject = stream;
    // 해상도(videoWidth)가 준비된 뒤 진행 (0 크기 프레임 인식 시 divide-by-zero 방지)
    await new Promise((resolve) => {
      if (webcamVideo.videoWidth) resolve();
      else webcamVideo.addEventListener("loadedmetadata", resolve, { once: true });
    });
    webcamCanvas.style.transform = "scaleX(-1)"; // 미러된 웹캠 영상과 스켈레톤 정렬
    camNotice.classList.add("hidden");
    // 카메라가 켜지면 '시작'을 누르지 않아도 바로 스켈레톤 루프를 돌린다.
    camReady = true;
    if (!renderStarted) {
      renderStarted = true;
      requestAnimationFrame(loop);
    }
  } catch (err) {
    camNotice.textContent = "카메라를 연결할 수 없습니다";
    setTimeout(() => camNotice.classList.add("hidden"), 1500);
  }
}

// 팔·손·다리·발까지 포함한 관절 연결(유연한 움직임 표현)
const BODY_CONNECTIONS = [
  [11, 12], [11, 23], [12, 24], [23, 24],                       // 몸통
  [11, 13], [13, 15], [15, 17], [15, 19], [15, 21], [17, 19],   // 왼팔 + 손
  [12, 14], [14, 16], [16, 18], [16, 20], [16, 22], [18, 20],   // 오른팔 + 손
  [23, 25], [25, 27], [27, 29], [27, 31], [29, 31],             // 왼다리 + 발
  [24, 26], [26, 28], [28, 30], [28, 32], [30, 32],             // 오른다리 + 발
];
const JOINT_IDS = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28];

function vis(p) { return p.visibility === undefined ? 1 : p.visibility; }

// 포즈의 몸통 중심(정규화 0~1). 사람 매칭·크기 비교용.
function poseCenter(lm) {
  const ids = [11, 12, 23, 24];
  let x = 0, y = 0, n = 0;
  for (const i of ids) { if (lm[i]) { x += lm[i].x; y += lm[i].y; n++; } }
  return n ? [x / n, y / n] : null;
}

// 포즈 크기(어깨너비 + 상체길이). "제일 크게 인식된" 사람 고르기용.
function poseSize(lm) {
  const ls = lm[11], rs = lm[12], lh = lm[23], rh = lm[24];
  if (!ls || !rs || !lh || !rh) return 0;
  const shoulderW = Math.hypot(rs.x - ls.x, rs.y - ls.y);
  const torsoH = Math.hypot((lh.x + rh.x) / 2 - (ls.x + rs.x) / 2, (lh.y + rh.y) / 2 - (ls.y + rs.y) / 2);
  return shoulderW + torsoH;
}

// 한 사람의 스켈레톤(다관절)을 그린다.
function drawPose(ctx, lm, w, h, color) {
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 5;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  // 뼈대
  for (const [a, b] of BODY_CONNECTIONS) {
    const pa = lm[a], pb = lm[b];
    if (!pa || !pb || vis(pa) < 0.3 || vis(pb) < 0.3) continue;
    ctx.beginPath();
    ctx.moveTo(pa.x * w, pa.y * h);
    ctx.lineTo(pb.x * w, pb.y * h);
    ctx.stroke();
  }

  // 목 + 머리
  const nose = lm[0], ls = lm[11], rs = lm[12];
  if (nose && ls && rs) {
    const shcx = (ls.x + rs.x) / 2 * w, shcy = (ls.y + rs.y) / 2 * h;
    const shoulderW = Math.hypot((rs.x - ls.x) * w, (rs.y - ls.y) * h);
    const r = Math.max(10, shoulderW * 0.35);
    ctx.beginPath(); ctx.moveTo(nose.x * w, nose.y * h); ctx.lineTo(shcx, shcy); ctx.stroke();
    ctx.beginPath(); ctx.arc(nose.x * w, nose.y * h, r, 0, Math.PI * 2); ctx.stroke();
  }

  // 관절 점
  for (const i of JOINT_IDS) {
    const p = lm[i];
    if (p && vis(p) >= 0.3) { ctx.beginPath(); ctx.arc(p.x * w, p.y * h, 4, 0, Math.PI * 2); ctx.fill(); }
  }
}

// ── 동작 유사도(정확도) 계산 ─────────────────────────────
// 주요 관절 각도를 비교해 0~100%를 낸다(사람 위치·키 차이와 무관하게 "자세 모양"만 비교).
function jointAngle(a, b, c) { // b를 꼭짓점으로 하는 a-b-c 각도(도)
  const abx = a.x - b.x, aby = a.y - b.y, cbx = c.x - b.x, cby = c.y - b.y;
  const mag = Math.hypot(abx, aby) * Math.hypot(cbx, cby);
  if (mag === 0) return null;
  let cos = (abx * cbx + aby * cby) / mag;
  cos = Math.max(-1, Math.min(1, cos));
  return Math.acos(cos) * 180 / Math.PI;
}
const ANGLE_DEFS = [
  [11, 13, 15], [12, 14, 16], // 팔꿈치(좌/우)
  [13, 11, 23], [14, 12, 24], // 어깨(좌/우)
  [23, 25, 27], [24, 26, 28], // 무릎(좌/우)
  [11, 23, 25], [12, 24, 26], // 골반(좌/우)
];
function poseAngles(lm) {
  return ANGLE_DEFS.map(([a, b, c]) =>
    (lm[a] && lm[b] && lm[c] && vis(lm[a]) > 0.3 && vis(lm[b]) > 0.3 && vis(lm[c]) > 0.3)
      ? jointAngle(lm[a], lm[b], lm[c]) : null);
}
function similarity(lmUser, lmAthlete) {
  const U = poseAngles(lmUser), A = poseAngles(lmAthlete);
  let sum = 0, n = 0;
  for (let i = 0; i < U.length; i++) {
    if (U[i] != null && A[i] != null) { sum += Math.abs(U[i] - A[i]); n++; }
  }
  if (n === 0) return 0;
  const meanDiff = sum / n;                              // 평균 각도차 0~180도
  return Math.max(0, Math.round(100 - meanDiff * 1.6)); // 약 62도 차이면 0점
}
// 감지 결과 중 가장 큰 포즈 하나(좌측 영상의 선수).
function largestPose(res) {
  const poses = res.landmarks || [];
  if (!poses.length) return null;
  return poses.reduce((best, lm) => (poseSize(lm) > poseSize(best) ? lm : best), poses[0]);
}

// 실시간 포즈 인식 + 스켈레톤 오버레이 루프 (카메라가 켜지면 세션과 무관하게 계속 돈다)
function loop() {
  const video = webcamVideo;

  if (!poseLandmarker || !drawingUtils) {
    accValue.textContent = "로딩…";        // 모델 아직 로딩 중
  } else if (video.readyState >= 2 && video.videoWidth > 0) {
    if (webcamCanvas.width !== video.videoWidth) {
      webcamCanvas.width = video.videoWidth;
      webcamCanvas.height = video.videoHeight;
    }
    const ctx = webcamCanvas.getContext("2d");

    const now = performance.now();
    // 인식은 DETECT_INTERVAL_MS 간격으로만 (매 프레임 돌리면 CPU가 터져 페이지가 멈춤).
    if (now - lastDetect >= DETECT_INTERVAL_MS) {
      lastDetect = now;
      try {
        const res = poseLandmarker.detect(video);
        const w = webcamCanvas.width, h = webcamCanvas.height;
        ctx.clearRect(0, 0, w, h);

        const poses = res.landmarks || [];
        lastDetectedPoses = poses;

        // 그릴 대상 결정
        let toDraw = [];
        if (isPlaying && lockedPlayers) {
          // 게임 중: 시작 때 고정된 사람만 위치로 추적해 그린다(새로 들어온 사람 무시).
          const used = new Set();
          lockedPlayers.forEach((pl, idx) => {
            let best = -1, bestD = 0.28; // 매칭 임계(정규화 거리)
            poses.forEach((lm, i) => {
              if (used.has(i)) return;
              const c = poseCenter(lm);
              if (!c) return;
              const d = Math.hypot(c[0] - pl.center[0], c[1] - pl.center[1]);
              if (d < bestD) { bestD = d; best = i; }
            });
            if (best >= 0) {
              used.add(best);
              pl.center = poseCenter(poses[best]); // 위치 갱신(따라다니기)
              toDraw.push({ lm: poses[best], color: PLAYER_COLORS[idx] });
            }
          });
        } else {
          // 게임 시작 전(미리보기): 제일 크게 잡힌 2명.
          const sorted = poses.map((lm) => ({ lm, size: poseSize(lm) }))
            .sort((a, b) => b.size - a.size).slice(0, 2);
          sorted.forEach((o, idx) => toDraw.push({ lm: o.lm, color: PLAYER_COLORS[idx] }));
        }

        for (const d of toDraw) drawPose(ctx, d.lm, w, h, d.color);

        // 게임 중이면 좌측 선수 포즈도 인식해 내 동작과의 유사도(정확도)를 낸다.
        if (isPlaying && lockedPlayers && toDraw.length &&
            archiveVideo.readyState >= 2 && archiveVideo.videoWidth > 0) {
          const athlete = largestPose(poseLandmarker.detect(archiveVideo));
          if (athlete) {
            const score = similarity(toDraw[0].lm, athlete); // 1P vs 선수
            scores.push(score);
            accValue.textContent = `${score}%`;
            accValue.style.color = score >= 80 ? "#4cd137" : (score >= 50 ? "#e1b12c" : "#e84118");
          }
        } else if (toDraw.length > 0) {
          accValue.textContent = `${toDraw.length}명`; // 시작 전: 인식 인원 미리보기
          accValue.style.color = "#888";
        } else {
          accValue.textContent = "미감지";
          accValue.style.color = "#888";
        }
      } catch (e) {
        console.error(e); // 초반 일시적 오류는 무시하고 계속 돈다
      }
    }
  }

  // 스켈레톤 루프는 세션과 무관하게 항상 다음 프레임을 예약한다.
  if (renderStarted) requestAnimationFrame(loop);
}

// 시작/멈춤 제어 (스켈레톤 루프는 건드리지 않고 세션 상태만 관리)
function startSession() {
  isPlaying = true;
  scores = [];
  videoNotice.classList.add("hidden");
  archiveVideo.currentTime = 0;
  archiveVideo.play().catch(() => {});

  startBtn.disabled = true;
  pauseBtn.disabled = false;
  resetBtn.disabled = false;

  // 시작 순간 감지된 사람 중 큰 순 2명을 플레이어로 고정한다.
  // 이후 프레임부터는 이 사람들만 추적하고, 새로 들어온 사람은 무시한다.
  lockedPlayers = lastDetectedPoses
    .map((lm) => ({ center: poseCenter(lm), size: poseSize(lm) }))
    .filter((o) => o.center)
    .sort((a, b) => b.size - a.size)
    .slice(0, 2)
    .map((o) => ({ center: o.center }));
  // 점수는 좌측 영상이 끝나면(finishSession) 표시된다. (아래 'ended' 이벤트)
}

function pauseSession() {
  isPlaying = false;
  archiveVideo.pause();
  clearTimeout(sessionTimer);
  startBtn.disabled = false;
  pauseBtn.disabled = true;
}

function resetSession() {
  pauseSession();
  archiveVideo.currentTime = 0;
  videoNotice.classList.remove("hidden");
  resetBtn.disabled = true;
  lockedPlayers = null; // 플레이어 고정 해제(다음 시작 때 다시 잡음)
  // 스켈레톤 캔버스는 지우지 않는다(루프가 계속 실시간으로 다시 그림).
}

function finishSession() {
  pauseSession();
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
  document.getElementById("finalScore").textContent = `${avg}%`;
  document.getElementById("resultText").textContent = avg >= 80 ? "선수와 거의 일치합니다!" : "조금 더 타이밍을 맞춰보세요.";
  resultModal.classList.remove("hidden");
}

// 이벤트 바인딩
document.getElementById("camPermitBtn").onclick = initWebcam;
startBtn.onclick = startSession;
pauseBtn.onclick = pauseSession;
resetBtn.onclick = resetSession;
// 좌측 영상이 끝까지 재생되면 결과(점수)를 띄운다.
archiveVideo.addEventListener("ended", () => {
  if (isPlaying) finishSession();
});
document.getElementById("modalRetryBtn").onclick = () => {
  resultModal.classList.add("hidden");
  startSession();
};
document.getElementById("modalCloseBtn").onclick = () => {
  resultModal.classList.add("hidden");
};

// 필터 초기화
const sports = [...new Set(CLIPS.map(c => c.sport))];
const countries = [...new Set(CLIPS.map(c => c.country))];
const sFilter = document.getElementById("sportFilter");
const cFilter = document.getElementById("countryFilter");

sports.forEach(s => sFilter.innerHTML += `<option value="${s}">${s}</option>`);
countries.forEach(c => cFilter.innerHTML += `<option value="${c}">${c}</option>`);

function runFilter() {
  const query = document.getElementById("searchInput").value.trim();
  const sp = sFilter.value;
  const ct = cFilter.value;
  const found = CLIPS.find(c => 
    (!query || c.title.includes(query) || c.athlete.includes(query)) &&
    (!sp || c.sport === sp) &&
    (!ct || c.country === ct)
  );
  if (found) setClip(found);
}

document.getElementById("searchInput").oninput = runFilter;
sFilter.onchange = runFilter;
cFilter.onchange = runFilter;

// 초기화
setClip(currentClip);
initPose(); // 포즈 모델 미리 로딩 (카메라 켜기 전에 준비)