# app/run.py — app 디렉터리에서 직접 실행하는 진입점
import os
import sys

# 실행 위치가 어디든, 현재 파일이 있는 폴더(app)를 sys.path에 올린다
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app as flask_app  # app/app.py 내부의 Flask 인스턴스
from stream_upload import bp as stream_bp  # JPEG 업로드 블루프린트

# 블루프린트 등록 (경로 충돌 없음: /stream, /api/upload_frame 등)
flask_app.register_blueprint(stream_bp)

if __name__ == "__main__":
    # 개발용 실행
    flask_app.run(host="0.0.0.0", port=8000, debug=True)
