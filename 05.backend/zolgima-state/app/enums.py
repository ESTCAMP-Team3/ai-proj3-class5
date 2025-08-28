from enum import IntEnum

class Stage(IntEnum):
    NORMAL = 30
    PRE_ALERT = 40            # 의심경고
    FOCUS_MONITOR = 50        # 집중모니터링
    PERSISTENT = 55           # 지속졸음
    L1 = 70                   # 경고강화 L1
    L2 = 80                   # 경고강화 L2
    L3 = 90                   # 경고강화 L3
    FAILSAFE = 999             # 페일세이프
    IMPROVEMENT = 60          # 개선
    REST = 20                 # 휴식모드

STAGE_NAME = {
    Stage.NORMAL: "정상",
    Stage.PRE_ALERT: "의심경고",
    Stage.FOCUS_MONITOR: "집중모니터링",
    Stage.PERSISTENT: "지속졸음",
    Stage.L1: "경고강화 L1",
    Stage.L2: "경고강화 L2",
    Stage.L3: "경고강화 L3",
    Stage.FAILSAFE: "페일세이프",
    Stage.IMPROVEMENT: "개선",
    Stage.REST: "휴식모드",
}
