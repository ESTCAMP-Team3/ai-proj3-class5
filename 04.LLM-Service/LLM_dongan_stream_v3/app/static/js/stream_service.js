const $ = (s) => document.querySelector(s);

const $video = $("#preview");
const $canvas = $("#stage");
const ctx = $canvas.getContext("2d");

const $camSel = $("#cameraSelect");
const $btnStart = $("#btnStart");
const $btnStop = $("#btnStop");
const $sid = $("#sid");
const $sent = $("#sent");
const $qRange = $("#qRange");
const $qLabel = $("#qLabel");
const $log = $("#log");
const $statFps = $("#statFps");

let mediaStream = null;
let running = false;
let sessionId = makeSessionId();
let seq = 0;
let busy = false;

const TARGET_FPS = 24;
const FRAME_INTERVAL = 1000 / TARGET_FPS;

$sid.textContent = sessionId;
$qLabel.textContent = $qRange.value;

$btnStart.addEventListener("click", start);
$btnStop.addEventListener("click", stop);
$camSel.addEventListener("change", async () => {
  const devId = $camSel.value || null;
  await setupStream(devId);
});
$qRange.addEventListener("input", () => {
  $qLabel.textContent = $qRange.value;
});

init().catch(e => log("초기화 실패: " + e.message));

async function init() {
  await ensurePermission();
  await populateCameras();
  await setupStream(null);
}

async function ensurePermission() {
  const temp = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
  temp.getTracks().forEach(t => t.stop());
}

async function populateCameras() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const vids = devices.filter(d => d.kind === "videoinput");
  $camSel.innerHTML = "";
  for (const d of vids) {
    const opt = document.createElement("option");
    opt.value = d.deviceId;
    opt.textContent = d.label || `Camera ${$camSel.length + 1}`;
    $camSel.appendChild(opt);
  }
  log(`비디오 입력 장치 ${vids.length}개`);
}

async function setupStream(deviceId) {
  stopTracks();

  const constraints = {
    audio: false,
    video: {
      width: { ideal: 640, max: 640 },
      height: { ideal: 480, max: 480 },
      frameRate: { ideal: 24, max: 24 },
      facingMode: deviceId ? undefined : "user",
      deviceId: deviceId ? { exact: deviceId } : undefined
    }
  };

  mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
  $video.srcObject = mediaStream;
  await $video.play();
  log("미리보기 시작");
}

function start() {
  if (!mediaStream) {
    log("스트림 없음");
    return;
  }
  running = true;
  seq = 0;
  sessionId = makeSessionId();
  $sid.textContent = sessionId;
  $btnStart.disabled = true;
  $btnStop.disabled = false;

  // 🔽 새 탭으로 서비스 화면 오픈 (세션ID 전달)
  window.open(`/drowny_service?sid=${encodeURIComponent(sessionId)}`, "_blank", "noopener");

  loopFrames();
  log("JPEG 업로드 시작");
}

function stop() {
  running = false;
  $btnStart.disabled = false;
  $btnStop.disabled = true;
  log("정지");
}

function stopTracks() {
  if (mediaStream) {
    for (const t of mediaStream.getTracks()) t.stop();
    mediaStream = null;
  }
}

let lastSent = 0;
function loopFrames() {
  if (!running) return;

  const now = performance.now();
  const delta = now - lastSent;

  // 목표 간격 도달 시 프레임 캡처/전송
  if (delta >= FRAME_INTERVAL && !busy) {
    lastSent = now;
    captureAndSend().catch(e => log("전송 실패: " + e.message));
  }
  requestAnimationFrame(loopFrames);
}

async function captureAndSend() {
  busy = true;

  // 640x480 캔버스에 현재 프레임 그리기
  ctx.drawImage($video, 0, 0, $canvas.width, $canvas.height);

  const quality = parseFloat($qRange.value); // 0.0~1.0
  const blob = await new Promise(res => $canvas.toBlob(res, "image/jpeg", quality));
  if (!blob || blob.size === 0) {
    busy = false;
    return;
  }

  const ok = await uploadJPEG(blob, sessionId, seq++);
  if (ok) $sent.textContent = String(seq);

  busy = false;
}

async function uploadJPEG(blob, session, seq) {
  const r = await fetch("/stream/upload", {
    method: "POST",
    headers: {
      "X-Session-Id": session,
      "X-Seq": String(seq),
      "Content-Type": "image/jpeg"
    },
    body: blob
  });
  if (!r.ok) {
    const t = await r.text();
    log(`HTTP ${r.status}: ${t}`);
    return false;
  }
  // const j = await r.json();
  // log("OK: " + j.saved);
  return true;
}

function makeSessionId() {
  return 'sess-' + Math.random().toString(36).slice(2, 10) + '-' + Date.now().toString(36);
}

function log(msg) {
  const ts = new Date().toLocaleTimeString();
  console.log(msg);
  $log.textContent = `[${ts}] ${msg}\n` + $log.textContent;
}
