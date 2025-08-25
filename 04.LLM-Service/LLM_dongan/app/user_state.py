user_states = {}

def get_user_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = {
            "last_stage": None,
            "last_emit_ts": 0.0,
            "pending_stage": None,
            "pending_since": 0.0
        }
    return user_states[user_id]

# ----------------------
# 졸음 지수 -> 단계 변환 (stage mapping)
# ----------------------
# 설명:
# - D(0~100)를 받아서 상태 문자열을 반환합니다.
# - 임계값은 코드에 하드코딩되어 있으며, 필요 시 환경변수/설정파일로 옮길 수 있습니다.
def stage_from_D(D):
    try:
        D = float(D)
    except Exception:
        return None
    if D <= 30: return "정상"
    if D <= 40: return "의심경고"
    if D <= 50: return "집중모니터링"
    if D <= 60: return "개선"
    if D <= 70: return "L1"
    if D <= 80: return "L2"
    if D <= 90: return "L3"
    return "FAILSAFE"


# 등급번호 → 단계명 (정확히 일치만)
# def stage_from_level(level_code: int | float | str):
def stage_from_level(level_code):
    try:
        v = int(float(level_code))
    except Exception:
        return None
    mapping = {
        30: "정상",
        40: "의심경고",
        50: "집중모니터링",
        60: "개선",
        70: "L1",
        80: "L2",
        90: "L3",
    }
    return mapping.get(v)

