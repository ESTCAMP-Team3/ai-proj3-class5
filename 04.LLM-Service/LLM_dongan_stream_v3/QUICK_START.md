# 졸음운전 방지 시스템 (Drowsy Driver Prevention System)

## 🎯 완성된 기능들

✅ **영상 데이터 수집기** - video_data_collector.py  
✅ **MySQL 데이터베이스 연동** - user_service.py, db_config.py  
✅ **실시간 Socket.IO 통신** - app.py  
✅ **LLM 기반 대화형 대응** - LLM_service.py  
✅ **웹 인터페이스** - templates/, static/  
✅ **보안 설정** - .env, .gitignore  

## 🚀 빠른 시작

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp app/.env.example app/.env
# .env 파일에서 API 키 및 DB 정보 수정

# 3. 서버 실행
cd app
python app.py
```

## 📊 테스트 URL

- **웹사이트**: http://localhost:8000
- **L3 테스트**: http://localhost:8000/api/test/force_event/90
- **시퀀스 테스트**: http://localhost:8000/api/test/sequence

## 📁 핵심 파일

- `app/app.py` - 메인 서버
- `app/video_data_collector.py` - 데이터 수집기
- `app/LLM_service.py` - AI 대화 서비스
- `app/user_service.py` - 사용자/DB 관리

---
**🚀 버전: v1.0.0 (Git 최적화 완료)**
