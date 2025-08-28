from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, join_room, emit
from dotenv import load_dotenv
import os
import time
import json
import random
import traceback
from threading import Thread

# 환경 변수 로드
load_dotenv()

# 로컬 모듈 임포트
from user_service import (
    validate_user, create_user, create_user_session, 
    insert_state_history, get_active_sessions, 
    get_latest_state_for_session, get_user_by_session_token,
    get_latest_states_for_all_active_sessions
)
from user_state import stage_from_level

# Flask 앱 초기화
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "drowsy-driver-prevention-secret-2025")

# Socket.IO 초기화
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# StateDBWatcher 초기화 (간단한 버전)
state_watcher = None

def init_state_watcher():
    """StateDBWatcher 초기화 (단순화)"""
    global state_watcher
    try:
        print("ℹ️ StateDBWatcher 비활성화 (단순화)")
        state_watcher = None
    except Exception as e:
        print(f"❌ StateDBWatcher 초기화 실패: {e}")
        state_watcher = None

# 서버 시작 시 상태 감시자 초기화
def init_app():
    """앱 초기화"""
    init_state_watcher()

def get_recommendation_for_stage(stage):
    """단계별 권장 사항 반환"""
    recommendations = {
        "정상": {
            "message": "운전 상태가 양호합니다. 계속 안전 운전하세요.",
            "actions": ["정상 운전 지속"],
            "audio_file": None
        },
        "의심경고": {
            "message": "약간의 피로 징후가 감지되었습니다. 주의하세요.",
            "actions": ["환기하기", "음악 볼륨 높이기"],
            "audio_file": "L1_alarm.wav"
        },
        "집중모니터링": {
            "message": "집중력 저하가 감지되었습니다. 더욱 주의하세요.",
            "actions": ["창문 열기", "냉방 강화", "스트레칭"],
            "audio_file": "L1_alarm.wav"
        },
        "개선": {
            "message": "운전 상태를 개선해야 합니다. 휴식을 고려하세요.",
            "actions": ["휴게소 찾기", "동승자와 대화", "음료 마시기"],
            "audio_file": "L2_alarm.wav"
        },
        "L1": {
            "message": "경고! 졸음이 감지되었습니다. 즉시 조치하세요.",
            "actions": ["안전한 곳에 정차", "냉수로 세면", "스트레칭"],
            "audio_file": "L1_alarm.wav"
        },
        "L2": {
            "message": "위험! 심각한 졸음 상태입니다. 운전을 중단하세요.",
            "actions": ["즉시 안전한 곳에 정차", "10분 이상 휴식", "교대 운전자 요청"],
            "audio_file": "L2_alarm.wav"
        },
        "L3": {
            "message": "매우 위험! 운전을 즉시 중단하고 충분한 휴식을 취하세요.",
            "actions": ["즉시 운전 중단", "30분 이상 휴식", "잠시 수면", "대체 교통수단 고려"],
            "audio_file": "L3_alarm.wav"
        },
        "FAILSAFE": {
            "message": "시스템 오류로 인한 안전 모드입니다. 즉시 안전한 곳에 정차하세요.",
            "actions": ["즉시 정차", "시스템 점검", "수동 운전"],
            "audio_file": "fail_alarm.wav"
        }
    }
    
    return recommendations.get(stage, recommendations["정상"])

# ============================================
# 유틸리티 함수들
# ============================================

def save_chat_message(user_id, session_token, sender, message, stage=None):
    """채팅 메시지 저장 (현재 비활성화 - chat_messages 테이블 없음)"""
    try:
        print(f"💬 Chat [{sender}]: {message} (stage: {stage})")
        return True
    except Exception as e:
        print(f"❌ Chat save error: {e}")
        return False

