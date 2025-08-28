import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import requests

from config import MYSQL_URL, LLM_SERVICE_BASE, LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

def create_mysql_engine() -> Engine:
    return create_engine(
        MYSQL_URL,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )

def insert_state_history(engine: Engine, user_id: int, session_token: str,
                         level_code: int, stage_name: str):
    sql = text("""
        INSERT INTO driver_state_history (user_id, session_token, level_code, stage)
        VALUES (:user_id, :session_token, :level_code, :stage)
    """)
    with engine.begin() as conn:
        conn.execute(sql, {
            "user_id": user_id,
            "session_token": session_token,
            "level_code": level_code,
            "stage": stage_name[:20],
        })

def notify_llm_service(user_id: int, session_id: str, level_code: int, stage_name: str):
    if not LLM_SERVICE_BASE:
        return
    try:
        url = f"{LLM_SERVICE_BASE.rstrip('/')}/api/state-change"
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "stage": stage_name,
            "level_code": level_code,
        }
        requests.post(url, json=payload, timeout=3)
    except Exception as e:
        logger.warning(f"LLM notify failed: {e}")
