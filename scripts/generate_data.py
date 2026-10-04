"""
VoiceGuard AI — สร้างชุดข้อมูลจำลอง (simulated) สำหรับ Storytelling Dashboard

    python dashboard/scripts/generate_data.py

- ใช้ Python standard library อย่างเดียว (ไม่ต้องติดตั้งอะไรเพิ่ม)
- seed คงที่ (RNG_SEED) -> รันกี่ครั้งก็ได้ข้อมูลชุดเดิม (reproducible)
- โครงสร้างคอลัมน์ "ตรงกับตารางจริง" ใน backend/app/models/*.py ทุกตาราง
  จึง COPY เข้า PostgreSQL ของระบบได้ทันที (ดู dashboard/sql/load_data.sql)
- ช่วงข้อมูล: 1 เม.ย. 2026 – 30 ก.ย. 2026 (6 เดือน, เวลา Asia/Bangkok +07:00)

สมมติฐานที่ใส่ลงในข้อมูล (เพื่อให้มี "เรื่อง" ให้เล่า — ทุกข้อเป็นการจำลอง ไม่ใช่ข้อมูลจริง):
  1) ผู้ใช้เพิ่มขึ้นต่อเนื่อง (~230 -> ~560 การตรวจ/วัน)
  2) สัดส่วนสายเสี่ยงสูงค่อย ๆ เพิ่ม และสาย "เสียงสังเคราะห์ (AI voice clone)" โตเร็วที่สุด
  3) มิจฉาชีพโทรช่วงเวลาทำการ (09–12, 13–16 น.) วันจันทร์–ศุกร์ เป็นหลัก
  4) มีคลื่นการหลอก (campaign wave) 2 ช่วง: "พัสดุ" กลาง ก.ค. และ "เสียงโคลน" ปลาย ส.ค.
  5) เบอร์มิจฉาชีพเป็นซิมใช้แล้วทิ้ง อายุสั้น 1–6 สัปดาห์ และ ~10% ของเบอร์ก่อเหตุส่วนใหญ่ (Pareto)
  6) ยิ่งมีพันธมิตร (ธนาคาร/Telco/รัฐ) ช่วยแจ้งมาก เวลาตั้งแต่ "เห็นสายแรก" ถึง "ขึ้น blacklist" ยิ่งสั้นลง
"""
import csv
import math
import random
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

RNG_SEED = 20261005
rng = random.Random(RNG_SEED)
TZ = timezone(timedelta(hours=7))
START = datetime(2026, 4, 1, tzinfo=TZ)
DAYS = 183  # 1 Apr – 30 Sep 2026
OUT = Path(__file__).resolve().parent.parent / "data" / "raw"

HIGH, SUSPECT = 80, 50  # ตรงกับ HIGH_RISK_THRESHOLD / SUSPECT_THRESHOLD ใน backend


def uid() -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def status_from_score(s: int) -> str:
    return "high_risk" if s >= HIGH else "suspect" if s >= SUSPECT else "safe"


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


# ---------------------------------------------------------------- scam_categories
CATEGORIES = [  # ตรงกับ DEFAULT_CATEGORIES ใน backend/app/models/scam_category.py (id = ลำดับ)
    ("impersonate_police", "แอบอ้างเป็นตำรวจ/DSI"),
    ("impersonate_bank", "แอบอ้างเป็นเจ้าหน้าที่ธนาคาร"),
    ("parcel", "พัสดุผิดกฎหมาย/ค้างส่ง"),
    ("investment", "ชวนลงทุนผลตอบแทนสูง"),
    ("loan", "เงินกู้ออนไลน์"),
    ("refund", "คืนเงิน/ภาษี/ค่าไฟ"),
    ("voice_clone", "ใช้เสียงสังเคราะห์เลียนแบบคนรู้จัก"),
    ("other", "อื่น ๆ"),
]
CAT_ID = {c: i + 1 for i, (c, _) in enumerate(CATEGORIES)}


