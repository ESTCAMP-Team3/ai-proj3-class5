# Python 3.11 slim 기반
FROM python:3.11-slim

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 필수 패키지 업데이트 및 빌드 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libffi-dev \
        && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0

# 작업 디렉토리 생성
WORKDIR /app

# requirements.txt 복사
COPY requirements.txt .

# pip 업그레이드 및 requirements 설치
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 로컬 app 폴더를 컨테이너 /app 에 복사
COPY app/ /app/

# 기본 실행 (필요시 변경 가능)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
