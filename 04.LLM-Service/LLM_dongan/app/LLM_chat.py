# LLM_chat.py
# Robust loader for OPENAI_API_KEY using .env (if present) then environment.
# Provides generate_stage_payload(stage, d, prefer_llm=True), verify_user_answer(), determine_stage_from_d()
# Includes debug prints for LLM calls.

import os
import time
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# Try to load dotenv (.env then .env.example) in a safe way.
try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except Exception:
    _DOTENV_AVAILABLE = False

_here = Path(__file__).parent.resolve()
env_path = _here / ".env"
example_path = _here / ".env.example"

if _DOTENV_AVAILABLE:
    # Load .env first (override any process env), then .env.example as defaults (do not override)
    if env_path.exists():
        load_dotenv(env_path, override=True)
    if example_path.exists():
        load_dotenv(example_path, override=False)
else:
    # If python-dotenv not installed, fall back to environment variables only.
    pass

# Read API key from environment (either set by .env loader above or by OS env)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Try to import openai only if key present (safer)
openai = None
if OPENAI_API_KEY:
    try:
        import openai as _openai
        _openai.api_key = OPENAI_API_KEY
        openai = _openai
    except Exception as e:
        print("LLM_chat: openai import failed - continuing without LLM:", e)
        openai = None
else:
    openai = None

# Debug: show whether key appears configured in this process
print("LLM_chat: OPENAI configured?:", bool(openai), "OPENAI_API_KEY present?:", bool(OPENAI_API_KEY))
if bool(OPENAI_API_KEY) and not bool(openai):
    print("LLM_chat: WARNING - OPENAI_API_KEY found but openai import/config failed.")

# -----------------------------
# Stage mapping (same 기준)
# -----------------------------
_STAGE_MAP_RANGES = [
    (30, "정상"),
    (40, "의심경고"),
    (50, "집중모니터링"),
    (60, "개선"),
    (70, "L1"),
    (80, "L2"),
    (90, "L3"),
    (9999, "FAILSAFE"),
]

# -----------------------------
# Default payloads (기본 템플릿)
# -----------------------------
_DEFAULT_PAYLOADS: Dict[str, Dict[str, Any]] = {
    "정상": {
        "announcement": "정상 상태입니다.",
        "question": "",
        "music": "",
        "music_action": "stop",
        "music_loop": False,
        "tts_voice": "female_30",
        "use_client_tts": True,
        "tts_audio_url": None,
        "volume": 0.6,
        "alert_tone": "none",
        "alert_gain": 0.0,
        "alert_interval_ms": 0
    },
    "의심경고": {
        "announcement": "주의! 졸음 신호 감지 - 집중해주세요.",
        "question": "",
        "music": "/static/sounds/soft_alarm.mp3",
        "music_action": "play",
        "music_loop": False,
        "tts_voice": "female_30",
        "use_client_tts": False,
        "tts_audio_url": None,
        "volume": 0.8,
        "alert_tone": "tone_soft",
        "alert_gain": 0.4,
        "alert_interval_ms": 0
    },
    "집중모니터링": {
        "announcement": "졸음 상태를 집중 모니터링 중입니다.",
        "question": "",
        "music": "",
        "music_action": "stop",
        "music_loop": False,
        "tts_voice": "female_30",
        "use_client_tts": True,
        "tts_audio_url": None,
        "volume": 0.6,
        "alert_tone": "none",
        "alert_gain": 0.0,
        "alert_interval_ms": 0
    },
    "개선": {
        "announcement": "좋아요. 상태가 나아졌어요.",
        "question": "",
        "music": "",
        "music_action": "stop",
        "music_loop": False,
        "tts_voice": "female_30",
        "use_client_tts": True,
        "tts_audio_url": None,
        "volume": 0.6,
        "alert_tone": "none",
        "alert_gain": 0.0,
        "alert_interval_ms": 0
    },
    "L1": {
        "announcement": "졸음이 계속됩니다. 휴식을 권장해요.",
        "question": "지금 날짜가 몇 일이죠?",
        "music": "/static/sounds/alert1.mp3",
        "music_action": "play",
        "music_loop": True,
        "tts_voice": "female_30",
        "use_client_tts": False,
        "tts_audio_url": None,
        "volume": 1.0,
        "alert_tone": "beep1",
        "alert_gain": 0.6,
        "alert_interval_ms": 1000
    },
    "L2": {
        "announcement": "강한 졸음 신호입니다. 창문 열기나 에어컨 강풍을 권장해요.",
        "question": "서울 다음 도시는?",
        "music": "/static/sounds/alert2.mp3",
        "music_action": "play",
        "music_loop": True,
        "tts_voice": "female_30",
        "use_client_tts": False,
        "tts_audio_url": None,
        "volume": 1.1,
        "alert_tone": "beep2",
        "alert_gain": 0.8,
        "alert_interval_ms": 800
    },
    "L3": {
        "announcement": "고위험 졸음 상태입니다. 지금 가까운 휴게소로 안내할까요?",
        "question": "10에서 1까지 거꾸로 말해보세요.",
        "music": "/static/sounds/alert3.mp3",
        "music_action": "play",
        "music_loop": True,
        "tts_voice": "female_30",
        "use_client_tts": False,
        "tts_audio_url": None,
        "volume": 1.2,
        "alert_tone": "beep3",
        "alert_gain": 1.0,
        "alert_interval_ms": 600
    },
    "FAILSAFE": {
        "announcement": "고위험 상태입니다!",
        "question": "",
        "music": "/static/sounds/failsafe_alarm.mp3",
        "music_action": "play",
        "music_loop": True,
        "tts_voice": "female_30",
        "use_client_tts": False,
        "tts_audio_url": None,
        "volume": 1.3,
        "alert_tone": "siren",
        "alert_gain": 1.2,
        "alert_interval_ms": 300
    },
    "휴식": {
        "announcement": "휴식 모드입니다. 휴게소 안내를 준비합니다.",
        "question": "",
        "music": "/static/sounds/rest_mode.mp3",
        "music_action": "play",
        "music_loop": False,
        "tts_voice": "female_30",
        "use_client_tts": False,
        "tts_audio_url": None,
        "volume": 0.9,
        "alert_tone": "none",
        "alert_gain": 0.0,
        "alert_interval_ms": 0
    }
}

