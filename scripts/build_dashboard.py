"""
ประกอบ dashboard: ฝัง data/aggregated/dashboard_data.json ลงใน src/template.html -> index.html

    python dashboard/scripts/build_dashboard.py

ได้ไฟล์เดียว (self-contained) เปิดด้วยดับเบิลคลิกได้เลย ไม่ต้องรันเซิร์ฟเวอร์
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tpl = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
data = (ROOT / "data" / "aggregated" / "dashboard_data.json").read_text(encoding="utf-8")
body = tpl.replace("/*__DATA__*/null", data)
html = ('<!doctype html>\n<html lang="th">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + body + "\n</html>\n")
(ROOT / "index.html").write_text(html, encoding="utf-8")
(ROOT / "dist").mkdir(exist_ok=True)
(ROOT / "dist" / "artifact.html").write_text(body, encoding="utf-8")  # เวอร์ชันไม่มี <head> สำหรับ publish
print("built", ROOT / "index.html", f"{len(html) / 1024:.0f} KB")
