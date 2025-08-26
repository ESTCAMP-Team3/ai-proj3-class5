// static/js/app.js - 모든 문제 해결된 최종 버전
const socket = io();
const $ = id => document.getElementById(id);
const els = {
    stage: $('stageLabel'), 
    dValue: $('dValue'), 
    area: $('stageArea'), 
    center: $('centerMessage'), 
    log: $('chatLog'), 
    input: $('chatInput')
};

let userResponded = false, skipNext = null, timers = {}, alertLoop = null, lastStage = null;

// === 음성 상태 관리 (중복 및 에코 방지) ===
let audioState = {
    isTTSPlaying: false,
    isSTTActive: false,
    lastTTSText: '',
    lastTTSTime: 0,
    recognition: null,
    isProcessingResponse: false
};

// 단계 매핑
const stages = [[30,'정상'],[40,'의심경고'],[50,'집중모니터링'],[60,'개선'],[70,'L1'],[80,'L2'],[90,'L3'],[999,'FAILSAFE']];
const labels = {'정상':'정상','의심경고':'의심경고','집중모니터링':'집중 모니터링','개선':'개선','L1':'졸음 지속\n경고 강화 L1','L2':'졸음 지속\n경고 강화 L2','L3':'졸음 지속\n경고 강화 L3','FAILSAFE':'고위험!\n즉시 정차'};
const messages = {'의심경고':['주의! 졸음 신호 감지! 집중해주세요.',1.0],'집중모니터링':['상태 확인 중입니다.',0.95],'개선':['좋아요. 상태가 나아졌어요.',0.95],'L1':['계속 졸고 계세요!\n휴식 또는 계속 중 하나만 말씀해 주세요',1.0],'L2':['강한 졸음신호입니다!\n창문 열기나 에어컨 강풍을 권장해요',1.3],'L3':['고위험 졸음 상태!\n지금 가까운 휴게소로 안내할까요?',1.4],'FAILSAFE':['고위험 상태입니다!\n즉시 정차하세요.',1.5]};

// 유틸 함수들
const getStage = D => stages.find(([t]) => D <= t)?.[1] || 'FAILSAFE';
const clear = obj => Object.values(obj).forEach(t => t && clearTimeout(t));

const beep = (vol=0.5) => {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator(), gain = ctx.createGain();
        osc.frequency.value = 880; gain.gain.value = Math.min(1, vol);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(); setTimeout(() => { osc.stop(); ctx.close?.(); }, 220);
    } catch(e) { console.warn('beep fail', e); }
};

// === 텍스트 정리 함수 ===
const cleanText = (text) => {
    if (!text) return '';
    return text
        .replace(/별표\s*사인\s*별표\s*사인/g, '**')
        .replace(/별표\s*싸인\s*별표\s*싸인/g, '**') 
        .replace(/별표\s*사인/g, '*')
        .replace(/별표\s*싸인/g, '*')
        .replace(/별표/g, '*')
        .replace(/샵\s*사인/g, '#')
        .replace(/\*{3,}/g, '**')
        .replace(/\s+/g, ' ')
        .trim();
};

// === 음성인식 제어 함수들 ===
const pauseRecognition = () => {
    console.log('🎤 음성인식 일시정지');
    if (audioState.recognition && audioState.isSTTActive) {
        try {
            audioState.recognition.stop();
        } catch(e) {}
        audioState.isSTTActive = false;
    }
};

const resumeRecognition = () => {
    console.log('🎤 음성인식 재개');
    if (audioState.recognition && !audioState.isSTTActive && !audioState.isTTSPlaying) {
        try {
            audioState.recognition.start();
            audioState.isSTTActive = true;
        } catch(e) {
            console.warn('음성인식 재개 실패:', e);
        }
    }
};

