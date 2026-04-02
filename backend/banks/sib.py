import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "sib"
BANK_DISPLAY_NAME = "South Indian Bank"


# =============================================================================
# SOUTH INDIAN BANK (SIB) — PDF FORMAT (Statement of Account)
# =============================================================================
#
# TOP-RIGHT INFO BLOCK (every page):
#   Branch Name : GOREGAON,MUMBAI
#   IFSC        : SIBL0000352
#   Customer ID : A52490063
#   Type        : CASH CREDIT - GENERAL
#   A/C No      : 0352083000000528
#   Currency    : INR
#   MICR        : 400059007
#   Swift Code  : SOININ55XXX
#
# TOP-LEFT INFO BLOCK:
#   M/S. AGRAWAL ASSOCIATES      ← account holder (first bold line)
#   Address lines...
#   DATE: 30-12-2025             ← statement request date
#
# STATEMENT PERIOD LINE:
#   "STATEMENT OF ACCOUNT FOR THE PERIOD FROM 01-04-2024 to 31-03-2025"
#
# TRANSACTION TABLE (6 columns):
#   DATE | PARTICULARS | CHQ_NO. | WITHDRAWALS | DEPOSITS | BALANCE
#
# DATE FORMAT  : "01-04-2024"  (DD-MM-YYYY) — already correct, no reformat needed
# BALANCE      : "5534039.39 Dr" or "180001.00 Cr" → strip suffix, negative if Dr
# WITHDRAWALS  : debit  (blank = None)
# DEPOSITS     : credit (blank = None)
# CHQ_NO.      : ref_no (often blank)
# SKIP ROWS    : "Page Total", "B/F" (opening balance carry-forward), dashes
# =============================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_IFSC_RE    = re.compile(r"\b(SIBL[A-Z0-9]{7})\b", re.I)
_MICR_RE    = re.compile(r"MICR\s*[:\-]?\s*(\d{9})", re.I)
_ACCT_RE    = re.compile(r"A/C\s*No\s*[:\-]?\s*(\d{10,})", re.I)
_CUSTID_RE  = re.compile(r"customer\s*id\s*[:\-]?\s*(\S+)", re.I)
_TYPE_RE    = re.compile(r"type\s*[:\-]?\s*(.+)", re.I)
_BRANCH_RE  = re.compile(r"branch\s*name\s*[:\-]?\s*(.+)", re.I)
_DATE_RE_   = re.compile(r"DATE\s*[:\-]?\s*(\d{2}-\d{2}-\d{4})", re.I)
_SWIFT_RE   = re.compile(r"swift\s*code\s*[:\-]?\s*(\S+)", re.I)
_PERIOD_RE  = re.compile(
    r"for\s+the\s+period\s+from\s+(\d{2}-\d{2}-\d{4})\s+to\s+(\d{2}-\d{2}-\d{4})",
    re.I,
)

# Transaction date: "01-04-2024" (DD-MM-YYYY)
_TXN_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")

# Balance suffix
_DR_RE = re.compile(r"\s*Dr\.?\s*$", re.I)
_CR_RE = re.compile(r"\s*Cr\.?\s*$", re.I)

# Rows to skip
_SKIP_ROW_RE = re.compile(
    r"^(page\s+total|b/f|brought\s+forward|[-=]{5,}|"
    r"date\s+particulars|this\s+is\s+a\s+system|"
    r"visit\s+us|page\s+\d+\s+of)",
    re.I,
)


