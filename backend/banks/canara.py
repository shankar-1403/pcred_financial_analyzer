import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns
)

BANK_KEY          = "canara"
BANK_DISPLAY_NAME = "Canara Bank"

# =====================================================================
# CANARA BANK — Handles 4 known PDF formats
#
# FORMAT 1 — Image/Scanned ("canara_removed" type)
#   - IMAGE-BASED (0 text chars) → OCR engine provides lines
#   - Account info: split label/value columns, OCR struggles
#   - Transactions: "DD-MM-YYYY HH:MM:SS | DD Mon YYYY [CHQ] DESC [BRANCH] AMOUNT"
#   - NO balance column in OCR output — balance not available per row
#   - Credit/Debit: keyword-based ("Dr"/"Cr" in description)
#   - Date format: DD-MM-YYYY
#
# FORMAT 2 — Doubled-character text PDF ("compressed" type)
#   - TEXT-BASED but every character is doubled: "CCuurrrreenntt" → "Current"
#   - After de-duplication, format similar to Format 1 layout
#   - Transactions: "DD-MM-YYYY[D?] H[H]:MM:SS [garbled_value_date] DESC [BRANCH] AMOUNT BALANCE"
#   - Has separate Debit/Credit columns + Balance column
#   - Date format: DD-MM-YYYY
#   - Account info available (de-dup the text first)
#   - NOTE: after dedup the timestamp hour bleeds an extra digit into the date:
#     "17-02-20231 0:41:05" — handled by the stray-digit in F2_TXN_RE
#   - Credit/Debit determined by balance DELTA (immune to garbled keywords)
#
# FORMAT 3 — E-Passbook ("canara_epassbook" type)
#   - TEXT-BASED, low char density
#   - Account info in 2-column key-value pairs at top
#   - Transactions: description lines appear ABOVE the date line;
#     some description text also wraps ONTO the date line as junk
#   - Date line layout: "DD-MM-YYYY [optional_junk] AMOUNT BALANCE"
#   - After the date line: timestamp + hash continuation lines
#   - Then: "Chq: XXXXXXXXXX" line that closes each transaction
#   - Separate Deposits / Withdrawals columns — determined by balance delta
#   - Date format: DD-MM-YYYY
#
# FORMAT 4 — Online / OD / OCC table-based ("canara_table" type)  ← NEW
#   - TEXT-BASED, medium-high char density
#   - Account info in a clean 2-column key-value table at top of page 1
#   - Transactions in an 8-column pdfplumber table (lines strategy):
#       [Txn Date+Time | Value Date | Cheque No. | Description |
#        Branch Code | Debit | Credit | Balance]
#   - Balance can be NEGATIVE (OD accounts): "-13,44,02,294.00"
#   - Empty Debit or Credit cell means no movement on that side
#   - Description can wrap across lines (pdfplumber joins with \n in cell)
#   - Date format: DD-MM-YYYY HH:MM:SS  (time stripped for output)
#   - Header signature: "Account Holders Name" / "Customer Id" /
#     "Searched By" ALL on separate label-value text lines
# =====================================================================


