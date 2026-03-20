import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns
)

BANK_KEY          = "kokan"
BANK_DISPLAY_NAME = "Kokan Mercantile Co-op Bank"

# =====================================================================
# KOKAN MERCANTILE CO-OP BANK — Scanned/Image-based PDF
#
# CHARACTERISTICS:
# - IMAGE-BASED (scanned via OKEN Scanner — 0 text chars in PDF)
#   → OCR engine (PaddleOCR) provides the text lines
# - Columns: Date | Particulars | Instrument No | Debit | Credit | Closing Balance
# - Date format: DD/MM/YYYY  (with OCR noise: ;|)} before date)
# - SEPARATE Debit and Credit columns (no +/- prefix)
# - Credit vs Debit determined by keywords + balance delta
# - Multi-line descriptions (continuation lines have no date)
# - OCR artefacts: spaces in numbers ("3500067 .26"), noise chars
# - Balance is always positive (closing balance shown)
# =====================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
DATE_PAT    = re.compile(r'(\d{2}/\d{2}/\d{4})')
AMOUNT_PAT  = re.compile(r'[\d,]+\.\s*\d{2}')   # handles "301289. 00"
PERIOD_PAT  = re.compile(
    r'(?:period|from)\s+(\d{2}-\d{2}-\d{4})\s+(?:to|To)\s+(\d{2}-\d{2}-\d{4})',
    re.I
)
OPEN_BAL_PAT = re.compile(
    r'opening\s+balance\s+as\s+on[^:]*:\s*([\d,]+\.?\d*)', re.I
)
ACCT_NO_PAT = re.compile(r'(\d{4}/\d{4})')
IFSC_PAT    = re.compile(r'\b(KKBK[A-Z0-9]{7})\b', re.I)
MICR_PAT    = re.compile(r'\b(\d{9})\b')

# Credit indicators in description
CREDIT_KW = re.compile(
    r'RTGS\s+INWARD|RTGS\s+Cr|BY\s+CLG|INWARD|credit\b', re.I
)
# Debit indicators in description
DEBIT_KW = re.compile(
    r'TO\s+TRF|TO\s+INSURANCE|TO\s+NOMINAL|CASH\s+WITHDRAWAL|ATM\s+Card|'
    r'IMPS/DR|SMS\s+Charges|Chq\s+Paid|S\.I\s+No|S\.1\s+No|IMPS\s+Charges|'
    r'TO\s+INSURANCE', re.I
)