def category_weights(day: int) -> dict:
    """น้ำหนักรูปแบบการหลอกตามเวลา (day 0 = 1 เม.ย.)"""
    t = day / DAYS
    w = {
        "impersonate_police": 30 - 14 * t,   # ลดลงหลังมีการประชาสัมพันธ์
        "impersonate_bank": 18,
        "parcel": 14,
        "investment": 12 + 2 * t,
        "loan": 8,
        "refund": 7,
        "voice_clone": 3 + 19 * t ** 1.4,     # โตเร็วที่สุด
        "other": 4,
    }
    if 100 <= day <= 118:  # คลื่น "พัสดุ" ~ 10–28 ก.ค.
        w["parcel"] += 22 * math.sin(math.pi * (day - 100) / 18)
    if 145 <= day <= 165:  # คลื่น "เสียงโคลน" ~ 24 ส.ค.–13 ก.ย.
        w["voice_clone"] += 16 * math.sin(math.pi * (day - 145) / 20)
    if 30 <= day <= 45:    # ช่วงยื่นภาษี/บิลค่าไฟพุ่ง ~ พ.ค.
        w["refund"] += 8
    return w


def pick(weights: dict) -> str:
    keys = list(weights)
    return rng.choices(keys, [max(weights[k], 0.01) for k in keys])[0]


# ---------------------------------------------------------------- users (พันธมิตร)
ORGS = [
    ("bank", ["ktb", "scb", "kbank", "bbl", "gsb"], "ธนาคาร"),
    ("telco", ["ais", "true", "nt"], "Telco"),
    ("gov", ["ccib", "dsi", "depa", "nbtc"], "หน่วยงานรัฐ"),
]
users = [dict(id=uid(), username="admin", email="admin@voiceguard.example", full_name="ผู้ดูแลระบบ",
              role="admin", is_active=True, auto_notify=True, created_at=iso(START - timedelta(days=30)))]
for role, orgs, label in ORGS:
    for org in orgs:
        for k in range(rng.randint(2, 4)):
            joined = START + timedelta(days=rng.choice([-20, -10, 0, 15, 30, 45, 60, 75, 90, 110, 130]),
                                       hours=rng.randint(8, 17))
            users.append(dict(
                id=uid(), username=f"{org}.officer{k + 1}", email=f"officer{k + 1}@{org}.example",
                full_name=f"เจ้าหน้าที่ {org.upper()} #{k + 1}", role=role, is_active=rng.random() > 0.04,
                auto_notify=rng.random() > 0.25, created_at=iso(joined),
            ))
partner_users = [u for u in users if u["role"] != "admin"]


def active_users(day: int) -> list:
    d = START + timedelta(days=day)
    return [u for u in partner_users if datetime.fromisoformat(u["created_at"]) <= d]


# ---------------------------------------------------------------- เบอร์มิจฉาชีพ (latent)
def mobile() -> str:
    return f"0{rng.choice([6, 8, 8, 9, 9])}{rng.randint(10_000_000, 99_999_999)}"


def spoof_landline() -> str:  # เบอร์บ้าน/สำนักงานปลอม 02-xxx-xxxx
    return f"02{rng.randint(1_000_000, 9_999_999)}"


scam_numbers = []  # dict: phone, start, life, weight, cat, voice_affinity
used = set()
for day in range(-20, DAYS):
    # จำนวนเบอร์ใหม่ต่อวันเพิ่มตามเวลา
    for _ in range(rng.randint(6, 9) + int(5 * max(day, 0) / DAYS)):
        cat = pick(category_weights(max(day, 0)))
        phone = spoof_landline() if cat in ("impersonate_bank", "impersonate_police") and rng.random() < 0.25 \
            else mobile()
        if phone in used:
            continue
        used.add(phone)
        scam_numbers.append(dict(
            phone=phone, start=day, life=rng.randint(7, 42),
            weight=rng.paretovariate(1.25),        # หางยาว -> Pareto
            cat=cat,
            voice=0.85 if cat == "voice_clone" else (0.25 if cat in ("impersonate_bank", "impersonate_police") else 0.1),
        ))


