# 🚗 졸음운전 방지 시스템 (Drowsy Driver Prevention System)

> **영상데이터 실시간 수집기**와 **LLM기반 대응서비스**가 통합된 지능형 졸음운전 방지 시스템

## 📋 개요

이 시스템은 실시간 영상 분석을 통해 운전자의 졸음 상태를 감지하고, AI 기반 대화형 인터페이스로 적절한 대응 서비스를 제공하는 통합 솔루션입니다.

### 🎯 주요 기능

- 🎥 **실시간 영상 데이터 수집** - 운전자 상태 모니터링
- 📊 **졸음 상태 분석** - 8단계 위험도 분류 (정상 → 의심경고 → 집중모니터링 → 개선 → L1 → L2 → L3 → FAILSAFE)
- 💬 **LLM 기반 대화형 대응** - OpenAI GPT-4 활용 상황별 맞춤형 응답
- 🌐 **실시간 웹 인터페이스** - Socket.IO 기반 즉시 상태 반영
- 🗄️ **MySQL 데이터베이스** - 운전 이력 및 상태 기록
- 🔔 **다단계 알람 시스템** - 위험도별 차등 경고 (음성, 진동, 사운드)
- 🎯 **인지능력 테스트** - 운전자 의식 수준 실시간 확인
- 🚨 **비상 안전 모드** - 시스템 오류 시 강제 안전 조치

## 🏗️ 시스템 아키텍처

```
🎥 영상분석 시스템
    ↓
📡 video_data_collector.py (데이터 수집기)
    ↓
🗄️ MySQL Database (상태 저장)
    ↓
📊 StateDBWatcher (실시간 감지)
    ↓
🌐 Flask Web Server (Socket.IO)
    ↓
💬 LLM Service (대화형 대응)
    ↓
👤 사용자 인터페이스
```

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 1. 저장소 클론
git clone https://github.com/your-username/drowsy-driver-prevention.git
cd drowsy-driver-prevention

# 2. 가상환경 생성 및 활성화
conda create -n drowsy_system python=3.11
conda activate drowsy_system

# 3. 패키지 설치
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
# .env.example을 .env로 복사
cp app/.env.example app/.env

# .env 파일 수정 (실제 API 키 입력)
# OPENAI_API_KEY=your-actual-openai-api-key
# DB_HOST=your-database-host
# DB_USER=your-database-user
# DB_PASS=your-database-password
```

### 3. 서버 실행

```bash
cd app
python app.py
```

서버 실행 후 http://localhost:8000 에서 접속 가능합니다.

## 📁 프로젝트 구조

```
LLM_dongan_stream_v3_250827/
├── app/
│   ├── app.py                 # 메인 Flask 서버
│   ├── video_data_collector.py # 영상 데이터 수집기
│   ├── LLM_service.py         # LLM 대응 서비스
│   ├── user_service.py        # 사용자 관리
│   ├── state_watcher.py       # 실시간 상태 감지
│   ├── user_state.py          # 상태 관리 유틸리티
│   ├── db_config.py           # 데이터베이스 설정
│   ├── stream_service.py      # 스트림 처리
│   ├── .env                   # 환경변수 (비공개)
│   ├── .env.example           # 환경변수 템플릿
│   ├── templates/             # HTML 템플릿
│   │   ├── index.html
│   │   ├── login.html
│   │   └── stream_service.html
│   ├── static/                # 정적 파일
│   │   ├── css/
│   │   ├── js/
│   │   ├── sounds/
│   │   └── music/
│   └── data/                  # 데이터 저장소
├── .gitignore                 # Git 제외 파일 설정
├── requirements.txt           # Python 패키지 목록
└── README.md                  # 프로젝트 문서
```

## 🎮 사용법

### 1. 영상 데이터 수집기 사용

#### DB 직접 삽입 모드
```bash
python video_data_collector.py --sequence "30,40,50,70,90,60,30" --interval 3 --loop 1
```

#### API 모드
```bash
python video_data_collector.py --api_mode --url http://localhost:8000 --sequence "30,70,90,30" --interval 2
```

### 2. 실시간 테스트

웹 브라우저에서 다음 URL로 즉시 상태 변경 테스트:

- **FAILSAFE 긴급 상태**: `http://localhost:8000/api/test/force_event/100`
- **L3 심각한 위험**: `http://localhost:8000/api/test/force_event/90`
- **L2 중간 위험**: `http://localhost:8000/api/test/force_event/80`
- **L1 경미한 졸음**: `http://localhost:8000/api/test/force_event/70`
- **정상 상태**: `http://localhost:8000/api/test/force_event/30`
- **전체 시퀀스 테스트**: `http://localhost:8000/api/test/sequence`

