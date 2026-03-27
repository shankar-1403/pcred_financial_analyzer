import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "idfc"
BANK_DISPLAY_NAME = "IDFC First Bank"


# =============================================================================
# IDFC FIRST BANK — PDF FORMAT
# =============================================================================
#
# FORMAT: Single format (online statement download)
#   7-column ruled table:
#     Transaction Date | Value Date | Particulars | Cheque No | Debit | Credit | Balance
#
#   Account info block (top of every page):
#     CUSTOMER ID      : 5207760608        ← pdfplumber renders as 5.207760608e+09
#     ACCOUNT NO       : 10067428649       ← pdfplumber renders as 1.0067428649e+10
#     STATEMENT PERIOD : 2024-12-01 TO 2025-04-17
#     CUSTOMER NAME    : Mr. Deepak Suresh Jaiswar  ACCOUNT BRANCH : BKC - Naman Branch
#     IFSC             : IDFB0040101
#     MICR             : 400751002
#     ACCOUNT TYPE     : Classic Corporate Salary
#     CURRENCY         : INR
#
#   Date format in PDF : DD-Mon-YYYY  (e.g. "01-Dec-2024")
#   Period format      : YYYY-MM-DD   (e.g. "2024-12-01 TO 2025-04-17")
#   Balance            : plain positive number  e.g. "26,377.10"
#   Debit / Credit     : plain numbers in their respective columns; empty = None
#   Opening Balance row: no date, "Opening Balance" in Particulars — skipped
#
# QUIRKS:
#   1. pdfplumber renders large account/customer numbers in scientific notation.
#      Fix: int(float(raw)) via _parse_sci_int()
#   2. CUSTOMER NAME and ACCOUNT BRANCH land on the SAME line with single-space
#      separator — old \s{2,} lookahead never triggered.
#      Fix: lookahead on known label keywords via _NEXT_LABEL_PAT
#   3. ACCOUNT TYPE spans multiple lines: "Classic\nCorporate\nSalary"
#      Fix: first match on the "Classic..." line is sufficient.
# =============================================================================


# ---------------------------------
# HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date":        ["transaction date", "txn date", "date"],
    "value_date":  ["value date"],
    "description": ["particulars", "narration", "description", "transaction details"],
    "cheque":      ["cheque no", "cheque number", "chq no", "ref no", "instrument no"],
    "debit":       ["debit", "withdrawal", "dr"],
    "credit":      ["credit", "deposit", "cr"],
    "balance":     ["balance", "closing balance", "running balance"],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_DATE_RE     = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")           # 01-Dec-2024

# Scientific notation safe — pdfplumber renders large numbers as e.g. 1.0067428649e+10
_ACCT_RE     = re.compile(r"account\s*no\s*[:\-]?\s*([\d.e+E]+)", re.I)
_CUST_ID_RE  = re.compile(r"customer\s*id\s*[:\-]?\s*([\d.e+E]+)", re.I)

_IFSC_RE     = re.compile(r"ifsc\s*[:\-]?\s*(IDFB[A-Z0-9]{7})", re.I)
_MICR_RE     = re.compile(r"micr\s*[:\-]?\s*(\d{9})", re.I)
_CURRENCY_RE = re.compile(r"currency\s*[:\-]?\s*([A-Z]{3})", re.I)
_PERIOD_RE   = re.compile(
    r"statement\s*period\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", re.I
)

# Lookahead stops capture at the next known label on the same line.
# Needed because pdfplumber concatenates two-column rows into one line e.g.:
#   "CUSTOMER NAME : Mr. Deepak Suresh Jaiswar ACCOUNT BRANCH : BKC - Naman Branch"
_NEXT_LABEL_PAT = (
    r"(?=\s+(?:ACCOUNT\s+(?:BRANCH|NO|TYPE|STATUS|OPENING)|"
    r"COMMUNICATION|BRANCH\s+ADDRESS|IFSC|MICR|EMAIL|PHONE\s+NO|"
    r"CKYC|NOMINATION|NOMINEE|CURRENCY|CUSTOMER\s+(?:ID|NAME)|STATEMENT)\b)"
)
_CUST_RE     = re.compile(r"customer\s*name\s*[:\-]\s*(.+?)(?:" + _NEXT_LABEL_PAT + r"|\s*$)", re.I)
_BRANCH_RE   = re.compile(r"account\s*branch\s*[:\-]\s*(.+?)(?:" + _NEXT_LABEL_PAT + r"|\s*$)", re.I)
_ACC_TYPE_RE = re.compile(r"account\s*type\s*[:\-]\s*(.+?)(?:" + _NEXT_LABEL_PAT + r"|\s*$)", re.I)

# Safety net: truncate captured value if a known label bleeds in
_FIELD_LABELS = re.compile(
    r"\b(account\s*branch|account\s*no|branch\s*address|ifsc|micr|"
    r"account\s*opening|account\s*status|account\s*type|currency|"
    r"communication|address|email(\s*id)?|phone(\s*no)?|ckyc(\s*id)?|"
    r"nomination|nominee(\s*name)?|customer\s*id|customer\s*name|"
    r"statement\s*period)\b",
    re.I,
)


