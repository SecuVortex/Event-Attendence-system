-- ==============================================================================
-- Cyber-Attend: Supabase PostgreSQL Schema
-- Event Attendance Management System
-- ==============================================================================

-- 1. Events Table: Container for symposiums, hackathons, conferences
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    venue VARCHAR(255),
    start_date VARCHAR(50) NOT NULL,
    end_date VARCHAR(50) NOT NULL,
    created_at VARCHAR(50) NOT NULL
);

-- 2. Sessions Table: Scheduled check-in sessions under events
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    session_date VARCHAR(50) NOT NULL,
    start_time VARCHAR(50) NOT NULL,
    end_time VARCHAR(50) NOT NULL,
    late_threshold_minutes INTEGER DEFAULT 15,
    is_active INTEGER DEFAULT 0,
    session_token VARCHAR(100) UNIQUE NOT NULL,
    created_at VARCHAR(50) NOT NULL
);

-- 3. Participants Table: Registered participants with unique ID and hashed PIN
CREATE TABLE IF NOT EXISTS participants (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    participant_id VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    organization VARCHAR(255),
    password_hash TEXT NOT NULL,
    created_at VARCHAR(50) NOT NULL
);

-- 4. Attendance Records: Enforces exactly 1 verified check-in per participant per session
CREATE TABLE IF NOT EXISTS attendance_records (
    id SERIAL PRIMARY KEY,
    participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    checkin_time VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK(status IN ('Present', 'Late')),
    admin_scanner_id VARCHAR(100) NOT NULL DEFAULT 'SYSTEM_GATE',
    created_at VARCHAR(50) NOT NULL,
    CONSTRAINT uq_participant_session UNIQUE(participant_id, session_id)
);

-- 5. Attendance Logs: Real-time telemetry for duplicate attempts, invalid credentials, etc.
CREATE TABLE IF NOT EXISTS attendance_logs (
    id SERIAL PRIMARY KEY,
    session_id INTEGER,
    participant_code_attempted VARCHAR(100),
    attempt_type VARCHAR(50) NOT NULL CHECK(attempt_type IN ('SUCCESS', 'DUPLICATE', 'INVALID_CREDENTIALS', 'SESSION_INACTIVE')),
    message TEXT,
    scanner_id VARCHAR(100) DEFAULT 'SYSTEM_GATE',
    created_at VARCHAR(50) NOT NULL
);

-- 6. Staff Accounts: Admin console authentication
CREATE TABLE IF NOT EXISTS staff_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name VARCHAR(255) NOT NULL DEFAULT 'Event Administrator',
    created_at VARCHAR(50) NOT NULL
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_event ON sessions(event_id);
CREATE INDEX IF NOT EXISTS idx_participants_event ON participants(event_id);
CREATE INDEX IF NOT EXISTS idx_participants_code ON participants(participant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance_records(session_id);
CREATE INDEX IF NOT EXISTS idx_attendance_participant ON attendance_records(participant_id);
CREATE INDEX IF NOT EXISTS idx_attendance_logs_session ON attendance_logs(session_id);
