import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns
)

BANK_KEY          = "indian"
BANK_DISPLAY_NAME = "Indian Bank"


# =============================================================================
# FORMAT DETECTION
# Indian Bank has TWO statement formats:
#
# FORMAT A — Branch Statement (8-col pdfplumber table, clean text)
#   Columns: Value Date | Post Date | Remitter Branch | Description |
#             Cheque No | DR | CR | Balance
#   Date format in cell: 'DD/MM\n/YYYY' (split by PDF line break)
#   Account info: line 0 = 'STATEMENT OF ACCOUNT from ... for Account Number ...'
#                 line 1 = 'INDIAN BANK', line 2 = branch name
#                 line 3 = 'IFSC CODE:IDIB000U016'
#                 line 7 = 'Product type : ...'
#                 line 8 = account holder name
#
# FORMAT B — ePassbook / mPassbook (doubled chars, no real table structure)
#   Every char printed twice: 'CCuussttoommeerr' = 'Customer'
#   Spaces inserted mid-pair:  'NN aammee'       = 'Name'
#   Decode: strip all spaces → take every-other char (no spaces in result)
#   Columns in text: TransactionDate | Particulars | Withdrawals | Deposit | Balance
#   Date format: 'DD/MM/YYYY' clean (after decode)
#   Empty cell placeholder: '-' dash character
# =============================================================================


