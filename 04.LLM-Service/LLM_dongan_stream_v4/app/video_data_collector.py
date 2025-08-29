# video_data_collector.py - 영상 데이터 수집기 시뮬레이터
"""
실제 영상 분석 시스템을 대신하여 MySQL DB에 직접 driver_state_history 레코드를 삽입하는 스크립트
실제 환경에서는 이 스크립트 대신 실제 영상 분석 시스템이 이 역할을 수행

사용법:
1. 기본 시퀀스 실행: python video_data_collector.py
2. 특정 세션으로 실행: python video_data_collector.py --session_id sess-abc123
3. API 모드: python video_data_collector.py --api_mode --url http://localhost:8000
"""

import time
import argparse
import sys
import requests
from datetime import datetime
from db_config import get_db_connection
from user_state import stage_from_level

# 기본 졸음 상태 시퀀스 (실제 운전 시나리오 반영)
DEFAULT_SEQUENCE = [
    30,  # 정상 - 운전 시작
    30,  # 정상 유지
    40,  # 의심경고 - 약간의 피로
    30,  # 정상 복귀
    40,  # 의심경고 재발
    50,  # 집중모니터링 - 피로 증가
    40,  # 의심경고로 복귀
    60,  # 개선 상태
    30,  # 정상 복귀
    70,  # L1 - 졸음 시작
    80,  # L2 - 졸음 심화
    70,  # L1으로 일시 개선
    90,  # L3 - 위험 상태
    60,  # 개선 - 각성 후
    30,  # 정상 복귀
]

class VideoDataCollector:
    """영상 데이터 수집기 시뮬레이터"""
    
    def __init__(self, session_id: str = None, api_url: str = None):
        self.session_id = session_id or self.generate_session_id()
        self.api_url = api_url
        self.user_id = 1  # 기본 사용자 ID (실제로는 세션에서 조회)
        
    def generate_session_id(self) -> str:
        """세션 ID 생성"""
        import random
        import string
        timestamp = str(int(time.time()))
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"video-sess-{random_str}-{timestamp[-6:]}"
    
    def insert_to_db(self, level_code: int, confidence: float = 1.0) -> bool:
        """DB에 직접 상태 기록 삽입"""
        try:
            stage = stage_from_level(level_code)
            if not stage:
                print(f"❌ Invalid level_code: {level_code}")
                return False
                
            conn = get_db_connection()
            cur = conn.cursor()
            
            # driver_state_history 테이블에 삽입
            cur.execute("""
                INSERT INTO driver_state_history 
                (user_id, session_token, level_code, stage, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                self.user_id,
                self.session_id,
                level_code,
                stage,
                datetime.now()
            ))
            
            conn.commit()
            cur.close()
            conn.close()
            
            print(f"✅ DB 삽입: level_code={level_code}, stage='{stage}', session={self.session_id}")
            return True
            
        except Exception as e:
            print(f"❌ DB 삽입 실패: {e}")
            return False
    
    def send_via_api(self, level_code: int, confidence: float = 1.0) -> bool:
        """API를 통해 상태 전송"""
        try:
            if not self.api_url:
                print("❌ API URL이 설정되지 않음")
                return False
                
            payload = {
                "session_id": self.session_id,
                "level_code": level_code,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "source": "video_collector",
                    "version": "1.0"
                }
            }
            
            response = requests.post(
                f"{self.api_url}/api/driver/state",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ API 전송: level_code={level_code}, stage='{result.get('stage')}', session={self.session_id}")
                return True
            else:
                print(f"❌ API 오류: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ API 전송 실패: {e}")
            return False
    
    def run_sequence(self, sequence: list, interval: float = 2.0, loop: int = 1, use_api: bool = False):
        """시퀀스 실행"""
        print(f"🎬 영상 데이터 수집기 시작")
        print(f"📋 세션 ID: {self.session_id}")
        print(f"🔄 시퀀스: {sequence}")
        print(f"⏱️  간격: {interval}초")
        print(f"🔁 반복: {loop}회 ({'무한' if loop == 0 else str(loop)})")
        print(f"🌐 모드: {'API' if use_api else 'Direct DB'}")
        print("-" * 60)
        
        iteration = 0
        
        try:
            while True:
                iteration += 1
                print(f"\n🔄 반복 #{iteration} 시작")
                
                for i, level_code in enumerate(sequence):
                    confidence = 0.9 + (0.1 * (i % 2))  # 0.9-1.0 사이 신뢰도
                    
                    # 상태 전송
                    if use_api:
                        success = self.send_via_api(level_code, confidence)
                    else:
                        success = self.insert_to_db(level_code, confidence)
                    
                    if not success:
                        print(f"⚠️ 전송 실패, 계속 진행...")
                    
                    # 다음 단계까지 대기
                    if i < len(sequence) - 1:  # 마지막이 아니면 대기
                        time.sleep(interval)
                
                # 반복 제어
                if loop > 0 and iteration >= loop:
                    print(f"\n✅ 요청된 {loop}회 반복 완료")
                    break
                elif loop == 0:
                    print(f"🔁 무한 반복 모드 - 다음 사이클 시작...")
                    time.sleep(interval)
                else:
                    print(f"🔁 다음 반복까지 대기...")
                    time.sleep(interval)
                    
        except KeyboardInterrupt:
            print(f"\n⏹️ 사용자 중단 (Ctrl+C)")
        except Exception as e:
            print(f"\n❌ 예외 발생: {e}")
        
        print(f"\n🏁 영상 데이터 수집기 종료")

def main():
    parser = argparse.ArgumentParser(description="영상 데이터 수집기 시뮬레이터")
    parser.add_argument("--session_id", type=str, help="세션 ID (기본값: 자동 생성)")
    parser.add_argument("--sequence", type=str, 
                       default=",".join(map(str, DEFAULT_SEQUENCE)),
                       help="졸음 상태 시퀀스 (쉼표 구분)")
    parser.add_argument("--interval", type=float, default=2.0, 
                       help="전송 간격 (초)")
    parser.add_argument("--loop", type=int, default=1,
                       help="반복 횟수 (0=무한)")
    parser.add_argument("--api_mode", action="store_true",
                       help="API 모드 사용 (기본값: DB 직접 삽입)")
    parser.add_argument("--url", type=str, default="http://localhost:8000",
                       help="API URL (API 모드에서만 사용)")
    
    args = parser.parse_args()
    
    # 시퀀스 파싱
    try:
        sequence = [int(x.strip()) for x in args.sequence.split(",") if x.strip()]
        if not sequence:
            raise ValueError("빈 시퀀스")
    except ValueError as e:
        print(f"❌ 잘못된 시퀀스 형식: {e}")
        sys.exit(1)
    
    # 수집기 생성 및 실행
    collector = VideoDataCollector(
        session_id=args.session_id,
        api_url=args.url if args.api_mode else None
    )
    
    collector.run_sequence(
        sequence=sequence,
        interval=args.interval,
        loop=args.loop,
        use_api=args.api_mode
    )

if __name__ == "__main__":
    main()
