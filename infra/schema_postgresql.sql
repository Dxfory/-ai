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

CREATE TABLE IF NOT EXISTS reference_uploads (
    id VARCHAR(32) PRIMARY KEY,
    original_filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_url TEXT NOT NULL,
    consent_scope VARCHAR(64) DEFAULT 'personal_analysis',
    notes TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS line_drafts (
    id VARCHAR(32) PRIMARY KEY,
    reference_upload_id VARCHAR(32) REFERENCES reference_uploads(id),
    file_path TEXT NOT NULL,
    file_url TEXT NOT NULL,
    line_strength INTEGER DEFAULT 3,
    detail_level INTEGER DEFAULT 3,
    preserve_texture BOOLEAN DEFAULT TRUE,
    provider VARCHAR(64) DEFAULT 'local_edge_preview',
    status VARCHAR(32) DEFAULT 'ready',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS practice_sessions (
    id VARCHAR(32) PRIMARY KEY,
    reference_upload_id VARCHAR(32) REFERENCES reference_uploads(id),
    line_draft_id VARCHAR(32) REFERENCES line_drafts(id),
    title VARCHAR(255) NOT NULL,
    status VARCHAR(32) DEFAULT 'active',
    current_step_num INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS practice_step_runs (
    id VARCHAR(32) PRIMARY KEY,
    session_id VARCHAR(32) REFERENCES practice_sessions(id),
    step_num INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    instruction TEXT NOT NULL,
    checklist JSONB DEFAULT '[]',
    common_mistakes JSONB DEFAULT '[]',
    status VARCHAR(32) DEFAULT 'pending',
    submission_image_url TEXT DEFAULT '',
    submission_image_path TEXT DEFAULT '',
    overlay_image_url TEXT DEFAULT '',
    overlay_image_path TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_courses_artwork ON courses(artwork_id);
CREATE INDEX idx_assets_risk_level ON assets(risk_level);
CREATE INDEX idx_assets_display_allowed ON assets(display_allowed);
CREATE INDEX idx_assets_train_allowed ON assets(train_allowed);
CREATE INDEX idx_steps_course ON steps(course_id);
CREATE INDEX idx_submissions_step ON submissions(step_id);
CREATE INDEX idx_submissions_user ON submissions(user_id);
CREATE INDEX idx_error_profiles_user ON error_profiles(user_id);
CREATE INDEX idx_line_drafts_reference ON line_drafts(reference_upload_id);
CREATE INDEX idx_practice_sessions_reference ON practice_sessions(reference_upload_id);
CREATE INDEX idx_practice_step_runs_session ON practice_step_runs(session_id);