// === 개선된 TTS (에코 방지) ===
const speak = (text, vol=1.0) => {
    if (!speechSynthesis || !text || audioState.isProcessingResponse) return;
    
    const cleanedText = cleanText(text);
    console.log('🔊 TTS 시작:', cleanedText);
    
    // 중복 재생 방지
    const now = Date.now();
    if (cleanedText === audioState.lastTTSText && now - audioState.lastTTSTime < 3000) {
        console.log('🔊 중복 TTS 방지');
        return;
    }
    
    // 음성인식 일시정지
    pauseRecognition();
    audioState.isTTSPlaying = true;
    audioState.lastTTSText = cleanedText;
    audioState.lastTTSTime = now;
    
    try {
        speechSynthesis.cancel();
    } catch(e) {}
    
    const utter = new SpeechSynthesisUtterance(cleanedText);
    const voices = speechSynthesis.getVoices();
    const ko = voices.find(v => v.lang?.startsWith('ko') && /female|Google|Noto|Yuna/i.test(v.name));
    if (ko) utter.voice = ko;
    utter.volume = Math.min(1.5, vol);
    utter.rate = 1.0;
    
    utter.onstart = () => {
        console.log('🔊 TTS 재생 중');
        audioState.isTTSPlaying = true;
    };
    
    utter.onend = () => {
        console.log('🔊 TTS 완료');
        audioState.isTTSPlaying = false;
        
        // 3초 후 음성인식 재개 (에코 방지)
        setTimeout(() => {
            if (!audioState.isTTSPlaying) {
                resumeRecognition();
            }
        }, 3000);
    };
    
    utter.onerror = () => {
        console.warn('🔊 TTS 오류');
        audioState.isTTSPlaying = false;
        resumeRecognition();
    };
    
    speechSynthesis.speak(utter);
};

// === 채팅 (중복 방지 강화) ===
const addBubble = (who, text, skipDuplicate = true) => {
    if (!els.log || !text) return;
    
    const cleanedText = cleanText(text);
    
    // 중복 방지
    if (skipDuplicate) {
        const lastBubble = els.log.lastElementChild;
        if (lastBubble && 
            lastBubble.className.includes(who) && 
            lastBubble.textContent.trim() === cleanedText) {
            console.log('💬 중복 메시지 방지:', cleanedText.substring(0, 20));
            return;
        }
    }
    
    const div = document.createElement('div');
    div.className = `bubble ${who}`;
    div.textContent = cleanedText;
    els.log.appendChild(div);
    els.log.scrollTop = els.log.scrollHeight;
    
    console.log(`💬 ${who}: ${cleanedText.substring(0, 30)}...`);
};

const save = (user, text) => fetch('/save_msg', {
    method: 'POST', 
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user, text: cleanText(text)})
}).catch(console.warn);

// === 중앙 메시지 (중복 방지) ===
const showCenter = (text, vol=1.0) => {
    userResponded = false;
    if (!els.center || !els.area) return;
    
    const cleanedText = cleanText(text);
    
    // 중복 표시 방지
    if (els.center.textContent === cleanedText && els.center.style.display === 'block') {
        console.log('🔔 중복 중앙메시지 방지');
        return;
    }
    
    clear(timers);
    els.center.textContent = cleanedText;
    els.center.style.display = 'block';
    els.area.classList.add('center-active');
    
    // TTS 재생
    speak(cleanedText, vol);
    
    timers.auto = setTimeout(() => !userResponded && save('assistant', cleanedText), 1500);
    timers.hide = setTimeout(() => {
        els.center.style.display = 'none';
        els.area.classList.remove('center-active');
    }, 5000);
};

// === 음악 및 알림 시스템 ===
let currentAudio = null;

const playMusic = (musicPath, loop = false) => {
    if (!musicPath) return;
    
    console.log('🎵 음악 재생:', musicPath);
    
    // 기존 음악 정지
    if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
    }
    
    try {
        currentAudio = new Audio(musicPath);
        currentAudio.loop = loop;
        currentAudio.volume = 0.7;
        
        const playPromise = currentAudio.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.warn('음악 재생 실패:', error);
                console.warn('파일 경로 확인:', musicPath);
            });
        }
    } catch(error) {
        console.warn('음악 로드 실패:', error);
    }
};

const stopMusic = () => {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
        console.log('🎵 음악 정지');
    }
};

const startAlert = stage => {
    stopAlert();
    const vols = {L1:0.5, L2:0.55, L3:0.6, FAILSAFE:0.65};
    const intervals = {L1:1000, L2:1000, L3:800, FAILSAFE:500};
    beep(vols[stage]);
    alertLoop = setInterval(() => beep(vols[stage]), intervals[stage] || 1000);
};

const stopAlert = () => { 
    if (alertLoop) clearInterval(alertLoop); 
    alertLoop = null; 
};

