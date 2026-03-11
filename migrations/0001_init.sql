CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    phone VARCHAR(32) NULL,
    avatar_path VARCHAR(512) NULL,
    created_at VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS item_reports (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    item_type VARCHAR(10) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(120) NOT NULL,
    location VARCHAR(255) NOT NULL,
    event_date VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    image_paths JSONB NULL,
    created_at VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS match_candidates (
    id VARCHAR(36) PRIMARY KEY,
    lost_item_id VARCHAR(36) NOT NULL REFERENCES item_reports(id),
    found_item_id VARCHAR(36) NOT NULL REFERENCES item_reports(id),
    text_score DOUBLE PRECISION NOT NULL,
    image_score DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    created_at VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS match_decisions (
    id VARCHAR(36) PRIMARY KEY,
    lost_item_id VARCHAR(36) NOT NULL REFERENCES item_reports(id),
    found_item_id VARCHAR(36) NOT NULL REFERENCES item_reports(id),
    status VARCHAR(20) NOT NULL,
    created_at VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_events (
    id VARCHAR(36) PRIMARY KEY,
    lost_item_id VARCHAR(36) NOT NULL,
    found_item_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(20) NOT NULL,
    payload TEXT NOT NULL,
    created_at VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS device_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    token VARCHAR(512) NOT NULL UNIQUE,
    platform VARCHAR(32) NOT NULL,
    created_at VARCHAR(64) NOT NULL
);
