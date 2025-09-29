-- PostgreSQL Query Optimizations for EndoFlix
-- Run these commands to improve query performance

-- Indexes for endoflix_files table
CREATE INDEX IF NOT EXISTS idx_endoflix_files_file_path ON endoflix_files(file_path);
CREATE INDEX IF NOT EXISTS idx_endoflix_files_hash_id ON endoflix_files(hash_id);
CREATE INDEX IF NOT EXISTS idx_endoflix_files_is_favorite ON endoflix_files(is_favorite);
CREATE INDEX IF NOT EXISTS idx_endoflix_files_view_count ON endoflix_files(view_count DESC);
CREATE INDEX IF NOT EXISTS idx_endoflix_files_size_bytes ON endoflix_files(size_bytes);
CREATE INDEX IF NOT EXISTS idx_endoflix_files_file_path_size ON endoflix_files(file_path, size_bytes);

-- Composite index for LIKE queries on file_path
CREATE INDEX IF NOT EXISTS idx_endoflix_files_file_path_gin ON endoflix_files USING gin (file_path gin_trgm_ops);

-- Indexes for endoflix_playlist table
CREATE INDEX IF NOT EXISTS idx_endoflix_playlist_is_temp ON endoflix_playlist(is_temp);
CREATE INDEX IF NOT EXISTS idx_endoflix_playlist_name ON endoflix_playlist(name);

-- Indexes for endoflix_session table
CREATE INDEX IF NOT EXISTS idx_endoflix_session_name ON endoflix_session(name);

-- Materialized view for analytics (refresh periodically)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_analytics_stats AS
SELECT
    (SELECT COUNT(*) FROM endoflix_files) as total_videos,
    (SELECT COUNT(*) FROM endoflix_playlist WHERE is_temp = FALSE) as total_playlists,
    (SELECT COUNT(*) FROM endoflix_session) as total_sessions,
    (SELECT COUNT(*) FROM endoflix_files WHERE is_favorite = TRUE) as favorite_videos;

-- View for top videos
CREATE OR REPLACE VIEW v_top_videos AS
SELECT file_path, view_count, is_favorite, last_viewed_at
FROM endoflix_files
ORDER BY view_count DESC
LIMIT 10;

-- View for file type statistics
CREATE OR REPLACE VIEW v_file_types AS
SELECT
    CASE
        WHEN file_path ILIKE '%.mp4' THEN 'mp4'
        WHEN file_path ILIKE '%.mkv' THEN 'mkv'
        WHEN file_path ILIKE '%.mov' THEN 'mov'
        WHEN file_path ILIKE '%.avi' THEN 'avi'
        WHEN file_path ILIKE '%.webm' THEN 'webm'
        ELSE 'other'
    END as file_type,
    COUNT(*) as count
FROM endoflix_files
GROUP BY file_type;

-- Function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_analytics_stats()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW mv_analytics_stats;
END;
$$ LANGUAGE plpgsql;

-- Optimized query examples (to be used in application code):

-- Instead of: SELECT COUNT(*) FROM endoflix_files
-- Use: SELECT total_videos FROM mv_analytics_stats;

-- Instead of: SELECT file_path, view_count, is_favorite FROM endoflix_files ORDER BY view_count DESC LIMIT 10
-- Use: SELECT * FROM v_top_videos;

-- For file type stats, use the view instead of processing in Python
-- SELECT * FROM v_file_types;