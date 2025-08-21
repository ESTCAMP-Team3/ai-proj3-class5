// static/js/app.js
// Auto voice/text input, 1s auto-send, L1-L3-FAILSAFE flash+alert sound, center-message behavior

const socket = io();
const stageLabel = document.getElementById('stageLabel');
const dValue = document.getElementById('dValue');
const stageArea = document.getElementById('stageArea');
const centerMessage = document.getElementById('centerMessage');
const chatLog = document.getElementById('chatLog');
const chatInput = document.getElementById('chatInput');

let userResponded = false;
let centerTimeout = null;
let autoPostTimeout = null;
let sendTimer = null;
let lastStage = null;
let alertInterval = null;

// Map D to stage
function stageFromD(D){
    if(D <= 30) return '정상';
    if(D <= 40) return '의심경고';
    if(D <= 50) return '집중모니터링';
    if(D <= 60) return '개선';
    if(D <= 70) return 'L1';
    if(D <= 80) return 'L2';
    if(D <= 90) return 'L3';
    return 'FAILSAFE';
}

// 표시 문구 변경
function displayLabel(stage){
  const map = {
    '정상': '정상',
    '의심경고': '의심경고',
    '집중모니터링': '집중 모니터링',
    '개선': '개선',
    'L1': '졸음 지속\n경고 강화 L1',
    'L2': '졸음 지속\n경고 강화 L2',
    'L3': '졸음 지속\n경고 강화 L3',
    'FAILSAFE': '고위험!\n즉시 정차',
    
  };
  return map[stage] || stage;
}

/* Flash classes control */
function clearFlashClasses(){
    stageArea.classList.remove('flash-L1','flash-L2','flash-L3','flash-FAILSAFE');
}
function manageFlash(stage){
    clearFlashClasses();
    if(stage === 'L1') stageArea.classList.add('flash-L1');
    else if(stage === 'L2') stageArea.classList.add('flash-L2');
    else if(stage === 'L3') stageArea.classList.add('flash-L3');
    else if(stage === 'FAILSAFE') stageArea.classList.add('flash-FAILSAFE');
}

/* Play repeating alert beep while in escalation stage */
function startAlertLoop(stage){
    stopAlertLoop();
    // gain base and multiplier (we clamp to <=1 for safety)
    const baseGain = 0.5;
    let factor = 1.0;
    if(stage === 'L1') factor = 1.0;
    else if(stage === 'L2') factor = 1.1;
    else if(stage === 'L3') factor = 1.2;
    else if(stage === 'FAILSAFE') factor = 1.3;
    const gainValue = Math.min(1.0, baseGain * factor);

    // play immediate beep and then repeat every 1000ms
    playBeep(gainValue);
    alertInterval = setInterval(()=> playBeep(gainValue), 1000);
}
function stopAlertLoop(){
    if(alertInterval){
        clearInterval(alertInterval);
        alertInterval = null;
    }
}

// simple beep via WebAudio API
function playBeep(gainVal=0.5, duration=220){
    try{
        const ac = new (window.AudioContext || window.webkitAudioContext)();
        const o = ac.createOscillator();
        const g = ac.createGain();
        o.type = 'sine';
        o.frequency.value = 880; // beep pitch
        g.gain.value = gainVal;
        o.connect(g); g.connect(ac.destination);
        o.start();
        setTimeout(()=> {
            o.stop();
            try{ ac.close(); }catch(e){}
        }, duration);
    }catch(e){
        // WebAudio might not be available; ignore
        console.warn('playBeep err', e);
    }
}

/* show center message; auto-save to chat if no user input within 1s */
function showCenterMessage(text, volume=1.0, duration=4000){
    userResponded = false;
    if(!centerMessage || !stageArea) return;

    centerMessage.textContent = text;
    centerMessage.style.display = 'block';
    stageArea.classList.add('center-active');

    // speak
    speak(text, volume);

    // clear timers
    if(centerTimeout) { clearTimeout(centerTimeout); centerTimeout = null; }
    if(autoPostTimeout) { clearTimeout(autoPostTimeout); autoPostTimeout = null; }

    // auto-post system message after 1000ms if user doesn't respond
    autoPostTimeout = setTimeout(()=>{
        if(!userResponded){
            fetch('/save_msg', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user: 'assistant', text: text })
            }).catch(err => console.warn('save_msg err', err));
        }
    }, 1000);

    centerTimeout = setTimeout(()=>{
        centerMessage.style.display = 'none';
        stageArea.classList.remove('center-active');
        centerTimeout = null;
    }, duration);
}

