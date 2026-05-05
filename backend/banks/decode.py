"""
debug_hsbc.py — Run this locally to diagnose OCR output
Usage: python debug_hsbc.py HSBC.pdf
"""
import re, sys, os, subprocess, tempfile, glob
from PIL import Image
import pytesseract

pdf_path = sys.argv[1] if len(sys.argv) > 1 else "d:\BankStats&GST3B\HSBC.pdf"

# ── OCR first 2 pages ────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmpdir:
    prefix = os.path.join(tmpdir, "pg")
    subprocess.run(["pdftoppm", "-r", "200", pdf_path, prefix], check=True)
    pages = sorted(glob.glob(f"{prefix}-*.ppm"))
    print(f"Total pages rendered: {len(pages)}\n")

    all_lines = []
    for p in pages[:3]:  # first 3 pages only
        img  = Image.open(p)
        text = pytesseract.image_to_string(img, config="--psm 6")
        lines = text.split("\n")
        all_lines.extend(lines)
        print(f"\n{'='*60}")
        print(f"PAGE: {p}")
        print(f"{'='*60}")
        for i, line in enumerate(lines):
            print(f"{i:03d} | {repr(line)}")

# ── Check what _TABLE_START actually sees ───────────────────────────
print("\n\n" + "="*60)
print("TABLE HEADER DETECTION CHECK")
print("="*60)
_TABLE_START = re.compile(
    r'\b(Withdrawals|Deposits|Debit|Credit)\b.*\bBalance\b',
    re.IGNORECASE,
)
_DATE_ANCHOR = re.compile(
    r'^([O0]?\d[A-Z]{3}\d{4}|\d{2}[A-Z]{3}\d{4})\s+(.+)$'
)
for i, line in enumerate(all_lines):
    s = line.strip()
    if _TABLE_START.search(s):
        print(f"[TABLE HEADER FOUND] line {i:03d}: {repr(s)}")
    if _DATE_ANCHOR.match(s):
        print(f"[DATE ANCHOR FOUND]  line {i:03d}: {repr(s)}")