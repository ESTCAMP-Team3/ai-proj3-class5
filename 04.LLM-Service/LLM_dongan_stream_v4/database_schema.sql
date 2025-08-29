-- database_schema.sql - 졸음운전 방지 시스템 DB 스키마

-- 사용자 테이블
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    INDEX idx_username (username),
    INDEX idx_email (email)
);

-- 사용자 세션 테이블
CREATE TABLE IF NOT EXISTS user_session (
    session_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    session_token VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_token (session_token),
    INDEX idx_user_active (user_id, is_active),
    INDEX idx_expires (expires_at)
);

-- 운전자 상태 히스토리 테이블 (핵심 테이블)
CREATE TABLE IF NOT EXISTS driver_state_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    session_token VARCHAR(64) NOT NULL,
    level_code INT NOT NULL COMMENT '졸음 등급: 30=정상, 40=의심경고, 50=집중모니터링, 60=개선, 70=L1, 80=L2, 90=L3',
    stage VARCHAR(20) NOT NULL COMMENT '단계명: 정상, 의심경고, 집중모니터링, 개선, L1, L2, L3, FAILSAFE',
    confidence DECIMAL(3,2) DEFAULT 1.00 COMMENT '신뢰도 0.00-1.00',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON COMMENT '추가 메타데이터 (선택사항)',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_time (session_token, created_at DESC),
    INDEX idx_user_time (user_id, created_at DESC),
    INDEX idx_level_code (level_code),
    INDEX idx_stage (stage),
    INDEX idx_created_at (created_at DESC)
);

-- 채팅 메시지 테이블 (LLM 서비스용)
CREATE TABLE IF NOT EXISTS chat_messages (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    session_token VARCHAR(64) NOT NULL,
    sender ENUM('user', 'assistant') NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stage VARCHAR(20) COMMENT '메시지 발생 시점의 단계',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_time (session_token, created_at DESC),
    INDEX idx_user_time (user_id, created_at DESC)
);

-- 알림 히스토리 테이블
CREATE TABLE IF NOT EXISTS alert_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    session_token VARCHAR(64) NOT NULL,
    alert_type ENUM('warning', 'danger', 'emergency') NOT NULL,
    alert_level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_time (session_token, created_at DESC),
    INDEX idx_alert_type (alert_type),
    INDEX idx_acknowledged (is_acknowledged)
);

-- 기본 사용자 데이터 삽입 (테스트용)
INSERT IGNORE INTO users (id, username, password_hash, name, email) VALUES
(1, 'test_driver', '$2b$12$LGHQrTGWwGlJfE1JgIgWr.K5Y2FJF.7nQlVQGUOHLPSGYGYGYGYGYG', 'Test Driver', 'driver@test.com'),
(2, 'demo_user', '$2b$12$LGHQrTGWwGlJfE1JgIgWr.K5Y2FJF.7nQlVQGUOHLPSGYGYGYGYGYG', 'Demo User', 'demo@test.com');

-- 영상 분석 결과 테이블 (확장용)
CREATE TABLE IF NOT EXISTS video_analysis_results (
    id INT PRIMARY KEY AUTO_INCREMENT,
    session_token VARCHAR(64) NOT NULL,
    frame_number INT NOT NULL,
    analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 얼굴 감지 결과
    face_detected BOOLEAN DEFAULT FALSE,
    face_confidence DECIMAL(3,2),
    face_bbox JSON COMMENT '얼굴 경계 상자 좌표',
    
    -- 눈 감지 결과  
    eyes_detected BOOLEAN DEFAULT FALSE,
    left_eye_open BOOLEAN,
    right_eye_open BOOLEAN,
    eye_aspect_ratio DECIMAL(4,3) COMMENT 'EAR 값',
    
    -- 머리 자세
    head_pose JSON COMMENT '머리 회전 각도 (pitch, yaw, roll)',
    
    -- 졸음 지표
    blink_duration_ms INT DEFAULT 0,
    microsleep_detected BOOLEAN DEFAULT FALSE,
    yawn_detected BOOLEAN DEFAULT FALSE,
    
    -- 최종 졸음 점수
    drowsiness_score DECIMAL(5,3) COMMENT '0.000-100.000',
    level_code INT COMMENT '계산된 등급',
    
    -- 원본 이미지 정보
    image_path VARCHAR(500) COMMENT '분석된 이미지 파일 경로',
    image_size JSON COMMENT '이미지 크기 정보',
    
    INDEX idx_session_frame (session_token, frame_number),
    INDEX idx_timestamp (analysis_timestamp DESC),
    INDEX idx_drowsiness_score (drowsiness_score DESC)
);