def generate_llm_response(user_message, stage, session_token):
    """LLM 기반 응답 생성"""
    try:
        from LLM_service import process_user_input
        return process_user_input(user_message, stage, session_token)
    except ImportError:
        print("LLM 서비스를 사용할 수 없습니다. 기본 응답 사용")
        recommendations = get_recommendation_for_stage(stage)
        return {
            "message": recommendations.get("message", "안전운전 하세요."),
            "actions": recommendations.get("actions", []),
            "audio_file": recommendations.get("audio_file")
        }
    except Exception as e:
        print(f"LLM 응답 생성 오류: {e}")
        recommendations = get_recommendation_for_stage(stage)
        return {
            "message": recommendations.get("message", "안전운전 하세요."),
            "actions": recommendations.get("actions", []),
            "audio_file": recommendations.get("audio_file")
        }

# ============================================
# 웹 라우트들
# ============================================

@app.route("/")
def home():
    """홈페이지 - 로그인으로 리다이렉트"""
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    """로그인 페이지"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if not username or not password:
            return render_template("login.html", error="사용자명과 비밀번호를 입력해주세요")
        
        user = validate_user(username, password)
        if user:
            session_token = create_user_session(user["id"])
            session["user_id"] = user["id"]
            session["session_token"] = session_token
            session["username"] = user["username"]
            
            print(f"✅ 로그인 성공: {username} (session: {session_token[:8]}...)")
            return redirect("/stream_service")
        else:
            return render_template("login.html", error="잘못된 사용자명 또는 비밀번호입니다")
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """회원가입 페이지"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        name = request.form.get("name", "")
        email = request.form.get("email", "")
        
        if not username or not password:
            return render_template("register.html", error="사용자명과 비밀번호는 필수입니다")
        
        try:
            create_user(username, password, name, email)
            print(f"✅ 회원가입 성공: {username}")
            return redirect("/login")
        except Exception as e:
            print(f"❌ 회원가입 실패: {e}")
            return render_template("register.html", error="회원가입 실패: 이미 존재하는 사용자명일 수 있습니다")
    
    return render_template("register.html")

@app.route("/stream_service")
def stream_service():
    """스트림 서비스 메인 페이지"""
    if "user_id" not in session:
        return redirect("/login")
    return render_template("stream_service.html")

@app.route("/drowny_service")
def drowny_service():
    """졸음 방지 서비스 페이지"""
    if "user_id" not in session:
        return redirect("/login")
    return render_template("drowny_service.html")

@app.route("/logout")
def logout():
    """로그아웃"""
    username = session.get("username", "Unknown")
    session.clear()
    print(f"👋 로그아웃: {username}")
    return redirect("/login")

# ============================================
# 중요! 비디오 스트림 업로드 엔드포인트
# ============================================

@app.route("/stream/upload", methods=["POST"])
def stream_upload():
    """비디오 프레임 업로드 처리"""
    try:
        # 헤더에서 세션 정보 추출
        session_id = request.headers.get('X-Session-Id')
        seq = request.headers.get('X-Seq', '0')
        
        if not session_id:
            return jsonify({"error": "No session ID"}), 400
        
        # JPEG 데이터 받기
        jpeg_data = request.data
        
        # TODO: 실제로는 이 데이터를 AI 모델로 전송하여 졸음 감지
        # 여기서는 더미 응답
        print(f"📷 Frame received: session={session_id}, seq={seq}, size={len(jpeg_data)} bytes")
        
        # 더미 졸음 레벨 생성 (실제로는 AI 분석 결과)
        dummy_level = random.choice([30, 30, 30, 40, 40, 50])  # 대부분 정상
        
        # 상태 업데이트 (로그인된 사용자만)
        if "user_id" in session:
            stage = stage_from_level(dummy_level)
            insert_state_history(
                user_id=session["user_id"],
                session_token=session.get("session_token"),
                level_code=dummy_level,
                stage=stage
            )
            
            # Socket.IO로 실시간 전송
            socketio.emit('d_update', {
                'D': dummy_level,
                'stage': stage,
                'timestamp': int(time.time())
            }, room=f"user_{session.get('username')}")
        
        return jsonify({
            "success": True,
            "saved": f"frame_{seq}",
            "level": dummy_level
        })
        
    except Exception as e:
        print(f"❌ /stream/upload 오류: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/analyze_voice_command", methods=["POST"])
