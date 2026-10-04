"""
สรุปข้อมูลดิบ (data/raw/*.csv) -> ตารางสรุปที่ dashboard ใช้ (data/aggregated/*.csv + dashboard_data.json)

    python dashboard/scripts/build_aggregates.py

ทุกตัวเลขบน dashboard มาจากไฟล์ในโฟลเดอร์ aggregated/ และมี SQL ที่ให้ผลเดียวกันใน sql/queries.sql
(standard library ล้วน — ไม่ต้องติดตั้ง pandas)
"""
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, AGG = ROOT / "data" / "raw", ROOT / "data" / "aggregated"
AGG.mkdir(parents=True, exist_ok=True)

# สมมติฐานสำหรับ "ความเสียหายที่ป้องกันได้" (แสดงบน dashboard พร้อมแหล่งที่มา)
AVG_LOSS_THB = 12_956          # ค่าเสียหายเฉลี่ยต่อเหยื่อ — GASA / Nation Thailand
DEFAULT_CONVERSION = 0.02      # สมมติ: 2% ของสายเสี่ยงสูงที่ "ถ้าไม่เตือน" จะกลายเป็นเหยื่อ


def read(name):
    with open(RAW / f"{name}.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(name, rows, cols):
    with open(AGG / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  {name:24s} {len(rows):>5} rows")


def dt(s):
    return datetime.fromisoformat(s)


def mask(p):  # ไม่โชว์เบอร์เต็มบนหน้าจอ (แม้เป็นข้อมูลจำลอง) — แนวปฏิบัติ PDPA
    return f"{p[:3]}-xxx-{p[-4:]}"


def prefix_group(p):
    return "02 (เบอร์บ้าน/ปลอมเป็นองค์กร)" if p.startswith("02") else f"{p[:2]}x (มือถือ)"


calls = read("call_logs")
bl = read("blacklist_numbers")
reports = read("reports")
rcats = read("report_categories")
cats = {r["id"]: r for r in read("scam_categories")}
users = {u["id"]: u for u in read("users")}
for c in calls:
    c["_dt"] = dt(c["created_at"])
    c["_syn"] = c["is_synthetic_voice"] == "true"
    c["_score"] = int(c["risk_score"])

# 1) daily -------------------------------------------------------------------
daily = defaultdict(Counter)
for c in calls:
    d = daily[c["_dt"].date().isoformat()]
    d["total"] += 1
    d[c["status"]] += 1
    d["synthetic"] += c["_syn"]
    d[f"src_{c['source']}"] += 1
daily_rows = [dict(date=k, total=v["total"], safe=v["safe"], suspect=v["suspect"], high_risk=v["high_risk"],
                   synthetic=v["synthetic"], number_check=v["src_number_check"], audio=v["src_audio"],
                   demo=v["src_demo"]) for k, v in sorted(daily.items())]
write("daily_calls", daily_rows, list(daily_rows[0]))

# 2) monthly KPI -------------------------------------------------------------
first_call = {}
for c in calls:
    first_call.setdefault(c["phone_number"], c["_dt"])  # calls เรียงตามเวลาอยู่แล้ว
bl_phones = {b["phone_number"] for b in bl}
monthly = defaultdict(lambda: dict(total=0, high_risk=0, suspect=0, synthetic=0, audio_hr=0, audio_hr_syn=0,
                                   hr_known=0, lags=[], new_numbers=0, reports=0))
for c in calls:
    m = monthly[c["created_at"][:7]]
    m["total"] += 1
    m["synthetic"] += c["_syn"]
    if c["status"] == "suspect":
        m["suspect"] += 1
    if c["status"] == "high_risk":
        m["high_risk"] += 1
        m["hr_known"] += c["phone_number"] in bl_phones
        if c["source"] != "number_check":
            m["audio_hr"] += 1
            m["audio_hr_syn"] += c["_syn"]
for b in bl:
    fc = first_call.get(b["phone_number"])
    if fc:
        mm = monthly[fc.isoformat()[:7]]
        mm["lags"].append((dt(b["first_reported_at"]) - fc).total_seconds() / 3600)
        mm["new_numbers"] += 1
for r in reports:
    monthly[r["created_at"][:7]]["reports"] += 1


def pct(a, b):
    return round(100 * a / b, 1) if b else 0


monthly_rows = []
for k in sorted(monthly):
    m = monthly[k]
    lags = sorted(m["lags"])
    monthly_rows.append(dict(
        month=k, total_checks=m["total"], high_risk=m["high_risk"], suspect=m["suspect"],
        high_risk_pct=pct(m["high_risk"], m["total"]), synthetic_calls=m["synthetic"],
        synthetic_pct_of_audio_high_risk=pct(m["audio_hr_syn"], m["audio_hr"]),
        new_scam_numbers=m["new_numbers"], reports=m["reports"],
        median_hours_to_blacklist=round(statistics.median(lags), 1) if lags else "",
        p75_hours_to_blacklist=round(lags[int(len(lags) * 0.75)], 1) if lags else "",
        est_prevented_loss_thb=round(m["high_risk"] * DEFAULT_CONVERSION * AVG_LOSS_THB),
    ))
write("monthly_kpi", monthly_rows, list(monthly_rows[0]))

# 3) heatmap วัน x ชั่วโมง (สายเสี่ยงสูง) ---------------------------------------
heat = Counter()
for c in calls:
    if c["status"] == "high_risk":
        heat[(c["_dt"].weekday(), c["_dt"].hour)] += 1
heat_rows = [dict(weekday=w, hour=h, high_risk_calls=heat[(w, h)]) for w in range(7) for h in range(24)]
write("heatmap_weekday_hour", heat_rows, ["weekday", "hour", "high_risk_calls"])

# 4) รูปแบบการหลอกรายเดือน (reports x categories) ------------------------------
rep_month = {r["id"]: r["created_at"][:7] for r in reports}
catm = Counter()
for rc in rcats:
    catm[(rep_month[rc["report_id"]], cats[rc["category_id"]]["code"])] += 1
months = sorted({m for m, _ in catm})
cat_rows = [dict(month=m, category_code=cats[cid]["code"], category_name=cats[cid]["name"],
                 reports=catm[(m, cats[cid]["code"])]) for m in months for cid in sorted(cats, key=int)]
write("category_monthly", cat_rows, ["month", "category_code", "category_name", "reports"])

# 5) Pareto: เบอร์ไม่กี่เบอร์ ก่อเหตุส่วนใหญ่ --------------------------------------
hr_by_num = Counter(c["phone_number"] for c in calls if c["status"] == "high_risk")
ranked = hr_by_num.most_common()
tot = sum(hr_by_num.values())
pareto_rows, cum = [], 0
for i, (p, n) in enumerate(ranked, 1):
    cum += n
    pct_nums = 100 * i / len(ranked)
    if i == 1 or i == len(ranked) or i % max(1, len(ranked) // 100) == 0:
        pareto_rows.append(dict(rank=i, pct_numbers=round(pct_nums, 2), cum_pct_calls=round(100 * cum / tot, 2)))
write("pareto_numbers", pareto_rows, ["rank", "pct_numbers", "cum_pct_calls"])

# 6) Top 10 เบอร์อันตราย -------------------------------------------------------
bl_by_phone = {b["phone_number"]: b for b in bl}
num_cat = {}
rep_bl = {r["id"]: r["blacklist_number_id"] for r in reports}
bl_id_phone = {b["id"]: b["phone_number"] for b in bl}
cat_count_by_phone = defaultdict(Counter)
for rc in rcats:
    cat_count_by_phone[bl_id_phone[rep_bl[rc["report_id"]]]][cats[rc["category_id"]]["name"]] += 1
top_rows = []
for p, n in ranked[:10]:
    b = bl_by_phone.get(p, {})
    top_rows.append(dict(phone_masked=mask(p), high_risk_calls=n, report_count=b.get("report_count", 0),
                         risk_score=b.get("risk_score", ""),
                         main_category=(cat_count_by_phone[p].most_common(1) or [("-", 0)])[0][0],
                         first_seen=first_call[p].date().isoformat(),
                         active_days=(max(c["_dt"] for c in calls if c["phone_number"] == p) - first_call[p]).days + 1))
write("top_numbers", top_rows, list(top_rows[0]))

# 7) prefix ของเบอร์มิจฉาชีพ -------------------------------------------------------
pre = Counter()
for p, n in hr_by_num.items():
    pre[prefix_group(p)] += n
prefix_rows = [dict(prefix=k, high_risk_calls=v) for k, v in pre.most_common()]
write("prefix_mix", prefix_rows, ["prefix", "high_risk_calls"])

# 8) พันธมิตร: report ตาม role รายเดือน --------------------------------------------
role_m = Counter()
for r in reports:
    role = users[r["reported_by"]]["role"] if r["reported_by"] else "anonymous"
    role_m[(r["created_at"][:7], role)] += 1
roles = ["bank", "telco", "gov", "anonymous"]
partner_rows = [dict(month=m, **{ro: role_m[(m, ro)] for ro in roles}) for m in months]
active_partner = Counter()
for m in months:
    end = datetime.fromisoformat(f"{m}-28T23:59:59+07:00")
    active_partner[m] = sum(1 for u in users.values() if u["role"] != "admin" and dt(u["created_at"]) <= end)
for row in partner_rows:
    row["partner_accounts"] = active_partner[row["month"]]
write("partner_reports_monthly", partner_rows, ["month"] + roles + ["partner_accounts"])

# 9) source mix ---------------------------------------------------------------
src = Counter((c["created_at"][:7], c["source"]) for c in calls)
src_rows = [dict(month=m, number_check=src[(m, "number_check")], audio=src[(m, "audio")], demo=src[(m, "demo")])
            for m in months]
write("source_monthly", src_rows, ["month", "number_check", "audio", "demo"])

# ---------------------------------------------------------------- JSON for dashboard
summary = dict(
    period=[daily_rows[0]["date"], daily_rows[-1]["date"]],
    total_checks=len(calls),
    high_risk=sum(r["high_risk"] for r in monthly_rows),
    synthetic=sum(r["synthetic_calls"] for r in monthly_rows),
    blacklist_numbers=len(bl), reports=len(reports),
    partners=sum(1 for u in users.values() if u["role"] != "admin"),
    top10pct_share=round(next(r["cum_pct_calls"] for r in pareto_rows if r["pct_numbers"] >= 10), 1),
    unique_scam_numbers=len(ranked),
    avg_loss_thb=AVG_LOSS_THB, default_conversion=DEFAULT_CONVERSION,
)
data = dict(summary=summary, daily=daily_rows, monthly=monthly_rows, heatmap=heat_rows, categories=cat_rows,
            pareto=pareto_rows, top_numbers=top_rows, prefix=prefix_rows, partners=partner_rows, sources=src_rows)
(AGG / "dashboard_data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("  dashboard_data.json written")
print(json.dumps(summary, ensure_ascii=False, indent=1))
