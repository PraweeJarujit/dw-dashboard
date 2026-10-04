-- โหลดข้อมูลจำลองของ dashboard เข้า PostgreSQL ของ VoiceGuard (schema จาก Alembic 0001/0002)
-- ใช้กับฐานข้อมูล "ว่าง" ที่รัน `alembic upgrade head` แล้วเท่านั้น (คำสั่งนี้ลบข้อมูลเดิมในตารางเหล่านี้!)
--
--   cd DetectCallcenter
--   psql "$DATABASE_URL" -f dashboard/sql/load_data.sql
--
-- users.csv ไม่มีรหัสผ่าน จึงใส่ hashed_password เป็นค่าที่ login ไม่ได้ ('!disabled')

BEGIN;

TRUNCATE report_categories, reports, blacklist_numbers, call_logs, emergency_contacts, users RESTART IDENTITY CASCADE;
DELETE FROM scam_categories;

\copy scam_categories (id, code, name) FROM 'dashboard/data/raw/scam_categories.csv' CSV HEADER

CREATE TEMP TABLE _users (id uuid, username text, email text, full_name text, role text,
                          is_active boolean, auto_notify boolean, created_at timestamptz);
\copy _users FROM 'dashboard/data/raw/users.csv' CSV HEADER
INSERT INTO users (id, username, email, hashed_password, full_name, role, is_active, auto_notify, created_at, updated_at)
SELECT id, username, email, '!disabled', full_name, role, is_active, auto_notify, created_at, created_at FROM _users;

\copy blacklist_numbers (id, phone_number, status, risk_score, report_count, first_reported_at, last_reported_at) FROM 'dashboard/data/raw/blacklist_numbers.csv' CSV HEADER
\copy reports (id, blacklist_number_id, reported_by, risk_score, note, created_at) FROM 'dashboard/data/raw/reports.csv' CSV HEADER NULL ''
\copy report_categories (report_id, category_id) FROM 'dashboard/data/raw/report_categories.csv' CSV HEADER
\copy call_logs (id, phone_number, user_id, risk_score, status, is_synthetic_voice, source, created_at) FROM 'dashboard/data/raw/call_logs.csv' CSV HEADER NULL ''
\copy emergency_contacts (id, user_id, name, phone_number, created_at, updated_at) FROM 'dashboard/data/raw/emergency_contacts.csv' CSV HEADER

-- call_logs.id เป็น identity -> เลื่อน sequence ให้ต่อจากค่าสูงสุด
SELECT setval(pg_get_serial_sequence('call_logs', 'id'), (SELECT max(id) FROM call_logs));
SELECT setval(pg_get_serial_sequence('scam_categories', 'id'), (SELECT max(id) FROM scam_categories));

COMMIT;

ANALYZE;