def analyze_voice_command():
    """GPT API를 활용한 지능형 음성 명령 분석"""
    try:
        data = request.get_json()
        text = data.get("text", "").strip()
        context = data.get("context", {})
        
        if not text:
            return jsonify({"error": "Empty text"}), 400
        
        # LLM 서비스를 통한 음성 명령 분석
        try:
            from LLM_service import DrowsinessLLMService
            
            service = DrowsinessLLMService()
            result = service.analyze_voice_command(text, context)
            
            return jsonify(result)
            
        except ImportError:
            print("LLM 서비스 없음, 기본 분석 사용")
            # 기본 키워드 기반 분석
            text_lower = text.lower()
            
            music_start_words = ['음악', '노래', '뮤직', 'music', '틀어', '재생', '플레이', 'play', '켜', '시작']
            music_stop_words = ['꺼', '중지', '멈춰', '스톱', 'stop', '끝', '그만', '정지']
            
            if any(word in text_lower for word in music_start_words):
                return jsonify({
                    "action": "start_music",
                    "confidence": 0.8,
                    "reasoning": "음악 재생 키워드 감지"
                })
            elif any(word in text_lower for word in music_stop_words):
                return jsonify({
                    "action": "stop_music", 
                    "confidence": 0.8,
                    "reasoning": "음악 중지 키워드 감지"
                })
            else:
                return jsonify({
                    "action": "general_chat",
                    "confidence": 0.9,
                    "reasoning": "일반 대화로 판단"
                })
                
        except Exception as e:
            print(f"음성 명령 분석 오류: {e}")
            return jsonify({
                "action": "general_chat",
                "confidence": 0.5,
                "reasoning": f"분석 실패: {str(e)}"
            })
            
    except Exception as e:
        print(f"❌ /api/analyze_voice_command 오류: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/chat_send", methods=["POST"])
def chat_send():
    """프론트엔드에서 채팅 메시지를 받아 처리"""
    try:
        data = request.get_json()
        text = data.get("text", "").strip()
        
        if not text:
            return jsonify({"error": "Empty message"}), 400
            
        # 세션 정보 확인
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
            
        session_token = session.get("session_token")
        username = session.get("username")
        
        # 현재 상태 확인
        current_state = get_latest_state_for_session(session_token)
        stage = current_state["stage"] if current_state else "정상"
        
        # LLM 응답 생성 시도
        try:
            from LLM_service import DrowsinessLLMService
            
            service = DrowsinessLLMService()
            response = service.generate_contextual_response(
                stage=stage, 
                d_value=current_state["level_code"] if current_state else 30,
                user_input=text
            )
            
            # 자연스러운 응답 텍스트만 추출 (시스템 메시지 제거)
            announcement = response.get('announcement', '')
            question = response.get('question', '')
            
            # "announcement:", "question:" 같은 시스템 태그 제거
            announcement_clean = announcement.replace('announcement:', '').replace('안ouncement:', '').strip()
            question_clean = question.replace('question:', '').strip()
            
            # 자연스러운 대화문만 조합
            if question_clean:
                response_text = question_clean  # 질문이 있으면 질문만 (더 자연스러움)
            elif announcement_clean:
                response_text = announcement_clean
            else:
                response_text = "안전운전 하세요."
            
        except ImportError as e:
            print(f"LLM 모듈 임포트 오류: {e}")
            # OpenAI 없이 기본 응답
            responses = {
                "정상": "네, 알겠습니다. 안전운전 하세요!",
                "의심경고": "주의하세요! 잠시 휴식이 필요할 수 있습니다.",
                "집중모니터링": "집중력이 떨어지고 있어요. 창문을 열어보시겠어요?",
                "개선": "상태가 개선되고 있네요. 계속 주의해주세요.",
                "L1": "위험합니다! 즉시 휴식을 취하세요!",
                "L2": "매우 위험! 즉시 정차하세요!",
                "L3": "긴급상황! 즉시 안전한 곳에 정차하세요!",
                "FAILSAFE": "시스템 오류. 안전을 최우선으로 하세요."
            }
            response_text = responses.get(stage, "안전운전 하세요.")
            
        except Exception as e:
            print(f"LLM 서비스 일반 오류: {e}")
            response_text = f"현재 {stage} 상태입니다. 안전운전 하세요."
        
        # Socket.IO로 브로드캐스트
        socketio.emit('chat_message', {
            'user': 'assistant',
            'text': response_text,
            'timestamp': int(time.time())
        }, room=f"user_{username}")
        
        return jsonify({
            "success": True,
            "text": response_text,
            "stage": stage
        })
        
    except Exception as e:
        print(f"❌ /chat_send 오류: {e}")
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/save_msg", methods=["POST"])
def save_msg():
    """메시지 저장 (현재는 로그만)"""
    try:
        data = request.get_json()
        user = data.get("user")
        text = data.get("text")
        
        print(f"💬 메시지 저장: [{user}] {text}")
        
        return jsonify({"success": True})
        
    except Exception as e:
        print(f"❌ /save_msg 오류: {e}")
        return jsonify({"error": "Save failed"}), 500