# ---------------------------------
# TABLE HEADER MAP — Format A
# ---------------------------------
HEADER_MAP_A = {
    "date": [
        "value date",
        "valuedate",
        "date",
    ],
    "description": [
        "description",
        "narration",
        "particulars",
    ],
    "cheque": [
        "cheque no",
        "chequeno",
        "cheque",
    ],
    "debit": [
        "dr",
        "debit",
        "withdrawal",
    ],
    "credit": [
        "cr",
        "credit",
        "deposit",
    ],
    "balance": [
        "balance",
        "running balance",
    ],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
# Format A (normal spaced text)
ACCT_NO_PATTERN_A   = r"account\s*number\s*[:\-]?\s*(\d{10,})"
IFSC_PATTERN_A      = r"(?:branch\s*)?ifsc(?:\s*code)?\s*[:\-]?\s*([A-Z]{4}[A-Z0-9]{7})"
ACCT_TYPE_PATTERN_A = r"(?:product\s*type|account\s*type)\s*[:\-]?\s*(.+)"
PERIOD_PATTERN_A    = r"from\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})"

# Format B (space-stripped decoded text — no spaces in keys)
ACCT_NO_PATTERN_B   = r"accountnumber[:\-]?(\d{10,})"
IFSC_PATTERN_B      = r"(?:branch)?ifsc[:\-]?([A-Z]{4}[A-Z0-9]{7})"
HOLDER_PATTERN_B    = r"customername[:\-]?(.+?)(?:cif[:\-]|$)"
BRANCH_PATTERN_B    = r"homebranch[:\-]?([A-Z]+)"
ACCT_TYPE_PATTERN_B = r"accounttype[:\-]?(\w+)"
PERIOD_PATTERN_B    = r"from(\d{2}/\d{2}/\d{4})to(\d{2}/\d{2}/\d{4})"

DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_DEC_RE      = re.compile(r"(\d+\.\d{2})")
# Realistic max for a single bank transaction (99 crore)
_MAX_TXN_AMT = 99_99_99_999.99


# =============================================================================
# DOUBLED-CHARACTER DECODER (Format B)
# =============================================================================
def _decode_doubled(text):
    """
    Decode doubled-char artifact from Indian Bank ePassbook PDFs.
    'CCuussttoommeerr NN aammee' → 'CustomerName' (spaces removed too).
    Applies only when ≥65% of adjacent pairs in space-stripped text are identical.
    Result is space-free — designed for regex matching, not display.
    """
    if not text or len(text) < 4:
        return text
    stripped = text.replace(" ", "")
    if len(stripped) < 4:
        return text
    doubled = sum(
        1 for i in range(0, len(stripped) - 1, 2)
        if stripped[i] == stripped[i + 1]
    )
    ratio = doubled / (len(stripped) // 2)
    if ratio < 0.65:
        return text
    return stripped[::2]


def _is_doubled_format(lines):
    """Return True if this PDF uses the ePassbook doubled-char format."""
    for line in lines[:15]:
        if line and len(line) > 6:
            decoded = _decode_doubled(line)
            if decoded != line:
                return True
    return False


# =============================================================================
# AMOUNT HELPERS
# =============================================================================
def _clean_amount_indian(value):
    """
    Format A: '1000000.0\n0', '600000.00C\nR' (newline-split CR suffix)
    Format B: '1000.00', '-' (None), '23004.85CR' (no space before CR)
    Returns float or None.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    value = re.sub(r"\s*(C\s*R|D\s*R|CR|DR)\s*$", "", value, flags=re.I).strip()
    value = re.sub(r"^(Rs\.?|INR|₹)\s*", "", value, flags=re.I).strip()
    value = value.replace(",", "").replace(" ", "").replace("\n", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _last_valid_decimal(text):
    """
    Find the last decimal amount (≤ _MAX_TXN_AMT) in text.
    Returns (float_value, re.Match) or (None, None).
    Used to avoid picking up ref-number artifacts like '63634182200.00'.
    """
    for m in reversed(list(_DEC_RE.finditer(text))):
        val = float(m.group())
        if val <= _MAX_TXN_AMT:
            return val, m
    return None, None


# =============================================================================
# DATE HELPERS
# =============================================================================
def _clean_date(value):
    """'18/02\n/2025' → '18/02/2025'"""
    if not value:
        return None
    return value.replace("\n", "").replace(" ", "").strip()


def _is_txn_date(value):
    if not value:
        return False
    return bool(DATE_PATTERN.match(_clean_date(value)))


# =============================================================================
# FORMAT A — COLUMN DETECTOR
# =============================================================================
def _detect_columns_fmt_a(row_clean):
    mapping = {}
    for field, variants in HEADER_MAP_A.items():
        for idx, cell in enumerate(row_clean):
            if cell in variants:
                mapping[field] = idx
                break
        if field in mapping:
            continue
        for idx, cell in enumerate(row_clean):
            if any(len(v) >= 4 and v in cell for v in variants):
                mapping[field] = idx
                break
    return mapping if len(mapping) >= 3 else None


# =============================================================================
# FORMAT B — TRANSACTION LINE PARSER
# =============================================================================
def _parse_txn_fmt_b(decoded_line):
    """
    Parse one decoded (space-stripped) ePassbook transaction line.

    Structure: DATE + DESCRIPTION + WDL_OR_DASH + DEP_OR_DASH + BALANCE + CR/DR
    The '-' dash is always present as the empty-column placeholder.

    Strategy:
    1. Strip trailing CR/DR.
    2. Find balance = last valid decimal (≤ MAX_TXN).
    3. In the text before balance, find the last '-' dash (empty-col separator).
    4. Text before dash = description + possible debit amount.
    5. Text after dash  = possible credit amount (if credit txn).
    6. Use _last_valid_decimal to find the actual amount, ignoring ref-number artifacts.
    """
    if not re.match(r"^\d{2}/\d{2}/\d{4}", decoded_line):
        return None
    date_str = decoded_line[:10]
    rest = re.sub(r"(?:CR|DR)$", "", decoded_line[10:].rstrip(), flags=re.I)

    # Step 1: Find balance (last valid decimal in full line)
    bal_val, bal_m = _last_valid_decimal(rest)
    if bal_m is None:
        return None

    pre_bal = rest[: bal_m.start()]

    # Step 2: Find the last '-' dash (empty-col placeholder)
    dash_pos = pre_bal.rfind("-")

    if dash_pos == -1:
        # No dash at all — treat last valid decimal as debit
        dr_val, dr_m = _last_valid_decimal(pre_bal)
        if dr_m is None:
            return None
        return {
            "date":        date_str,
            "description": pre_bal[: dr_m.start()].strip(),
            "debit":       dr_val,
            "credit":      None,
            "balance":     bal_val,
        }

    before_dash = pre_bal[:dash_pos]
    after_dash  = pre_bal[dash_pos + 1:]

    cr_val, cr_m = _last_valid_decimal(after_dash)
    dr_val, dr_m = _last_valid_decimal(before_dash)

    if cr_val is not None and dr_val is None:
        # Credit transaction: desc '-' amount balance
        return {
            "date":        date_str,
            "description": before_dash.strip(),
            "debit":       None,
            "credit":      cr_val,
            "balance":     bal_val,
        }
    elif dr_val is not None and cr_val is None:
        # Debit transaction: desc amount '-' balance
        return {
            "date":        date_str,
            "description": before_dash[: dr_m.start()].strip(),
            "debit":       dr_val,
            "credit":      None,
            "balance":     bal_val,
        }
    elif dr_val is not None and cr_val is not None:
        # Both present (rare)
        return {
            "date":        date_str,
            "description": before_dash[: dr_m.start()].strip(),
            "debit":       dr_val,
            "credit":      cr_val,
            "balance":     bal_val,
        }
    return None


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines, pdf_path=None):
    """Dispatch to format-specific extractor."""
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    if _is_doubled_format(lines):
        _extract_account_info_fmt_b(lines, info)
    else:
        _extract_account_info_fmt_a(lines, info)

    return info


def _extract_account_info_fmt_a(lines, info):
    """Format A — clean text, index-based + regex."""
    full_text = "\n".join(lines)

    m = re.search(PERIOD_PATTERN_A, full_text, re.I)
    if m:
        info["statement_period"]["from"] = m.group(1)
        info["statement_period"]["to"]   = m.group(2)

    m = re.search(r"for\s+account\s+number\s+(\d{10,})", full_text, re.I)
    if m:
        info["account_number"] = m.group(1)

    for i, line in enumerate(lines):
        text = line.strip()

        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN_A, text, re.I)
            if m:
                info["ifsc"] = m.group(1).upper()

        if info["account_number"] is None:
            m = re.search(ACCT_NO_PATTERN_A, text, re.I)
            if m:
                info["account_number"] = m.group(1)

        # Branch = line immediately after 'INDIAN BANK'
        if info["branch"] is None and text.upper() == "INDIAN BANK":
            if i + 1 < len(lines):
                info["branch"] = lines[i + 1].strip()

        if info["acc_type"] is None:
            m = re.search(ACCT_TYPE_PATTERN_A, text, re.I)
            if m:
                info["acc_type"] = m.group(1).strip()

        # Account holder = line immediately after 'Product type'
        if info["account_holder"] is None:
            m = re.search(r"product\s*type\s*[:\-]", text, re.I)
            if m and i + 1 < len(lines):
                info["account_holder"] = lines[i + 1].strip()


def _extract_account_info_fmt_b(lines, info):
    """Format B — decode doubled chars, match space-stripped regexes."""
    for line in lines:
        decoded = _decode_doubled(line)
        if decoded == line:
            continue  # Not a doubled line

        if info["account_holder"] is None:
            m = re.search(HOLDER_PATTERN_B, decoded, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()

        if info["account_number"] is None:
            m = re.search(ACCT_NO_PATTERN_B, decoded, re.I)
            if m:
                info["account_number"] = m.group(1)

        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN_B, decoded, re.I)
            if m:
                info["ifsc"] = m.group(1).upper()

        if info["branch"] is None:
            m = re.search(BRANCH_PATTERN_B, decoded, re.I)
            if m:
                info["branch"] = m.group(1).strip()

        if info["acc_type"] is None:
            m = re.search(ACCT_TYPE_PATTERN_B, decoded, re.I)
            if m:
                val = m.group(1).strip()
                if val.upper() not in ("OF", "THE", "IN", "AN"):
                    info["acc_type"] = val

        if info["statement_period"]["from"] is None:
            m = re.search(PERIOD_PATTERN_B, decoded, re.I)
            if m:
                info["statement_period"]["from"] = m.group(1)
                info["statement_period"]["to"]   = m.group(2)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path):
    """Detect format and dispatch."""
    with pdfplumber.open(pdf_path) as pdf:
        sample_lines = []
        for page in pdf.pages[:2]:
            t = page.extract_text() or ""
            sample_lines.extend(t.split("\n")[:20])

    if _is_doubled_format(sample_lines):
        return _extract_transactions_fmt_b(pdf_path)
    return _extract_transactions_fmt_a(pdf_path)


def _extract_transactions_fmt_a(pdf_path):
    """Format A — pdfplumber 8-column table extraction."""
    transactions   = []
    column_mapping = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )
            if not tables:
                continue
            for table in tables:
                if not table or len(table[0]) != 8:
                    continue
                for row in table:
                    if not row or len(row) < 8:
                        continue
                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]
                    detected = _detect_columns_fmt_a(row_clean)
                    if detected:
                        column_mapping = detected
                        continue
                    if column_mapping is None:
                        continue
                    raw_date  = row[column_mapping.get("date", 0)] or ""
                    date_cell = _clean_date(raw_date)
                    if not _is_txn_date(date_cell):
                        continue
                    desc_raw    = row[column_mapping.get("description", 3)] or ""
                    description = re.sub(r"\s+", " ", desc_raw.replace("\n", " ")).strip()
                    debit   = _clean_amount_indian(row[column_mapping.get("debit",   5)])
                    credit  = _clean_amount_indian(row[column_mapping.get("credit",  6)])
                    balance = _clean_amount_indian(row[column_mapping.get("balance", 7)])
                    transactions.append({
                        "date":        date_cell,
                        "description": description,
                        "debit":       debit,
                        "credit":      credit,
                        "balance":     balance,
                    })
    return transactions


def _extract_transactions_fmt_b(pdf_path):
    """Format B — decode doubled-char text lines and parse transactions."""
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            raw_text = page.extract_text() or ""
            for line in raw_text.split("\n"):
                decoded = _decode_doubled(line)
                if decoded == line:
                    continue  # Not a doubled line
                txn = _parse_txn_fmt_b(decoded)
                if txn:
                    transactions.append(txn)

    return transactions