-- 시스템 설정 테이블
CREATE TABLE IF NOT EXISTS system_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    setting_key VARCHAR(100) UNIQUE NOT NULL,
    setting_value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_setting_key (setting_key)
);

-- 기본 시스템 설정
INSERT IGNORE INTO system_settings (setting_key, setting_value, description) VALUES
('drowsiness_threshold_l1', '70', 'L1 경고 임계값'),
('drowsiness_threshold_l2', '80', 'L2 경고 임계값'),
('drowsiness_threshold_l3', '90', 'L3 경고 임계값'),
('stability_seconds', '2.0', '상태 안정화 시간(초)'),
('cooldown_seconds', '30.0', '알림 쿨다운 시간(초)'),
('max_session_duration_hours', '8', '최대 세션 지속 시간'),
('video_analysis_fps', '5', '영상 분석 FPS'),
('confidence_threshold', '0.7', '최소 신뢰도 임계값');

-- 실시간 상태 뷰 (최신 상태 조회용)
CREATE OR REPLACE VIEW v_latest_driver_states AS
SELECT 
    h.user_id,
    h.session_token,
    u.username,
    u.name,
    h.level_code,
    h.stage,
    h.confidence,
    h.created_at,
    TIMESTAMPDIFF(MINUTE, h.created_at, NOW()) AS minutes_ago,
    s.is_active AS session_active
FROM driver_state_history h
JOIN users u ON u.id = h.user_id
LEFT JOIN user_session s ON s.session_token = h.session_token
WHERE h.id IN (
    SELECT MAX(id) 
    FROM driver_state_history 
    GROUP BY session_token
)
ORDER BY h.created_at DESC;

-- 세션 통계 뷰
CREATE OR REPLACE VIEW v_session_statistics AS
SELECT 
    h.session_token,
    h.user_id,
    u.username,
    COUNT(*) AS total_records,
    MIN(h.created_at) AS session_start,
    MAX(h.created_at) AS last_update,
    TIMESTAMPDIFF(MINUTE, MIN(h.created_at), MAX(h.created_at)) AS duration_minutes,
    AVG(h.level_code) AS avg_level_code,
    MAX(h.level_code) AS max_level_code,
    SUM(CASE WHEN h.level_code >= 70 THEN 1 ELSE 0 END) AS warning_count,
    SUM(CASE WHEN h.level_code >= 90 THEN 1 ELSE 0 END) AS critical_count
FROM driver_state_history h
JOIN users u ON u.id = h.user_id
GROUP BY h.session_token, h.user_id, u.username
ORDER BY last_update DESC;

-- 영상 데이터 수집기 상태 확인을 위한 프로시저
DELIMITER //
CREATE OR REPLACE PROCEDURE GetActiveSessionStatus()
BEGIN
    SELECT 
        s.session_token,
        s.user_id,
        u.username,
        s.created_at AS session_start,
        s.last_activity,
        latest.level_code AS current_level,
        latest.stage AS current_stage,
        latest.created_at AS last_state_update,
        TIMESTAMPDIFF(SECOND, latest.created_at, NOW()) AS seconds_since_last_update,
        CASE 
            WHEN TIMESTAMPDIFF(SECOND, latest.created_at, NOW()) > 60 THEN 'STALE'
            WHEN latest.level_code >= 90 THEN 'CRITICAL'
            WHEN latest.level_code >= 70 THEN 'WARNING'
            ELSE 'NORMAL'
        END AS status
    FROM user_session s
    JOIN users u ON u.id = s.user_id
    LEFT JOIN (
        SELECT DISTINCT session_token,
               FIRST_VALUE(level_code) OVER (PARTITION BY session_token ORDER BY created_at DESC) AS level_code,
               FIRST_VALUE(stage) OVER (PARTITION BY session_token ORDER BY created_at DESC) AS stage,
               FIRST_VALUE(created_at) OVER (PARTITION BY session_token ORDER BY created_at DESC) AS created_at
        FROM driver_state_history
    ) latest ON latest.session_token = s.session_token
    WHERE s.is_active = 1
      AND (s.expires_at IS NULL OR s.expires_at > NOW())
    ORDER BY latest.created_at DESC;
END //
DELIMITER ;

-- 데이터 정리를 위한 이벤트 (선택사항)
-- SET GLOBAL event_scheduler = ON;
-- CREATE EVENT IF NOT EXISTS cleanup_old_data
-- ON SCHEDULE EVERY 1 DAY
-- DO
--   DELETE FROM driver_state_history 
--   WHERE created_at < DATE_SUB(NOW(), INTERVAL 7 DAY);