@app.route("/api/state/latest", methods=["GET"])
def api_state_latest():
    """현재 사용자의 최신 상태 반환"""
    try:
        # 세션 확인
        if "user_id" not in session:
            # 로그인 안 된 경우 기본값 반환
            return jsonify({
                "success": True,
                "D": 30,
                "d_value": 30,
                "level_code": 30,
                "stage": "정상",
                "timestamp": int(time.time())
            })
            
        session_token = session.get("session_token")
        if not session_token:
            return jsonify({
                "success": True,
                "D": 30,
                "d_value": 30,
                "level_code": 30,
                "stage": "정상",
                "timestamp": int(time.time())
            })
            
        # 최신 상태 조회
        state = get_latest_state_for_session(session_token)
        
        if state:
            return jsonify({
                "success": True,
                "D": state["level_code"],  # app.js에서 기대하는 필드명
                "d_value": state["level_code"],
                "level_code": state["level_code"],
                "stage": state["stage"],
                "timestamp": int(state["created_at"].timestamp()) if state["created_at"] else int(time.time())
            })
        else:
            # 상태가 없으면 기본값 반환
            return jsonify({
                "success": True,
                "D": 30,
                "d_value": 30,
                "level_code": 30,
                "stage": "정상",
                "timestamp": int(time.time())
            })
            
    except Exception as e:
        print(f"❌ /api/state/latest 오류: {e}")
        traceback.print_exc()
        return jsonify({"error": "Internal server error"}), 500

# ============================================
# API 엔드포인트들
# ============================================

