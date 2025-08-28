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
            'last_question_asked': None,  # 마지막 질문 저장
            'engagement_mode': None,      # 'joke' or 'quiz'
            'engagement_step': 0,        # 반복 횟수
            'last_quiz': None,            # 마지막 퀴즈
            'last_joke': None            # 마지막 아재개그
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
        중요한 규칙:
        1. 화면 중앙에 표시될 주요 경고 메시지('announcement')는 명사형으로 간결하게 종결할 것. (예: "고위험 상태. 즉시 정차.")
        2. 채팅창에만 표시될 후속 질문('question')은 부드러운 대화체 말투를 유지할 것. (예: "가까운 휴게소로 안내할까요?")
        3. 운전자의 상태(stage, d_value)에 따라 단호하고 권위적인 톤을 유지할 것.
        4. 필요시, 창문 개방, 에어컨 강풍, 휴게소 안내 등 구체적인 행동을 지시할 것.
        5. 운전자의 말을 정확히 이해하고 맥락에 맞는 응답을 할 것.
        6. "졸려"라는 말에는 "안녕하세요"가 아닌 졸음과 관련된 적절한 응답을 할 것.
        7. 음악 관련 명령어("음악 틀어줘", "음악 꺼줘" 등)를 정확히 인식하고 처리할 것.
        """

        # 아재개그/퀴즈 리스트
        self.jokes = [
            "자동차가 가장 좋아하는 과일은? 카~멜론!",
            "운전자가 가장 싫어하는 채소는? 브레이크~콜리!",
            "도로 위에서 춤추는 차는? 스텝웨건!"
        ]
        self.quizzes = [
            {"question": "우리나라 수도는 어디일까요?", "answer": "서울"},
            {"question": "자동차 바퀴는 몇 개일까요?", "answer": "4개"},
            {"question": "빨간불에 해야 할 행동은?", "answer": "정지"}
        ]
    def _start_engagement(self, mode: str):
        """
        의심경고 단계 진입 시 아재개그/퀴즈/음악/경고 대화 시작
        mode: 'joke' or 'quiz'
        """
        self.driver_context['engagement_mode'] = mode
        self.driver_context['engagement_step'] = 1
        if mode == 'joke':
            joke = random.choice(self.jokes)
            self.driver_context['last_joke'] = joke
            return {
                'announcement': "졸음이 시작됩니다. 창문을 내리세요! 혹시 아재개그 들어보실래요?",
                'question': joke + "\n재밌으셨나요? 하나 더 들어볼까요?",
                'action_suggestion': "창문을 열거나 음악을 틀어보세요.",
                'engagement_mode': 'joke'
            }
        elif mode == 'quiz':
            quiz = random.choice(self.quizzes)
            self.driver_context['last_quiz'] = quiz
            return {
                'announcement': "졸음이 시작됩니다. 창문을 내리세요! 퀴즈 하나 풀어보실래요?",
                'question': quiz['question'] + "\n정답을 말씀해 주세요!",
                'action_suggestion': "창문을 열거나 음악을 틀어보세요.",
                'engagement_mode': 'quiz'
            }
        else:
            return {
                'announcement': "졸음이 시작됩니다. 창문을 내리세요! 음악을 틀어드릴까요?",
                'question': "졸음 방지 음악을 재생할까요?",
                'action_suggestion': "창문을 열거나 음악을 틀어보세요.",
                'engagement_mode': None
            }

    def _continue_engagement(self, user_input: str):
        """
        운전자 반응에 따라 아재개그/퀴즈 반복 또는 종료
        """
        mode = self.driver_context.get('engagement_mode')
        if not mode:
            return None
        # 긍정/부정 판별
        positive = any(x in user_input for x in ['네', '좋아요', '응', '재밌', '풀', '더', '예', 'OK', '또'])
        negative = any(x in user_input for x in ['아니', '그만', '싫', '안', '노', '아니오', '그만해'])
        if mode == 'joke':
            if positive:
                joke = random.choice(self.jokes)
                self.driver_context['last_joke'] = joke
                self.driver_context['engagement_step'] += 1
                return {
                    'announcement': "하나 더!",
                    'question': joke + "\n또 하나 더 들어볼까요?",
                    'action_suggestion': "창문을 열거나 음악을 틀어보세요.",
                    'engagement_mode': 'joke'
                }
            elif negative:
                self.driver_context['engagement_mode'] = None
                return {
                    'announcement': "알겠어요, 안전운전하세요!",
                    'question': "졸음이 오면 언제든 말씀해 주세요.",
                    'action_suggestion': "창문을 열거나 음악을 틀어보세요.",
                    'engagement_mode': None
                }
        elif mode == 'quiz':
            last_quiz = self.driver_context.get('last_quiz')
            if last_quiz and last_quiz['answer'] in user_input:
                # 정답
                self.driver_context['engagement_step'] += 1
                quiz = random.choice(self.quizzes)
                self.driver_context['last_quiz'] = quiz
                return {
                    'announcement': "정답입니다! 또다른 퀴즈를 풀어볼까요?",
                    'question': quiz['question'] + "\n정답을 말씀해 주세요!",
                    'action_suggestion': "창문을 열거나 음악을 틀어보세요.",
                    'engagement_mode': 'quiz'
                }
            elif negative:
                self.driver_context['engagement_mode'] = None
                return {
                    'announcement': "알겠어요, 안전운전하세요!",
                    'question': "졸음이 오면 언제든 말씀해 주세요.",
                    'action_suggestion': "창문을 열거나 음악을 틀어보세요.",
                    'engagement_mode': None
                }
            else:
                # 오답
                return {
                    'announcement': "아쉽네요! 정답은 " + last_quiz['answer'] + "입니다. 또다른 퀴즈를 풀어볼까요?",
                    'question': random.choice(self.quizzes)['question'] + "\n정답을 말씀해 주세요!",
                    'action_suggestion': "창문을 열거나 음악을 틀어보세요.",
                    'engagement_mode': 'quiz'
                }
        return None
    
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
                'system': """졸음 신호가 감지되었습니다. 공감을 먼저 표현하고 자연스러운 제안을 하세요.
                '피곤하시겠어요' 같은 공감부터 시작하고, 구체적이고 실용적인 조치를 제안하세요.""",
                'templates': [
                    "피곤하시겠어요. 창문을 조금 열어서 신선한 바람 쐬는 게 어떨까요?",
                    "졸음이 오시는군요. 깊게 심호흡을 몇 번 해보시거나 목을 좌우로 돌려보세요.",
                    "운전하느라 수고가 많으세요. 잠깐 어깨를 으쓱해보시면 기분이 나아질 거예요."
                ],
                'engaging_questions': [
                    "목적지까지 얼마나 남았나요",
                    "오늘 컨디션은 어떠세요",
                    "커피 한 잔 하시고 싶지 않나요"
                ]
            },
            
            'L1': {
                'system': """위험 수준입니다. 공감과 이해를 표현한 후 단호하지만 친근한 톤으로 
                즉각적인 행동을 유도하세요. 운전자가 짜증내더라도 침착하게 대응하고, 안전을 최우선으로 하세요.""",
                'templates': [
                    "많이 피곤하시겠어요. 정말 위험해요! 가까운 휴게소에서 5분만 쉬어가시죠.",
                    "졸음이 심하시네요. 사고가 날 수 있어요. 잠시만 차를 세우고 스트레칭해보세요.",
                    "이해해요, 바쁘시겠지만... 지금 상태로는 정말 위험해요. 안전이 우선이에요."
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

        # 2. 의심경고 단계 진입 시 아재개그/퀴즈/음악/경고 대화 시작
        if stage == '의심경고' and self.driver_context.get('engagement_mode') is None and not user_input:
            # 랜덤으로 아재개그/퀴즈/음악 중 하나 선택
            mode = random.choice(['joke', 'quiz', 'music'])
            return self._start_engagement(mode)

        # 3. 아재개그/퀴즈 반복 대화 처리
        if self.driver_context.get('engagement_mode') in ['joke', 'quiz'] and user_input:
            engagement_response = self._continue_engagement(user_input)
            if engagement_response:
                return engagement_response

        # 4. 사용자가 답변을 한 경우 (이전 질문이 있었고, 사용자 입력이 있을 때)
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

        # 5. 일반적인 상황 (LLM 또는 규칙 기반 응답 생성)
        if self.api_key:
            return self._generate_llm_response(stage, d_value, user_input)
        return self._generate_rule_based_response(stage, d_value)
    
    def _generate_llm_response(self, stage: str, d_value: int, user_input: str) -> Dict:
        """OpenAI API를 사용한 자연스러운 응답 생성 (API 호출 방식 수정)"""
        
        prompt_config = self.stage_prompts.get(stage, self.stage_prompts['정상'])
        
        # 프롬프트 구성
        messages = [
            {"role": "system", "content": prompt_config['system']},
            {"role": "system", "content": self.system_prompt},
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
                6. 사용자 입력의 의도를 정확히 파악하여 관련된 응답을 할 것
                
                특별 처리 지침:
                - "졸려", "피곤해" → "피곤하시겠어요" 같은 공감부터 시작하고 구체적 조치 제안
                - "음악 틀어", "노래 틀어" → 음악 재생 확인 
                - "음악 꺼", "그만", "멈춰" → 음악 중지 확인
                - 일반 안부 인사에는 친근하게 응답
                - 항상 공감 표현을 먼저 하고 실용적인 제안을 할 것
                
                응답 패턴: [공감] + [제안] 형식으로 구성
                예: "피곤하시겠어요. 창문을 조금 열어보시는 게 어떨까요?"
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
                "question": "운전하기 좋은 날이네요! 목적지까지 안전하게 가요."
            },
            "의심경고": {
                "announcement": "졸음 신호 감지",
                "question": "졸음이 오시는군요. 창문을 열어 신선한 공기를 들이키는 것은 어떠세요?"
            },
            "L1": {
                "announcement": "졸음 지속",
                "question": "졸음이 지속되고 있네요. 음악을 틀어드릴까요? 아니면 잠시 쉬어가시는 건 어떨까요?"
            },
            "L2": {
                "announcement": "강한 졸음 감지",
                "question": "졸음이 심해지고 있어요. 창문을 열거나 에어컨을 강하게 틀어보시는 게 어떨까요?"
            },
            "L3": {
                "announcement": "고위험 상태",
                "question": "정말 위험한 상태예요. 가까운 휴게소에서 잠시 쉬어가시는 것을 강력히 권합니다."
            },
            "FAILSAFE": {
                "announcement": "즉시 정차",
                "question": "지금 당장 갓길에 정차하세요! 생명이 소중해요!"
            }
        }
        
        response = responses.get(stage, responses['정상'])
        response['music'] = self._select_appropriate_music(stage)
        response['emotional_tone'] = self.conversation_tones[stage]
        response['tts_params'] = {
            'voice': 'female_calm' if stage in ['정상', '개선'] else 'female_urgent',
            'speed': 1.0 if stage in ['정상', '개선'] else 1.2,
            'volume': min(1.5, 0.8 + (0.1 * self._get_stage_level(stage)))
        }
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
    
    def analyze_voice_command(self, text: str, context: Dict = None) -> Dict:
        """
        GPT API를 활용한 지능형 음성 명령 분석
        
        Args:
            text: 사용자가 말한 내용
            context: 현재 상황 정보 (음악 재생 상태, 단계 등)
            
        Returns:
            dict: 분석 결과 (action, confidence, reasoning)
        """
        if not self.api_key:
            # API 키가 없으면 기본 키워드 분석
            return self._basic_command_analysis(text)
        
        try:
            # GPT를 통한 지능형 분석
            messages = [
                {
                    "role": "system", 
                    "content": """
                    당신은 운전자의 음성 명령을 분석하는 AI입니다. 
                    사용자의 말을 듣고 다음 중 하나로 분류하세요:
                    
                    1. start_music: 음악을 틀어달라는 의도
                       - 예: "음악 틀어줘", "뮤직 스타트", "노래 좀", "music please", "tune을 틀어봐"
                    
                    2. stop_music: 음악을 중지해달라는 의도  
                       - 예: "음악 꺼줘", "뮤직 스톱", "그만", "중지해", "music off", "turn it off"
                    
                    3. general_chat: 일반적인 대화
                       - 예: "졸려", "피곤해", "안녕", "어디가?", "몇 시야?"
                    
                    응답은 반드시 JSON 형식으로 하세요:
                    {
                        "action": "start_music|stop_music|general_chat",
                        "confidence": 0.0-1.0,
                        "reasoning": "판단 근거"
                    }
                    """
                },
                {
                    "role": "user",
                    "content": f"""
                    분석할 텍스트: "{text}"
                    
                    현재 상황:
                    - 음악 재생 중: {context.get('current_music_state', False) if context else False}
                    - 운전 상태: {context.get('stage', '정상') if context else '정상'}
                    
                    위 텍스트의 의도를 분석해주세요.
                    """
                }
            ]
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # 빠른 응답을 위해 3.5 사용
                messages=messages,
                temperature=0.1,  # 일관성을 위해 낮은 온도
                max_tokens=150
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # JSON 파싱 시도
            try:
                import json
                result = json.loads(result_text)
                
                # 유효성 검증
                valid_actions = ['start_music', 'stop_music', 'general_chat']
                if result.get('action') not in valid_actions:
                    result['action'] = 'general_chat'
                
                # confidence 범위 확인
                confidence = float(result.get('confidence', 0.5))
                result['confidence'] = max(0.0, min(1.0, confidence))
                
                return result
                
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"GPT 응답 파싱 오류: {e}, 원본: {result_text}")
                return self._basic_command_analysis(text)
                
        except Exception as e:
            print(f"GPT 음성 명령 분석 오류: {e}")
            return self._basic_command_analysis(text)
    
    def _basic_command_analysis(self, text: str) -> Dict:
        """기본 키워드 기반 음성 명령 분석"""
        text_lower = text.lower()
        
        # 음악 재생 관련
        start_keywords = [
            '음악', '노래', '뮤직', 'music', '틀어', '재생', '플레이', 'play', 
            '켜', '시작', 'start', '들려줘', '들려', '트는', '켜줘', 'on'
        ]
        
        # 음악 중지 관련  
        stop_keywords = [
            '꺼', '중지', '멈춰', '스톱', 'stop', '끝', '그만', '정지', 'off',
            '꺼줘', '멈춰줘', '중지해', '끄자', '멈추자', 'turn off', 'shut'
        ]
        
        start_score = sum(1 for keyword in start_keywords if keyword in text_lower)
        stop_score = sum(1 for keyword in stop_keywords if keyword in text_lower)
        
        if start_score > stop_score and start_score > 0:
            return {
                "action": "start_music",
                "confidence": min(0.9, 0.6 + (start_score * 0.1)),
                "reasoning": f"음악 재생 키워드 {start_score}개 감지"
            }
        elif stop_score > 0:
            return {
                "action": "stop_music", 
                "confidence": min(0.9, 0.6 + (stop_score * 0.1)),
                "reasoning": f"음악 중지 키워드 {stop_score}개 감지"
            }
        else:
            return {
                "action": "general_chat",
                "confidence": 0.8,
                "reasoning": "음악 관련 키워드 없음, 일반 대화로 판단"
            }

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