/* send chat (programmatic auto-send) */
async function sendChat(){
    const txt = chatInput.value ? chatInput.value.trim() : '';
    if(!txt) {
        // nothing to send
        return;
    }
    userResponded = true;
    appendBubble('user', txt);
    chatInput.value = '';

    try{
        const res = await fetch('/chat_send', {
            method:'POST',
            headers:{ 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: txt })
        });
        const j = await res.json();
        // Add assistant reply immediately and speak
        appendBubble('assistant', j.text);
        speak(j.text, 1.0);
    }catch(e){
        appendBubble('assistant', '서버 에러: 응답 없음');
        console.warn(e);
    }
}

/* schedule auto-send after 1s of inactivity */
function scheduleAutoSend(){
    if(sendTimer) clearTimeout(sendTimer);
    sendTimer = setTimeout(()=> {
        sendTimer = null;
        sendChat();
    }, 1000);
}

// Append chat bubble
function appendBubble(who, text){
    if(!chatLog) return;
    const b = document.createElement('div');
    b.className = 'bubble ' + (who === 'user' ? 'user' : 'assistant');
    b.textContent = text;
    chatLog.appendChild(b);
    chatLog.scrollTop = chatLog.scrollHeight;
}

/* TTS */
function speak(text, volume=1.0){
    if(!('speechSynthesis' in window)) return;
    try{ window.speechSynthesis.cancel(); } catch(e){}
    const utter = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices() || [];
    for(const v of voices){
        if(v.lang && v.lang.startsWith('ko') && /female|Google|Noto|Yuna/i.test(v.name)){
            utter.voice = v;
            break;
        }
    }
    utter.volume = Math.max(0.0, Math.min(1.5, volume));
    utter.rate = 1.0;
    window.speechSynthesis.speak(utter);
}

/* Continuous speech recognition: always listen and populate the text input.
   On result, schedule auto-send. If recognition is unsupported, fallback to text-only. */
let recogActive = false;
let recognition = null;
function startRecognition(){
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if(!SpeechRecognition) {
        console.warn('SpeechRecognition not supported');
        return;
    }
    recognition = new SpeechRecognition();
    recognition.lang = 'ko-KR';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = (e) => {
        const text = e.results[0][0].transcript;
        chatInput.value = text;
        userResponded = true; // user has "spoken"
        scheduleAutoSend();
    };
    recognition.onerror = (err) => {
        console.warn('recog error', err);
    };
    recognition.onend = () => {
        // restart to keep continuous listening
        setTimeout(()=> {
            try { recognition.start(); } catch(e){}
        }, 200);
    };

    try{
        recognition.start();
        recogActive = true;
    }catch(e){
        console.warn('recog start err', e);
    }
}

/* Stop recognition on demand */
function stopRecognition(){
    try{
        if(recognition) recognition.onend = null;
        if(recognition) recognition.stop();
    }catch(e){}
    recognition = null;
    recogActive = false;
}

/* Handle D updates from server; apply stage UI, center messages, flash, alerts */
let lastStageLocal = null;
socket.on('d_update', (data)=>{
    const D = data && data.D !== undefined ? data.D : null;
    if(D === null) return;
    const stage = stageFromD(D);

    // apply UI
    if (stageLabel) stageLabel.textContent = displayLabel(stage);
    if(dValue) dValue.textContent = '졸음 지수 : ' + D;

    // center messages depending on stage
    switch(stage){
        case '의심경고':
            showCenterMessage('주의! 졸음 신호 감지 - 집중해주세요.', 1.0);
            break;
        case '집중모니터링':
            showCenterMessage('상태 확인 중입니다.', 0.95);
            break;
        case '개선':
            showCenterMessage('좋아요. 상태가 나아졌어요.', 0.95);
            break;
        case 'L1':
            showCenterMessage('계속 졸고 계세요!\n휴식 또는 계속 중 하나만 말씀해 주세요', 1.0);
            break;
        case 'L2':
            showCenterMessage('강한 졸음신호입니다!\n창문 열기나 에어컨 강풍을 권장해요', 1.1);
            break;
        case 'L3':
            showCenterMessage('고위험 졸음 상태!\n지금 가까운 휴게소로 안내할까요?', 1.2);
            break;
        case 'FAILSAFE':
            showCenterMessage('고위험 상태입니다!\n즉시 정차하세요.', 1.3);
            break;
    }

    
    // update stage-area classes (keeping single unified background)
    // remove old bg classes and add new one
    const bgClasses = ['bg-normal','bg-attention','bg-suspected','bg-focused','bg-improving','bg-persistent','bg-L1','bg-L2','bg-L3','bg-FAILSAFE'];
    bgClasses.forEach(c=> stageArea.classList.remove(c));
    let cls = 'bg-normal';
    switch(stage){
        case '정상': cls='bg-normal'; break;
        case '의심경고': cls='bg-attention'; break;
        case '집중모니터링': cls='bg-focused'; break;
        case '개선': cls='bg-improving'; break;
        case 'L1': cls='bg-L1'; break;
        case 'L2': cls='bg-L2'; break;
        case 'L3': cls='bg-L3'; break;
        case 'FAILSAFE': cls='bg-FAILSAFE'; break;
    }
    stageArea.classList.add(cls);

    // flashing and alert handling: only when entering escalation stages start alert loop
    const escalationStages = ['L1','L2','L3','FAILSAFE'];
    manageFlash(stage);
    if(escalationStages.includes(stage)){
        // if newly entered escalate
        if(lastStageLocal !== stage){
            startAlertLoop(stage);
        }
    } else {
        stopAlertLoop();
    }

    lastStageLocal = stage;
});

