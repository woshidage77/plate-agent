CREATE DATABASE IF NOT EXISTS plate_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE plate_agent;

CREATE TABLE IF NOT EXISTS plate_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plate_number VARCHAR(10) NOT NULL,
    image_path VARCHAR(500),
    plate_color VARCHAR(20),
    avg_confidence DOUBLE,
    blacklist_hit BOOLEAN DEFAULT FALSE,
    blacklist_type VARCHAR(50),
    recognize_method VARCHAR(20),
    process_time_ms BIGINT,
    status VARCHAR(20),
    error_message VARCHAR(1000),
    raw_result TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_plate_number (plate_number),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;