# Lines to skip entirely
SKIP_RE = re.compile(
    r'scanned\s+with|^CE\b|^CG\b|^©|page\s+\d+|^total\b|'
    r'opening\s+balance|statement\s+of|for\s+the\s+period|'
    r'kokan|koram|mercantile|^address\b|IFSC|MICR|'
    r'^debit\s+closing|^date\s+particulars|^instrument|'
    r'^Dat\b|^asin\b|^semen\b|^hemouch\b|MALPLID|SLATE',
    re.I
)


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_kokan(value):
    """Handles OCR spaces in numbers: '3500067 .26' → 3500067.26"""
    if not value:
        return None
    value = str(value).strip().replace(' ', '').replace(',', '')
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines):
    """
    Extract account metadata from OCR text lines of Kokan Mercantile PDF.

    OCR output (first page, approximate):
      'KOKAN MERCANTILE CO-OP BANK LTD.'
      '1101/4732'   ← account number
      'SHAKEEL TRADING CORPORATION'  ← holder name (may be split across lines)
      'KKBKOKMCB02'  ← IFSC
      '400075006'    ← MICR
      'Address GM LINK ROAD BAIGANWADI GOVANDI,MUMBAI 400043'
      'Statement of Operative Account for the period 01-04-2024 To 31-03-2025'
      'Opening Balance As On 01-04-2024 : 6022814.44'
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Account number: "1101/4732"
    m = ACCT_NO_PAT.search(full_text)
    if m:
        info["account_number"] = m.group(1)

    # IFSC
    m = IFSC_PAT.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    # Account type: look for CURRENT / SAVINGS nearby
    for line in lines[:20]:
        m = re.search(r'(CURRENT\s+DEPOSITS|CURRENT|SAVINGS)', line, re.I)
        if m:
            info["acc_type"] = m.group(1).strip()
            break

    # Statement period
    for line in lines:
        m = PERIOD_PAT.search(line)
        if m:
            info["statement_period"]["from"] = m.group(1)
            info["statement_period"]["to"]   = m.group(2)
            break

    # Opening balance
    for line in lines:
        m = OPEN_BAL_PAT.search(line)
        if m:
            info["opening_balance"] = _clean_amount_kokan(m.group(1))
            break

    # Branch / address
    for line in lines:
        m = re.search(r'address\s+(.+)', line, re.I)
        if m:
            info["branch"] = m.group(1).strip()
            break

    # Account holder — look for ALL-CAPS multi-word name near account number
    acct_idx = None
    for i, line in enumerate(lines):
        if ACCT_NO_PAT.search(line):
            acct_idx = i
            break

    if acct_idx is not None:
        # Extract words from nearby lines, strip OCR noise prefixes
        # OCR often gives "hemouch SHAKEEL TRADING" — take only UPPERCASE words
        name_words = []
        for line in lines[max(0, acct_idx-5):acct_idx+8]:
            text = line.strip()
            if not text:
                continue
            if re.search(r'kokan|koram|mercantile|bank|kkbk|address|'
                         r'statement|opening|MICR|IFSC|\d{4}/\d{4}|'
                         r'Dat\b|asin\b|semen\b|hemouch|MALPLID|SLATE',
                         text, re.I):
                continue
            # Extract only all-caps words (real name tokens vs OCR noise)
            caps_words = re.findall(r'\b[A-Z][A-Z]+\b', text)
            name_words.extend(caps_words)

        if name_words:
            # Filter common noise words
            noise = {'THE', 'AND', 'FOR', 'OF', 'IN', 'CO', 'LTD',
                     'BANK', 'TYPE', 'CODE', 'DATE', 'IFSC', 'MICR'}
            clean = [w for w in name_words if w not in noise and len(w) > 2]
            if clean:
                info["account_holder"] = " ".join(clean[:4])

    return info


# ---------------------------------
# OPENING / CLOSING BALANCE
# ---------------------------------
def extract_summary_balances(pdf_path, info):
    """Opening balance from header; closing from last transaction."""
    txns = extract_transactions(pdf_path)
    if txns and info.get("closing_balance") is None:
        info["closing_balance"] = txns[-1].get("balance")


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path, lines=None):
    """
    Extract all transactions from Kokan Mercantile Co-op Bank PDF.

    The PDF is image-based (scanned). The ocr_engine provides text lines.
    We can also receive pre-extracted lines via the `lines` parameter.

    OCR line format:
      "DD/MM/YYYY[noise] DESCRIPTION [INSTRUMENT_NO] AMOUNT CLOSING_BALANCE"
    Continuation lines (no date at start) append to previous transaction.

    Credit vs Debit:
    - Separate columns in PDF but OCR collapses them
    - Determined by: keyword matching + balance delta
    - RTGS INWARD / BY CLG = credit; TO TRF / ATM / IMPS/DR = debit
    """
    if lines is None:
        # For text-based fallback (shouldn't happen for Kokan)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                lines = []
                for page in pdf.pages:
                    lines.extend((page.extract_text() or '').split('\n'))
        except Exception:
            return []

    transactions = []
    current      = None
    prev_balance = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Skip noise/header lines
        if SKIP_RE.search(line):
            continue

        # Find date at start of line (tolerant of OCR prefix noise: ;|)})
        date_m = DATE_PAT.search(line[:15])

        if date_m:
            # ── Save previous transaction ──
            if current:
                _finalize_kokan(current, prev_balance)
                if current.get('balance') is not None:
                    prev_balance = current['balance']
                # Only keep rows that have some data
                if (current.get('balance') is not None
                        or current.get('debit')
                        or current.get('credit')):
                    transactions.append(current)

            date_str = date_m.group(1)
            rest     = line[date_m.end():].strip().lstrip('|;)}/=: ')

            # Skip bare date-only lines (OCR fragments)
            if not rest:
                current = None
                continue

            # Normalize OCR space in decimal: "3500067 .26" → "3500067.26"
            rest_norm = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', rest)

            # Extract all amounts from the line
            amounts_raw = AMOUNT_PAT.findall(rest_norm)
            amounts = [a.replace(' ', '') for a in amounts_raw]

            balance = None
            amount  = None
            desc    = rest_norm

            if len(amounts) >= 2:
                # Last = closing balance, second-to-last = transaction amount
                balance = _clean_amount_kokan(amounts[-1])
                amount  = _clean_amount_kokan(amounts[-2])
                # Strip amounts from description (peel off from right side)
                desc = re.sub(r'[\d,]+\.\d{2}\s*\w{0,3}\s*$', '', rest_norm).strip()
                desc = re.sub(r'[\d,]+\.\d{2}\s*\w{0,3}\s*$', '', desc).strip()
                # Strip long instrument numbers
                desc = re.sub(r'[|/]?\s*\d{10,}\s*[|/]?', ' ', desc).strip()
                desc = re.sub(r'\s+', ' ', desc).strip().strip('|=/- ')
            elif len(amounts) == 1:
                # Only one amount visible → it's the balance
                # Transaction amount will be derived from balance delta
                balance = _clean_amount_kokan(amounts[0])
                desc = re.sub(r'[\d,]+\.\d{2}\s*\w{0,3}\s*$', '', rest_norm).strip()
                desc = re.sub(r'[|/]?\s*\d{10,}\s*[|/]?', ' ', desc).strip()
                desc = re.sub(r'\s+', ' ', desc).strip().strip('|=/- ')

            current = {
                'date':        date_str,
                'description': desc or rest,
                'ref_no':      None,
                'debit':       None,
                'credit':      None,
                'balance':     balance,
                '_amount':     amount,
            }

        elif current is not None:
            # Continuation line — append to description
            # BUT: if it looks like a new transaction start (no date in OCR),
            # save current and start a new implicit transaction
            if re.search(r'^(CE|CG|©|scanned|\d+\s*$)', line, re.I):
                pass
            elif re.match(r'^RTGS\s+INWARD|^RTGS\s+Cr', line, re.I):
                # This is a new credit transaction whose date was lost in OCR
                # Finalize current and start new
                _finalize_kokan(current, prev_balance)
                if current.get('balance') is not None:
                    prev_balance = current['balance']
                if (current.get('balance') is not None
                        or current.get('debit') or current.get('credit')):
                    transactions.append(current)

                # Normalize and extract amounts
                line_norm = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', line)
                amounts_raw = AMOUNT_PAT.findall(line_norm)
                amounts = [a.replace(' ','') for a in amounts_raw]
                balance = _clean_amount_kokan(amounts[-1]) if len(amounts) >= 1 else None
                amount  = _clean_amount_kokan(amounts[-2]) if len(amounts) >= 2 else None
                desc = re.sub(r'[\d,]+\.\d{2}\s*\w{0,3}\s*$', '', line_norm).strip()
                desc = re.sub(r'\s+', ' ', desc).strip()

                current = {
                    'date':        prev_balance and transactions[-1]['date'] or 'unknown',
                    'description': desc,
                    'ref_no':      None,
                    'debit':       None,
                    'credit':      None,
                    'balance':     balance,
                    '_amount':     amount,
                }
            else:
                current['description'] = (current['description'] + ' ' + line).strip()

    # Finalize last transaction
    if current:
        _finalize_kokan(current, prev_balance)
        if (current.get('balance') is not None
                or current.get('debit')
                or current.get('credit')):
            transactions.append(current)

    # Clean up internal key
    for t in transactions:
        t.pop('_amount', None)

    return transactions


def _finalize_kokan(txn, prev_balance):
    """
    Determine debit/credit direction for Kokan Mercantile transactions.

    Priority:
    1. Description keywords (most reliable)
    2. Balance delta (balance went up = credit, down = debit)
    3. Default to debit if cannot determine
    """
    desc    = txn.get('description', '')
    amount  = txn.get('_amount')
    balance = txn.get('balance')

    # If no amount found, try to derive from balance delta
    if amount is None and prev_balance is not None and balance is not None:
        amount = abs(round(balance - prev_balance, 2))

    if amount is None or amount == 0:
        return

    # Determine direction
    if CREDIT_KW.search(desc):
        txn['credit'] = amount
    elif DEBIT_KW.search(desc):
        txn['debit'] = amount
    elif prev_balance is not None and balance is not None:
        delta = round(balance - prev_balance, 2)
        if delta > 0:
            txn['credit'] = amount
        else:
            txn['debit'] = amount
    else:
        txn['debit'] = amount  # default