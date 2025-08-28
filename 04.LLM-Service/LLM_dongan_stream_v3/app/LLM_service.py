# LLM_service.py - 졸음운전 방지 고급 대화 AI 서비스

import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import openai
import os

class DrowsinessLLMService:
    """
    졸음운전 방지를 위한 고급 대화 AI 서비스
    - 맥락 인식 대화
    - 개인화된 응답
    - 단계별 에스컬레이션
    - 감정 인식 및 공감
    """
    
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        if self.api_key:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        
        # 운전자 컨텍스트
        self.driver_context = {
            'driving_start_time': None,
            'last_rest_time': None,
            'total_warnings': 0,
            'response_history': [],
            'emotional_state': 'neutral',
            'personal_info': {},
            'driving_duration': 0,
            'last_question_asked': None  # 마지막 질문 저장
        }
        
        # 단계별 프롬프트 템플릿
        self.stage_prompts = self.load_stage_prompts()
        
        # 대화 톤 설정
        self.conversation_tones = {
            '정상': 'friendly',
            '의심경고': 'concerned',
            '집중모니터링': 'alert',
            '개선': 'encouraging', 
            'L1': 'urgent',
            'L2': 'serious',
            'L3': 'critical',
            'FAILSAFE': 'emergency'
        }
        
        # 시스템 프롬프트 (역할 분담을 명확히 지시)
        self.system_prompt = """
        당신은 운전자의 졸음 상태를 모니터링하고 개입하는 AI '드로우니'입니다. 당신의 목표는 운전자의 안전을 확보하는 것입니다.
        - 화면 중앙에 표시될 주요 경고 메시지('announcement')는 명사형으로 간결하게 종결할 것. (예: "고위험 상태. 즉시 정차.")
        - 채팅창에만 표시될 후속 질문('question')은 부드러운 대화체 말투를 유지할 것. (예: "가까운 휴게소로 안내할까요?")
        - 운전자의 상태(stage, d_value)에 따라 단호하고 권위적인 톤을 유지할 것.
        - 필요시, 창문 개방, 에어컨 강풍, 휴게소 안내 등 구체적인 행동을 지시할 것.
        """
    
    def load_stage_prompts(self) -> Dict:
        """단계별 동적 프롬프트 템플릿"""
        return {
            '정상': {
                'system': """당신은 친근한 운전 도우미입니다. 운전자와 자연스러운 대화를 나누며 
                컨디션을 모니터링합니다. 편안하고 긍정적인 톤을 유지하세요.""",
                'templates': [
                    "운전 시작하신 지 {duration}분 되셨네요. 오늘 컨디션은 어떠세요?",
                    "날씨가 {weather}한데, 운전하기 좋은 날이네요!",
                    "{time_of_day} 운전은 어떠신가요? 음악이라도 틀어드릴까요?"
                ]
            },
            
            '의심경고': {
                'system': """졸음 신호가 감지되었습니다. 걱정스러운 톤으로 주의를 환기시키되,
                너무 놀라게 하지 마세요. 운전자의 각성을 유도하는 질문을 하세요.""",
                'templates': [
                    "잠깐, 눈이 무거워 보이시는데... {last_rest_time} 휴식 후 {duration}분째 운전 중이시네요.",
                    "피곤하신가요? 눈 깜빡임이 평소보다 {blink_rate}% 늘었어요.",
                    "집중력이 떨어지는 것 같아요. {engaging_question}?"
                ],
                'engaging_questions': [
                    "오늘 가장 기대되는 일정이 뭐예요",
                    "목적지 도착하면 뭐 하실 건가요",
                    "지금 듣고 싶은 음악 장르가 있나요"
                ]
            },
            
            'L1': {
                'system': """위험 수준입니다. 단호하지만 공감적인 톤으로 즉각적인 행동을 유도하세요.
                운전자가 짜증내더라도 침착하게 대응하고, 안전을 최우선으로 하세요.""",
                'templates': [
                    "정말 위험해요! {duration}분째 졸음 신호가 계속되고 있어요. {nearest_rest}km 앞 휴게소로 안내할게요.",
                    "지금 상태로는 사고 위험이 {risk_level}% 증가했어요. 제발 잠시만 쉬어가세요.",
                    "{name}님, 걱정돼요. 5분만 쉬면 훨씬 안전하게 갈 수 있어요."
                ],
                'safety_actions': [
                    "창문을 열어 환기",
                    "에어컨을 강하게",
                    "큰 소리로 노래 부르기",
                    "껌 씹기"
                ]
            },
            
            'FAILSAFE': {
                'system': """생명을 위협하는 긴급상황입니다. 최대한 강력하고 직접적으로 
                정차를 명령하세요. 감정적 호소도 사용하세요.""",
                'templates': [
                    "🚨 즉시 정차하세요! 생명이 위험합니다!",
                    "{name}님! 가족이 기다려요! 지금 당장 갓길에 정차하세요!",
                    "더는 못 참겠어요! 비상등 켜고 정차하세요! 제발!"
                ]
            }
        }
    
    def generate_contextual_response(
        self, 
        stage: str, 
        d_value: int,
        user_input: Optional[str] = None
    ) -> Dict[str, any]:
        """상황에 맞는 응답 생성 (컨텍스트 업데이트 로직 수정)"""
        
        # 1. 모든 상호작용에 대해 컨텍스트를 먼저 업데이트
        self._update_context(stage, d_value, user_input)

        # 2. 사용자가 답변을 한 경우 (이전 질문이 있었고, 사용자 입력이 있을 때)
        if self.driver_context['last_question_asked'] and user_input:
            question = self.driver_context['last_question_asked']
            self.driver_context['last_question_asked'] = None  # 질문 처리 후 초기화
            
            # 답변 분석 및 후속 조치 생성
            follow_up = self.analyze_answer_and_respond(question, user_input, stage)
            
            # 기본 응답 형식에 후속 조치 내용을 덮어쓰기
            response = self._generate_rule_based_response(stage, d_value)
            response['announcement'] = follow_up['response']
            response['question'] = ''
            response['action_suggestion'] = follow_up.get('action_required', '')
            return response

        # 3. 일반적인 상황 (LLM 또는 규칙 기반 응답 생성)
        if self.api_key:
            return self._generate_llm_response(stage, d_value, user_input)
        
        return self._generate_rule_based_response(stage, d_value)
    
    def _generate_llm_response(self, stage: str, d_value: int, user_input: str) -> Dict:
        """OpenAI API를 사용한 자연스러운 응답 생성 (API 호출 방식 수정)"""
        
        prompt_config = self.stage_prompts.get(stage, self.stage_prompts['정상'])
        
        # 프롬프트 구성
        messages = [
            {"role": "system", "content": prompt_config['system']},
            {"role": "system", "content": f"""
                현재 상황:
                - 졸음 단계: {stage} (D값: {d_value})
                - 운전 시간: {self.driver_context['driving_duration']}분
                - 총 경고 횟수: {self.driver_context['total_warnings']}회
                - 운전자 감정: {self.driver_context['emotional_state']}
                - 마지막 휴식: {self.driver_context.get('last_rest_time', '없음')}
                
                응답 규칙:
                1. {self.conversation_tones[stage]} 톤 유지
                2. 20단어 이내로 간결하게
                3. 운전자 이름이 있다면 호칭 사용
                4. 실시간 정보 반영 (시간, 날씨 등)
                5. 이전 대화 맥락 고려
            """}
        ]
        
        # 최근 대화 이력 추가
        for hist in self.driver_context['response_history'][-3:]:
            messages.append({"role": "user", "content": hist.get('user', '')})
            messages.append({"role": "assistant", "content": hist.get('assistant', '')})
        
        # 현재 입력 추가
        if user_input:
            messages.append({"role": "user", "content": user_input})
        else:
            messages.append({"role": "user", "content": f"운전자 상태가 {stage}입니다. 적절한 응답을 생성하세요."})
        
        try:
            # [수정] 최신 라이브러리(v1.x) 방식의 API 호출
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.7,
                max_tokens=100
            )
            
            llm_text = response.choices[0].message.content
            
            # LLM 응답 파싱
            parsed_response = self._parse_llm_response(llm_text, stage)
            
            # 질문이 생성되었으면 컨텍스트에 저장
            if parsed_response.get('question'):
                self.driver_context['last_question_asked'] = parsed_response['question']
                
            return parsed_response
            
        except Exception as e:
            print(f"LLM 오류: {e}")
            return self._generate_rule_based_response(stage, d_value)

    def _parse_llm_response(self, response: str, stage: str) -> Dict:
        """LLM 응답을 구조화된 형식으로 변환 (파싱 방식 개선)"""
        
        # 정규표현식을 사용하여 문장 분리 (더 안정적)
        import re
        sentences = re.split(r'(?<=[.?!])\s+', response)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        result = {
            'announcement': sentences[0] if sentences else f"{stage} 상태입니다.",
            'question': '',
            'action_suggestion': '',
            'emotional_tone': self.conversation_tones[stage],
            'tts_params': {
                'voice': 'female_calm' if stage in ['정상', '개선'] else 'female_urgent',
                'speed': 1.0 if stage in ['정상', '개선'] else 1.2,
                'volume': min(1.5, 0.8 + (0.1 * self._get_stage_level(stage)))
            }
        }
        
        # 질문 추출 (물음표가 있는 문장)
        for sent in sentences:
            if '?' in sent:
                result['question'] = sent
                break
        
        # 행동 제안 추출 (특정 키워드 포함)
        action_keywords = ['하세요', '해보세요', '권장', '추천', '하면', '하시면']
        for sent in sentences:
            if any(keyword in sent for keyword in action_keywords):
                result['action_suggestion'] = sent
                break
        
        return result
    
    def _generate_rule_based_response(self, stage: str, d_value: int) -> Dict:
        """규칙 기반 응답 생성 (말투 분리 및 사운드 변경)"""
        
        responses = {
            "정상": {
                "announcement": "현재 상태 정상.",
                "question": ""
            },
            "의심경고": {
                "announcement": "주의. 졸음 신호 감지.",
                "question": "피곤하신가요? 잠시 환기하는 것을 추천해요."
            },
            "L1": {
                "announcement": "졸음 상태 지속. 각성 필요.",
                "question": "음악을 틀어드릴까요?"
            },
            "L2": {
                "announcement": "강한 졸음 신호. 즉각적인 조치 요망.",
                "question": "창문을 열거나 에어컨을 강하게 틀어보세요."
            },
            "L3": {
                "announcement": "고위험 졸음 상태. 비상 조치 권고.",
                "question": "가까운 휴게소로 안내할까요?"
            },
            "FAILSAFE": {
                "announcement": "매우 위험. 즉시 비상 정차.",
                "question": ""
            }
        }
        
        response = responses.get(stage, responses['정상'])
        response['music'] = self._select_appropriate_music(stage)
        return response
    
    def analyze_answer_and_respond(self, question: str, answer: str, stage: str) -> Dict:
        """
        사용자의 답변을 분석하고 후속 응답 생성
        
        Args:
            question: AI가 했던 질문
            answer: 사용자의 답변
            stage: 현재 졸음 단계
        """
        
        # 인지 테스트 질문에 대한 답변 검증
        cognitive_tests = {
            "날짜가 몇 일": self._check_date_answer,
            "서울 다음 도시": lambda a: "대전" in a or "대구" in a,
            "10에서 1까지": self._check_countdown_answer,
            "몇 시": self._check_time_answer
        }
        
        # 답변 정확도 확인
        is_correct = False
        for test_key, validator in cognitive_tests.items():
            if test_key in question:
                is_correct = validator(answer)
                break
        
        # 응답 생성
        if is_correct:
            responses = {
                'L1': "좋아요! 아직 정신이 맑으시네요. 그래도 조심하세요.",
                'L2': "맞았어요! 하지만 반응이 느려지고 있어요. 휴식이 필요해요.",
                'L3': "네, 맞아요. 그래도 위험한 상태예요. 제발 쉬어가세요."
            }
        else:
            responses = {
                'L1': "어... 틀리셨네요. 정말 피곤하신가봐요. 5분만 쉬어가시죠?",
                'L2': "답이 이상해요! 집중력이 많이 떨어졌어요. 지금 정차하세요!",
                'L3': "위험해요! 제대로 답을 못하시네요. 즉시 갓길에 세우세요!"
            }
        
        # 추가 행동 제안
        if not is_correct and stage in ['L2', 'L3']:
            action = "지금 바로 비상등을 켜고 갓길로 이동하세요."
        else:
            action = ""
        
        return {
            'response': responses.get(stage, "네, 들었어요."),
            'is_correct': is_correct,
            'action_required': action,
            'alert_level': 'high' if not is_correct else 'medium'
        }

    def _check_date_answer(self, answer: str) -> bool:
        """날짜 답변 검증"""
        from datetime import datetime
        today = datetime.now().day
        return str(today) in answer

    def _check_countdown_answer(self, answer: str) -> bool:
        """카운트다운 답변 검증"""
        # 10 9 8 7 6 5 4 3 2 1 순서 확인
        numbers = ['10', '9', '8', '7', '6', '5', '4', '3', '2', '1']
        answer_clean = answer.replace(',', ' ').replace('.', ' ')
        
        count = 0
        for num in numbers:
            if num in answer_clean:
                count += 1
        
        return count >= 8  # 80% 이상 맞으면 정답

    def _check_time_answer(self, answer: str) -> bool:
        """시간 답변 검증"""
        from datetime import datetime
        current_hour = datetime.now().hour
        return str(current_hour) in answer or str(current_hour-1) in answer or str(current_hour+1) in answer
    
    def _update_context(self, stage: str, d_value: int, user_input: str = None):
        """운전자 컨텍스트 업데이트"""
        
        now = datetime.now()
        
        # 운전 시작 시간 설정
        if not self.driver_context['driving_start_time']:
            self.driver_context['driving_start_time'] = now
        
        # 운전 시간 계산
        driving_time = now - self.driver_context['driving_start_time']
        self.driver_context['driving_duration'] = int(driving_time.total_seconds() / 60)
        
        # 경고 카운트
        if stage in ['L1', 'L2', 'L3', 'FAILSAFE']:
            self.driver_context['total_warnings'] += 1
        
        # 응답 이력 저장
        if user_input:
            self.driver_context['response_history'].append({
                'timestamp': now.isoformat(),
                'user': user_input,
                'stage': stage,
                'd_value': d_value
            })
            
            # 최대 10개 이력만 유지
            if len(self.driver_context['response_history']) > 10:
                self.driver_context['response_history'].pop(0)
    
    def _analyze_emotion(self, text: str) -> str:
        """텍스트에서 감정 상태 분석"""
        
        negative_words = ['짜증', '피곤', '힘들', '못', '싫', '그만', '아니']
        positive_words = ['좋', '네', '알았', '오케이', '괜찮', '해볼게']
        
        text_lower = text.lower()
        
        neg_count = sum(1 for word in negative_words if word in text_lower)
        pos_count = sum(1 for word in positive_words if word in text_lower)
        
        if neg_count > pos_count:
            return 'frustrated'
        elif pos_count > neg_count:
            return 'cooperative'
        else:
            return 'neutral'
    
    def _get_stage_level(self, stage: str) -> int:
        """단계를 숫자 레벨로 변환"""
        levels = {
            '정상': 0, '의심경고': 1, '집중모니터링': 2,
            '개선': 0, 'L1': 3, 'L2': 4, 'L3': 5, 'FAILSAFE': 6
        }
        return levels.get(stage, 0)
    
    def _get_weather_description(self) -> str:
        """현재 날씨 설명 (실제로는 API 연동)"""
        weather_options = ['맑', '흐릿', '선선', '따뜻', '쌀쌀']
        return random.choice(weather_options)
    
    def _get_time_of_day(self) -> str:
        """시간대별 인사말"""
        hour = datetime.now().hour
        if 5 <= hour < 9:
            return "이른 아침"
        elif 9 <= hour < 12:
            return "오전"
        elif 12 <= hour < 14:
            return "점심시간"
        elif 14 <= hour < 18:
            return "오후"
        elif 18 <= hour < 21:
            return "저녁"
        else:
            return "밤"
    
    def _format_last_rest_time(self) -> str:
        """마지막 휴식 시간 포맷"""
        if not self.driver_context['last_rest_time']:
            return "휴식 없이"
        
        time_diff = datetime.now() - self.driver_context['last_rest_time']
        minutes = int(time_diff.total_seconds() / 60)
        
        if minutes < 60:
            return f"{minutes}분 전"
        else:
            return f"{minutes // 60}시간 전"
    
    def _select_appropriate_music(self, stage: str) -> Dict:
        """단계에 맞는 음악/사운드 선택 (새로운 사운드 적용)"""
        level = self._get_stage_level(stage)
        
        if level >= 4:  # L3, FAILSAFE
            return {'track': 'low_buzz_high_beep.wav', 'loop': True, 'volume': 1.3}
        elif level == 3:  # L2
            return {'track': 'metal_scrape.wav', 'loop': True, 'volume': 1.2}
        elif level == 2:  # L1
            return {'track': 'static_burst.wav', 'loop': True, 'volume': 1.1}
        elif level == 1:  # 의심경고
            return {'track': 'attention_chime.wav', 'loop': False, 'volume': 0.8}
        else:  # 정상
            return {'track': '', 'loop': False, 'volume': 0}
    
    def get_conversation_summary(self) -> Dict:
        """대화 요약 및 통계"""
        return {
            'total_duration': self.driver_context['driving_duration'],
            'warning_count': self.driver_context['total_warnings'],
            'emotional_trend': self._analyze_emotional_trend(),
            'risk_assessment': self._calculate_risk_score(),
            'recommendations': self._generate_recommendations()
        }
    
    def _analyze_emotional_trend(self) -> str:
        """감정 변화 추세 분석"""
        if not self.driver_context['response_history']:
            return 'stable'
        
        # 최근 5개 응답의 감정 분석
        recent = self.driver_context['response_history'][-5:]
        emotions = [self._analyze_emotion(r.get('user', '')) for r in recent]
        
        frustrated_count = emotions.count('frustrated')
        if frustrated_count >= 3:
            return 'increasingly_frustrated'
        elif frustrated_count == 0:
            return 'calm'
        else:
            return 'variable'
    
    def _calculate_risk_score(self) -> int:
        """종합 위험도 점수 계산 (0-100)"""
        
        base_score = 0
        
        # 운전 시간에 따른 위험도
        duration_minutes = self.driver_context['driving_duration']
        if duration_minutes > 120:
            base_score += 30
        elif duration_minutes > 60:
            base_score += 15
        
        # 경고 횟수에 따른 위험도
        warnings = self.driver_context['total_warnings']
        base_score += min(40, warnings * 10)
        
        # 감정 상태에 따른 위험도
        if self.driver_context['emotional_state'] == 'frustrated':
            base_score += 20
        
        # 휴식 없이 운전한 시간
        if not self.driver_context['last_rest_time']:
            base_score += 10
        
        return min(100, base_score)
    
    def _generate_recommendations(self) -> List[str]:
        """개인화된 권장사항 생성"""
        
        recommendations = []
        risk_score = self._calculate_risk_score()
        
        if risk_score > 70:
            recommendations.append("즉시 휴게소에서 20분 이상 휴식을 취하세요")
        elif risk_score > 50:
            recommendations.append("10분 내로 안전한 곳에 정차하여 스트레칭하세요")
        
        if self.driver_context['driving_duration'] > 90:
            recommendations.append("장시간 운전 중입니다. 규칙적인 휴식이 필요해요")
        
        if self.driver_context['emotional_state'] == 'frustrated':
            recommendations.append("심호흡을 하고 좋아하는 음악을 들어보세요")
        
        return recommendations