# ---------------------------------
# SHARED REGEX PATTERNS
# ---------------------------------
DATE_DDMMYYYY   = re.compile(r'\b(\d{2}-\d{2}-\d{4})\b')
AMOUNT_RE       = re.compile(r'-?[\d,]+\.\d{2}')
IFSC_PAT        = re.compile(r'\b(CNRB[A-Z0-9]{7})\b', re.I)
MICR_PAT        = re.compile(r'MICR\s+(?:Code\s+)?(\d{9})', re.I)
ACCT_NO_PAT     = re.compile(r'Account\s+Number\s+(\d{10,})', re.I)
CUSTOMER_PAT    = re.compile(r'Customer\s+Id\s+(\S+)', re.I)
BRANCH_PAT      = re.compile(r'Branch\s+Name\s+(.+)', re.I)
OPEN_BAL_PAT    = re.compile(r'Opening\s+Balance\s+Rs?\.?\s*(-?[\d,]+\.?\d*)', re.I)
CLOSE_BAL_PAT   = re.compile(r'Closing\s+Balance\s+Rs?\.?\s*(-?[\d,]+\.?\d*)', re.I)
HOLDER_PAT      = re.compile(r'Account\s+Holders?\s+Name\s+(.+)', re.I)
PRODUCT_PAT     = re.compile(r'Product\s+Name\s+(.+)', re.I)
PERIOD_PAT      = re.compile(r'(?:Searched\s+By\s+)?From\s+(\d{2}\s+\w+\s+\d{4})\s+To\s+(\d{2}\s+\w+\s+\d{4})', re.I)
PERIOD_PAT2     = re.compile(r'between\s+(\d{2}-\w{3}-\d{4})\s+and\s+(\d{2}-\w{3}-\d{4})', re.I)
CURRENCY_PAT    = re.compile(r'Account\s+Currency\s+(INR|USD|EUR)', re.I)

# Credit/Debit keyword detection (used only for F1 / fallback)
CREDIT_KW = re.compile(
    r'\bCr\b|\bCr-|NEFT\s*Cr|RTGS\s*Cr|By\s+Clg|CASH-BNA|Cash\s*Deposit|'
    r'MOB-IMPS-CR|UPI/CR|INW\s+Chq\s+return.*?(?=\s+\d)|'
    r'Chq\s+return.*?Insufficient.*?(?=\s+\d)', re.I
)
DEBIT_KW = re.compile(
    r'\bDr\b|\bDr-|RTGS\s*Dr|NEFT\s*Dr|IB-IMPS-DR|UPI/DR|ATM|'
    r'Chq\s+Paid|Funds\s+Transfer\s+Debit|INW\s+CHQ\s+RTN|'
    r'SC\s+NEFT|SMS\s+Charges|Service\s+Charges|IMPS-DR|'
    r'ADDITION\s+DELETION|Proc\s+Chgs|Doc\s+Chgs|GODOWN|'
    r'Periodic\s+Godown|ATM\s+/\s+IMPS\s+Transaction|'
    r'RTGS\s+\d+|IB\s+ITG', re.I
)

SKIP_LINE = re.compile(
    r'^page\s+\d+|disclaimer|unless\s+the\s+constituent|canara\s*bank|'
    r'if\s+you\s+have|centralized|reserve\s+bank|www\.|https?://|'
    r'toll\s+free|--+\s*END|borel\s+ada|current\s*&\s*saving\s*account\s*statement|'
    r'^txn\s*date|^date\s+particulars|^\s*code\s*$',
    re.I
)

# Additional skip patterns specific to F3 header area
F3_HEADER_SKIP = re.compile(
    r'^Statement\s+for|^Customer\s+Id|^Name\s+[A-Z]|^Phone\s+|'
    r'^Address\s+|^Branch\s+(Code|Name)\s+|^IFSC\s+Code|'
    r'^Date\s+Particulars|^Opening\s+Balance',
    re.I
)


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_canara(value):
    if not value:
        return None
    value = str(value).strip().replace(',', '')
    try:
        return float(value)
    except ValueError:
        return None


# =============================================================
# FORMAT DETECTION
# =============================================================