@app.route("/api/state", methods=["POST"])
def api_state():
    """외부에서 상태 데이터를 받는 API (video_data_collector용)"""
    try:
        data = request.get_json()
        session_token = data.get("session_token")
        level_code = data.get("level_code")
        
        if not session_token or level_code is None:
            return jsonify({"error": "Missing session_token or level_code"}), 400
        
        # level_code 검증
        stage = stage_from_level(level_code)
        if not stage:
            return jsonify({"error": f"Invalid level_code: {level_code}"}), 400
        
        # 세션으로 사용자 찾기
        user_info = get_user_by_session_token(session_token)
        if not user_info:
            return jsonify({"error": "Invalid or expired session"}), 401
        
        # 상태 히스토리에 저장
        insert_state_history(user_info["user_id"], session_token, level_code, stage)
        
        # Socket.IO로 실시간 업데이트 전송
        update_data = {
            'session_token': session_token,
            'user_id': user_info["user_id"],
            'username': user_info['username'],
            'level_code': level_code,
            'stage': stage,
            'timestamp': int(time.time())
        }
        
        print(f"📡 상태 업데이트 전송 시작: {user_info['username']} -> {stage}")
        
        # 1. 해당 사용자 룸에 전송
        user_room = f"user_{user_info['username']}"
        try:
            socketio.emit('state_update', update_data, room=user_room)
            socketio.emit('d_update', {'D': level_code}, room=user_room)
            print(f"  ✅ 사용자 룸 전송: {user_room}")
        except Exception as e:
            print(f"  ❌ 사용자 룸 전송 실패: {e}")
        
        # 2. 전체 사용자 룸에도 전송
        try:
            socketio.emit('state_update', update_data, room="all_users")
            socketio.emit('d_update', {'D': level_code}, room="all_users")
            print(f"  ✅ 전체 룸 전송: all_users")
        except Exception as e:
            print(f"  ❌ 전체 룸 전송 실패: {e}")
        
        # 3. 일반 브로드캐스트도 유지
        try:
            socketio.emit('state_update', update_data)
            socketio.emit('d_update', {'D': level_code})
            print(f"  ✅ 브로드캐스트 전송 완료")
        except Exception as e:
            print(f"  ❌ 브로드캐스트 전송 실패: {e}")
        
        print(f"📊 상태 업데이트 완료: {user_info['username']} -> {stage} (level: {level_code})")
        
        return jsonify({
            "success": True, 
            "stage": stage,
            "user": user_info['username']
        })
        
    except Exception as e:
        print(f"❌ API /state 오류: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/sessions", methods=["GET"])
def api_sessions():
    """활성 세션 목록 조회"""
    try:
        sessions = get_active_sessions()
        return jsonify({
            "success": True,
            "sessions": sessions,
            "count": len(sessions)
        })
    except Exception as e:
        print(f"❌ API /sessions 오류: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/session/<session_token>/state", methods=["GET"])
