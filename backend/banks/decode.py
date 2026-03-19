import sys
import os
import json

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from ocr_engine import extract_text_from_pdf
from banks.bank_detector import detect_bank
from banks.boi import extract_transactions

pdf = "C:/Users/admin/Downloads/boi_removed.pdf"

# ── STEP 1: What does ocr_engine return? ──
lines = extract_text_from_pdf(pdf)
print(f"Lines from ocr_engine : {len(lines)}")
print(f"First 5 lines:")
for l in lines[:5]:
    print(f"  {repr(l)}")

# ── STEP 2: What bank is detected? ──
bank_key = detect_bank(pdf, lines)
print(f"\nDetected bank : '{bank_key}'")   # Must be 'boi', not 'generic'

# ── STEP 3: How many transactions does boi.extract_transactions return? ──
txns = extract_transactions(pdf)
print(f"\nboi.extract_transactions count : {len(txns)}")  # Must be 149

# ── STEP 4: Full parse ──
from banks import parse_bank_statement
data = parse_bank_statement(pdf)
print(f"\nparse_bank_statement count : {len(data['transactions'])}")