def detect_format(pdf_path, lines):
    """
    Returns 'f1' (image/OCR), 'f2' (doubled-char text),
    'f3' (epassbook), or 'f4' (table-based OD/OCC).
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            chars = len(pdf.pages[0].chars)
    except Exception:
        chars = 0

    if chars == 0:
        return 'f1'  # image-based

    # ── FORMAT 4 detection ──────────────────────────────────────
    # Signature: clean 2-col account-info table + 8-col transaction
    # table on page 1.  Identified by:
    #   • "Account Holders Name" AND "Customer Id" AND "Searched By"
    #     all present as label-value text lines in the header, AND
    #   • pdfplumber finds an 8-column table on page 1.
    header_text = " ".join(lines[:20]).lower()
    has_f4_labels = (
        "account holders name" in header_text
        and "customer id" in header_text
        and "searched by" in header_text
    )
    if has_f4_labels:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                tables = pdf.pages[0].extract_tables(
                    {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
                )
                for t in tables:
                    if t and len(t[0]) == 8:
                        return 'f4'
        except Exception:
            pass

    # ── FORMAT 2: doubled characters ────────────────────────────
    sample = " ".join(lines[:5])
    pairs = sum(1 for i in range(len(sample) - 1) if sample[i] == sample[i + 1])
    if pairs > len(sample) * 0.3:
        return 'f2'

    # ── FORMAT 3: e-passbook ────────────────────────────────────
    full = " ".join(lines[:5]).lower()
    if 'statement for a/c' in full or 'between' in full:
        return 'f3'

    return 'f2'  # default for text-based


# =============================================================
# SHARED ACCOUNT INFO EXTRACTION
# =============================================================

def extract_account_info(lines, pdf_path=None):
    """
    Extract account metadata from Canara Bank statement.
    Works across all 4 formats.
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    fmt = detect_format(pdf_path or '', lines)

    if fmt == 'f2':
        normalized = [re.sub(r'(.)\1', r'\1', line) for line in lines]
    else:
        normalized = lines

    full_text = "\n".join(normalized)

    # ── FORMAT 4: clean 2-col table — parse directly from text lines ──
    # All fields are "Label Value" on the same line (pdfplumber text extract)
    # e.g. "Account Holders Name GALAXY MACHINERY PVT LTD"
    if fmt == 'f4':
        for line in normalized[:25]:
            line_s = (line or "").strip()
            if not line_s:
                continue

            if info["account_holder"] is None:
                m = re.search(r"Account\s+Holders?\s+Name\s+(.+)", line_s, re.I)
                if m:
                    info["account_holder"] = m.group(1).strip()

            if info["customer_id"] is None:
                m = re.search(r"Customer\s+Id\s+(\S+)", line_s, re.I)
                if m:
                    info["customer_id"] = m.group(1).strip()

            if info["branch"] is None:
                m = re.search(r"Branch\s+Name\s+(.+)", line_s, re.I)
                if m:
                    info["branch"] = m.group(1).strip()

            if info["micr"] is None:
                m = re.search(r"MICR\s+Code\s+(\d{9})", line_s, re.I)
                if m:
                    info["micr"] = m.group(1).strip()

            if info["ifsc"] is None:
                m = re.search(r"IFSC\s+Code\s+(\S+)", line_s, re.I)
                if m:
                    info["ifsc"] = m.group(1).strip()

            if info["account_number"] is None:
                m = re.search(r"Account\s+Number\s+(\d{10,})", line_s, re.I)
                if m:
                    info["account_number"] = m.group(1).strip()

            if info["currency"] == "INR":
                m = re.search(r"Account\s+Currency\s+(INR|USD|EUR)", line_s, re.I)
                if m:
                    info["currency"] = m.group(1).strip()

            if info["acc_type"] is None:
                m = re.search(r"Product\s+Name\s+(.+)", line_s, re.I)
                if m:
                    info["acc_type"] = m.group(1).strip()

            if info["statement_period"]["from"] is None:
                m = re.search(
                    r"Searched\s+By\s+From\s+(.+?)\s+To\s+(.+)", line_s, re.I
                )
                if m:
                    info["statement_period"]["from"] = m.group(1).strip()
                    info["statement_period"]["to"]   = m.group(2).strip()

            if info["statement_request_date"] is None:
                m = re.search(
                    r"Account\s+Statement\s+as\s+of\s+(\d{2}-\d{2}-\d{4})", line_s, re.I
                )
                if m:
                    info["statement_request_date"] = m.group(1).strip()

        # Opening / closing balance: "Opening Balance Rs. -13,32,15,104.00"
        m = OPEN_BAL_PAT.search(full_text)
        if m:
            info["opening_balance"] = _clean_amount_canara(m.group(1))

        m = CLOSE_BAL_PAT.search(full_text)
        if m:
            info["closing_balance"] = _clean_amount_canara(m.group(1))

        return info

    # ── Formats 1 / 2 / 3 (existing logic unchanged) ──────────────────

    # ── Account holder ─────────────────────────────────────────
    m = HOLDER_PAT.search(full_text)
    if m:
        val = m.group(1).strip()
        if val and not re.search(
            r'^(Customer|Branch|MICR|IFSC|Searched|Account|Product|Opening|Closing)',
            val, re.I
        ):
            info["account_holder"] = val

    # F1 OCR: labels and values on separate lines
    if info["account_holder"] is None and fmt == 'f1':
        LABEL_WORDS = re.compile(
            r'^(Customer\s+Id|Branch\s+Name|MICR\s+Code|IFSC\s+Code|Searched\s+By|'
            r'Account\s+Number|Account\s+Currency|Product\s+Name|Opening\s+Balance|'
            r'Closing\s+Balance|Account\s+Holders|Value\s+Date|Cheque|Txn\s+Date|'
            r'Description|Branch\s+Code)', re.I
        )
        label_map = {
            r'Account\s+Holders?\s+Name': 'account_holder',
            r'Customer\s+Id':             'customer_id',
            r'Branch\s+Name':             'branch',
            r'MICR\s+Code':               'micr',
            r'IFSC\s+Code':               'ifsc',
            r'Account\s+Number':          'account_number',
            r'Product\s+Name':            'acc_type',
            r'Opening\s+Balance':         'opening_balance',
            r'Closing\s+Balance':         'closing_balance',
        }
        for i, line in enumerate(normalized):
            for pat, field in label_map.items():
                if re.match(pat, line.strip(), re.I) and i + 1 < len(normalized):
                    val = normalized[i + 1].strip()
                    if not val or LABEL_WORDS.match(val):
                        break
                    if field in ('opening_balance', 'closing_balance'):
                        val = re.sub(r'Rs\.?\s*', '', val).strip()
                        info[field] = _clean_amount_canara(val)
                    elif info.get(field) is None:
                        info[field] = val.strip()
                    break

    # F3 e-passbook: "Name AAIMATAJIELECTRICALS" on a single line
    if info["account_holder"] is None and fmt == 'f3':
        m = re.search(r'^Name\s+([A-Z][A-Z0-9\s]+?)(?:\s+Branch|$)', full_text, re.I | re.M)
        if m:
            info["account_holder"] = m.group(1).strip()

    # ── Account number ─────────────────────────────────────────
    m = ACCT_NO_PAT.search(full_text)
    if m:
        info["account_number"] = m.group(1).strip()

    # F3: "Statement for A/c XXXXXXXXX0170"
    if info["account_number"] is None:
        m = re.search(r'Statement\s+for\s+A/c\s+(\S+)', full_text, re.I)
        if m:
            info["account_number"] = m.group(1).strip()

    # ── Customer ID ────────────────────────────────────────────
    m = CUSTOMER_PAT.search(full_text)
    if m:
        info["customer_id"] = m.group(1).strip()

    # ── IFSC ───────────────────────────────────────────────────
    m = IFSC_PAT.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    # ── MICR ───────────────────────────────────────────────────
    m = MICR_PAT.search(full_text)
    if m:
        info["micr"] = m.group(1).strip()

    # ── Branch ─────────────────────────────────────────────────
    m = BRANCH_PAT.search(full_text)
    if m:
        info["branch"] = m.group(1).strip()

    # ── Account type / product ─────────────────────────────────
    m = PRODUCT_PAT.search(full_text)
    if m:
        info["acc_type"] = m.group(1).strip()

    # ── Currency ───────────────────────────────────────────────
    m = CURRENCY_PAT.search(full_text)
    if m:
        info["currency"] = m.group(1).strip()

    # ── Opening / Closing balance ──────────────────────────────
    m = OPEN_BAL_PAT.search(full_text)
    if m:
        info["opening_balance"] = _clean_amount_canara(m.group(1))

    m = CLOSE_BAL_PAT.search(full_text)
    if m:
        info["closing_balance"] = _clean_amount_canara(m.group(1))

    # ── Statement period ───────────────────────────────────────
    m = PERIOD_PAT.search(full_text)
    if m:
        info["statement_period"]["from"] = m.group(1).strip()
        info["statement_period"]["to"]   = m.group(2).strip()

    # F3: "between 01-Jan-2023 and 19-Jan-2024"
    if info["statement_period"]["from"] is None:
        m = PERIOD_PAT2.search(full_text)
        if m:
            info["statement_period"]["from"] = m.group(1).strip()
            info["statement_period"]["to"]   = m.group(2).strip()

    # ── Fallback: account holder from first meaningful line ─────
    if info["account_holder"] is None:
        for line in normalized[:5]:
            text = line.strip()
            if (text and len(text) > 3
                    and re.match(r'^[A-Z]', text)
                    and not re.search(
                        r'canara|current|saving|statement|bank', text, re.I)):
                info["account_holder"] = text
                break

    # Clean up if account_holder captured metadata
    if info.get("account_holder") and re.search(
        r'Customer\s+Id|Branch\s+Code', info["account_holder"], re.I
    ):
        for line in normalized[:8]:
            text = line.strip()
            m = re.search(r'Name\s+([A-Z][A-Z\s]+?)(?:\s+Branch|$)', text, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()
                break

    return info


# =============================================================
# OPENING / CLOSING BALANCE
# =============================================================

def extract_summary_balances(pdf_path, info):
    """Supplement balances from last transaction if not in header."""
    if info.get("closing_balance") is None:
        txns = extract_transactions(pdf_path)
        if txns:
            for t in reversed(txns):
                if t.get("balance") is not None:
                    info["closing_balance"] = t["balance"]
                    break


# =============================================================
# TRANSACTION EXTRACTION — DISPATCHER
# =============================================================

def extract_transactions(pdf_path, lines=None):
    """
    Extract all transactions from a Canara Bank PDF statement.
    Auto-detects format and dispatches to the appropriate parser.
    """
    if lines is None:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                lines = []
                for page in pdf.pages:
                    lines.extend((page.extract_text() or '').split('\n'))
        except Exception:
            lines = []

    fmt = detect_format(pdf_path, lines)

    if fmt == 'f1':
        return _extract_f1(lines)
    elif fmt == 'f2':
        return _extract_f2(lines)
    elif fmt == 'f3':
        return _extract_f3(lines)
    else:
        return _extract_f4(pdf_path)


# =============================================================
# FORMAT 1: Image/OCR
# =============================================================

F1_TXN_RE = re.compile(
    r'^(\d{2}-\d{2}-\d{4})\s+\d{2}:\d{2}:\d{2}\s*\|?\s*'
    r'\d{2}\s+\w{3}\s+\d{4}\s+'
    r'(.+)'
)


def _extract_f1(lines):
    """
    Parse OCR lines from image-based Canara Bank statement.
    Format: "DD-MM-YYYY HH:MM:SS | DD Mon YYYY [CHQ] DESCRIPTION AMOUNT"
    No balance column in OCR — balance is null.
    Continuation lines are appended to current transaction description.
    """
    transactions = []
    current      = None

    for line in lines:
        line_s = line.strip()
        if not line_s or SKIP_LINE.search(line_s):
            continue

        m = F1_TXN_RE.match(line_s)
        if m:
            if current:
                _finalize_canara(current)
                transactions.append(current)

            date_str = m.group(1)
            rest     = m.group(2).strip()

            amounts  = AMOUNT_RE.findall(rest)
            amount   = _clean_amount_canara(amounts[-1]) if amounts else None

            desc = rest
            if amounts:
                desc = rest[:rest.rfind(amounts[-1])].strip()
            desc = re.sub(r'\b\d{2,5}\b\s*$', '', desc).strip()
            desc = re.sub(r'\s+', ' ', desc).strip()

            current = {
                'date':        date_str,
                'description': desc,
                'ref_no':      None,
                'debit':       None,
                'credit':      None,
                'balance':     None,
                '_amount':     amount,
            }

        elif current is not None:
            if not re.search(r'^(borel\s+ada|=+|[A-Z]{1,3}$)', line_s, re.I):
                current['description'] = (current['description'] + ' ' + line_s).strip()

    if current:
        _finalize_canara(current)
        transactions.append(current)

    for t in transactions:
        t.pop('_amount', None)

    return transactions


# =============================================================
# FORMAT 2: Doubled-char text
# =============================================================

F2_TXN_RE = re.compile(
    r'^(\d{2}-\d{2}-\d{4})\d?\s+'
    r'\d{1,2}:\d{2}:\d{2}\s*'
    r'(?:\d{1,2}\s*[A-Za-z]+\s*\d{1,4}\s+)?'
    r'(.+?)\s+'
    r'(-?[\d,]+\.\d{2})\s+'
    r'(-?[\d,]+\.\d{2})\s*$'
)

_F2_VALDATE_STRIP  = re.compile(r'^\d{1,2}\s*[A-Za-z]{1,5}\s*\d{1,4}\s+')
_F2_CHQNO_STRIP    = re.compile(r'^\d{9,12}\s+')
_F2_BRANCH_STRIP   = re.compile(r'\s+\d{2,5}\s*$')
_F2_TIMESTAMP_ONLY = re.compile(r'^\d{2}:\d{2}:\d{2}$')


def _clean_desc_f2(middle: str) -> str:
    d = middle.strip()
    d = _F2_VALDATE_STRIP.sub('', d).strip()
    d = _F2_CHQNO_STRIP.sub('', d).strip()
    d = _F2_BRANCH_STRIP.sub('', d).strip()
    return re.sub(r'\s+', ' ', d).strip()


def _extract_f2(lines):
    """
    Parse de-duplicated text lines from a doubled-char Canara Bank statement.
    Credit/Debit determined by balance delta.
    """
    deduped = [re.sub(r'(.)\1', r'\1', line) for line in lines]

    transactions = []
    current      = None
    prev_balance = None

    for line in deduped:
        line_s = line.strip()

        if not line_s or SKIP_LINE.search(line_s):
            continue

        if _F2_TIMESTAMP_ONLY.match(line_s):
            continue

        m = F2_TXN_RE.match(line_s)
        if m:
            if current:
                transactions.append(current)

            date_str    = m.group(1)
            middle      = m.group(2)
            amount_raw  = m.group(3)
            balance_raw = m.group(4)

            amount  = _clean_amount_canara(amount_raw)
            balance = _clean_amount_canara(balance_raw)
            desc    = _clean_desc_f2(middle)

            debit = credit = None
            if prev_balance is not None and balance is not None and amount is not None:
                delta = round(balance - prev_balance, 2)
                if delta >= 0:
                    credit = amount
                else:
                    debit = amount
            elif amount is not None:
                if balance is not None and abs(balance - amount) < 0.01:
                    credit = amount
                else:
                    debit = amount

            current = {
                'date':        date_str,
                'description': desc,
                'ref_no':      None,
                'debit':       debit,
                'credit':      credit,
                'balance':     balance,
            }

            if balance is not None:
                prev_balance = balance

        elif current is not None:
            if not re.search(r'^TxnD\s*ate|^Date\s+Particulars|^Code\s*$',
                             line_s, re.I):
                current['description'] = (
                    current['description'] + ' ' + line_s
                ).strip()

    if current:
        transactions.append(current)

    return transactions


# =============================================================
# FORMAT 3: E-Passbook
# =============================================================

_F3_DATE_LINE = re.compile(
    r'^(\d{2}-\d{2}-\d{4})\s+'
    r'(.*?)\s*'
    r'(-?[\d,]+\.\d{2})\s+'
    r'(-?[\d,]+\.\d{2})\s*$'
)

_F3_CHQ_LINE = re.compile(r'^Chq:\s*(\S+)')

_F3_HEADER_SKIP = re.compile(
    r'^Statement\s+for|^Customer\s+Id|^Name\s+[A-Z]|^Phone\s+\+|'
    r'^Address\s+[A-Z]|^[A-Z]+\s+NAGAR|^TELANGANA|^Branch\s+(Code|Name)\s+|'
    r'^IFSC\s+Code|^Date\s+Particulars|^Opening\s+Balance|'
    r'^Raghurama|^HYDERABAD\s+TELANGANA|^Plot\s+No',
    re.I
)


def _extract_f3(lines):
    """
    Parse e-passbook format Canara Bank statement.
    Credit/Debit determined by balance delta.
    """
    transactions = []
    prev_balance = None

    for line in lines[:15]:
        m = re.search(r'Opening\s+Balance\s+([\d,]+\.?\d*)', line, re.I)
        if m:
            prev_balance = _clean_amount_canara(m.group(1))
            break

    desc_buffer = []
    current     = None

    for line in lines:
        line_s = line.strip()

        if not line_s:
            continue

        if SKIP_LINE.search(line_s) or _F3_HEADER_SKIP.search(line_s):
            continue

        chq_m = _F3_CHQ_LINE.match(line_s)
        if chq_m:
            if current is not None:
                ref = chq_m.group(1)
                current['ref_no'] = None if ref == '0' else ref
                transactions.append(current)
                current = None
            desc_buffer = []
            continue

        date_m = _F3_DATE_LINE.match(line_s)
        if date_m:
            date_str    = date_m.group(1)
            inline_junk = date_m.group(2).strip()
            amount      = _clean_amount_canara(date_m.group(3))
            balance     = _clean_amount_canara(date_m.group(4))

            parts = [x for x in desc_buffer if x]
            if inline_junk:
                parts.append(inline_junk)
            desc = re.sub(r'\s+', ' ', ' '.join(parts)).strip()

            debit = credit = None
            if prev_balance is not None and balance is not None and amount is not None:
                delta = round(balance - prev_balance, 2)
                if delta >= 0:
                    credit = amount
                else:
                    debit = amount
            elif amount is not None:
                credit = amount

            current = {
                'date':        date_str,
                'description': desc,
                'ref_no':      None,
                'debit':       debit,
                'credit':      credit,
                'balance':     balance,
            }

            if balance is not None:
                prev_balance = balance

            desc_buffer = []
            continue

        if current is not None:
            current['description'] = (
                current['description'] + ' ' + line_s
            ).strip()
        else:
            desc_buffer.append(line_s)

    if current is not None:
        transactions.append(current)

    return transactions


# =============================================================
# FORMAT 4: Table-based OD / OCC / Online statement  ← NEW
# =============================================================
#
# PDF CHARACTERISTICS:
# =====================
# - TEXT-BASED; pdfplumber line strategy gives clean 8-column tables
# - Page 1 has 3 tables: address block (1-col), account info (2-col),
#   transactions (8-col)
# - Page 2 onwards has transactions (8-col) + optional disclaimer (1-col)
# - 8 columns per row:
#     [Txn Date+Time | Value Date | Cheque No. | Description |
#      Branch Code   | Debit      | Credit     | Balance]
# - Balance CAN BE NEGATIVE for OD accounts: "-13,44,02,294.00"
# - Empty Debit or Credit cell = no movement on that side
# - Description wraps across lines (pdfplumber joins with \n in cell)
# - Date format: "DD-MM-YYYY HH:MM:SS" — strip time, keep DD-MM-YYYY
# - Header row text: "Txn Date" / "Value Date" / "Cheque No." etc.
# - Skip rows: header row + disclaimer table (identified by 1-col)

_F4_DATE_RE   = re.compile(r'^(\d{2}-\d{2}-\d{4})')   # extract date from datetime
_F4_SKIP_DESC = re.compile(
    r'^disclaimer|unless\s+the\s+constituent|if\s+you\s+have|'
    r'centralized|reserve\s+bank|www\.|https?://|toll\s+free|'
    r'end\s+of\s+statement',
    re.I
)


def _extract_f4(pdf_path):
    """
    Extract transactions from a Format 4 Canara Bank statement.

    Uses pdfplumber table extraction (8-column tables) directly.
    Debit / Credit are explicit separate columns — no delta logic needed.
    Balance can be negative (OD accounts).
    """
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )

            if not tables:
                continue

            for table in tables:

                if not table or len(table[0]) != 8:
                    continue  # only 8-column transaction tables

                for row in table:

                    if not row or len(row) < 8:
                        continue

                    # Skip header row
                    first_cell = (row[0] or "").strip()
                    if re.match(r'^txn\s*date', first_cell, re.I):
                        continue

                    # Skip disclaimer / footer rows
                    desc_cell = (row[3] or "").strip()
                    if _F4_SKIP_DESC.search(desc_cell) or _F4_SKIP_DESC.search(first_cell):
                        continue

                    txn = _build_txn_f4(row)
                    if txn:
                        transactions.append(txn)

    return transactions


