# 베이스 이미지: 기존 Harbor 레지스트리의 이미지
FROM harbor.dongango.com/pub/fsk-py311:0.2

# 작업 디렉토리 지정
WORKDIR /app

# 로컬 app 폴더를 컨테이너 /app 에 복사
COPY app/ /app/

# 필요시 requirements 설치 (이미 base 이미지에 있으면 생략 가능)
# RUN pip install --no-cache-dir -r requirements.txt

# 컨테이너 실행 시 python app.py 실행
CMD ["python", "app.py"]