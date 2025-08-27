// static/js/app.js - Socket.io + REST API 폴링 통합 완전판
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

// === 중복 업데이트 방지용 ===
let lastUpdateTime = 0;
let lastDValue = null;
const UPDATE_THROTTLE = 500; // 500ms 내 중복 업데이트 방지
let pollingInterval = null;
let socketConnected = false;

// 단계 매핑
const stages = [[30,'정상'],[40,'의심경고'],[50,'집중모니터링'],[60,'개선'],[70,'L1'],[80,'L2'],[90,'L3'],[999,'FAILSAFE']];
const labels = {'정상':'정상','의심경고':'의심경고','집중모니터링':'집중 모니터링','개선':'개선','L1':'졸음 지속\n경고 강화 L1','L2':'졸음 지속\n경고 강화 L2','L3':'졸음 지속\n경고 강화 L3','FAILSAFE':'고위험!\n즉시 정차'};
const messages = {'의심경고':['주의!\n 졸음 신호 감지',1.0],
    '집중모니터링':['졸음 상태 확인 중',0.95],'개선':['상태 개선됨. 안전 운전 하세요.',0.95],
    'L1':['졸음 지속! \n 휴식 권장!',1.0],
    'L2':['강한 졸음 신호!\n 환기 필요!!',1.1],
    'L3':['고위험 졸음 상태!\n 가족을 생각 하세요!!',1.2],
    'FAILSAFE':['고위험 상태!\n즉시 정차하세요!!',1.3]};

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
    console.log('🔍 addBubble 호출:', { who, text: text?.substring(0, 30), skipDuplicate });
    
    if (!els.log) {
        console.error('❌ chatLog 요소를 찾을 수 없음');
        return;
    }
    
    if (!text) {
        console.warn('⚠️ 텍스트가 비어있음');
        return;
    }
    
    const cleanedText = cleanText(text);
    console.log('✅ 정리된 텍스트:', cleanedText.substring(0, 50));
    
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
    
    console.log(`✅ 채팅 버블 추가됨 - ${who}: ${cleanedText.substring(0, 30)}...`);
    console.log('📊 현재 채팅로그 자식 수:', els.log.children.length);
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
    
    if (els.center.textContent === cleanedText && els.center.style.display === 'block') {
        console.log('🔔 중복 중앙메시지 방지');
        return;
    }
    
    clear(timers);
    els.center.innerHTML = cleanedText.replace(/\n/g, '<br>'); // textContent 대신 innerHTML 사용 및 \n을 <br>로 교체
    els.center.style.display = 'block';
    els.area.classList.add('center-active');
    
    speak(cleanedText, vol);
    
    timers.auto = setTimeout(() => !userResponded && save('assistant', cleanedText), 1500);
    timers.hide = setTimeout(() => {
        els.center.style.display = 'none';
        els.area.classList.remove('center-active');
    }, 5000);
};

// === 음악 및 알림 시스템 ===
let currentAudio = null;
let backgroundMusicMode = false;
let musicFiles = ['music_1.mp3', 'music_2.mp3', 'music_3.mp3', 'music_4.mp3'];

const playMusic = (musicPath, loop = false) => {
    if (!musicPath) return;
    
    console.log('🎵 음악 재생:', musicPath);
    
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
    backgroundMusicMode = false;
};

// === 랜덤 배경음악 시스템 ===
const playRandomBackgroundMusic = () => {
    if (!backgroundMusicMode) return;
    
    const randomIndex = Math.floor(Math.random() * musicFiles.length);
    const randomMusic = `/static/music/${musicFiles[randomIndex]}`;
    
    console.log('🎵 랜덤 배경음악 재생:', randomMusic);
    
    if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
    }
    
    try {
        currentAudio = new Audio(randomMusic);
        currentAudio.volume = 0.5; // 배경음악은 볼륨 낮게
        
        // 음악이 끝나면 다음 랜덤 음악 재생
        currentAudio.onended = () => {
            if (backgroundMusicMode) {
                setTimeout(playRandomBackgroundMusic, 1000); // 1초 후 다음 음악
            }
        };
        
        currentAudio.onerror = () => {
            console.warn('배경음악 재생 실패:', randomMusic);
            if (backgroundMusicMode) {
                setTimeout(playRandomBackgroundMusic, 2000); // 2초 후 재시도
            }
        };
        
        const playPromise = currentAudio.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.warn('배경음악 재생 실패:', error);
                if (backgroundMusicMode) {
                    setTimeout(playRandomBackgroundMusic, 2000); // 2초 후 재시도
                }
            });
        }
    } catch(error) {
        console.warn('배경음악 로드 실패:', error);
    }
};

