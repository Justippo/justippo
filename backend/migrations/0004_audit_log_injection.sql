-- Sprint 3 NT-3: Prompt Injection Hardening
-- Adds injection detection fields to audit_log table.
-- injection_detected: 1 when sanitize_for_injection() found patterns, 0 otherwise
-- injection_patterns: JSON array of matched pattern names (NULL when no detection)
--
-- D1 SQLite: ALTER TABLE is safe when using IF NOT EXISTS pattern for new tables.
-- These columns use DEFAULT so existing rows are not affected.

ALTER TABLE audit_log ADD COLUMN injection_detected INTEGER DEFAULT 0;
ALTER TABLE audit_log ADD COLUMN injection_patterns TEXT;
