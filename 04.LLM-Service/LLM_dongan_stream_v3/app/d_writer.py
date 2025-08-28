# d_writer.py - MySQL driver_state_history 테이블에 졸음 상태를 기록하는 시뮬레이터
"""
기존 D값 전송 방식에서 MySQL DB 직접 삽입 방식으로 변경
실제 영상 분석 시스템을 시뮬레이션하여 driver_state_history 테이블에 level_code를 기록

사용법:
1. DB 직접 모드: python d_writer.py
2. API 모드: python d_writer.py --api
3. 특정 시퀀스: python d_writer.py --sequence "30,40,50,70,90"
"""

import time
import requests
import os
import sys
import argparse
from datetime import datetime

# 로컬 모듈 import
try:
    from db_config import get_db_connection
    from user_state import stage_from_level
except ImportError:
    print("❌ db_config.py 또는 user_state.py를 찾을 수 없습니다.")
    print("📁 app 폴더에서 실행하세요.")
    sys.exit(1)

# 기본 설정
DEFAULT_API_URL = os.environ.get('SERVER_URL', 'http://127.0.0.1:8000')
DEFAULT_SESSION_ID = "video-test-session-001"
DEFAULT_USER_ID = 1

# 졸음 상태 시퀀스 (레벨 코드)
DEFAULT_SEQUENCE = [30, 40, 30, 50, 40, 60, 30, 70, 80, 70, 90, 60, 30]

class DrowsinessDataWriter:
    """졸음 상태 데이터 작성기"""
    
    def __init__(self, api_url=None, session_id=None, user_id=None):
        self.api_url = api_url or DEFAULT_API_URL
        self.session_id = session_id or DEFAULT_SESSION_ID
        self.user_id = user_id or DEFAULT_USER_ID
        
    def write_to_db(self, level_code: int) -> bool:
        """DB에 직접 상태 기록"""
        try:
            stage = stage_from_level(level_code)
            if not stage:
                print(f"❌ 잘못된 level_code: {level_code}")
                return False
                
            conn = get_db_connection()
            cur = conn.cursor()
            
            # driver_state_history 테이블에 삽입
            cur.execute("""
                INSERT INTO driver_state_history 
                (user_id, session_token, level_code, stage, created_at, confidence, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                self.user_id,
                self.session_id,
                level_code,
                stage,
                datetime.now(),
                0.95,  # 기본 신뢰도
                '{"source": "d_writer", "mode": "simulator"}'
            ))
            
            conn.commit()
            cur.close()
            conn.close()
            
            print(f"✅ DB 기록: level_code={level_code}, stage='{stage}'")
            return True
            
        except Exception as e:
            print(f"❌ DB 기록 실패: {e}")
            return False
    
    def send_to_api(self, level_code: int) -> bool:
        """API로 상태 전송 (기존 /ingest 방식)"""
        try:
            payload = {
                'D': level_code,  # 기존 호환성을 위해 D 파라미터 사용
                'level_code': level_code,
                'ts': time.time(),
                'session_id': self.session_id
            }
            
            # 기존 /ingest 엔드포인트 사용
            response = requests.post(f"{self.api_url}/ingest", json=payload, timeout=5)
            
            if response.status_code == 200:
                print(f"✅ API 전송: level_code={level_code} -> {response.status_code}")
                return True
            else:
                print(f"❌ API 오류: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ API 전송 실패: {e}")
            return False
    
    def run_sequence(self, sequence, interval=2.0, loop=1, use_api=False):
        """시퀀스 실행"""
        mode = "API" if use_api else "DB 직접"
        print(f"🚗 졸음 상태 시뮬레이터 시작 ({mode} 모드)")
        print(f"📋 세션 ID: {self.session_id}")
        print(f"👤 사용자 ID: {self.user_id}")
        print(f"🔄 시퀀스: {sequence}")
        print(f"⏱️  간격: {interval}초")
        print(f"🔁 반복: {loop}회")
        print("-" * 50)
        
        try:
            for iteration in range(loop if loop > 0 else float('inf')):
                if loop > 1:
                    print(f"\n🔄 반복 #{iteration + 1}/{loop}")
                
                for i, level_code in enumerate(sequence):
                    # 상태 전송
                    if use_api:
                        success = self.send_to_api(level_code)
                    else:
                        success = self.write_to_db(level_code)
                    
                    if not success:
                        print(f"⚠️ 전송 실패, 계속 진행...")
                    
                    # 마지막이 아니면 대기
                    if i < len(sequence) - 1:
                        time.sleep(interval)
                
                # 반복 간 대기 (무한 루프인 경우)
                if loop == 0 or (loop > 1 and iteration < loop - 1):
                    print("🔁 다음 사이클까지 대기...")
                    time.sleep(interval)
                    
        except KeyboardInterrupt:
            print(f"\n⏹️ 사용자 중단 (Ctrl+C)")
        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
        
        print(f"\n🏁 시뮬레이터 종료")

def main():
    parser = argparse.ArgumentParser(description="졸음 상태 데이터 작성기")
    parser.add_argument("--api", action="store_true", 
                       help="API 모드 사용 (기본값: DB 직접 모드)")
    parser.add_argument("--url", type=str, default=DEFAULT_API_URL,
                       help=f"서버 URL (기본값: {DEFAULT_API_URL})")
    parser.add_argument("--session", type=str, default=DEFAULT_SESSION_ID,
                       help=f"세션 ID (기본값: {DEFAULT_SESSION_ID})")
    parser.add_argument("--user", type=int, default=DEFAULT_USER_ID,
                       help=f"사용자 ID (기본값: {DEFAULT_USER_ID})")
    parser.add_argument("--sequence", type=str, 
                       default=",".join(map(str, DEFAULT_SEQUENCE)),
                       help="졸음 상태 시퀀스 (쉼표 구분)")
    parser.add_argument("--interval", type=float, default=2.0,
                       help="전송 간격 (초)")
    parser.add_argument("--loop", type=int, default=1,
                       help="반복 횟수 (0=무한)")
    
    args = parser.parse_args()
    
    # 시퀀스 파싱
    try:
        sequence = [int(x.strip()) for x in args.sequence.split(",") if x.strip()]
        if not sequence:
            raise ValueError("빈 시퀀스")
        
        # level_code 유효성 검사
        valid_levels = [30, 40, 50, 60, 70, 80, 90]
        for level in sequence:
            if level not in valid_levels:
                print(f"⚠️ 경고: {level}은 유효하지 않은 level_code입니다. 유효한 값: {valid_levels}")
                
    except ValueError as e:
        print(f"❌ 잘못된 시퀀스: {e}")
        sys.exit(1)
    
    # 데이터 작성기 실행
    writer = DrowsinessDataWriter(
        api_url=args.url,
        session_id=args.session,
        user_id=args.user
    )
    
    writer.run_sequence(
        sequence=sequence,
        interval=args.interval,
        loop=args.loop,
        use_api=args.api
    )

if __name__ == '__main__':
    main()

# 기존 호환성을 위한 심플 실행 함수
def run():
    """기존 d_writer.py와 호환성을 위한 함수"""
    print("⚠️ 기존 run() 함수 호출됨. 새로운 방식으로 실행합니다.")
    writer = DrowsinessDataWriter()
    writer.run_sequence(DEFAULT_SEQUENCE, interval=2.0, loop=1, use_api=False)