# -----------------------------
# JSON 추출 헬퍼 (LLM 출력에서 JSON 파싱)
# -----------------------------
def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    # remove triple backticks and leading/trailing code fences
    t = re.sub(r"(?ms)```.*?```", "", text).strip()
    # try to find the first { ... } block (balanced-ish)
    m = re.search(r"\{(?:[^{}]*|\{.*\})*\}", t, flags=re.S)
    if not m:
        m = re.search(r"\{.*\}", t, flags=re.S)
    if not m:
        return None
    candidate = m.group(0)
    # try JSON loads, with minor fixes
    try:
        return json.loads(candidate)
    except Exception:
        try:
            fixed = candidate.replace("'", '"')
            fixed = re.sub(r",\s*}", "}", fixed)
            fixed = re.sub(r",\s*]", "]", fixed)
            return json.loads(fixed)
        except Exception:
            return None

# -----------------------------
# Prompt templates (Korean) + few-shot examples
# -----------------------------
SYSTEM_PROMPT = (
    "당신은 자동차 내 운전자 안전 어시스턴트입니다. "
    "응답은 항상 JSON 형식으로만 반환하세요. "
    "출력 스키마: {\"announcement\":str, \"question\":str|null}. "
    "announcement는 TTS용 짧은 문장(최대 100자), question은 필요 시 검증용 질문(또는 빈 문자열)입니다. "
    "언어: 한국어. 어투: 차분하지만 단호."
)

FEW_SHOT = [
    {
        "input": {"stage": "L1", "D": 72},
        "output": {"announcement": "주의! 졸음 신호가 감지됐어요. 상태 확인 질문 드릴게요.", "question": "오늘 날짜가 며칠인가요?"}
    },
    {
        "input": {"stage": "L2", "D": 82},
        "output": {"announcement": "강한 졸음 신호입니다. 창문을 열고 환기하세요.", "question": "서울 다음 도시는 어디인가요?"}
    }
]