// 한 번만 선언 (파일 최상단에 이미 선언돼있지 않다면)
let skipNextChatMessageText = null;

// state_prompt 수신 핸들러 — 서버에서 state change 시 emit 하는 이벤트를 처리
socket.on('state_prompt', (m) => {
  console.log('DEBUG: state_prompt recv ->', m);
  if (!m) return;

  const ann = (m.announcement || "").toString();
  const q = (m.question || "").toString();

  // 중앙 경고 표시 (함수 존재 여부 체크)
  if (typeof showCenterMessage === 'function' && ann) {
    try { showCenterMessage(ann, 3.0); } catch(e){ console.warn('showCenterMessage err', e); }
  } else if (ann) {
    console.log('No showCenterMessage; announcement:', ann);
  }

  // 채팅창에 한 번만 기록
  if (typeof appendBubble === 'function' && ann) {
    try { appendBubble('assistant', ann); } catch(e){ console.warn('appendBubble err', e); }
  } else if (ann) {
    console.log('No appendBubble; announcement:', ann);
  }

  // 음성 출력 (TTS) — 함수가 있으면 호출
  if (typeof speak === 'function' && ann) {
    try { speak(ann, 1.0); } catch(e){ console.warn('speak err', e); }
  }

  // 서버가 여전히 chat_message를 emit할 가능성에 대비해 중복 차단 플래그 설정
  if (ann) skipNextChatMessageText = ann;

  // 질문(q)이 있으면 약간 있다가 표시 및 음성, 서버 저장(선택)
  setTimeout(()=> {
    if (q && q.length > 0) {
      if (typeof appendBubble === 'function') {
        try { appendBubble('assistant', q); } catch(e){ console.warn('appendBubble err', e); }
      }
      if (typeof speak === 'function') {
        try { speak(q, 1.0); } catch(e){ console.warn('speak err', e); }
      }
      // 참고: 서버의 save_msg()가 chat_message를 emit하지 않도록 서버에서 조치했으면
      // 아래 fetch는 유지해도 무방. 서버가 emit하면 중복될 수 있으니 서버 변경여부에 따라 주석처리하세요.
      fetch('/save_msg', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ user:'assistant', text: q })
      }).catch(e => console.warn('save_msg failed', e));
    }
  }, 1200);
});

// chat_message 수신 시 중복 필터 적용(기존 handler를 이 형태로 바꿔주세요)
socket.on('chat_message', (m) => {
  console.log('DEBUG: chat_message recv ->', m);
  if (!m) return;
  // 최근에 state_prompt에서 append된 동일 텍스트면 한 번만 무시
  if (skipNextChatMessageText && m.user === 'assistant' && m.text === skipNextChatMessageText) {
    console.log('Skipped duplicate chat_message:', m.text);
    skipNextChatMessageText = null;
    return;
  }
  // 기존 동작
  if (typeof appendBubble === 'function') {
    appendBubble(m.user, m.text);
  } else {
    console.log('No appendBubble; chat_message:', m);
  }
});



/* Input events: typing schedules auto-send */
chatInput.addEventListener('input', ()=>{
    userResponded = true;
    scheduleAutoSend();
});

/* Start continuous recognition on load (if available) */
window.addEventListener('load', ()=>{
    try{ startRecognition(); } catch(e){ console.warn('startRecognition failed', e); }
});