# ---------------------------------
# HELPERS
# ---------------------------------
def _is_txn_date(value: str) -> bool:
    return bool(_TXN_DATE_RE.match((value or "").strip()))


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_sib(value) -> float | None:
    """
    Handles:
      - "10166.66"          → 10166.66   (debit/credit cell)
      - "5534039.39 Dr"     → 5534039.39 (balance, Dr = overdraft but stored positive)
      - "180001.00 Cr"      → 180001.00  (balance)
      - ""  / None          → None
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "", "None", "null"):
        return None
    # Strip Dr/Cr suffix
    s = _DR_RE.sub("", s).strip()
    s = _CR_RE.sub("", s).strip()
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------
# COLUMN DETECTION
# ---------------------------------
def _detect_cols(row: list) -> dict:
    """
    Header-based column detection — works regardless of total column count.
    Returns mapping if 'date' and 'balance' found, else {}.
    """
    mapping = {}
    for idx, cell in enumerate(row):
        c = (cell or "").replace("\n", " ").strip().lower()
        if c in ("date", "transaction date", "tran date", "txn date"):
            mapping["date"] = idx
        elif c in ("particulars", "description", "narration", "remarks"):
            mapping["description"] = idx
        elif c in ("chq no.", "chq no", "chq_no.", "chq_no",
                   "cheque no", "cheque no.", "ref no", "instrument no"):
            mapping["ref_no"] = idx
        elif c in ("withdrawals", "withdrawal", "debit", "dr"):
            mapping["debit"] = idx
        elif c in ("deposits", "deposit", "credit", "cr"):
            mapping["credit"] = idx
        elif c == "balance":
            mapping["balance"] = idx
    return mapping if ("date" in mapping and "balance" in mapping) else {}


def _is_header_row(row: list) -> bool:
    joined = " ".join((cell or "").replace("\n", " ").strip().lower() for cell in row)
    return (
        ("date" in joined)
        and "balance" in joined
        and ("withdrawal" in joined or "deposit" in joined or "particulars" in joined)
    )


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str]) -> dict:
    """
    Extract account metadata from South Indian Bank statement.

    Top-right block (key : value pairs):
        Branch Name : GOREGAON,MUMBAI
        IFSC        : SIBL0000352
        Customer ID : A52490063
        Type        : CASH CREDIT - GENERAL
        A/C No      : 0352083000000528
        MICR        : 400059007

    Top-left block:
        M/S. AGRAWAL ASSOCIATES     ← account holder
        <address lines>
        DATE: 30-12-2025

    Statement line:
        STATEMENT OF ACCOUNT FOR THE PERIOD FROM 01-04-2024 to 31-03-2025
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # IFSC
    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    # MICR
    m = _MICR_RE.search(full_text)
    if m:
        info["micr"] = m.group(1)

    # Account number
    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1)

    # Customer ID
    m = _CUSTID_RE.search(full_text)
    if m:
        info["customer_id"] = m.group(1).strip()

    # Account type
    m = _TYPE_RE.search(full_text)
    if m:
        candidate = m.group(1).strip()
        # Avoid picking up "ANY ONE" (mode of operation) or other noise
        if candidate and "ANY" not in candidate.upper() and len(candidate) > 3:
            info["acc_type"] = candidate

    # Branch
    m = _BRANCH_RE.search(full_text)
    if m:
        info["branch"] = m.group(1).strip()

    # Statement request date: "DATE: 30-12-2025"
    m = _DATE_RE_.search(full_text)
    if m:
        info["statement_request_date"] = m.group(1)

    # Statement period
    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = m.group(1)
        info["statement_period"]["to"]   = m.group(2)

    # Account holder — first non-empty line that looks like a name
    # (appears in top-left before address, starts with M/S. or ALL CAPS)
    _NOISE_RE = re.compile(
        r"branch|ifsc|customer|a/c|account|micr|swift|currency|mode|"
        r"type|date|statement|period|visit|page|system|phone|ph:|"
        r"ground|floor|road|nagar|maharashtra|india|mumbai|@",
        re.I,
    )
    for line in lines[:30]:
        s = line.strip()
        if not s or len(s) < 3:
            continue
        if _NOISE_RE.search(s):
            continue
        if re.match(r"^\d", s):
            continue
        if re.match(r"^[A-Z]", s) and not re.search(r"\d{6,}", s):
            info["account_holder"] = s
            break

    return info


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from a South Indian Bank PDF statement.

    6-column table:
        DATE | PARTICULARS | CHQ_NO. | WITHDRAWALS | DEPOSITS | BALANCE

    DATE format  : 'DD-MM-YYYY' (already correct — no reformat needed)
    BALANCE      : 'AMOUNT Dr' or 'AMOUNT Cr' — strip suffix, store as positive float
    Skip rows    : Page Total, B/F, dashed lines, footer text
    """
    transactions   = []
    column_mapping = None
    last_txn       = None

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
                    if not row:
                        continue

                    # Skip footer/summary/header noise rows
                    first = (row[0] or "").replace("\n", " ").strip()
                    row_text = " ".join((cell or "") for cell in row)

                    if _SKIP_ROW_RE.search(first) or _SKIP_ROW_RE.search(row_text):
                        continue

                    # Detect header row
                    if _is_header_row(row):
                        detected = _detect_cols(row)
                        if detected:
                            column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    def _get(key):
                        idx = column_mapping.get(key)
                        if idx is None or idx >= len(row):
                            return None
                        return (row[idx] or "").replace("\n", " ").strip() or None

                    date_raw = _get("date")

                    # Continuation row — no date, append description
                    if not date_raw or not _is_txn_date(date_raw):
                        if last_txn:
                            extra = _get("description")
                            if extra:
                                last_txn["description"] = (
                                    (last_txn["description"] or "") + " " + extra
                                ).strip()
                        continue

                    # Skip B/F (brought forward) opening balance row
                    desc_raw = _get("description") or ""
                    if re.match(r"^b/?f$", desc_raw.strip(), re.I):
                        continue

                    desc = re.sub(r"\s+", " ", desc_raw).strip() or None

                    txn = {
                        "date":        date_raw,            # already DD-MM-YYYY
                        "description": desc,
                        "ref_no":      _get("ref_no") or None,
                        "debit":       _clean_amount_sib(_get("debit")),
                        "credit":      _clean_amount_sib(_get("credit")),
                        "balance":     _clean_amount_sib(_get("balance")),
                    }
                    transactions.append(txn)
                    last_txn = txn

    # Sort chronologically oldest → newest
    transactions.sort(key=_sort_key)
    return transactions