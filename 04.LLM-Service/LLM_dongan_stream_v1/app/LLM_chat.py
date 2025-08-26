#!/usr/bin/env python3
# 최적화된 LLM_chat.py - 졸음운전 방지 LLM 유틸리티
import os, json, re, time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

class LLMChat:
    def __init__(self):
        self.setup_config()
        self.setup_openai()
        self.load_payloads()
        
    def setup_config(self):
        """환경변수 및 설정"""
        # 간단한 dotenv 로딩
        try:
            from dotenv import load_dotenv
            for env_file in [".env", ".env.example"]:
                if Path(env_file).exists():
                    load_dotenv(env_file, override=env_file==".env")
        except ImportError:
            pass
            
        self.config = {
            'api_key': os.getenv("OPENAI_API_KEY"),
            'model': os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            'timeout': 10,
            'max_tokens': 150
        }
        
    def setup_openai(self):
        """OpenAI 클라이언트 설정"""
        self.client = None
        if self.config['api_key']:
            try:
                import openai
                self.client = openai.OpenAI(api_key=self.config['api_key'])
            except Exception as e:
                print(f"OpenAI setup failed: {e}")
                
        print(f"LLM configured: {bool(self.client)}")
        
    def load_payloads(self):
        """기본 페이로드 및 외부 파일 로드"""
        # 압축된 기본 페이로드
        self.payloads = {
            '정상': {'announcement': '정상 상태입니다.', 'question': ''},
            '의심경고': {'announcement': '주의! 졸음 신호 감지', 'question': ''},
            '집중모니터링': {'announcement': '상태 확인 중입니다.', 'question': ''},
            '개선': {'announcement': '상태가 나아졌어요.', 'question': ''},
            'L1': {'announcement': '졸음이 지속됩니다. 휴식을 권장해요.', 'question': '지금 날짜가 몇 일이죠?'},
            'L2': {'announcement': '강한 졸음 신호입니다. 창문 열기 권장.', 'question': '서울 다음 도시는?'},
            'L3': {'announcement': '고위험 졸음 상태입니다.', 'question': '10에서 1까지 거꾸로 말해보세요.'},
            'FAILSAFE': {'announcement': '고위험! 즉시 정차하세요.', 'question': ''},
            '휴식': {'announcement': '휴식 모드입니다.', 'question': ''}
        }
        
        # 외부 페이로드 병합
        payload_file = Path("stage_payloads.json")
        if payload_file.exists():
            try:
                with open(payload_file, encoding='utf-8') as f:
                    external = json.load(f)
                for stage, data in external.items():
                    if stage in self.payloads:
                        self.payloads[stage].update(data)
                    else:
                        self.payloads[stage] = data
                print(f"External payloads merged: {list(external.keys())}")
            except Exception as e:
                print(f"Failed to load external payloads: {e}")
                
    # === D값 -> 단계 변환 ===
    def determine_stage_from_d(self, D: float) -> str:
        """D값을 단계로 변환"""
        try:
            d = float(D)
            stages = [(30,'정상'), (40,'의심경고'), (50,'집중모니터링'), (60,'개선'), 
                     (70,'L1'), (80,'L2'), (90,'L3'), (999,'FAILSAFE')]
            return next((stage for threshold, stage in stages if d <= threshold), 'FAILSAFE')
        except:
            return '정상'
            
    # === LLM 호출 ===
    def call_llm(self, stage: str, d: float) -> Optional[Dict[str, str]]:
        """LLM 호출로 동적 페이로드 생성"""
        if not self.client:
            return None
            
        try:
            prompt = f"""당신은 졸음운전 방지 어시스턴트입니다.
단계: {stage}, 졸음지수: {d}

다음 JSON 형식으로만 응답하세요:
{{"announcement": "TTS용 짧은 경고문 (100자 이내)", "question": "검증용 질문 (또는 빈 문자열)"}}

한국어로 차분하지만 단호하게 작성하세요."""

            response = self.client.chat.completions.create(
                model=self.config['model'],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.config['max_tokens'],
                temperature=0.3,
                timeout=self.config['timeout']
            )
            
            content = response.choices[0].message.content.strip()
            return self.parse_json(content)
            
        except Exception as e:
            print(f"LLM call failed: {e}")
            return None
            
    def parse_json(self, text: str) -> Optional[Dict]:
        """텍스트에서 JSON 추출"""
        if not text:
            return None
            
        # 코드 펜스 제거
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL).strip()
        
        # JSON 블록 찾기
        json_match = re.search(r'\{[^}]*\}', text, re.DOTALL)
        if not json_match:
            return None
            
        try:
            candidate = json_match.group(0)
            return json.loads(candidate)
        except:
            try:
                # 간단한 수정 시도
                fixed = candidate.replace("'", '"')
                fixed = re.sub(r',\s*}', '}', fixed)
                return json.loads(fixed)
            except:
                return None
                
    # === 메인 페이로드 생성 ===
    def generate_stage_payload(self, stage: str, d: float, prefer_llm: bool = True) -> Dict[str, Any]:
        """단계별 페이로드 생성 (LLM 우선, 폴백 지원)"""
        # 기본 페이로드 복사
        base = self.payloads.get(stage, self.payloads['정상']).copy()
        
        # LLM 증강 시도
        if prefer_llm:
            llm_result = self.call_llm(stage, d)
            if llm_result:
                if llm_result.get('announcement'):
                    base['announcement'] = llm_result['announcement'].strip()
                if 'question' in llm_result:
                    base['question'] = llm_result.get('question', '').strip()
                    
        # 메타데이터 추가
        base.update({
            'stage': stage,
            'd': float(d) if d is not None else None,
            'ts': time.time(),
            'llm_used': prefer_llm and bool(self.client)
        })
        
        return base
        
    # === 사용자 답변 검증 ===
    def verify_user_answer(self, user_text: str, expected: Optional[List[str]] = None, 
                          regex: Optional[str] = None) -> Tuple[bool, str]:
        """사용자 답변 검증"""
        text = (user_text or "").strip().lower()
        if not text:
            return False, "empty"
            
        # 정확한 답변 체크
        if expected:
            for exp in expected:
                if text == exp.lower() or self.levenshtein(text, exp.lower()) <= 2:
                    return True, "match"
                    
        # 정규식 체크
        if regex:
            try:
                if re.search(regex, user_text, re.IGNORECASE):
                    return True, "regex"
            except:
                pass
                
        # 숫자 답변 허용
        if text.isdigit() and regex and r'\d' in regex:
            return True, "numeric"
            
        return False, "no_match"
        
    def levenshtein(self, a: str, b: str) -> int:
        """간단한 편집 거리 계산"""
        if not a or not b:
            return max(len(a or ""), len(b or ""))
            
        if len(a) < len(b):
            a, b = b, a
            
        if len(b) == 0:
            return len(a)
            
        prev_row = list(range(len(b) + 1))
        for i, a_char in enumerate(a):
            curr_row = [i + 1]
            for j, b_char in enumerate(b):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (a_char != b_char)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row
            
        return prev_row[-1]