def _build_txn_f4(row):
    """
    Build one transaction dict from a Format 4 table row.
    Columns: [Txn Date+Time, Value Date, Cheque No., Description,
              Branch Code, Debit, Credit, Balance]
    Returns None if the row has no valid date.
    """
    def _cell(idx):
        if idx >= len(row):
            return None
        return (row[idx] or "").replace("\n", " ").strip() or None

    datetime_raw = _cell(0)
    if not datetime_raw:
        return None

    # Extract just the date portion "DD-MM-YYYY" from "DD-MM-YYYY HH:MM:SS"
    m = _F4_DATE_RE.match(datetime_raw)
    if not m:
        return None
    date_str = m.group(1)

    value_date = (_cell(1) or "").strip() or None
    cheque_no  = _cell(2) or None

    desc = _cell(3)
    if desc:
        desc = re.sub(r"\s+", " ", desc).strip()

    branch_code = _cell(4) or None

    debit   = _clean_amount_canara(_cell(5))
    credit  = _clean_amount_canara(_cell(6))
    balance = _clean_amount_canara(_cell(7))

    return {
        "date":        date_str,
        "value_date":  value_date,
        "cheque_no":   cheque_no,
        "description": desc,
        "branch_code": branch_code,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }


# =============================================================
# SHARED FINALIZER  (used only by F1)
# =============================================================

def _finalize_canara(txn):
    """Assign debit/credit from keyword detection (F1 only)."""
    amount = txn.get('_amount')
    desc   = txn.get('description', '')

    if amount is None:
        return

    is_credit = bool(CREDIT_KW.search(desc))
    is_debit  = bool(DEBIT_KW.search(desc))

    if is_credit and not is_debit:
        txn['credit'] = amount
    elif is_debit and not is_credit:
        txn['debit'] = amount
    else:
        if re.search(r'RTGS\s*Cr|NEFT\s*Cr|By\s+Clg|CASH-BNA', desc, re.I):
            txn['credit'] = amount
        else:
            txn['debit'] = amount

    txn['description'] = re.sub(r'\s+', ' ', txn['description']).strip()