### 3. 졸음 상태 코드 및 대응 체계

| 코드 | 상태 | 위험도 | 설명 | 시스템 대응 | 권장 조치 |
|------|------|--------|------|------------|----------|
| 30 | **정상** | 🟢 안전 | 정상적인 운전 상태 | 일반 모니터링 | 현재 상태 유지 |
| 40 | **의심경고** | 🟡 주의 | 초기 피로 징후 감지 | 주의 환기 메시지 | 환기, 음악 볼륨 조절 |
| 50 | **집중모니터링** | 🟠 경계 | 피로도 증가, 집중 관찰 | 집중 모니터링 시작 | 창문 개방, 냉방 강화 |
| 60 | **개선** | 🟡 회복 | 상태 호전 중 | 격려 메시지 | 현재 조치 지속 |
| 70 | **L1 경고** | 🔴 위험 | 경미한 졸음 감지 | 경고 알림, 음성 안내 | 안전한 곳 정차 검토 |
| 80 | **L2 심각** | 🔴 고위험 | 뚜렷한 졸음 상태 | 강력한 경고, 사운드 알람 | 즉시 정차, 10분 휴식 |
| 90 | **L3 매우심각** | 🚨 매우위험 | 운전 지속 불가 상태 | 긴급 경고, 진동, 경고음 | 즉시 정차, 30분 이상 휴식 |
| 100+ | **FAILSAFE** | ⚠️ 시스템오류 | 센서/시스템 오류 시 | 강제 안전 모드 | 즉시 정차, 시스템 점검 |

### 4. LLM 대화형 대응 시스템

- **상황별 맞춤 응답**: 현재 졸음 단계에 따른 차별화된 대화
- **인지능력 테스트**: "오늘이 몇 일인가요?", "10부터 1까지 세어보세요" 등
- **감정 상태 분석**: 사용자 답변을 통한 협조도/짜증 수준 파악
- **에스컬레이션**: 답변 실패 시 더 강한 경고로 단계적 증가

## 🔧 API 엔드포인트

### 주요 API

- `POST /api/state` - 영상분석 시스템에서 졸음 상태 데이터 수신
- `GET /api/state/latest` - 현재 사용자의 최신 졸음 상태 조회
- `GET /api/sessions` - 활성 사용자 세션 목록 조회
- `POST /chat_send` - LLM 기반 대화형 인터페이스
- `POST /save_msg` - 대화 메시지 저장
- `POST /stream/upload` - 브라우저 카메라 프레임 업로드
- `GET /api/test/force_event/<level>` - 강제 이벤트 발생 (테스트용)
- `GET /api/test/sequence` - 정상→L3 자동 시퀀스 테스트

### Socket.IO 실시간 이벤트

- `state_update` - 졸음 상태 변경 시 실시간 브로드캐스트
- `d_update` - D값 업데이트 (프론트엔드 호환)
- `chat_message` - LLM 대화 메시지 실시간 전송
- `connection_status` - 사용자 로그인/연결 상태
- `user_login` - 사용자별 룸 참여 이벤트

### 데이터 형식

#### 졸음 상태 데이터 (POST /api/state)
```json
{
  "session_token": "a1b2c3d4e5f6...",
  "level_code": 90,
  "confidence": 0.95,
  "timestamp": "2025-08-28T10:30:00Z",
  "metadata": {
    "source": "video_collector",
    "version": "1.0"
  }
}
```

#### Socket.IO 상태 업데이트 이벤트
```json
{
  "session_token": "a1b2c3d4e5f6...",
  "user_id": 123,
  "username": "class5_3",
  "level_code": 90,
  "stage": "L3",
  "timestamp": 1725014400
}
```

#### LLM 대화 응답 형식
```json
{
  "message": "현재 L3 위험 상태입니다. 즉시 정차하세요.",
  "actions": ["즉시 정차", "30분 휴식", "대체 운전자"],
  "audio_file": "L3_alarm.wav"
}
```

## 🗄️ 데이터베이스 스키마

### 주요 테이블

