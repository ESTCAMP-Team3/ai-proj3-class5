// app.js
// 카메라 영상 녹화 및 서버 업로드
const $ = (sel) => document.querySelector(sel);
const FORCE_WEBM_VP8 = 'video/webm;codecs="vp8"';

let mediaStream = null;
let recorder = null;
let sessionId = makeSessionId();
let seq = 0;
let currentMime = null;
let sending = false;

const $video = $("#preview");
const $btnStart = $("#btnStart");
const $btnStop = $("#btnStop");
const $log = $("#log");
const $sid = $("#sid");
const $sentCount = $("#sentCount");
const $camSel = $("#cameraSelect");
const $codecTag = $("#codecTag");

$sid.textContent = sessionId;

$btnStart.addEventListener("click", startStreaming);
$btnStop.addEventListener("click", stopStreaming);
$camSel.addEventListener("change", restartWithDevice);

// === 초기화: 먼저 권한 팝업을 띄워 라벨이 보이게 함 ===
init();
async function init() {
  try {
    log("초기화 시작");
    // 1) 최소 권한 요청 (전면 카메라)
    await ensurePermission();
    // 2) 장치 라벨/목록 채우기
    await enumerateCameras();
    // 3) 미리보기 준비
    await setupStream();
    log("초기화 완료");
  } catch (e) {
    log("초기화 실패: " + e);
  }
}

async function ensurePermission() {
  try {
    const temp = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user" },
      audio: false
    });
    // 곧바로 종료(권한만 획득)
    temp.getTracks().forEach(t => t.stop());
    log("카메라 권한 획득");
  } catch (e) {
    log("카메라 권한 요청 실패: " + e.name + " / " + e.message);
    throw e;
  }
}

async function enumerateCameras() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const vids = devices.filter(d => d.kind === "videoinput");
    $camSel.innerHTML = "";
    for (const d of vids) {
      const opt = document.createElement("option");
      opt.value = d.deviceId;
      opt.textContent = d.label || `Camera ${$camSel.length + 1}`;
      $camSel.appendChild(opt);
    }
    log(`비디오 입력 장치: ${vids.length}개`);
  } catch (e) {
    log("카메라 나열 실패: " + e);
  }
}

async function setupStream(deviceId=null) {
  stopTracks();
  const constraints = {
    audio: false,
    video: {
      width: { ideal: 640, max: 640 },
      height:{ ideal: 480, max: 480 },
      frameRate: { ideal: 24, max: 24 },
      facingMode: deviceId ? undefined : "user",
      deviceId: deviceId ? { exact: deviceId } : undefined
    }
  };
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
    $video.srcObject = mediaStream;
    await $video.play();
    log("미리보기 시작");
  } catch (e) {
    log("getUserMedia 실패: " + e.name + " / " + e.message);
    throw e;
  }
}

async function restartWithDevice() {
  const devId = $camSel.value || null;
  await setupStream(devId);
  if (sending) await startRecorder();
}

async function startStreaming() {
  if (!mediaStream) await setupStream();
  sending = true;
  seq = 0;
  sessionId = makeSessionId();
  $sid.textContent = sessionId;
  await startRecorder();
  $btnStart.disabled = true;
  $btnStop.disabled = false;
}

// startRecorder() 전체 교체
async function startRecorder() {
  stopRecorder();
  if (typeof MediaRecorder === "undefined") {
    log("이 브라우저는 MediaRecorder를 지원하지 않습니다.");
    return;
  }

  // 1) 우선 WebM(VP8) 강제 시도
  let chosenMime = null;
  if (MediaRecorder.isTypeSupported(FORCE_WEBM_VP8)) {
    chosenMime = FORCE_WEBM_VP8;
  } else {
    // 2) 폴백: 브라우저가 지원하는 최선의 MIME 선택
    chosenMime = pickBestMime(); // 'video/mp4;codecs="h264"' or webm/vp9/vp8 ...
  }

  currentMime = chosenMime;                 // 업로드 헤더용
  $codecTag.textContent = `코덱: ${currentMime || "(브라우저 기본)"}`;
  log("선택 MIME: " + (currentMime || "(브라우저 기본)"));

  try {
    const opts = { videoBitsPerSecond: 1_200_000 };
    if (currentMime) opts.mimeType = currentMime;
    recorder = new MediaRecorder(mediaStream, opts);
  } catch (e) {
    log("MediaRecorder 생성 실패: " + e.name + " / " + e.message);
    return;
  }

  recorder.ondataavailable = async (ev) => {
    if (!ev.data || ev.data.size === 0) return;
    try {
      // ev.data.type이 공백일 수 있으므로 currentMime 폴백
      const mime = ev.data.type || currentMime || "application/octet-stream";
      await uploadChunk(ev.data, sessionId, seq++, mime);
      $sentCount.textContent = String(seq);
    } catch (e) {
      log("업로드 실패: " + e.message);
    }
  };
  recorder.onerror = (ev) => log("Recorder error: " + ev.error);
  recorder.onstop = () => log("Recorder stopped");

  recorder.start(1000); // 1초 세그먼트
  log("스트리밍 시작");
}


function stopStreaming() {
  sending = false;
  stopRecorder();
  stopTracks();
  $btnStart.disabled = false;
  $btnStop.disabled = true;
  log("스트리밍 종료");
}

function stopRecorder() {
  if (recorder && recorder.state !== "inactive") {
    try { recorder.stop(); } catch {}
  }
  recorder = null;
}

function stopTracks() {
  if (mediaStream) {
    for (const t of mediaStream.getTracks()) t.stop();
    mediaStream = null;
  }
}

async function uploadChunk(blob, sessionId, seq, mime) {
  const res = await fetch("/upload", {
    method: "POST",
    headers: {
      "X-Session-Id": sessionId,
      "X-Seq": String(seq),
      "X-Mime": mime
    },
    body: blob
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status} - ${text}`);
  }
  const j = await res.json();
  log(`업로드 OK: ${j.saved}`);
}

function pickBestMime() {
  const candidates = [
    'video/mp4;codecs="h264"',
    'video/mp4',
    'video/webm;codecs="vp9"',
    'video/webm;codecs="vp8"',
    'video/webm'
  ];
  for (const m of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) return m;
  }
  return null;
}

function makeSessionId() {
  return 'sess-' + Math.random().toString(36).slice(2, 10) + '-' + Date.now().toString(36);
}

function log(msg) {
  console.log(msg);
  const ts = new Date().toLocaleTimeString();
  $log.textContent = `[${ts}] ${msg}\n` + $log.textContent;
}
