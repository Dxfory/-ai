-- 国画临摹 AI 教练 - PostgreSQL Schema (Phase 0 修改版)
-- 无 teacher 表、无 classroom 表

CREATE TABLE IF NOT EXISTS assets (
    id VARCHAR(32) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    source_url TEXT NOT NULL,
    license_type VARCHAR(64) NOT NULL,
    license_url TEXT DEFAULT '',
    attribution_text TEXT DEFAULT '',
    display_allowed BOOLEAN DEFAULT FALSE,
    train_allowed BOOLEAN DEFAULT FALSE,
    commercial_allowed BOOLEAN DEFAULT FALSE,
    derivative_allowed BOOLEAN DEFAULT FALSE,
    risk_level VARCHAR(32) DEFAULT 'unknown',
    file_hash VARCHAR(128) DEFAULT '',
    image_url TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS artworks (
    id VARCHAR(32) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    genre VARCHAR(32) NOT NULL,
    method VARCHAR(32) NOT NULL,
    image_url TEXT,
    input_method VARCHAR(32) DEFAULT 'photo',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS courses (
    id VARCHAR(32) PRIMARY KEY,
    artwork_id VARCHAR(32) REFERENCES artworks(id),
    genre VARCHAR(32) NOT NULL,
    method VARCHAR(32) NOT NULL,
    template_version VARCHAR(16) DEFAULT '1.0',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS steps (
    id VARCHAR(32) PRIMARY KEY,
    course_id VARCHAR(32) REFERENCES courses(id),
    step_num INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    instruction TEXT NOT NULL,
    demo_image_url TEXT DEFAULT '',
    checklist JSONB DEFAULT '[]',
    materials JSONB DEFAULT '[]',
    common_mistakes JSONB DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS submissions (
    id VARCHAR(32) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    step_id VARCHAR(32) REFERENCES steps(id),
    image_url TEXT NOT NULL,
    status VARCHAR(32) DEFAULT 'pending',
    feedback JSONB,
    submitted_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS error_profiles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    error_type VARCHAR(64) NOT NULL,
    frequency INTEGER DEFAULT 0,
    trend VARCHAR(32) DEFAULT 'stable',
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_courses_artwork ON courses(artwork_id);
CREATE INDEX idx_assets_risk_level ON assets(risk_level);
CREATE INDEX idx_assets_display_allowed ON assets(display_allowed);
CREATE INDEX idx_assets_train_allowed ON assets(train_allowed);
CREATE INDEX idx_steps_course ON steps(course_id);
CREATE INDEX idx_submissions_step ON submissions(step_id);
CREATE INDEX idx_submissions_user ON submissions(user_id);
CREATE INDEX idx_error_profiles_user ON error_profiles(user_id);
