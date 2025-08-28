# state_watcher.py
import os
import time
import threading
import hashlib
from datetime import datetime

DEFAULT_STABILITY_SECONDS = float(os.getenv("STABILITY_SECONDS", "0.5"))  # 0.5초로 단축
DEFAULT_COOLDOWN_SECONDS  = float(os.getenv("COOLDOWN_SECONDS",  "5.0"))   # 5초로 단축

class StateDBWatcher:
    """
    DB의 driver_state_history 최신값 변화를 감지하여
    안정화(히스테리시스) 후 Socket.IO로 사용자 room에 브로드캐스트.

    의존성은 생성자에서 주입:
      - socketio: flask_socketio.SocketIO 인스턴스
      - get_active_sessions(): [{session_id, user_id, username}, ...]
      - get_latest_state_for_session(session_id) -> dict | None
      - get_user_state(user_id) -> dict (메모리 상태 저장소)
      - stage_from_level(level_code) -> str | None
    """

    def __init__(
        self,
        socketio,
        get_active_sessions,
        get_latest_state_for_session,
        get_user_state,
        stage_from_level,
        stability_seconds: float = DEFAULT_STABILITY_SECONDS,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ):
        self.socketio = socketio
        self.get_active_sessions = get_active_sessions
        self.get_latest_state_for_session = get_latest_state_for_session
        self.get_user_state = get_user_state
        self.stage_from_level = stage_from_level

        self.STABILITY_SECONDS = stability_seconds
        self.COOLDOWN_SECONDS  = cooldown_seconds

        self._last_observed_by_session = {}  # {session_id: (level, stage, row_id)}
        self._stop_evt = None
        self._thread = None

    # ---------- public API ----------
    def start(self, interval_sec: float = 1.0):
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt = threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(interval_sec,), daemon=True)
        self._thread.start()

    def stop(self):
        if self._stop_evt:
            self._stop_evt.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        self._stop_evt = None

    # ---------- internal ----------
    def _emit_state(self, username: str, level_code: int, stage: str, ts_iso: str | None = None):
        if ts_iso is None:
            ts_iso = datetime.utcnow().isoformat() + "Z"
        # 숫자 실시간 표시
        self.socketio.emit("d_update", {"D": int(level_code), "ts": ts_iso}, room=username)
        # 상태 프롬프트
        msg_id = hashlib.sha1((username + "|" + stage + "|" + ts_iso).encode()).hexdigest()
        self.socketio.emit(
            "state_prompt",
            {"stage": stage, "announcement": f"{stage} 상태입니다.", "question": "", "msg_id": msg_id},
            room=username,
        )

    def _apply_hysteresis_and_emit(self, user_id: int, username: str, level_code: int, stage: str, created_at):
        st = self.get_user_state(user_id)
        now = time.time()
        ts_iso = created_at.isoformat() + "Z" if hasattr(created_at, "isoformat") else datetime.utcnow().isoformat() + "Z"

        # 이미 확정된 단계와 같으면 변동 없음
        if stage == st.get("last_stage"):
            st["pending_stage"] = None
            st["pending_since"] = 0.0
            return False

        # pending 시작/변경
        if st.get("pending_stage") != stage:
            st["pending_stage"] = stage
            st["pending_since"] = now
            return False

        # 안정화 시간 미달
        if now - st.get("pending_since", 0.0) < self.STABILITY_SECONDS:
            return False

        # (선택) 쿨다운: 같은 단계 연속 송출 억제
        if st.get("last_stage") == stage and (now - st.get("last_emit_ts", 0.0)) < self.COOLDOWN_SECONDS:
            st["pending_stage"] = None
            st["pending_since"] = 0.0
            return False

        # 확정 → emit
        self._emit_state(username, level_code, stage, ts_iso=ts_iso)

        # 상태 갱신
        st["last_stage"]   = stage
        st["last_emit_ts"] = now
        st["pending_stage"] = None
        st["pending_since"] = 0.0
        return True

    def _loop(self, interval_sec: float):
        while not (self._stop_evt and self._stop_evt.is_set()):
            try:
                sessions = self.get_active_sessions() or []
                for s in sessions:
                    sess_token = s["session_token"]
                    row = self.get_latest_state_for_session(sess_token)
                    if not row:
                        continue

                    lvl = int(row["level_code"])
                    stg = row.get("stage") or self.stage_from_level(lvl) or "정상"
                    row_id = row["id"]

                    last = self._last_observed_by_session.get(sess_token)
                    if last and last == (lvl, stg, row_id):
                        continue

                    self._apply_hysteresis_and_emit(row["user_id"], s["username"], lvl, stg, row["created_at"])

                    self._last_observed_by_session[sess_token] = (lvl, stg, row_id)

            except Exception as e:
                print("StateDBWatcher loop error:", e)
            finally:
                time.sleep(interval_sec)

