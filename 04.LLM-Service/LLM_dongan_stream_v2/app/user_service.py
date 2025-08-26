from werkzeug.security import check_password_hash, generate_password_hash
from db_config import get_db_connection
import secrets
from datetime import datetime, timedelta


def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s AND is_active=1", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def validate_user(username, password):
    user = get_user_by_username(username)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None

def create_user(username, password, name=None, email=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = generate_password_hash(password)
    cursor.execute(
        "INSERT INTO users (username, password_hash, name, email) VALUES (%s, %s, %s, %s)",
        (username, password_hash, name, email)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return True

def create_user_session(user_id, expire_minutes=60):
    """로그인 성공 시 DB에 세션 기록"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 랜덤 세션 토큰 생성
    session_token = secrets.token_hex(32)
    expires_at = datetime.utcnow() + timedelta(minutes=expire_minutes)

    cursor.execute(
        """
        INSERT INTO user_session (user_id, session_token, expires_at, is_active)
        VALUES (%s, %s, %s, %s)
        """,
        (user_id, session_token, expires_at, True)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return session_token

def insert_state_history(user_id: int, session_token: str, level_code: int, stage: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO driver_state_history (user_id, session_token, level_code, stage)
        VALUES (%s, %s, %s, %s)
        """,
        (user_id, session_token, level_code, stage)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_latest_state_for_session(session_token: str):
    """세션별 최신 등급 1건 반환 (없으면 None)"""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, user_id, session_token, level_code, stage, created_at
        FROM driver_state_history
        WHERE session_token = %s
        ORDER BY id DESC
        LIMIT 1
    """, (session_token,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def get_latest_states_for_all_active_sessions():
    """
    활성 세션별 최신 상태를 가져옴.
    반환: [{session_id, user_id, username, level_code, stage, created_at}, ...]
    """
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 활성 세션 목록 (user_session 테이블 기준)
    cur.execute("""
      SELECT s.session_id, s.user_id, u.username
      FROM user_session s
      JOIN users u ON u.id = s.user_id
      WHERE s.is_active = 1
        AND (s.expires_at IS NULL OR s.expires_at > UTC_TIMESTAMP())
    """)
    sessions = cur.fetchall()
    results = []
    if sessions:
        # 세션별 최신 driver_state_history
        # (MAX(id) 이용: created_at보다 id가 빠르고 안전)
        cur2 = conn.cursor(dictionary=True)
        for sess in sessions:
            cur2.execute("""
              SELECT h.*
              FROM driver_state_history h
              WHERE h.session_token = %s
              ORDER BY h.id DESC
              LIMIT 1
            """, (sess["session_token"],))
            row = cur2.fetchone()
            if row:
                row["username"] = sess["username"]
                results.append(row)
        cur2.close()

    cur.close()
    conn.close()
    return results


def get_active_sessions():
    """활성 세션 목록: [{session_token, user_id, username}, ...]"""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
      SELECT s.session_token, s.user_id, u.username
      FROM user_session s
      JOIN users u ON u.id = s.user_id
      WHERE s.is_active = 1
        AND (s.expires_at IS NULL OR s.expires_at > UTC_TIMESTAMP())
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_latest_state_for_session(session_token: str):
    """지정 세션의 최신 상태 1건 반환. 없으면 None"""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, user_id, session_token, level_code, stage, created_at
        FROM driver_state_history
        WHERE session_token = %s
        ORDER BY id DESC
        LIMIT 1
    """, (session_token,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row
    