# === 전역 인스턴스 및 편의 함수들 ===
_llm_chat = None

def get_llm_chat():
    """LLMChat 인스턴스 반환 (싱글톤)"""
    global _llm_chat
    if _llm_chat is None:
        _llm_chat = LLMChat()
    return _llm_chat

def generate_stage_payload(stage: str, d: float, prefer_llm: bool = True) -> Dict[str, Any]:
    """편의 함수: 단계별 페이로드 생성"""
    return get_llm_chat().generate_stage_payload(stage, d, prefer_llm)
    
def verify_user_answer(user_text: str, expected_answers: Optional[List[str]] = None, 
                      verify_regex: Optional[str] = None) -> Tuple[bool, str]:
    """편의 함수: 사용자 답변 검증"""
    return get_llm_chat().verify_user_answer(user_text, expected_answers, verify_regex)
    
def determine_stage_from_d(D: float) -> str:
    """편의 함수: D값을 단계로 변환"""
    return get_llm_chat().determine_stage_from_d(D)

# === 테스트 실행 ===
if __name__ == "__main__":
    print("🧠 LLM_chat 테스트 시작")
    
    llm = get_llm_chat()
    print(f"OpenAI 연결: {bool(llm.client)}")
    
    # 기본 테스트
    test_values = [25, 35, 45, 55, 65, 75, 85, 95]
    for d in test_values:
        stage = determine_stage_from_d(d)
        payload = generate_stage_payload(stage, d, prefer_llm=False)  # LLM 없이 테스트
        print(f"D={d} -> {stage}: {payload['announcement']}")
        
    # LLM 테스트 (키가 있는 경우)
    if llm.client:
        print("\n🤖 LLM 테스트 (L2 단계)...")
        llm_payload = generate_stage_payload("L2", 82, prefer_llm=True)
        print(f"LLM 결과: {llm_payload['announcement']}")
        
    print("✅ 테스트 완료")