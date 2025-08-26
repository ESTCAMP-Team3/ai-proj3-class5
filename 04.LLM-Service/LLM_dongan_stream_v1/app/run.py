#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
최적화된 졸음운전 방지 서비스 서버
- Flask-SocketIO 기반 실시간 통신
- LLM을 활용한 동적 상호작용
- 상태 안정화 및 쿨다운 로직 적용
"""
import os
import json
import time
import hashlib
import threading
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from LLM_chat import generate_stage_payload
import requests

# eventlet/gevent 사용 시 DNS 문제 방지를 위한 설정
os.environ.setdefault("EVENTLET_NO_GREENDNS", "yes")
import eventlet
eventlet.monkey_patch()

class DrowsinessServer:
    """졸음운전 방지 서버 메인 클래스"""

    # --- 상수 정의 ---
    # API 모델 및 시스템 프롬프트
    LLM_MODEL = "gpt-4o-mini"
    LLM_SYSTEM_PROMPT = "당신은 졸음운전 방지 어시스턴트입니다. 한국어로 간결하고 친근하게 응답하세요."
    
    # 로컬 저장 파일명
    LOCAL_CHAT_FILE = "chats_local.jsonl"

    def __init__(self):
        """서버 초기화"""
        self.setup_env()
        self.setup_app()
        self.setup_storage()
        self.setup_state()
        
    def setup_env(self):
        """환경변수 로드 및 설정 초기화"""
        env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=env_path)
        
        self.config = {
            'OPENAI_API_KEY': os.getenv("OPENAI_API_KEY", ""),
            'PORT': int(os.getenv("PORT", "8000")),
            'MONGO_URI': os.getenv("MONGO_URI", ""),
            'STABILITY_SECONDS': float(os.getenv("STABILITY_SECONDS", "3.0")),
            'COOLDOWN_SECONDS': float(os.getenv("COOLDOWN_SECONDS", "5.0")),
            'SECRET_KEY': os.getenv("SECRET_KEY", "dev_secret_key")
        }
        print(f"Config loaded - Port: {self.config['PORT']}, OpenAI: {bool(self.config['OPENAI_API_KEY'])}")

    def setup_app(self):
        """Flask 및 SocketIO 애플리케이션 초기화"""
        self.app = Flask(__name__, static_folder="static", template_folder="templates")
        self.app.config["SECRET_KEY"] = self.config['SECRET_KEY']
        
        # 비동기 모드로 SocketIO 설정 (eventlet 우선)
        try:
            self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode="eventlet")
        except ImportError:
            self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode="threading")
            
        self.setup_routes()
        
    def setup_storage(self):
        """데이터 저장소(MongoDB 또는 로컬 파일) 설정"""
        self.msg_col = None
        self.local_file = Path(self.LOCAL_CHAT_FILE)
        
        if self.config['MONGO_URI']:
            try:
                from pymongo import MongoClient, errors
                mongo_client = MongoClient(self.config['MONGO_URI'], serverSelectionTimeoutMS=3000)
                mongo_client.server_info() # 연결 테스트
                self.msg_col = mongo_client.drowsy_db.chat_messages
                print("✅ MongoDB connected successfully.")
            except errors.ServerSelectionTimeoutError as e:
                print(f"⚠️ MongoDB connection failed: {e}. Falling back to local storage.")
        else:
            print("ℹ️ Using local JSONL file for chat storage.")
            
    def setup_state(self):
        """실시간 상태 관리 변수 초기화"""
        self.state = {
            'last_stage': None,      # 마지막으로 확정된 단계
            'last_emit_ts': 0.0,     # 마지막으로 이벤트를 보낸 타임스탬프
            'pending_stage': None,   # 변경 감지 후 안정화를 기다리는 단계
            'pending_since': 0.0     # pending 상태가 시작된 타임스탬프
        }
        self.emit_lock = threading.Lock() # 동시성 제어를 위한 Lock

    # === 유틸리티 메서드 ===
    def get_stage_from_d(self, D_value):
        """D값(졸음 점수)을 기반으로 현재 단계를 결정"""
        try:
            D = float(D_value)
            # (임계값, 단계명) 순서의 튜플 리스트
            stages = [
                (30, '정상'), (40, '의심경고'), (50, '집중모니터링'), (60, '개선'), 
                (70, 'L1'), (80, 'L2'), (90, 'L3'), (float('inf'), 'FAILSAFE')
            ]
            # D값이 임계값보다 작거나 같은 첫 번째 단계를 반환
            return next((stage for threshold, stage in stages if D <= threshold), 'FAILSAFE')
        except (ValueError, TypeError):
            return None
            
    def save_chat(self, msg: dict):
        """채팅 메시지를 설정된 저장소에 저장"""
        try:
            if self.msg_col is not None:
                self.msg_col.insert_one(msg)
            else:
                # 로컬 파일에 JSON Lines 형식으로 추가 (효율적)
                with open(self.local_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(msg, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"🚨 Error saving chat message: {e}")
            
    def get_fallback_payload(self, stage: str) -> dict:
        """LLM 호출 실패 시 사용할 정적 페이로드 생성"""
        fallbacks = {
            '정상': ('정상 상태입니다.', ''),
            '의심경고': ('주의! 졸음 신호가 감지되었습니다.', ''),
            '집중모니터링': ('운전자 상태를 확인하고 있습니다.', ''),
            '개선': ('상태가 개선되었습니다. 계속 안전 운전하세요.', ''),
            'L1': ('졸음이 감지됩니다. 잠시 휴식을 권장합니다.', '지금 계신 곳의 다음 휴게소는 어디인가요?'),
            'L2': ('강한 졸음 신호입니다. 창문을 열어 환기하세요.', '오늘의 날짜와 요일을 말씀해주세요.'),
            'L3': ('위험! 매우 졸린 상태입니다. 즉시 안전한 곳에 정차하세요.', '10부터 1까지 거꾸로 숫자를 세어보세요.'),
            'FAILSAFE': ('고위험! 즉시 차량을 정차하고 휴식을 취하세요.', '')
        }
        announcement, question = fallbacks.get(stage, ('상태가 변경되었습니다.', ''))
        return {'announcement': announcement, 'question': question, 'stage': stage, 'ts': time.time()}
        
    # === 라우트 및 소켓 이벤트 핸들러 설정 ===
    def setup_routes(self):
        """Flask 라우트와 SocketIO 이벤트 핸들러를 정의"""
        
        @self.app.route("/")
        def index():
            # templates 폴더의 index.html을 렌더링
            return render_template("index.html")

        @self.app.route("/ingest", methods=["POST"])
        def ingest():
            # 졸음 데이터 수신 및 처리
            return self.handle_ingest()
            
        @self.app.route("/chat_send", methods=["POST"]) 
        def chat_send():
            # 사용자 채팅 메시지 수신 및 응답 생성
            return self.handle_chat_send()
            
        @self.app.route("/health", methods=["GET"])
        def health():
            # 서버 상태 확인용 엔드포인트
            return jsonify({"status": "ok"})
            
        @self.socketio.on("connect")
        def on_connect():
            print("✅ Client connected")
            
        @self.socketio.on("disconnect") 
        def on_disconnect():
            print("🔌 Client disconnected")
            
    # === 핵심 로직 핸들러 ===
    def handle_ingest(self):
        """/ingest 요청 처리: D값을 받아 상태를 결정하고 이벤트를 발생시키는 핵심 로직"""
        data = request.get_json(force=True) or {}
        D_value = data.get("D")
        
        if D_value is None:
            return jsonify({"error": "D value is required"}), 400
            
        # D값을 모든 클라이언트에게 브로드캐스트
        self.socketio.emit("d_update", {"D": D_value, "ts": data.get("ts", time.time())})
            
        stage = self.get_stage_from_d(D_value)
        if not stage:
            return jsonify({"error": "Invalid D value"}), 400
            
        now = time.time()
        
        # --- 상태 전이 로직 ---
        # 1. 이전과 동일한 단계는 무시하고, pending 상태 초기화
        if stage == self.state['last_stage']:
            self.state['pending_stage'] = None
            return jsonify({"ok": True, "stage": stage, "emitted": False, "reason": "no_change"}), 200
            
        # 2. 새로운 단계가 감지되면 'pending' 상태로 전환
        if self.state['pending_stage'] != stage:
            self.state['pending_stage'] = stage
            self.state['pending_since'] = now
            return jsonify({"ok": True, "stage": stage, "status": "pending"}), 200
            
        # 3. 'pending' 상태가 안정화 시간(STABILITY_SECONDS)을 충족했는지 확인
        if now - self.state['pending_since'] < self.config['STABILITY_SECONDS']:
            return jsonify({"ok": True, "stage": stage, "status": "stabilizing"}), 200
            
        # 4. 안정화 완료, 이벤트 발생 시도
        with self.emit_lock:
            # 쿨다운(COOLDOWN_SECONDS) 시간 확인
            if now - self.state['last_emit_ts'] < self.config['COOLDOWN_SECONDS']:
                return jsonify({"ok": True, "stage": stage, "emitted": False, "reason": "cooldown"}), 200
                
            # LLM 또는 폴백을 사용하여 페이로드 생성
            try:
                use_llm = bool(self.config['OPENAI_API_KEY'])
                payload = generate_stage_payload(stage, D_value, prefer_llm=use_llm)
            except Exception as e:
                print(f"🚨 LLM payload generation failed: {e}. Using fallback.")
                payload = self.get_fallback_payload(stage)
                
            print(f"🚀 Stage transition: {self.state['last_stage']} -> {stage} (D={D_value})")
            
            # 클라이언트에 'state_prompt' 이벤트 전송
            self.socketio.emit("state_prompt", payload)
                
            # 상태 변수 업데이트
            self.state['last_stage'] = stage
            self.state['last_emit_ts'] = now
            self.state['pending_stage'] = None
            
            return jsonify({"ok": True, "stage": stage, "emitted": True, "payload": payload}), 200
            
    def handle_chat_send(self):
        """/chat_send 요청 처리: 사용자 메시지에 대한 LLM 응답 생성 및 전송"""
        data = request.get_json() or {}
        text = data.get("text", "").strip()
        
        if not text:
            return jsonify({"error": "text is required"}), 400
            
        # 사용자 메시지 저장
        ts = time.time()
        user_msg = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
            "user": "user", 
            "text": text,
            "msg_id": hashlib.sha1(f"user|{ts}|{text}".encode()).hexdigest()
        }
        self.save_chat(user_msg)
        
        # LLM 응답 생성
        assistant_text = self.generate_llm_response(text)
        
        # 어시스턴트 응답 저장 및 클라이언트에 전송
        assistant_msg = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user": "assistant",
            "text": assistant_text, 
            "msg_id": hashlib.sha1(f"assistant|{ts}|{assistant_text}".encode()).hexdigest()
        }
        self.save_chat(assistant_msg)
        self.socketio.emit("chat_message", assistant_msg)
        
        return jsonify(assistant_msg), 200
        
    def generate_llm_response(self, text: str) -> str:
        """OpenAI API를 호출하여 LLM 응답을 생성. 실패 시 정적 응답 반환."""
        if not self.config['OPENAI_API_KEY']:
            return f"응답(샘플): \"{text}\"라고 말씀하셨네요. 현재는 OpenAI API 키가 설정되지 않았습니다."
            
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.config['OPENAI_API_KEY']}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": self.LLM_SYSTEM_PROMPT},
                        {"role": "user", "content": text}
                    ],
                    "max_tokens": 150,
                    "temperature": 0.7
                },
                timeout=10
            )
            response.raise_for_status() # 200번대 응답이 아니면 예외 발생
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except requests.RequestException as e:
            print(f"🚨 LLM API call failed: {e}")
            return f"응답 생성에 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
        
    def run(self):
        """서버를 시작"""
        print("="*50)
        print(f"🚗 졸음운전 방지 서버 시작 - http://0.0.0.0:{self.config['PORT']}")
        print(f"📊 안정화 시간: {self.config['STABILITY_SECONDS']}초 | 쿨다운: {self.config['COOLDOWN_SECONDS']}초")
        print("="*50)
        
        self.socketio.run(
            self.app, 
            host="0.0.0.0", 
            port=self.config['PORT'], 
            debug=False, 
            use_reloader=False
        )

# --- 서버 실행 ---
if __name__ == "__main__":
    server = DrowsinessServer()
    server.run()