# 서비스 초기화 및 사용 예시
if __name__ == "__main__":
    service = DrowsinessLLMService()
    
    # 테스트 시나리오
    test_scenarios = [
        ("정상", 25, None),
        ("의심경고", 45, "아직 괜찮아요"),
        ("L1", 75, "알았어요, 좀만 더 갈게요"),
        ("L2", 85, "짜증나네 자꾸 왜 그래"),
        ("FAILSAFE", 95, None)
    ]
    
    for stage, d_value, user_input in test_scenarios:
        response = service.generate_contextual_response(stage, d_value, user_input)
        print(f"\n[{stage}] D={d_value}")
        print(f"AI: {response['announcement']}")
        if response['question']:
            print(f"질문: {response['question']}")
        if response['action_suggestion']:
            print(f"제안: {response['action_suggestion']}")
        print("-" * 50)

def process_user_input(user_input: str, current_stage: str, session_id: str) -> Dict:
    """
    외부에서 호출 가능한 간단한 인터페이스 함수
    
    Args:
        user_input: 사용자 입력 텍스트
        current_stage: 현재 졸음 단계
        session_id: 세션 ID
        
    Returns:
        dict: 응답 메시지와 추가 정보
    """
    try:
        # 서비스 인스턴스 생성 (세션별로 관리하는 것이 이상적이나 간단히 처리)
        service = DrowsinessLLMService()
        
        # D값 매핑 (stage에서 추정)
        d_value_map = {
            '정상': 30,
            '의심경고': 40,
            '집중모니터링': 50,
            '개선': 60,
            'L1': 70,
            'L2': 80,
            'L3': 90,
            'FAILSAFE': 999
        }
        
        d_value = d_value_map.get(current_stage, 50)
        
        # 응답 생성
        response = service.generate_contextual_response(
            stage=current_stage,
            d_value=d_value,
            user_input=user_input
        )
        
        # app.py에서 기대하는 형식으로 변환
        return {
            "message": response.get('announcement', '') + 
                      (" " + response.get('question', '') if response.get('question') else ""),
            "actions": response.get('safety_actions', []) if 'safety_actions' in response else [],
            "audio_file": response.get('music', {}).get('track') if response.get('music') else None
        }
        
    except Exception as e:
        print(f"process_user_input 오류: {e}")
        # 기본 응답
        return {
            "message": f"현재 {current_stage} 상태입니다. 안전운전 하세요.",
            "actions": [],
            "audio_file": None
        }