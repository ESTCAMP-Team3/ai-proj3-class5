# 실시간 카메라 스트림 연동 설정

## 개요
`LLM_dongan_stream_v3` UI에서 `phone-cam-transfer` 서버의 실시간 카메라 영상을 볼 수 있도록 연동했습니다.

## 수정된 파일들

### 1. `app/templates/index.html`
- 우측 상단에 실시간 카메라 영역 추가
- WebSocket 연결로 실시간 영상 스트림 수신
- 자동 재연결 기능

### 2. `app/static/css/style.css`  
- 카메라 스트림 영역 스타일링
- 투명 배경, 블러 효과
- 반응형 디자인

### 3. `05.backend/phone-cam-transfer.ipynb`
- CORS 헤더 추가로 크로스 도메인 WebSocket 연결 허용
- 인덱스 페이지에 연결 정보 추가

## 사용 방법

### 1단계: phone-cam-transfer 서버 실행
```bash
# 05.backend 폴더로 이동
cd c:\ai-pjt3-class5\05.backend

# Jupyter 노트북으로 phone-cam-transfer.ipynb 실행
# 또는 Python 파일로 실행:
python phone-cam-transfer.py
```
서버는 `https://localhost:8443`에서 실행됩니다.

### 2단계: 카메라 스트림 시작
1. 브라우저에서 `https://localhost:8443/sender` 접속
2. "카메라 시작" 버튼 클릭
3. "시작" 버튼 클릭하여 스트리밍 시작

### 3단계: LLM Service 실행
```bash
# LLM_dongan_stream_v3 폴더로 이동
cd c:\ai-pjt3-class5\04.LLM-Service\LLM_dongan_stream_v3

# Flask 앱 실행
python app/app.py
```

### 4단계: 통합 확인
- LLM Service UI에서 우측 상단에 실시간 카메라 영상이 표시됨
- 연결 상태 표시: "연결 대기중", "영상 연결됨", "영상 연결 끊어짐"

## 연결 구조
```
[카메라] → [phone-cam-transfer:8443] → [LLM Service UI]
                WebSocket /ws/sender       WebSocket /ws/viewer
```

## 문제 해결

### SSL 인증서 오류
- 브라우저에서 `https://localhost:8443` 접속 시 "고급 설정 → 안전하지 않음으로 이동" 클릭

### WebSocket 연결 실패
1. phone-cam-transfer 서버가 실행 중인지 확인
2. 방화벽에서 8443 포트 허용 확인
3. 브라우저 개발자 도구 콘솔에서 오류 메시지 확인

### 영상이 안 보임
1. 카메라 권한이 허용되었는지 확인
2. /sender 페이지에서 카메라가 정상 작동하는지 확인
3. /viewer 페이지에서 영상이 보이는지 먼저 테스트

## 추가 기능
- 자동 재연결: 연결이 끊어지면 2초 후 자동으로 재연결 시도
- 연결 상태 표시: 실시간으로 연결 상태를 UI에 표시
- 메모리 관리: 이전 프레임 URL 정리로 메모리 누수 방지