# ---------------------------------
# DATE HELPERS
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """
    Convert to DD-MM-YYYY:
      'DD-Mon-YYYY' (transaction dates) e.g. '01-Dec-2024' → '01-12-2024'
      'YYYY-MM-DD'  (statement period)  e.g. '2024-12-01'  → '01-12-2024'
    """
    if not date_str:
        return date_str
    s = date_str.strip()
    for fmt, out in [("%d-%b-%Y", "%d-%m-%Y"), ("%Y-%m-%d", "%d-%m-%Y")]:
        try:
            return datetime.strptime(s, fmt).strftime(out)
        except ValueError:
            continue
    return date_str


def _is_txn_date(value: str) -> bool:
    """Return True only for transaction-row dates: DD-Mon-YYYY."""
    return bool(_DATE_RE.match((value or "").strip()))


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_idfc(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace(" ", "")
    if not s or s in ("-", "", "None", "null"):
        return None
    s = re.sub(r"^(Rs\.?|INR|₹)\s*", "", s, flags=re.I)
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------
# CAPTURED VALUE HELPERS
# ---------------------------------
def _parse_sci_int(raw: str) -> str | None:
    """
    Convert scientific notation string to integer string.
    e.g. '1.0067428649e+10' → '10067428649'
    """
    try:
        return str(int(float(raw)))
    except (ValueError, TypeError):
        return None


def _clean_captured(value: str) -> str | None:
    """
    Truncate at any known field label that may have bled into the captured value,
    then strip whitespace and separator chars.
    """
    if not value:
        return None
    m = _FIELD_LABELS.search(value)
    if m:
        value = value[:m.start()]
    value = re.sub(r"\s+", " ", value).strip(" :-")
    return value if len(value) > 1 else None


# ---------------------------------
# COLUMN DETECTOR
# ---------------------------------
def _detect_columns(row_clean: list[str]) -> dict | None:
    mapping = {}
    for field, variants in HEADER_MAP.items():
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
    # Minimum required columns
    required = {"date", "balance", "description"}
    if not required.issubset(mapping):
        return None
    if "debit" not in mapping and "credit" not in mapping:
        return None
    return mapping


def _is_header_row(row_clean: list[str]) -> bool:
    joined = " ".join(row_clean)
    return (
        ("transaction date" in joined or "txn date" in joined)
        and ("debit" in joined or "withdrawal" in joined)
        and "balance" in joined
    )


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Account number — scientific notation safe
    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = _parse_sci_int(m.group(1)) or m.group(1)

    # Customer ID — scientific notation safe
    m = _CUST_ID_RE.search(full_text)
    if m:
        info["customer_id"] = _parse_sci_int(m.group(1)) or m.group(1)

    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    m = _MICR_RE.search(full_text)
    if m:
        info["micr"] = m.group(1)

    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    m = _CURRENCY_RE.search(full_text)
    if m:
        info["currency"] = m.group(1).upper()

    # Line-by-line for fields that may share a line with adjacent labels
    for line in lines:
        s = line.strip()
        if not s:
            continue

        if info["account_holder"] is None:
            m = _CUST_RE.search(s)
            if m:
                candidate = _clean_captured(m.group(1).strip())
                if candidate:
                    info["account_holder"] = candidate

        if info["branch"] is None:
            m = _BRANCH_RE.search(s)
            if m:
                candidate = _clean_captured(m.group(1).strip())
                if candidate:
                    info["branch"] = candidate

        if info["acc_type"] is None:
            m = _ACC_TYPE_RE.search(s)
            if m:
                candidate = _clean_captured(m.group(1).strip())
                if candidate:
                    info["acc_type"] = candidate

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Dispatcher-compatible wrapper."""
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    transactions:   list[dict] = []
    column_mapping: dict | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )
            if not tables:
                continue

            for table in tables:
                if not table:
                    continue

                for row in table:
                    if not row or len(row) < 5:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    # Re-detect header on every page (header repeats each page)
                    if _is_header_row(row_clean):
                        col = _detect_columns(row_clean)
                        if col:
                            column_mapping = col
                        continue

                    if column_mapping is None:
                        continue

                    date_raw = (row[column_mapping.get("date", 0)] or "").strip()
                    if not _is_txn_date(date_raw):
                        continue

                    txn = _build_txn(row, column_mapping, date_raw)
                    if txn:
                        transactions.append(txn)

    transactions.sort(key=_sort_key)
    return transactions


# ---------------------------------
# ROW BUILDER
# ---------------------------------
def _build_txn(row, col, date_raw) -> dict | None:
    desc_raw    = row[col.get("description", 2)] or ""
    description = re.sub(r"\s+", " ", desc_raw.replace("\n", " ")).strip() or None
    cheque_no   = (row[col.get("cheque", 3)] or "").strip() or None
    debit       = _clean_amount_idfc(row[col.get("debit",   4)]) if "debit"   in col else None
    credit      = _clean_amount_idfc(row[col.get("credit",  5)]) if "credit"  in col else None
    balance     = _clean_amount_idfc(row[col.get("balance", 6)]) if "balance" in col else None

    return {
        "date":        _reformat_date(date_raw),
        "description": description,
        "ref_no":      cheque_no,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }