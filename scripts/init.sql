-- Initialize database with required schema
-- This file is mounted as read-only in production

-- Create users table for EndoFlix user management
CREATE TABLE IF NOT EXISTS endoflix_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Create index on username for faster lookups
CREATE INDEX IF NOT EXISTS idx_endoflix_users_username ON endoflix_users(username);

-- Insert default admin user (password: admin123)
-- Hash generated with bcrypt
INSERT INTO endoflix_users (username, password_hash)
VALUES ('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPjYLC3zyKQO')
ON CONFLICT (username) DO NOTHING;