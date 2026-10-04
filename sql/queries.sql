-- SQL ที่ให้ผลเดียวกับไฟล์ใน dashboard/data/aggregated/ (หนึ่ง query ต่อหนึ่งกราฟ)
-- เวลาในระบบเก็บเป็น timestamptz -> แปลงเป็นเวลาไทยก่อนตัดวัน/เดือน/ชั่วโมง
-- ทุก query กรองด้วย "ช่วงเวลา" (ไม่ใช้ date(created_at) = ...) จึงใช้ index IDX-6 / IDX-7 ได้

SET TIME ZONE 'Asia/Bangkok';

-- ① daily_calls.csv — ปริมาณการตรวจรายวัน แยกสถานะ/แหล่งที่มา
SELECT created_at::date                                   AS date,
       count(*)                                           AS total,
       count(*) FILTER (WHERE status = 'safe')            AS safe,
       count(*) FILTER (WHERE status = 'suspect')         AS suspect,
       count(*) FILTER (WHERE status = 'high_risk')       AS high_risk,
       count(*) FILTER (WHERE is_synthetic_voice)         AS synthetic,
       count(*) FILTER (WHERE source = 'number_check')    AS number_check,
       count(*) FILTER (WHERE source = 'audio')           AS audio,
       count(*) FILTER (WHERE source = 'demo')            AS demo
FROM call_logs
WHERE created_at >= '2026-04-01' AND created_at < '2026-10-01'
GROUP BY 1 ORDER BY 1;

-- ② monthly_kpi.csv — % เสียงสังเคราะห์ ในสายเสี่ยงสูงที่ถูกวิเคราะห์ด้วยเสียง
SELECT to_char(created_at, 'YYYY-MM')                                        AS month,
       count(*)                                                              AS total_checks,
       count(*) FILTER (WHERE status = 'high_risk')                          AS high_risk,
       round(100.0 * count(*) FILTER (WHERE status = 'high_risk') / count(*), 1) AS high_risk_pct,
       round(100.0 * count(*) FILTER (WHERE status = 'high_risk' AND source <> 'number_check' AND is_synthetic_voice)
                   / nullif(count(*) FILTER (WHERE status = 'high_risk' AND source <> 'number_check'), 0), 1)
                                                                             AS synthetic_pct_of_audio_high_risk
FROM call_logs
GROUP BY 1 ORDER BY 1;

-- ③ monthly_kpi.median_hours_to_blacklist — เวลาจาก "สายแรกที่ระบบเห็น" ถึง "report แรก"
WITH first_seen AS (
    SELECT phone_number, min(created_at) AS first_call FROM call_logs GROUP BY phone_number
)
SELECT to_char(f.first_call, 'YYYY-MM') AS month,
       round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY extract(epoch FROM b.first_reported_at - f.first_call) / 3600))::numeric, 1) AS median_hours,
       round((percentile_cont(0.75) WITHIN GROUP (ORDER BY extract(epoch FROM b.first_reported_at - f.first_call) / 3600))::numeric, 1) AS p75_hours
FROM blacklist_numbers b JOIN first_seen f USING (phone_number)
GROUP BY 1 ORDER BY 1;

-- ④ heatmap_weekday_hour.csv — มิจฉาชีพโทรวันไหน เวลาไหน (weekday: 0 = จันทร์)
SELECT (extract(isodow FROM created_at)::int - 1) AS weekday,
       extract(hour FROM created_at)::int         AS hour,
       count(*)                                   AS high_risk_calls
FROM call_logs
WHERE risk_score >= 80                     -- ตรงเงื่อนไข partial index IDX-7
GROUP BY 1, 2 ORDER BY 1, 2;

-- ⑤ category_monthly.csv — รูปแบบการหลอก (M-N reports <-> scam_categories)
SELECT to_char(r.created_at, 'YYYY-MM') AS month, c.code AS category_code, c.name AS category_name, count(*) AS reports
FROM reports r
JOIN report_categories rc ON rc.report_id = r.id
JOIN scam_categories c    ON c.id = rc.category_id
GROUP BY 1, 2, 3, c.id ORDER BY 1, c.id;

-- ⑥ pareto_numbers.csv — กี่ % ของเบอร์ ก่อสายเสี่ยงสูงกี่ %
WITH per_number AS (
    SELECT phone_number, count(*) AS n FROM call_logs WHERE risk_score >= 80 GROUP BY 1
), ranked AS (
    SELECT row_number() OVER (ORDER BY n DESC) AS rank,
           count(*) OVER ()                    AS numbers,
           sum(n) OVER (ORDER BY n DESC ROWS UNBOUNDED PRECEDING) AS cum,
           sum(n) OVER ()                      AS total
    FROM per_number
)
SELECT rank, round(100.0 * rank / numbers, 2) AS pct_numbers, round(100.0 * cum / total, 2) AS cum_pct_calls
FROM ranked ORDER BY rank;

-- ⑦ partner_reports_monthly.csv — ใครช่วยแจ้ง (1-N users -> reports)
SELECT to_char(r.created_at, 'YYYY-MM') AS month,
       count(*) FILTER (WHERE u.role = 'bank')  AS bank,
       count(*) FILTER (WHERE u.role = 'telco') AS telco,
       count(*) FILTER (WHERE u.role = 'gov')   AS gov,
       count(*) FILTER (WHERE r.reported_by IS NULL) AS anonymous
FROM reports r LEFT JOIN users u ON u.id = r.reported_by
GROUP BY 1 ORDER BY 1;

-- ⑧ top_numbers.csv — 10 เบอร์อันตรายที่สุด
SELECT left(cl.phone_number, 3) || '-xxx-' || right(cl.phone_number, 4) AS phone_masked,
       count(*) AS high_risk_calls, b.report_count, b.risk_score
FROM call_logs cl JOIN blacklist_numbers b USING (phone_number)
WHERE cl.risk_score >= 80
GROUP BY cl.phone_number, b.report_count, b.risk_score
ORDER BY high_risk_calls DESC LIMIT 10;