def active_numbers(day: int) -> list:
    return [n for n in scam_numbers if n["start"] <= day < n["start"] + n["life"]]


# ---------------------------------------------------------------- call_logs
HOUR_SCAM = [0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.5, 1.2, 3, 6.5, 8, 7.5, 4, 6.5, 7.5, 7, 5, 3, 2, 1.5, 1.2, 0.8, 0.5, 0.3]
HOUR_SAFE = [0.3, 0.2, 0.1, 0.1, 0.1, 0.3, 1, 2.5, 4.5, 5.5, 5.5, 5, 4.5, 5, 5, 5, 5, 5, 4.5, 4.5, 4, 3, 1.8, 0.8]

call_logs = []
first_call_seen = {}   # phone -> datetime ของสายแรกที่ระบบเห็น
calls_per_number = defaultdict(int)

for day in range(DAYS):
    date = START + timedelta(days=day)
    t = day / DAYS
    weekday = date.weekday()  # 0 = Mon
    base = 230 + 330 * t ** 1.1                       # การเติบโตของผู้ใช้
    base *= 0.72 if weekday >= 5 else 1.0             # เสาร์-อาทิตย์ใช้น้อยลง
    if 100 <= day <= 118:
        base *= 1 + 0.35 * math.sin(math.pi * (day - 100) / 18)
    if 145 <= day <= 165:
        base *= 1 + 0.30 * math.sin(math.pi * (day - 145) / 20)
    n_calls = max(50, int(rng.gauss(base, base * 0.07)))

    p_scam = 0.30 + 0.10 * t                           # สัดส่วนสายที่เกี่ยวกับมิจฉาชีพ
    if weekday >= 5:
        p_scam *= 0.6
    nums = active_numbers(day)
    weights = [n["weight"] for n in nums]
    users_today = active_users(day)
    p_demo = 0.16 - 0.12 * t                           # ช่วงแรกคนลองหน้า demo เยอะ
    for _ in range(n_calls):
        is_scam = rng.random() < p_scam and nums
        hour = rng.choices(range(24), HOUR_SCAM if is_scam else HOUR_SAFE)[0]
        ts = date + timedelta(hours=hour, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        r = rng.random()
        source = "demo" if r < p_demo else ("audio" if r < p_demo + 0.30 + 0.08 * t else "number_check")
        synthetic = False
        if is_scam:
            n = rng.choices(nums, weights)[0]
            phone = n["phone"]
            calls_per_number[phone] += 1
            first_call_seen.setdefault(phone, ts)
            score = rng.choices([rng.randint(80, 99), rng.randint(55, 79)], [0.62 + 0.1 * t, 0.38 - 0.1 * t])[0]
            if source != "number_check":  # ตรวจเสียงได้เฉพาะสายที่วิเคราะห์ audio
                synthetic = rng.random() < n["voice"] * (0.55 + 0.75 * t)
                if synthetic:
                    score = max(score, rng.randint(84, 99))
        else:
            phone = mobile()
            score = rng.choices([rng.randint(0, 34), rng.randint(35, 49), rng.randint(50, 64)], [80, 17, 3])[0]
            synthetic = source != "number_check" and rng.random() < 0.006  # false positive เล็กน้อย
        user = rng.choice(users_today) if users_today and rng.random() < 0.55 else None
        call_logs.append(dict(
            phone_number=phone, user_id=user["id"] if user else "", risk_score=score,
            status=status_from_score(score), is_synthetic_voice=synthetic, source=source, created_at=ts,
        ))

call_logs.sort(key=lambda c: c["created_at"])
for i, c in enumerate(call_logs, 1):
    c["id"] = i

# ---------------------------------------------------------------- blacklist_numbers + reports
blacklist, reports, report_cats = [], [], []
END = START + timedelta(days=DAYS)
for n in scam_numbers:
    phone = n["phone"]
    seen = first_call_seen.get(phone)
    vol = calls_per_number.get(phone, 0)
    if not seen or vol < 2:
        continue  # เบอร์ที่แทบไม่มีคนเจอ ไม่มีใครแจ้ง
    day = (seen - START).days
    t = day / DAYS
    # เวลาจากสายแรก -> report แรก หดลงเมื่อเครือข่ายพันธมิตรโตขึ้น (ชั่วโมง)
    lag_h = rng.lognormvariate(math.log(46 - 36 * t), 0.55)
    first = seen + timedelta(hours=lag_h)
    if first >= END:
        continue
    n_rep = min(1 + int(vol ** 0.55 * rng.uniform(0.3, 0.8)), 60)
    last_possible = min(seen + timedelta(days=n["life"] + 3), END - timedelta(minutes=1))
    rep_times = sorted([first] + [first + (last_possible - first) * rng.random() ** 1.6 for _ in range(n_rep - 1)])
    bl_id = uid()
    score_base = 78 if n["cat"] in ("loan", "other") else 84
    max_score = 0
    for k, rt in enumerate(rep_times):
        users_then = [u for u in active_users((rt - START).days) if u["is_active"]] or partner_users
        score = min(99, score_base + int(rng.gauss(4 + k * 0.6, 6)))
        max_score = max(max_score, score)
        rid = uid()
        reporter = rng.choices(users_then + [None], [1] * len(users_then) + [len(users_then) * 0.15])[0]
        reports.append(dict(
            id=rid, blacklist_number_id=bl_id, reported_by=reporter["id"] if reporter else "",
            risk_score=score, note="", created_at=iso(rt),
        ))
        cats = {n["cat"]}
        if rng.random() < 0.28:
            cats.add(rng.choice(["voice_clone", "impersonate_bank", "other", "impersonate_police"]))
        for c in sorted(cats, key=lambda c: CAT_ID[c]):
            report_cats.append(dict(report_id=rid, category_id=CAT_ID[c]))
    blacklist.append(dict(
        id=bl_id, phone_number=phone, status=status_from_score(max_score), risk_score=max_score,
        report_count=len(rep_times), first_reported_at=iso(rep_times[0]), last_reported_at=iso(rep_times[-1]),
    ))

# ---------------------------------------------------------------- emergency_contacts (เล็กน้อย)
emergency = []
for u in partner_users:
    for k in range(rng.choice([0, 1, 1, 2])):
        emergency.append(dict(id=uid(), user_id=u["id"], name=rng.choice(
            ["คุณแม่", "คุณพ่อ", "ลูกชาย", "ลูกสาว", "หัวหน้างาน", "สายด่วน 1441"]),
            phone_number="1441" if k == 1 else mobile(), created_at=u["created_at"], updated_at=u["created_at"]))


# ---------------------------------------------------------------- write CSV
def write(name, rows, cols):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (iso(v) if isinstance(v, datetime) else str(v).lower() if isinstance(v, bool) else v)
                        for k, v in r.items()})
    print(f"  {name:22s} {len(rows):>7,} rows")


print("writing ->", OUT)
write("scam_categories", [dict(id=i + 1, code=c, name=n) for i, (c, n) in enumerate(CATEGORIES)], ["id", "code", "name"])
write("users", users, ["id", "username", "email", "full_name", "role", "is_active", "auto_notify", "created_at"])
write("blacklist_numbers", blacklist, ["id", "phone_number", "status", "risk_score", "report_count",
                                       "first_reported_at", "last_reported_at"])
write("reports", reports, ["id", "blacklist_number_id", "reported_by", "risk_score", "note", "created_at"])
write("report_categories", report_cats, ["report_id", "category_id"])
write("call_logs", call_logs, ["id", "phone_number", "user_id", "risk_score", "status", "is_synthetic_voice",
                               "source", "created_at"])
write("emergency_contacts", emergency, ["id", "user_id", "name", "phone_number", "created_at", "updated_at"])