#### users (사용자 정보)
```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    email VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### user_session (로그인 세션 관리)
```sql
CREATE TABLE user_session (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_token VARCHAR(64) UNIQUE NOT NULL,
    expires_at DATETIME,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

#### driver_state_history (졸음 상태 이력) - 핵심 테이블
```sql
CREATE TABLE driver_state_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_token VARCHAR(64) NOT NULL,
    level_code INT NOT NULL,
    stage VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

#### chat_messages (대화 기록) - 선택사항
```sql
CREATE TABLE chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    session_token VARCHAR(64) NOT NULL,
    sender ENUM('user', 'assistant') NOT NULL,
    message TEXT NOT NULL,
    stage VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## 🔒 보안 설정

- `.env` 파일에 API 키 및 민감 정보 저장
- `.gitignore`로 보안 파일 Git 커밋 방지
- Flask Session 암호화
- 데이터베이스 연결 보안

## 🧪 테스트 및 개발

### 개발 환경 테스트
```bash
# 1. 데이터베이스 연결 테스트
cd app
python -c "from db_config import get_db_connection; conn = get_db_connection(); print('✅ DB 연결 성공' if conn else '❌ DB 연결 실패'); conn.close() if conn else None"

# 2. 영상 데이터 수집기 테스트 (DB 모드)
python video_data_collector.py --sequence "30,70,90,30" --interval 2 --loop 1

# 3. 영상 데이터 수집기 테스트 (API 모드)
python video_data_collector.py --api_mode --url http://localhost:8000 --sequence "30,40,70,90"

# 4. LLM 서비스 단독 테스트
python LLM_service.py
```

### 통합 테스트 시나리오
```bash
# 1. 서버 시작
python app.py

# 2. 브라우저에서 테스트
# http://localhost:8000/login (로그인)
# http://localhost:8000/stream_service (메인 인터페이스)

# 3. API 테스트
curl -X GET "http://localhost:8000/api/test/force_event/90"
curl -X GET "http://localhost:8000/api/test/sequence"
```

### 실시간 Socket.IO 테스트
- 브라우저 개발자 도구 > Network > WS 탭에서 Socket.IO 연결 확인
- 콘솔에서 `socket.emit('ping')` 테스트
- 여러 브라우저 탭으로 동시 접속 테스트

## 📦 배포

### Docker 배포
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "app.py"]
```

### 환경 변수 설정 (운영)
```bash
export OPENAI_API_KEY="your-production-key"
export DB_HOST="production-db-host"
export SECRET_KEY="your-production-secret"
export DEBUG=0
```

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT License 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 📞 문의

- 프로젝트 링크: [https://github.com/your-username/drowsy-driver-prevention](https://github.com/your-username/drowsy-driver-prevention)
- 이슈 리포트: [Issues](https://github.com/your-username/drowsy-driver-prevention/issues)

## 🙏 감사의 말

- OpenAI GPT API
- Flask & Socket.IO
- MySQL Connector
- 모든 기여자들

---

## 📊 시스템 현황 및 버전 정보

### ✅ 완성된 핵심 기능
- ✅ **영상 데이터 수집기** (video_data_collector.py) - DB/API 이중 모드
- ✅ **MySQL 데이터베이스 완전 연동** - 사용자, 세션, 상태 이력 관리
- ✅ **실시간 Socket.IO 통신** - 룸 기반 사용자별 타겟팅
- ✅ **LLM 기반 대화형 대응** - OpenAI GPT-4 + 폴백 규칙 시스템
- ✅ **다단계 경고 시스템** - 8단계 위험도별 차등 대응
- ✅ **웹 인터페이스** - 실시간 상태 표시 + 대화형 UI
- ✅ **보안 설정** - 환경변수 분리 + Git 보안 설정
- ✅ **FAILSAFE 시스템** - 센서/시스템 오류 시 강제 안전 모드

### 📈 기술 스택
- **Backend**: Flask 3.0.3 + Socket.IO
- **Frontend**: HTML5 + JavaScript + Socket.IO Client
- **Database**: MySQL 8.0+
- **AI/LLM**: OpenAI GPT-4 API
- **Real-time**: Socket.IO (WebSocket)
- **Security**: python-dotenv + .gitignore

### 🎯 주요 개선사항 (v1.0.0)
1. **FAILSAFE 모드 추가** - 시스템 오류 시 강제 안전 조치
2. **룸 기반 Socket.IO** - 사용자별 개별 메시지 타겟팅  
3. **LLM 인지능력 테스트** - 운전자 의식 수준 실시간 확인
4. **다단계 사운드 시스템** - 위험도별 차등 알람
5. **완전한 MySQL 연동** - 모든 데이터 영속성 보장
6. **포괄적 에러 핸들링** - 시스템 안정성 극대화

**🚀 현재 버전: v1.0.0 - 완전 통합 시스템 (Git 최적화 완료)**
