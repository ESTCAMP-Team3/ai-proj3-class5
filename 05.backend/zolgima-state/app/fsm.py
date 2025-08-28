from dataclasses import dataclass
from typing import Optional
import logging

from config import FRAMES_PER_SEC, LOGGER_NAME
from enums import Stage, STAGE_NAME
from db import insert_state_history, notify_llm_service

logger = logging.getLogger(LOGGER_NAME)

@dataclass
class SessionFSM:
    session_id: str
    user_id: int
    session_token: str
    engine: "Engine"

    state: Stage = Stage.NORMAL
    state_timer: float = 0.0
    drowsy_acc: float = 0.0
    clear_acc: float = 0.0
    last_frame: Optional[int] = None

    def _is_drowsy(self, drowny_level: int) -> bool:
        # -1, 0 → 정상
        if drowny_level <= 0:
            return False

        if self.state in (Stage.NORMAL,):
            return drowny_level in (1, 2, 3)

        if self.state in (Stage.FOCUS_MONITOR, Stage.L1, Stage.L2, Stage.L3, Stage.FAILSAFE):
            return drowny_level in (2, 3)

        if self.state in (Stage.PERSISTENT, Stage.IMPROVEMENT, Stage.REST, Stage.PRE_ALERT):
            # 보수적 기준: 2,3만 졸음
            return drowny_level in (2, 3)

        return False

    def _secs_from_frame(self, frame: Optional[int]) -> float:
        if frame is None or self.last_frame is None:
            return 1.0 / FRAMES_PER_SEC
        diff = frame - self.last_frame
        if diff <= 0:
            return 1.0 / FRAMES_PER_SEC
        return diff / FRAMES_PER_SEC

    def _commit_state(self, new_state: Stage):
        if new_state == self.state:
            return
        self.state = new_state
        self.state_timer = 0.0
        self.drowsy_acc = 0.0
        self.clear_acc = 0.0

        stage_name = STAGE_NAME[self.state]
        insert_state_history(self.engine, self.user_id, self.session_token, int(self.state), stage_name)
        logger.info(f"[{self.session_token}] State → {stage_name} ({int(self.state)})")
        notify_llm_service(self.user_id, self.session_id, int(self.state), stage_name)

    def feed(self, frame: Optional[int], drowny_level: int):
        secs = self._secs_from_frame(frame)
        self.state_timer += secs

        logger.info(f"[{self.session_id}] call feed: frame={frame}, drowny_level={drowny_level}")

        is_drowsy = self._is_drowsy(drowny_level)
        if is_drowsy:
            self.drowsy_acc += secs
            self.clear_acc = 0.0
        else:
            self.clear_acc += secs
            self.drowsy_acc = 0.0

        st = self.state

        if st == Stage.NORMAL:
            if is_drowsy:
                self._commit_state(Stage.PRE_ALERT)

        elif st == Stage.PRE_ALERT:
            if self.state_timer >= 1.0:
                self._commit_state(Stage.FOCUS_MONITOR)

        elif st == Stage.FOCUS_MONITOR:
            if not is_drowsy:
                self._commit_state(Stage.IMPROVEMENT)
            elif self.drowsy_acc >= 5.0:
                self._commit_state(Stage.PERSISTENT)

        elif st == Stage.PERSISTENT:
            if self.state_timer >= 1.0:
                self._commit_state(Stage.L1)

        elif st in (Stage.L1, Stage.L2, Stage.L3):
            if not is_drowsy:
                self._commit_state(Stage.REST)
            elif self.drowsy_acc >= 5.0:
                if st == Stage.L1:
                    self._commit_state(Stage.L2)
                elif st == Stage.L2:
                    self._commit_state(Stage.L3)
                elif st == Stage.L3:
                    self._commit_state(Stage.FAILSAFE)

        elif st == Stage.FAILSAFE:
            if not is_drowsy:
                self._commit_state(Stage.REST)

        elif st == Stage.REST:
            if not is_drowsy and self.clear_acc >= 5.0:
                self._commit_state(Stage.IMPROVEMENT)
            elif is_drowsy and self.drowsy_acc >= 2.0:
                self._commit_state(Stage.L1)

        elif st == Stage.IMPROVEMENT:
            if not is_drowsy and self.clear_acc >= 5.0:
                self._commit_state(Stage.NORMAL)
            elif is_drowsy and self.drowsy_acc >= 2.0:
                self._commit_state(Stage.PRE_ALERT)

        if frame is not None:
            self.last_frame = frame
