# run.py - 졸음운전 방지 시스템 v2.1 (최적화 버전)

import json
import os
import time
import threading
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# LLM 서비스 임포트 (없으면 규칙 기반으로 자동 전환)
try:
    from LLM_service import DrowsinessLLMService
    LLM_AVAILABLE = True
    print("✅ LLM 서비스 로드 완료")
except ImportError:
    LLM_AVAILABLE = False
    print("⚠️ LLM 서비스 없음 - 규칙 기반 모드로 작동")

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# === 전역 상태 관리 ===
class GlobalState:
    def __init__(self):
        self.current_d = 0
        self.current_stage = "정상"
        self.stage_payloads = self._load_stage_payloads()
        
        # TTS 목소리 설정 (중앙 관리)
        self.tts_voice = "Microsoft Heami - Korean (Korea)"
        
        # 프롬프트 반복 방지를 위한 쿨다운 설정
        self.last_prompt_time = 0
        self.prompt_cooldown = 15  # 경고 재전송 대기 시간 (초)
        
        # LLM 서비스 인스턴스 관리
        self.llm_services = {}
        self.use_llm = LLM_AVAILABLE and bool(os.getenv('OPENAI_API_KEY'))
        if self.use_llm:
            print("🤖 OpenAI API 활성화 - LLM 모드로 작동")
        else:
            print("⚠️ OpenAI API 없음 - 규칙 기반 모드로 작동")

    def _load_stage_payloads(self):
        """stage_payloads.json 로드 (폴백용)"""
        try:
            with open('stage_payloads.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("⚠️ stage_payloads.json 없음 - 기본 페이로드 사용")
            return self._get_default_payloads()

    def get_llm_service(self, session_id='default'):
        """세션별 LLM 서비스 인스턴스 반환 (없으면 생성)"""
        if not self.use_llm:
            return None
        if session_id not in self.llm_services:
            self.llm_services[session_id] = DrowsinessLLMService()
        return self.llm_services[session_id]

    def _get_default_payloads(self):
        """규칙 기반 응답을 위한 기본 페이로드 (말투 분리 및 사운드 변경)"""
        return {
            "정상": {
                "announcement": "현재 상태 정상.", 
                "music_action": "stop"
            },
            "의심경고": {
                "announcement": "주의. 졸음 신호 감지.", 
                "question": "피곤하신가요? 잠시 환기하는 것을 추천해요.",
                "music": "/static/sounds/attention_chime.wav", 
                "music_action": "play"
            },
            "L1": {
                "announcement": "졸음 상태 지속. 각성 필요.", 
                "question": "음악을 틀어드릴까요?", 
                "music": "/static/sounds/static_burst.wav",
                "music_action": "play"
            },
            "L2": {
                "announcement": "강한 졸음 신호. 즉각적인 조치 요망.", 
                "question": "창문을 열거나 에어컨을 강하게 틀어보세요.", 
                "music": "/static/sounds/metal_scrape.wav",
                "music_action": "play"
            },
            "L3": {
                "announcement": "고위험 졸음 상태. 비상 조치 권고.", 
                "question": "가까운 휴게소로 안내할까요?", 
                "music": "/static/sounds/low_buzz_high_beep.wav",
                "music_action": "play"
            },
            "FAILSAFE": {
                "announcement": "매우 위험. 즉시 비상 정차.", 
                "music": "/static/sounds/low_buzz_high_beep.wav",
                "music_action": "play"
            }
        }

state = GlobalState()
file_lock = threading.Lock()

# === 헬퍼 함수 ===
def format_text_for_display(text: str) -> str:
    """디스플레이용으로 텍스트 포맷팅. 문장 기호 뒤에 줄바꿈 추가."""
    if not text:
        return ""
    # '!', '?', '.' 바로 뒤에 줄바꿈 문자를 삽입 (이미 공백/줄바꿈이 있어도 처리)
    text = re.sub(r'([!?.]\s*)', r'\1\n', text)
    return text.strip()

def get_stage_from_d(d_value: int) -> str:
    """D값으로 단계 결정 (더 직관적으로 수정)"""
    if d_value < 30: return "정상"
    if d_value < 40: return "의심경고"
    if d_value < 50: return "집중모니터링"
    if d_value < 60: return "개선"
    if d_value < 70: return "L1"
    if d_value < 80: return "L2"
    if d_value < 90: return "L3"
    return "FAILSAFE"

def get_stage_response(stage, d_value, session_id='default', user_input=None):
    """단계별 응답 생성 (LLM 우선, 실패 시 규칙 기반으로 폴백)"""
    llm_response = None
    if state.use_llm:
        try:
            service = state.get_llm_service(session_id)
            llm_response = service.generate_contextual_response(stage, d_value, user_input)
        except Exception as e:
            print(f"LLM 서비스 호출 오류, 규칙 기반으로 폴백: {e}")
            llm_response = None # 오류 발생 시 None으로 설정하여 폴백 유도
    
    # LLM 응답이 성공적으로 왔을 경우
    if llm_response:
        # LLM 응답에 기본 tts_voice 추가
        llm_response['tts_voice'] = state.tts_voice
        return llm_response

    # LLM을 사용하지 않거나, 호출에 실패했을 경우 규칙 기반 응답 사용
    rule_based_response = state.stage_payloads.get(stage, state.stage_payloads["정상"]).copy()
    # 규칙 기반 응답에도 기본 tts_voice 추가
    if 'tts_voice' not in rule_based_response:
        rule_based_response['tts_voice'] = state.tts_voice
    return rule_based_response

def save_chat_message(user, text, session_id='default'):
    """채팅 메시지를 로컬 JSON 파일에 저장 (동시성 처리)"""
    if not text: return
    
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'session_id': session_id,
        'user': user,
        'text': text,
        'stage': state.current_stage
    }
    
    with file_lock:
        try:
            try:
                with open('chats_local.json', 'r', encoding='utf-8') as f:
                    chats = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                chats = []
            
            chats.append(log_entry)
            # 최신 1000개 로그만 유지
            with open('chats_local.json', 'w', encoding='utf-8') as f:
                json.dump(chats[-1000:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"채팅 로그 저장 실패: {e}")

# === 라우트 ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/drowny_service')
def drowny_service():
    return render_template('drowny_service.html')

@app.route('/api/state/latest', methods=['GET'])
def get_latest_state():
    """클라이언트 폴링을 위한 최신 상태 API (간소화됨)"""
    return jsonify({
        'd_value': state.current_d,
        'stage': state.current_stage,
        'timestamp': time.time(),
        'llm_enabled': state.use_llm
    })

@app.route('/ingest', methods=['POST'])
def ingest():
    """D값 수신 및 단계 변경 처리"""
    data = request.json
    if not data or 'D' not in data:
        return jsonify({'error': 'Missing D value'}), 400
    
    d_value = int(data['D'])
    session_id = data.get('session_id', 'default')
    new_stage = get_stage_from_d(d_value)
    stage_changed = (new_stage != state.current_stage)
    
    state.current_d = d_value
    state.current_stage = new_stage
    
    socketio.emit('d_update', {'D': d_value, 'stage': new_stage})
    
    if stage_changed:
        is_high_warning = new_stage in ['L1', 'L2', 'L3', 'FAILSAFE']
        current_time = time.time()

        if is_high_warning and (current_time - state.last_prompt_time < state.prompt_cooldown):
            print(f"쿨다운 활성화 중... ({int(state.prompt_cooldown - (current_time - state.last_prompt_time))}초 남음)")
        else:
            response = get_stage_response(new_stage, d_value, session_id)
            announcement = response.get('announcement', '')
            question = response.get('question', '')
            
            # 프롬프트 전송 전 텍스트 포맷팅
            response['announcement'] = format_text_for_display(announcement)
            response['question'] = format_text_for_display(question)
            
            socketio.emit('state_prompt', response)
            
            if is_high_warning:
                state.last_prompt_time = current_time
            
            if announcement:
                save_chat_message('assistant', announcement, session_id)
    
    return jsonify({'status': 'ok', 'stage': new_stage})

@app.route('/chat_send', methods=['POST'])
def chat_send():
    """사용자 채팅 메시지 처리 및 응답 생성"""
    data = request.json
    text = data.get('text', '').strip()
    session_id = data.get('session_id', 'default')
    
    if not text:
        return jsonify({'text': '무엇을 도와드릴까요?'})
    
    save_chat_message('user', text, session_id)
    
    response = get_stage_response(state.current_stage, state.current_d, session_id, user_input=text)
    
    # 응답 텍스트 조합 및 포맷팅
    response_text = response.get('announcement', '')
    if response.get('action_suggestion'):
        response_text += f" {response['action_suggestion']}"
    if not response_text:
        response_text = "네, 들었습니다. 안전 운전하세요."
    
    formatted_text = format_text_for_display(response_text)
    save_chat_message('assistant', formatted_text, session_id)
    
    socketio.emit('chat_message', {'user': 'assistant', 'text': formatted_text})
    
    return jsonify({'text': formatted_text})

# === Socket.IO 이벤트 ===
@socketio.on('connect')
def handle_connect():
    print(f'클라이언트 연결: {request.sid}')
    emit('connected', {'llm_enabled': state.use_llm})

@socketio.on('disconnect')
def handle_disconnect():
    print(f'클라이언트 연결 해제: {request.sid}')

# === 메인 실행 ===
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    print("="*50)
    print("🚗 졸음운전 방지 시스템 v2.1 시작")
    print(f"  - 모드: {'🤖 LLM' if state.use_llm else '⚙️ 규칙 기반'}")
    print(f"  - 주소: http://0.0.0.0:{port}")
    print(f"  - 디버그: {'활성화' if debug else '비활성화'}")
    print("="*50)
    
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)