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
let animId = null;
let scores = [];

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

// 카메라 연결
async function initWebcam() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    webcamVideo.srcObject = stream;
    camNotice.classList.add("hidden");
  } catch (err) {
    camNotice.textContent = "카메라를 연결할 수 없습니다 (가상 모드로 동작)";
    setTimeout(() => camNotice.classList.add("hidden"), 1500);
  }
}

// 스켈레톤 및 유사도 루프
function loop() {
  if (!isPlaying) return;

  const ctx = webcamCanvas.getContext("2d");
  webcamCanvas.width = webcamCanvas.clientWidth;
  webcamCanvas.height = webcamCanvas.clientHeight;
  ctx.clearRect(0, 0, webcamCanvas.width, webcamCanvas.height);

  // 실시간 포즈 변동 시뮬레이션
  const t = Date.now() * 0.003;
  const currentAcc = Math.round(72 + Math.sin(t) * 16);
  scores.push(currentAcc);

  // 우측 상단 갱신
  accValue.textContent = `${currentAcc}%`;
  accValue.style.color = currentAcc >= 80 ? "#4cd137" : (currentAcc >= 60 ? "#e1b12c" : "#e84118");

  // 미니멀 스켈레톤 렌더링
  const cx = webcamCanvas.width / 2;
  const cy = webcamCanvas.height / 2;
  ctx.strokeStyle = "#4cd137";
  ctx.lineWidth = 3;

  ctx.beginPath();
  ctx.arc(cx, cy - 40, 12, 0, Math.PI * 2); // 머리
  ctx.moveTo(cx, cy - 28);
  ctx.lineTo(cx, cy + 30); // 몸통
  ctx.moveTo(cx, cy - 15);
  ctx.lineTo(cx - 30, cy - 10 + Math.sin(t) * 20); // 왼팔
  ctx.moveTo(cx, cy - 15);
  ctx.lineTo(cx + 30, cy - 10 - Math.sin(t) * 20); // 오른팔
  ctx.stroke();

  animId = requestAnimationFrame(loop);
}

// 시작/멈춤 제어
function startSession() {
  isPlaying = true;
  scores = [];
  videoNotice.classList.add("hidden");
  archiveVideo.currentTime = 0;
  archiveVideo.play().catch(() => {});

  startBtn.disabled = true;
  pauseBtn.disabled = false;
  resetBtn.disabled = false;

  loop();
  sessionTimer = setTimeout(finishSession, 8000); // 8초 시연
}

function pauseSession() {
  isPlaying = false;
  archiveVideo.pause();
  cancelAnimationFrame(animId);
  clearTimeout(sessionTimer);
  startBtn.disabled = false;
  pauseBtn.disabled = true;
}

function resetSession() {
  pauseSession();
  archiveVideo.currentTime = 0;
  videoNotice.classList.remove("hidden");
  resetBtn.disabled = true;
  accValue.textContent = "0%";
  accValue.style.color = "#4cd137";
  const ctx = webcamCanvas.getContext("2d");
  ctx.clearRect(0, 0, webcamCanvas.width, webcamCanvas.height);
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