def api_session_state(session_token):
    """특정 세션의 최신 상태 조회"""
    try:
        state = get_latest_state_for_session(session_token)
        if state:
            return jsonify({
                "success": True,
                "state": state
            })
        else:
            return jsonify({
                "success": True,
                "state": None,
                "message": "No state history found"
            })
    except Exception as e:
        print(f"❌ API /session/{session_token}/state 오류: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """채팅 메시지 처리 API"""
    try:
        data = request.get_json()
        message = data.get("message")
        session_token = data.get("session_token") or session.get("session_token")
        
        if not message or not session_token:
            return jsonify({"error": "Missing message or session_token"}), 400
        
        # 사용자 정보 확인
        user_info = get_user_by_session_token(session_token)
        if not user_info:
            return jsonify({"error": "Invalid session"}), 401
        
        # 현재 상태 확인
        current_state = get_latest_state_for_session(session_token)
        stage = current_state["stage"] if current_state else "정상"
        
        # 사용자 메시지 저장
        save_chat_message(user_info["user_id"], session_token, "user", message, stage)
        
        # LLM 응답 생성
        llm_response = generate_llm_response(message, stage, session_token)
        
        # AI 응답 저장
        save_chat_message(user_info["user_id"], session_token, "assistant", 
                         llm_response.get("message", ""), stage)
        
        # Socket.IO로 실시간 전송
        socketio.emit('chat_message', {
            'session_token': session_token,
            'username': user_info['username'],
            'message': message,
            'sender': 'user',
            'timestamp': int(time.time())
        })
        
        socketio.emit('chat_message', {
            'session_token': session_token,
            'username': 'Assistant',
            'message': llm_response.get("message", ""),
            'sender': 'assistant',
            'timestamp': int(time.time()),
            'actions': llm_response.get("actions", []),
            'audio_file': llm_response.get("audio_file")
        })
        
        return jsonify({
            "success": True,
            "response": llm_response
        })
        
    except Exception as e:
        print(f"❌ Chat API 오류: {e}")
        return jsonify({"error": "Internal server error"}), 500

# ============================================
# 테스트용 API 엔드포인트들
# ============================================

@app.route("/api/test/force_event/<int:level_code>", methods=["GET"])
def test_force_event(level_code):
    """강제로 Socket.IO 이벤트를 발생시키는 테스트 엔드포인트"""
    try:
        stage = stage_from_level(level_code)
        if not stage:
            return jsonify({"error": f"Invalid level_code: {level_code}"}), 400
        
        # 실제 활성 사용자에게 테스트 이벤트 발생
        try:
            active_sessions = get_active_sessions()
            if active_sessions:
                # 첫 번째 활성 사용자에게 테스트 이벤트 전송
                user_session = active_sessions[0]
                username = user_session['username']
                session_token = user_session['session_token']
                
                # 상태 히스토리에 저장
                insert_state_history(
                    user_id=user_session['user_id'],
                    session_token=session_token,
                    level_code=level_code,
                    stage=stage
                )
                
                update_data = {
                    'session_token': session_token,
                    'user_id': user_session['user_id'],
                    'username': username,
                    'level_code': level_code,
                    'stage': stage,
                    'timestamp': int(time.time())
                }
                
                # Socket.IO 이벤트 발생
                socketio.emit('d_update', {'D': level_code}, room=f"user_{username}")
                socketio.emit('state_update', update_data, room=f"user_{username}")
                socketio.emit('state_update', update_data, room="all_users")
                socketio.emit('state_update', update_data)
                
                print(f"🧪 실제 사용자 테스트 이벤트: {username} -> {stage} (level: {level_code})")
                
                return jsonify({
                    "success": True,
                    "message": f"Socket.IO event sent to {username}: {stage} (level: {level_code})",
                    "target_user": username
                })
            else:
                # 활성 사용자가 없으면 테스트용 데이터로 전송
                socketio.emit('d_update', {'D': level_code})
                socketio.emit('state_update', {
                    'session_token': 'test-session-' + str(int(time.time())),
                    'user_id': 999,
                    'username': 'test-user',
                    'level_code': level_code,
                    'stage': stage,
                    'timestamp': int(time.time())
                })
                
                print(f"🧪 테스트 이벤트 발생 (활성 사용자 없음): {stage} (level: {level_code})")
                
                return jsonify({
                    "success": True,
                    "message": f"Socket.IO test event emitted: {stage} (level: {level_code})",
                    "note": "No active users found, sent test data"
                })
                
        except Exception as e:
            print(f"❌ 활성 사용자 조회 실패: {e}")
            # 기본 테스트 이벤트
            socketio.emit('d_update', {'D': level_code})
            socketio.emit('state_update', {
                'session_token': 'test-session-' + str(int(time.time())),
                'user_id': 999,
                'username': 'test-user',
                'level_code': level_code,
                'stage': stage,
                'timestamp': int(time.time())
            })
            
            return jsonify({
                "success": True,
                "message": f"Socket.IO fallback event emitted: {stage} (level: {level_code})",
                "error": str(e)
            })
        
    except Exception as e:
        print(f"❌ 테스트 이벤트 오류: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/test/sequence", methods=["GET"])
def test_sequence():
    """연속 상태 변화 테스트 (정상 → L3까지)"""
    def emit_sequence():
        sequence = [30, 40, 50, 60, 70, 80, 90]  # 정상 → L3까지
        test_session = f'test-sequence-{int(time.time())}'
        
        print(f"🧪 시퀀스 테스트 시작: {len(sequence)}개 단계")
        
        for i, level_code in enumerate(sequence):
            stage = stage_from_level(level_code)
            socketio.emit('d_update', {'D': level_code})
            socketio.emit('state_update', {
                'session_token': test_session,
                'user_id': 998,
                'username': f'sequence-test',
                'level_code': level_code,
                'stage': stage,
                'timestamp': int(time.time())
            })
            print(f"  📊 {i+1}/{len(sequence)}: {stage} (level: {level_code})")
            time.sleep(2)
        
        print(f"✅ 시퀀스 테스트 완료")
    
    Thread(target=emit_sequence, daemon=True).start()
    return jsonify({
        "success": True, 
        "message": "Sequence test started (7 stages, 2s interval)"
    })

# ============================================
# Socket.IO 이벤트 핸들러들
# ============================================

@socketio.on('connect')
def handle_connect():
    """클라이언트 연결"""
    print(f"🔗 클라이언트 연결: {request.sid}")
    
    # 모든 클라이언트를 기본 룸에 추가
    join_room("all_users")
    
    # 기본 연결 확인 메시지
    emit('connection_status', {
        'status': 'connected',
        'server_time': int(time.time()),
        'message': '서버에 연결되었습니다.'
    })

@socketio.on('user_login')
def handle_user_login(data):
    """사용자 로그인 시 호출되는 이벤트"""
    try:
        session_token = data.get('session_token')
        username = data.get('username')
        
        print(f"🔑 로그인 요청: {username} ({session_token[:8] if session_token else 'None'}...)")
        
        if not session_token or not username:
            print(f"❌ 로그인 데이터 누락: token={bool(session_token)}, user={bool(username)}")
            emit('error', {'message': 'Missing session_token or username'})
            return
        
        # 사용자 정보 검증
        user_info = get_user_by_session_token(session_token)
        if not user_info:
            print(f"❌ 세션 토큰 무효: {session_token[:8]}...")
            emit('error', {'message': 'Invalid session token'})
            return
            
        if user_info['username'] != username:
            print(f"❌ 사용자명 불일치: {user_info['username']} != {username}")
            emit('error', {'message': 'Username mismatch'})
            return
        
        # 사용자별 룸에 join
        user_room = f"user_{username}"
        
        try:
            join_room(user_room)
            join_room("all_users")
            print(f"✅ 룸 참여 성공: {username} -> {user_room}")
        except Exception as join_error:
            print(f"❌ 룸 참여 실패: {join_error}")
            emit('error', {'message': f'Room join failed: {str(join_error)}'})
            return
        
        # 연결 확인 메시지 전송
        response_data = {
            'status': 'logged_in',
            'server_time': int(time.time()),
            'username': username,
            'session_token': session_token[:8] + '...',
            'room': user_room,
            'message': f'{username}님이 연결되었습니다'
        }
        
        emit('connection_status', response_data)
        print(f"📡 연결 상태 전송: {username}")
        
        # 현재 상태 정보 전송
        try:
            current_state = get_latest_state_for_session(session_token)
            if current_state:
                state_data = {
                    'session_token': session_token,
                    'user_id': current_state['user_id'],
                    'username': username,
                    'level_code': current_state['level_code'],
                    'stage': current_state['stage'],
                    'timestamp': int(current_state['created_at'].timestamp()) if current_state['created_at'] else int(time.time())
                }
                emit('state_update', state_data)
                emit('d_update', {'D': current_state['level_code']})
                print(f"📊 현재 상태 전송: {username} -> {current_state['stage']}")
            else:
                print(f"ℹ️ {username}의 상태 이력 없음")
        except Exception as e:
            print(f"❌ 현재 상태 전송 실패: {e}")
            
    except Exception as e:
        print(f"❌ 사용자 로그인 처리 오류: {e}")
        traceback.print_exc()
        emit('error', {'message': f'Login processing failed: {str(e)}'})

@socketio.on('disconnect')
def handle_disconnect():
    """클라이언트 연결 해제"""
    print(f"🔌 클라이언트 연결 해제: {request.sid}")

@socketio.on('join_room')
def handle_join_room(data):
    """룸 참여 (레거시 지원)"""
    try:
        room = data.get('room', 'default') if data else 'default'
        join_room(room)
        print(f"🏠 클라이언트 {request.sid} 룸 참여: {room}")
        
        # 룸 참여 확인
        emit('room_joined', {'room': room, 'status': 'success'})
                
    except Exception as e:
        print(f"❌ 룸 참여 오류: {e}")
        emit('error', {'message': f'Room join failed: {str(e)}'})

@socketio.on('ping')
def handle_ping():
    """연결 테스트용 핑"""
    emit('pong', {'timestamp': int(time.time())})

@socketio.on('chat_message')
def handle_chat_message(data):
    """채팅 메시지 처리"""
    try:
        message = data.get('message')
        session_token = data.get('session_token')
        
        if not message or not session_token:
            emit('error', {'message': 'Invalid message data'})
            return
        
        # 사용자 정보 확인
        user_info = get_user_by_session_token(session_token)
        if not user_info:
            emit('error', {'message': 'Invalid session'})
            return
        
        # 현재 상태 확인
        current_state = get_latest_state_for_session(session_token)
        stage = current_state["stage"] if current_state else "정상"
        
        # 사용자 메시지 저장 및 브로드캐스트
        save_chat_message(user_info["user_id"], session_token, "user", message, stage)
        
        emit('chat_message', {
            'session_token': session_token,
            'username': user_info['username'],
            'message': message,
            'sender': 'user',
            'timestamp': int(time.time())
        }, broadcast=True)
        
        # LLM 응답 생성
        llm_response = generate_llm_response(message, stage, session_token)
        
        # AI 응답 저장 및 브로드캐스트
        save_chat_message(user_info["user_id"], session_token, "assistant", 
                         llm_response.get("message", ""), stage)
        
        emit('chat_message', {
            'session_token': session_token,
            'username': 'Assistant',
            'message': llm_response.get("message", ""),
            'sender': 'assistant',
            'timestamp': int(time.time()),
            'actions': llm_response.get("actions", []),
            'audio_file': llm_response.get("audio_file")
        }, broadcast=True)
        
    except Exception as e:
        print(f"❌ Socket.IO 채팅 오류: {e}")
        emit('error', {'message': 'Chat processing failed'})

@socketio.on('request_state_update')
def handle_request_state_update():
    """현재 상태 업데이트 요청"""
    try:
        states = get_latest_states_for_all_active_sessions()
        for state in states:
            emit('state_update', {
                'session_token': state['session_token'],
                'user_id': state['user_id'],
                'username': state['username'],
                'level_code': state['level_code'],
                'stage': state['stage'],
                'timestamp': int(state['created_at'].timestamp()) if state['created_at'] else int(time.time())
            }, broadcast=True)
    except Exception as e:
        print(f"❌ 상태 업데이트 요청 오류: {e}")
        emit('error', {'message': 'State update failed'})

# ============================================
# 서버 시작
# ============================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "1") == "1"
    
    print("=" * 60)
    print("🚗💤 졸음 운전 방지 시스템 서버")
    print("=" * 60)
    print(f"🚀 Flask + Socket.IO 서버 시작")
    print(f"📡 포트: {port}")
    print(f"🔧 디버그 모드: {debug}")
    print(f"🌐 웹 URL: http://localhost:{port}")
    print(f"📊 스트림 서비스: http://localhost:{port}/stream_service")
    print(f"🧪 테스트 API: http://localhost:{port}/api/test/force_event/70")
    print("=" * 60)
    
    # MySQL 연결 테스트
    try:
        from db_config import get_db_connection
        conn = get_db_connection()
        conn.close()
        print("✅ MySQL 연결 확인됨")
    except Exception as e:
        print(f"❌ MySQL 연결 실패: {e}")
    
    try:
        # StateDBWatcher 수동 시작
        if not state_watcher:
            init_state_watcher()
        
        # Socket.IO와 함께 서버 실행
        socketio.run(
            app, 
            host="0.0.0.0", 
            port=port, 
            debug=debug,
            allow_unsafe_werkzeug=True  # 개발용
        )
    except KeyboardInterrupt:
        print("\n🛑 서버 종료 요청...")
        if state_watcher:
            print("✅ StateDBWatcher 정지됨")
    except Exception as e:
        print(f"❌ 서버 시작 실패: {e}")
        print("🔄 기본 Flask 서버로 대체 실행...")
        app.run(host="0.0.0.0", port=port, debug=debug)
    finally:
        if state_watcher:
            print("🧹 정리 작업 완료")