// === UI 업데이트 (음악 재생 추가) ===
const updateUI = (stage, D) => {
    if (els.stage) els.stage.textContent = labels[stage] || stage;
    if (els.dValue) els.dValue.textContent = `졸음 지수 : ${D}`;
    
    // 배경 클래스
    const bgClasses = ['bg-normal','bg-attention','bg-focused','bg-improving','bg-L1','bg-L2','bg-L3','bg-FAILSAFE'];
    const bgMap = {'정상':'bg-normal','의심경고':'bg-attention','집중모니터링':'bg-focused','개선':'bg-improving','L1':'bg-L1','L2':'bg-L2','L3':'bg-L3','FAILSAFE':'bg-FAILSAFE'};
    bgClasses.forEach(c => els.area.classList.remove(c));
    els.area.classList.add(bgMap[stage] || 'bg-normal');
    
    // 플래시
    const flashClasses = ['flash-L1','flash-L2','flash-L3','flash-FAILSAFE'];
    flashClasses.forEach(c => els.area.classList.remove(c));
    if (['L1','L2','L3','FAILSAFE'].includes(stage)) els.area.classList.add(`flash-${stage}`);
    
    // 음악 재생 (단계별)
    if (lastStage !== stage) {
        const stageMusic = {
            'L1': '/static/sounds/L1_alarm.wav',
            'L2': '/static/sounds/L2_alarm.wav', 
            'L3': '/static/sounds/L3_alarm.wav',
            'FAILSAFE': '/static/sounds/fail_alarm.wav'
        };
        
        if (stageMusic[stage]) {
            playMusic(stageMusic[stage], true);
        } else {
            stopMusic();
        }
    }
    
    // 메시지 (단계 변경시에만)
    const msg = messages[stage];
    if (msg && lastStage !== stage) {
        showCenter(msg[0], msg[1]);
    }
    
    // 알림
    const escalation = ['L1','L2','L3','FAILSAFE'];
    if (escalation.includes(stage) && lastStage !== stage) startAlert(stage);
    else if (!escalation.includes(stage)) stopAlert();
    
    lastStage = stage;
};

// === 채팅 전송 (중복 방지) ===
const sendChat = async () => {
    const text = els.input.value?.trim();
    if (!text || audioState.isProcessingResponse) return;
    
    console.log('📤 채팅 전송:', text);
    audioState.isProcessingResponse = true;
    userResponded = true;
    
    addBubble('user', text, false); // 사용자 입력은 중복 체크 안함
    els.input.value = '';
    
    try {
        const res = await fetch('/chat_send', {
            method:'POST', 
            headers:{'Content-Type':'application/json'}, 
            body:JSON.stringify({text})
        });
        const data = await res.json();
        const responseText = cleanText(data.text);
        
        // 응답 추가 및 TTS
        addBubble('assistant', responseText);
        speak(responseText);
        
    } catch(e) {
        addBubble('assistant', '서버 오류');
        console.warn(e);
    } finally {
        audioState.isProcessingResponse = false;
    }
};

const scheduleAutoSend = () => {
    if (timers.send) clearTimeout(timers.send);
    timers.send = setTimeout(sendChat, 1200); // 약간 늘림
};

// === 개선된 음성인식 ===
const startRecognition = () => {
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) return console.warn('음성인식 미지원');
    
    audioState.recognition = new Speech();
    audioState.recognition.lang = 'ko-KR';
    audioState.recognition.interimResults = false;
    audioState.recognition.continuous = false; // 한 번에 하나씩
    audioState.recognition.maxAlternatives = 1;
    
    audioState.recognition.onstart = () => {
        console.log('🎤 음성인식 시작');
        audioState.isSTTActive = true;
    };
    
    audioState.recognition.onresult = (e) => {
        const transcript = e.results[e.results.length-1][0].transcript.trim();
        console.log('🎤 음성인식 결과:', transcript);
        
        // 에코 검사 (최근 TTS와 유사한지 확인)
        const now = Date.now();
        if (audioState.lastTTSText && now - audioState.lastTTSTime < 5000) {
            const similarity = transcript.length > 5 && 
                             audioState.lastTTSText.includes(transcript.substring(0, 10));
            if (similarity) {
                console.log('🎤 에코 감지, 무시:', transcript);
                return;
            }
        }
        
        // 입력 처리
        if (transcript.length > 1) { // 너무 짧은 입력 무시
            els.input.value = transcript;
            userResponded = true;
            scheduleAutoSend();
        }
    };
    
    audioState.recognition.onerror = (e) => {
        console.warn('🎤 음성인식 오류:', e.error);
        audioState.isSTTActive = false;
    };
    
    audioState.recognition.onend = () => {
        console.log('🎤 음성인식 종료');
        audioState.isSTTActive = false;
        
        // TTS 재생 중이 아니라면 1초 후 재시작
        if (!audioState.isTTSPlaying) {
            setTimeout(() => {
                if (!audioState.isTTSPlaying && !audioState.isSTTActive) {
                    try {
                        audioState.recognition.start();
                        audioState.isSTTActive = true;
                    } catch(e) {
                        console.warn('음성인식 재시작 실패:', e);
                    }
                }
            }, 1000);
        }
    };
    
    // 초기 시작
    try {
        audioState.recognition.start();
        audioState.isSTTActive = true;
    } catch(e) {
        console.warn('음성인식 초기 시작 실패:', e);
    }
};

