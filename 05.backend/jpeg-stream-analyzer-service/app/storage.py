
from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
import json, time
from config import STATE_DIR

class StateStore:
    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _topic_path(self, topic: str) -> Path:
        safe = "".join([c if c.isalnum() or c in "._-+" else "_" for c in topic])
        return self.state_dir / f"{safe}.last.json"

    def load_last(self, topic: str) -> Optional[Dict[str, Any]]:
        p = self._topic_path(topic)
        if not p.exists(): return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_last(self, topic: str, record: Dict[str, Any]):
        p = self._topic_path(topic)
        p.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