const startBackgroundMusic = () => {
    if (backgroundMusicMode) return; // 이미 재생 중이면 무시
    
    backgroundMusicMode = true;
    const responseText = "음악을 틀게요~";
    
    // 채팅창에 응답 추가
    addBubble('assistant', responseText);
    speak(responseText, 1.0);
    
    setTimeout(() => {
        playRandomBackgroundMusic();
    }, 2000); // TTS 후 2초 뒤 음악 시작
};

const stopBackgroundMusic = () => {
    backgroundMusicMode = false;
    stopMusic();
    
    const responseText = "음악을 중지할게요";
    
    // 채팅창에 응답 추가
    addBubble('assistant', responseText);
    speak(responseText, 1.0);
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

// === 통합 업데이트 함수 (Socket + REST 중복 방지) ===
const handleDUpdate = (D, source) => {
    const now = Date.now();
    
    // 중복 체크 (같은 값이 500ms 내 들어오면 무시)
    if (D === lastDValue && (now - lastUpdateTime) < UPDATE_THROTTLE) {
        console.log(`🔄 중복 업데이트 스킵 (${source}): D=${D}`);
        return;
    }
    
    lastUpdateTime = now;
    lastDValue = D;
    
    console.log(`✅ 업데이트 적용 (${source}): D=${D}`);
    updateUI(getStage(D), D);
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
        
        // 위험 단계에서는 배경음악 중지
        if (['L1', 'L2', 'L3', 'FAILSAFE'].includes(stage)) {
            stopBackgroundMusic();
        }
        
        if (stageMusic[stage]) {
            playMusic(stageMusic[stage], true);
        } else if (!['L1', 'L2', 'L3', 'FAILSAFE'].includes(stage)) {
            // 정상/안전 단계에서만 기존 배경음악 유지
            // 알람 음악이 아닌 경우 음악 중지하지 않음
            if (currentAudio && currentAudio.src && 
                (currentAudio.src.includes('alarm') || currentAudio.src.includes('fail'))) {
                stopMusic();
            }
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

// === REST API 폴링 ===
const pollState = async () => {
    try {
        const res = await fetch('/api/state/latest', { 
            method: 'GET',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!res.ok) {
            console.warn(`REST API 응답 오류: ${res.status}`);
            return;
        }
        
        const data = await res.json();
        
        // 여러 가능한 응답 형식 처리
        let D = null;
        if (data.D !== undefined) {
            D = data.D;
        } else if (data.d_value !== undefined) {
            D = data.d_value;
        } else if (data.level_code !== undefined) {
            D = parseInt(data.level_code, 10);
        }
        
        if (D !== null && !isNaN(D)) {
            handleDUpdate(D, 'REST');
        }
    } catch(e) {
        // 폴링 실패는 조용히 무시 (Socket이 있으므로)
        console.debug('REST 폴링 실패 (정상일 수 있음):', e.message);
    }
};

// === 폴링 제어 ===
const startPolling = (intervalMs = 2000) => {
    if (pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(pollState, intervalMs);
    console.log(`📊 REST 폴링 시작 (${intervalMs}ms 간격)`);
};

const stopPolling = () => {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
        console.log('📊 REST 폴링 중지');
    }
};

// === 채팅 전송 (중복 방지) ===
const sendChat = async () => {
    const text = els.input.value?.trim();
    if (!text || audioState.isProcessingResponse) return;
    
    console.log('📤 채팅 전송:', text);
    audioState.isProcessingResponse = true;
    userResponded = true;
    
    addBubble('user', text, false);
    els.input.value = '';
    
    try {
        const res = await fetch('/chat_send', {
            method:'POST', 
            headers:{'Content-Type':'application/json'}, 
            body:JSON.stringify({text})
        });
        const data = await res.json();
        const responseText = cleanText(data.text);
        
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
    timers.send = setTimeout(sendChat, 1200);
};

// === 개선된 음성인식 ===
const startRecognition = () => {
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) return console.warn('음성인식 미지원');
    
    audioState.recognition = new Speech();
    audioState.recognition.lang = 'ko-KR';
    audioState.recognition.interimResults = false;
    audioState.recognition.continuous = false;
    audioState.recognition.maxAlternatives = 1;
    
    audioState.recognition.onstart = () => {
        console.log('🎤 음성인식 시작');
        audioState.isSTTActive = true;
    };
    
    audioState.recognition.onresult = (e) => {
        const transcript = e.results[e.results.length-1][0].transcript.trim();
        console.log('🎤 음성인식 결과:', transcript);
        
        const now = Date.now();
        if (audioState.lastTTSText && now - audioState.lastTTSTime < 5000) {
            const similarity = transcript.length > 5 && 
                             audioState.lastTTSText.includes(transcript.substring(0, 10));
            if (similarity) {
                console.log('🎤 에코 감지, 무시:', transcript);
                return;
            }
        }
        
        // 음악 제어 명령어 처리 (안전한 단계에서만)
        const safeStages = ['정상', '의심경고', '집중모니터링', '개선'];
        if (safeStages.includes(lastStage)) {
            const musicStartKeywords = ['음악', '노래', '틀어', '재생', '들려줘', '음악 틀어', '노래 틀어'];
            const musicStopKeywords = ['음악 꺼', '음악 중지', '음악 멈춰', '노래 꺼', '노래 중지', '노래 멈춰', '그만', '꺼줘', '중지해', '멈춰줘'];
            
            // 디버깅 로그 추가
            console.log('🎵 음성 명령 확인:', transcript);
            console.log('🎵 현재 배경음악 모드:', backgroundMusicMode);
            
            const hasStartKeyword = musicStartKeywords.some(keyword => transcript.includes(keyword));
            const hasStopKeyword = musicStopKeywords.some(keyword => transcript.includes(keyword));
            
            console.log('🎵 시작 키워드 감지:', hasStartKeyword);
            console.log('🎵 중지 키워드 감지:', hasStopKeyword);
            
            if (hasStartKeyword && !backgroundMusicMode) {
                console.log('🎵 음악 재생 요청 감지');
                // 채팅창에 사용자 메시지 추가
                addBubble('user', transcript, false);
                startBackgroundMusic();
                return; // 일반 채팅으로 보내지 않음
            } else if (hasStopKeyword) { // backgroundMusicMode 조건 제거
                console.log('🎵 음악 중지 요청 감지');
                // 채팅창에 사용자 메시지 추가
                addBubble('user', transcript, false);
                stopBackgroundMusic();
                return; // 일반 채팅으로 보내지 않음
            }
        }
        
        if (transcript.length > 1) {
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
    
    try {
        audioState.recognition.start();
        audioState.isSTTActive = true;
    } catch(e) {
        console.warn('음성인식 초기 시작 실패:', e);
    }
};

// === Socket.io 이벤트 ===
socket.on('connect', () => {
    console.log('🟢 Socket 연결됨');
    socketConnected = true;
    // Socket 연결되면 폴링을 백업 모드로 (5초)
    startPolling(5000);
});

socket.on('disconnect', () => {
    console.log('🔴 Socket 끊김, REST 폴링 강화');
    socketConnected = false;
    // Socket 끊기면 폴링을 메인 모드로 (1초)
    startPolling(1000);
});

socket.on('connect_error', (error) => {
    console.warn('⚠️ Socket 연결 오류:', error.message);
    if (!socketConnected) {
        // 초기 연결 실패시 폴링 즉시 시작
        startPolling(1000);
    }
});

socket.on('d_update', data => {
    const D = data?.D;
    if (D != null) {
        handleDUpdate(D, 'Socket');
    }
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
    
    if (musicAction === 'play' && music) {
        playMusic(music, musicLoop);
    } else if (musicAction === 'stop') {
        stopMusic();
    }
    
    if (ann) {
        showCenter(ann, 3.0);
        addBubble('assistant', ann);
        skipNext = ann;
    }
    
    if (q) {
        setTimeout(() => {
            addBubble('assistant', q);
            speak(q, 1.0);
            save('assistant', q);
        }, 2000);
    }
});

socket.on('chat_message', data => {
    if (!data) return;
    
    if (skipNext && data.user === 'assistant' && 
        (data.text === skipNext || cleanText(data.text) === cleanText(skipNext))) {
        console.log('💬 중복 chat_message 스킵:', data.text.substring(0, 20));
        skipNext = null;
        return;
    }
    
    addBubble(data.user, data.text);
});

// === 음악 명령 Socket 이벤트 ===
socket.on('music_command', data => {
    if (!data || !data.action) return;
    
    console.log('🎵 음악 명령 수신:', data.action);
    
    if (data.action === 'start_background_music') {
        startBackgroundMusic();
    } else if (data.action === 'stop_background_music') {
        stopBackgroundMusic();
    }
});

// === 이벤트 리스너 ===
els.input.addEventListener('input', () => {
    userResponded = true;
    scheduleAutoSend();
});

// === 세션 ID 처리 (stream_service와 연동) ===
const urlParams = new URLSearchParams(window.location.search);
const sessionId = urlParams.get('sid');
if (sessionId) {
    console.log('📹 스트리밍 세션 ID:', sessionId);
    socket.emit('register_session', { sid: sessionId });
}

// === 초기화 ===
document.addEventListener('click', () => {
    if (!audioState.isSTTActive && !audioState.recognition) {
        startRecognition();
    }
}, { once: true });

window.addEventListener('load', () => {
    console.log('🚗 졸음운전 방지 시스템 로드 완료');
    console.log('📡 Socket.io + REST API 하이브리드 모드');
    console.log('👆 페이지를 클릭하여 음성인식을 활성화하세요');
    
    // REST API 폴링 시작 (초기값: 2초)
    startPolling(2000);
    
    // 개발용 테스트 버튼 추가
    const testContainer = document.createElement('div');
    testContainer.id = 'testPanel';
    testContainer.style.cssText = `
        position: fixed; 
        top: 10px; 
        right: 10px; 
        z-index: 9999;
        background: rgba(0,0,0,0.8);
        padding: 10px;
        border-radius: 8px;
        font-size: 12px;
        color: white;
    `;
    
    // 연결 상태 표시
    const statusDiv = document.createElement('div');
    statusDiv.id = 'connectionStatus';
    statusDiv.style.cssText = 'margin-bottom: 8px; font-size: 10px;';
    statusDiv.innerHTML = `
        Socket: <span id="socketStatus">⚫</span> | 
        REST: <span id="restStatus">⚫</span>
    `;
    testContainer.appendChild(statusDiv);
    
    // 사운드 테스트 버튼들
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
    
    // 음악 테스트 버튼 추가
    const musicBtn = document.createElement('button');
    musicBtn.textContent = '🎵';
    musicBtn.style.cssText = 'margin: 2px; padding: 4px 8px; font-size: 10px; background: #FF9800;';
    musicBtn.onclick = () => {
        if (backgroundMusicMode) {
            stopBackgroundMusic();
        } else {
            startBackgroundMusic();
        }
    };
    testContainer.appendChild(musicBtn);
    
    const stopBtn = document.createElement('button');
    stopBtn.textContent = '⏹️';
    stopBtn.style.cssText = 'margin: 2px; padding: 4px 8px; font-size: 10px;';
    stopBtn.onclick = stopMusic;
    testContainer.appendChild(stopBtn);
    
    // REST 테스트 버튼
    const restBtn = document.createElement('button');
    restBtn.textContent = 'REST';
    restBtn.style.cssText = 'margin: 2px; padding: 4px 8px; font-size: 10px; background: #4CAF50;';
    restBtn.onclick = () => {
        console.log('🧪 REST API 테스트');
        pollState();
    };
    testContainer.appendChild(restBtn);
    
    document.body.appendChild(testContainer);
    
    // 연결 상태 업데이트
    setInterval(() => {
        const socketEl = document.getElementById('socketStatus');
        const restEl = document.getElementById('restStatus');
        if (socketEl) socketEl.textContent = socketConnected ? '🟢' : '🔴';
        if (restEl) restEl.textContent = pollingInterval ? '🟢' : '⚫';
    }, 1000);
    
    // 10초 후 테스트 패널 숨기기 (개발 모드가 아니면)
    const isDev = localStorage.getItem('devMode') === 'true';
    if (!isDev) {
        setTimeout(() => {
            testContainer.style.display = 'none';
            console.log('💡 개발 패널 활성화: localStorage.setItem("devMode", "true")');
        }, 10000);
    }
});

// === 개발자 도구 명령어 ===
window.drowsyDev = {
    showPanel: () => {
        const panel = document.getElementById('testPanel');
        if (panel) panel.style.display = 'block';
        localStorage.setItem('devMode', 'true');
    },
    hidePanel: () => {
        const panel = document.getElementById('testPanel');
        if (panel) panel.style.display = 'none';
        localStorage.setItem('devMode', 'false');
    },
    testD: (value) => {
        console.log(`🧪 D값 테스트: ${value}`);
        handleDUpdate(value, 'Manual');
    },
    stopPolling: () => stopPolling(),
    startPolling: (ms) => startPolling(ms || 2000),
    status: () => {
        console.log({
            socket: socketConnected,
            polling: !!pollingInterval,
            lastD: lastDValue,
            stage: lastStage,
            tts: audioState.isTTSPlaying,
            stt: audioState.isSTTActive
        });
    }
};