# -----------------------------
# LLM 호출: 안전하게 JSON을 반환받도록 시도
# -----------------------------
def _call_llm(stage: str, d: float, timeout: int = 15) -> Optional[Dict[str, str]]:
    """
    Return dict: {"announcement": str, "question": str or ""} or None on any failure.
    Defensive: prints debug info and swallows errors so caller can fallback.
    """
    if not openai:
        print(f"[LLM_DEBUG] openai not configured; skipping LLM call for stage={stage} d={d}")
        return None
    try:
        print(f"[LLM_DEBUG] calling LLM for stage={stage} d={d} (model={OPENAI_MODEL})")
        user_prompt = f"Stage: {stage}\nD: {d}\nRespond with JSON only as described."
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}]
        for ex in FEW_SHOT:
            messages.append({"role": "assistant", "content": "Example Input: " + json.dumps(ex["input"], ensure_ascii=False)})
            messages.append({"role": "assistant", "content": "Example Output: " + json.dumps(ex["output"], ensure_ascii=False)})

        resp = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.12,
            max_tokens=180,
            top_p=0.9,
            request_timeout=timeout
        )
        # extract text safely (support older/newer openai lib shapes)
        txt = ""
        try:
            txt = resp.choices[0].message["content"]
        except Exception:
            try:
                txt = resp.choices[0].text
            except Exception:
                txt = ""
        txt_clean = txt.strip()
        print("[LLM_DEBUG] raw LLM text:", txt_clean[:1500])
        parsed = _extract_json_from_text(txt_clean)
        print("[LLM_DEBUG] parsed JSON from LLM:", parsed)
        if parsed:
            ann = parsed.get("announcement") or parsed.get("ann") or parsed.get("text") or ""
            q = parsed.get("question") or parsed.get("q") or ""
            return {"announcement": ann.strip(), "question": q.strip()}
        # heuristic fallback: first non-empty line is announcement; next line that looks like question -> question
        lines = [ln.strip() for ln in txt_clean.splitlines() if ln.strip()]
        if not lines:
            return None
        ann = lines[0]
        q = ""
        for l in lines[1:]:
            if "?" in l or "몇" in l or "말해" in l:
                q = l
                break
        return {"announcement": ann, "question": q}
    except Exception as e:
        print("LLM call failed:", e)
        return None

# -----------------------------
# Public utilities
# -----------------------------
def determine_stage_from_d(D: float) -> str:
    try:
        d = float(D)
    except Exception:
        return "정상"
    for upper, name in _STAGE_MAP_RANGES:
        if d <= upper:
            return name
    return "FAILSAFE"

def _levenshtein(a: str, b: str) -> int:
    a = a or ""
    b = b or ""
    n, m = len(a), len(b)
    if n == 0: return m
    if m == 0: return n
    dp = [[0]*(m+1) for _ in range(n+1)]
    for i in range(n+1): dp[i][0] = i
    for j in range(m+1): dp[0][j] = j
    for i in range(1, n+1):
        for j in range(1, m+1):
            cost = 0 if a[i-1] == b[j-1] else 1
            dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+cost)
    return dp[n][m]

def verify_user_answer(user_text: str, expected_answers: Optional[List[str]] = None, verify_regex: Optional[str] = None) -> Tuple[bool, str]:
    txt = (user_text or "").strip()
    if not txt:
        return False, "empty"
    if expected_answers:
        for e in expected_answers:
            if txt.lower() == e.lower():
                return True, "exact"
            if _levenshtein(txt.lower(), e.lower()) <= 2:
                return True, "fuzzy"
    if verify_regex:
        try:
            if re.search(verify_regex, txt):
                return True, "regex"
        except re.error:
            pass
    if txt.isdigit() and verify_regex and re.search(r"\d", verify_regex):
        return True, "numeric_allow"
    return False, "no_match"

def generate_stage_payload(stage: str, d: float, prefer_llm: bool = True) -> Dict[str, Any]:
    stage_key = stage if stage in _DEFAULT_PAYLOADS else stage
    base = json.loads(json.dumps(_DEFAULT_PAYLOADS.get(stage_key, _DEFAULT_PAYLOADS["정상"])))  # deep copy
    # try LLM augmentation
    if prefer_llm and openai:
        try:
            llm_out = _call_llm(stage_key, float(d))
            if llm_out:
                ann = (llm_out.get("announcement", "") or "").strip()
                q = (llm_out.get("question", "") or "").strip()
                if ann:
                    base["announcement"] = ann
                if q is not None:
                    base["question"] = q
        except Exception as e:
            print("generate_stage_payload LLM augment failed:", e)
    # attach metadata
    base["stage"] = stage_key
    try:
        base["d"] = float(d)
    except Exception:
        base["d"] = None
    base["ts"] = time.time()
    return base

# -----------------------------
# CLI quick test
# -----------------------------
if __name__ == "__main__":
    print("LLM_chat smoke test. OPENAI configured?:", bool(openai))
    # Quick local tests without calling LLM (prefer_llm=False)
    for v in [10, 35, 45, 55, 65, 75, 85, 95]:
        s = determine_stage_from_d(v)
        p = generate_stage_payload(s, v, prefer_llm=False)
        print(v, "->", s, json.dumps(p, ensure_ascii=False))
    # If openai configured, test one LLM attempt (this will make an API call)
    if openai:
        print("Attempting a single LLM call for stage L2 (this will call OpenAI)...")
        out = generate_stage_payload("L2", 82, prefer_llm=True)
        print("LLM-augmented payload:", json.dumps(out, ensure_ascii=False))
