import sys
import os
sys.path.insert(0, "D:\\Pcred_BankStats_Proj\\pcred_financial_analyzer\\backend")

# ── TEST 1: Which saraswat.py is actually loaded ──────────────────────
import banks.karnataka as sw
print(f"[1] karnatak.py path  : {sw.__file__}")
print(f"[2] has TXN_LINE_RE   : {hasattr(sw, 'TXN_LINE_RE')}")
print(f"[3] BANK_DISPLAY_NAME : {sw.BANK_DISPLAY_NAME}")

# ── TEST 2: What ocr_engine returns ──────────────────────────────────
from ocr_engine import extract_text_from_pdf
pdf = "d:/BankStats&GST3B/kbl.pdf"
lines = extract_text_from_pdf(pdf)
print(f"\n[4] ocr_engine line count : {len(lines)}")
print(f"[5] First 10 lines:")
for i, l in enumerate(lines[:10]):
    print(f"     {i:2d} | {repr(l)}")

# ── TEST 3: What detect_bank returns ─────────────────────────────────
from banks.bank_detector import detect_bank
bank_key = detect_bank(pdf, lines)
print(f"\n[6] detect_bank result : {bank_key}")

# ── TEST 4: Run extract_account_info directly ─────────────────────────
info = sw.extract_account_info(lines)
print(f"\n[7] account_holder : {info.get('account_holder')}")
print(f"[8] account_number : {info.get('account_number')}")
print(f"[9] bank_name      : {info.get('bank_name')}")
print(f"[10] period from   : {info.get('statement_period', {}).get('from')}")

# ── TEST 5: Run extract_transactions directly ─────────────────────────
txns = sw.extract_transactions(pdf)
print(f"\n[11] Total transactions : {len(txns)}")
if txns:
    print(f"[12] First transaction  : {txns[0]}")