// === 소켓 이벤트 (중복 방지 강화) ===
socket.on('d_update', data => {
    const D = data?.D;
    if (D != null) updateUI(getStage(D), D);
});

socket.on('state_prompt', data => {
    if (!data) return;
    
    const ann = data.announcement?.toString() || '';
    const q = data.question?.toString() || '';
    const music = data.music?.toString() || '';
    const musicLoop = data.music_loop || false;
    const musicAction = data.music_action || '';
    
    console.log('📡 State prompt 수신:', {
        ann: ann.substring(0, 30), 
        q: q.substring(0, 30),
        music: music,
        musicAction: musicAction
    });
    
    // 음악 제어
    if (musicAction === 'play' && music) {
        playMusic(music, musicLoop);
    } else if (musicAction === 'stop') {
        stopMusic();
    }
    
    if (ann) {
        // 중앙 메시지는 showCenter에서 처리 (중복 방지 포함)
        showCenter(ann, 3.0);
        // 채팅 로그에는 한 번만 추가
        addBubble('assistant', ann);
        skipNext = ann;
    }
    
    if (q) {
        setTimeout(() => {
            addBubble('assistant', q);
            speak(q, 1.0);
            save('assistant', q);
        }, 2000); // 딜레이 증가
    }
});

socket.on('chat_message', data => {
    if (!data) return;
    
    // 중복 필터링
    if (skipNext && data.user === 'assistant' && 
        (data.text === skipNext || cleanText(data.text) === cleanText(skipNext))) {
        console.log('💬 중복 chat_message 스킵:', data.text.substring(0, 20));
        skipNext = null;
        return;
    }
    
    addBubble(data.user, data.text);
});

// === 이벤트 리스너 ===
els.input.addEventListener('input', () => {
    userResponded = true;
    scheduleAutoSend();
});

// === 초기화 및 테스트 버튼 ===
document.addEventListener('click', () => {
    if (!audioState.isSTTActive && !audioState.recognition) {
        startRecognition();
    }
}, { once: true });

window.addEventListener('load', () => {
    console.log('🚗 졸음운전 방지 시스템 로드 완료');
    console.log('👆 페이지를 클릭하여 음성인식을 활성화하세요');
    
    // 개발용 테스트 버튼 추가
    const testContainer = document.createElement('div');
    testContainer.style.cssText = `
        position: fixed; 
        top: 10px; 
        right: 10px; 
        z-index: 9999;
        background: rgba(0,0,0,0.8);
        padding: 10px;
        border-radius: 8px;
        font-size: 12px;
    `;
    
    const sounds = [
        ['L1', '/static/sounds/L1_alarm.wav'],
        ['L2', '/static/sounds/L2_alarm.wav'],
        ['L3', '/static/sounds/L3_alarm.wav'],
        ['FAIL', '/static/sounds/fail_alarm.wav'],
        ['REST', '/static/sounds/rest_mode.mp3']
    ];
    
    sounds.forEach(([name, path]) => {
        const btn = document.createElement('button');
        btn.textContent = name;
        btn.style.cssText = 'margin: 2px; padding: 4px 8px; font-size: 10px;';
        btn.onclick = () => {
            console.log('🧪 테스트:', path);
            playMusic(path, false);
        };
        testContainer.appendChild(btn);
    });
    
    const stopBtn = document.createElement('button');
    stopBtn.textContent = '⏹️';
    stopBtn.style.cssText = 'margin: 2px; padding: 4px 8px; font-size: 10px;';
    stopBtn.onclick = stopMusic;
    testContainer.appendChild(stopBtn);
    
    document.body.appendChild(testContainer);
    
    // 5초 후 테스트 버튼 숨기기
    setTimeout(() => {
        testContainer.style.display = 'none';
    }, 5000);
});