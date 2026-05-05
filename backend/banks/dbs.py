import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "dbs"
BANK_DISPLAY_NAME = "DBS Bank India"


# =============================================================================
# DBS BANK INDIA — PDF FORMAT (Account Details)
# =============================================================================
#
# ACCOUNT INFO BLOCK (page 1):
#   Account Number   : 8856210000021942 - INR
#   Account Name     : ENVIROTECH AKVA PRIVATE LIMITED - 8856210000021942 - INR
#   Product Type     : CALRT LAKSHMI PRIME TASC
#   Opening Balance  : 411,801.00  01-Aug-2025
#   Ledger Balance   : 2,085,579.97  30-Aug-2025
#   Available Balance: 2,085,579.97  30-Aug-2025
#
# TRANSACTION TABLE (6 columns):
#   Date | Value Date | Transaction Details | Debit | Credit | Running Balance
#
# DATE FORMAT   : "01-Aug-2025"  (DD-Mon-YYYY) → DD-MM-YYYY
# BALANCE       : plain Indian comma float "8,211,801.00" (no Dr/Cr suffix)
# DEBIT/CREDIT  : Indian comma format; blank cell → None
# DETAILS       : multi-line, wraps extensively within cell
# SKIP ROWS     : "Printed By", "Printed On", "Page X / Y", header rows
# PERIOD        : derived from Opening Balance date → Ledger Balance date
# IFSC PREFIX   : DBSS
# =============================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_IFSC_RE    = re.compile(r"\b(DBSS[A-Z0-9]{7})\b", re.I)
_ACCT_RE    = re.compile(r"account\s*number\s*[:\-]?\s*(\d{10,})", re.I)
_NAME_RE    = re.compile(r"account\s*name\s*[:\-]?\s*(.+?)(?:\s*-\s*\d{10,}|$)", re.I)
_PROD_RE    = re.compile(r"product\s*type\s*[:\-]?\s*(.+)", re.I)
_OPENBAL_RE = re.compile(
    r"opening\s*balance\s*[:\-]?\s*([\d,]+\.\d{2})\s+(\d{2}-[A-Za-z]{3}-\d{4})", re.I
)
_LEDGERBAL_RE = re.compile(
    r"ledger\s*balance\s*[:\-]?\s*([\d,]+\.\d{2})\s+(\d{2}-[A-Za-z]{3}-\d{4})", re.I
)
_PRINTDATE_RE = re.compile(
    r"printed\s*on\s*[:\-]?\s*(\d{2}-[A-Za-z]{3}-\d{4})", re.I
)

# Transaction date: "01-Aug-2025" (DD-Mon-YYYY)
_TXN_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")

# Rows to skip
_SKIP_ROW_RE = re.compile(
    r"^(printed\s+(by|on)|page\s+\d+\s*/|account\s+details)",
    re.I,
)

_HEADER_KEYWORDS = {
    "date", "value date", "transaction details", "debit", "credit",
    "running balance", "balance",
}


# ---------------------------------
# DATE REFORMAT
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert 'DD-Mon-YYYY' (01-Aug-2025) → 'DD-MM-YYYY' (01-08-2025)."""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d-%b-%Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


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
def _clean_amount_dbs(value) -> float | None:
    """
    Handles Indian comma format: '7,800,000.00', '281,548.00'
    Blank / None → None.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "", "None", "null"):
        return None
    s = s.replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------
# COLUMN DETECTION
# ---------------------------------
def _detect_cols(row: list) -> dict:
    """
    Header-based column detection — no strict column count.
    Returns mapping if 'date' and 'balance' found, else {}.
    """
    mapping = {}
    for idx, cell in enumerate(row):
        c = (cell or "").replace("\n", " ").strip().lower()
        if c == "date":
            mapping["date"] = idx
        elif c == "value date":
            mapping["value_date"] = idx
        elif c in ("transaction details", "particulars", "description",
                   "narration", "details"):
            mapping["description"] = idx
        elif c in ("debit", "withdrawal", "dr"):
            mapping["debit"] = idx
        elif c in ("credit", "deposit", "cr"):
            mapping["credit"] = idx
        elif c in ("running balance", "balance", "closing balance"):
            mapping["balance"] = idx
    return mapping if ("date" in mapping and "balance" in mapping) else {}


def _is_header_row(row: list) -> bool:
    cells = {(cell or "").replace("\n", " ").strip().lower() for cell in row}
    return bool(
        cells & {"date"}
        and cells & {"running balance", "balance"}
        and cells & {"debit", "credit", "transaction details"}
    )


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str]) -> dict:
    """
    Extract account metadata from DBS Bank Account Details statement.

    Page 1 layout (label : value):
        Account Number   : 8856210000021942 - INR
        Account Name     : ENVIROTECH AKVA PRIVATE LIMITED - 8856210000021942 - INR
        Product Type     : CALRT LAKSHMI PRIME TASC
        Opening Balance  : 411,801.00  01-Aug-2025
        Ledger Balance   : 2,085,579.97  30-Aug-2025
        Printed On       : 01-Sep-2025 07:08:13
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # IFSC (may appear in transaction details or header)
    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    # Account number — strip " - INR" suffix
    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1)

    # Account holder name — strip trailing "- <account_number> - INR"
    m = _NAME_RE.search(full_text)
    if m:
        candidate = m.group(1).strip()
        # Clean: remove trailing account number reference
        candidate = re.sub(r"\s*-\s*\d{10,}.*$", "", candidate).strip()
        if candidate and len(candidate) > 2:
            info["account_holder"] = candidate

    # Product type → acc_type
    m = _PROD_RE.search(full_text)
    if m:
        info["acc_type"] = m.group(1).strip()

    # Opening balance + period FROM date
    m = _OPENBAL_RE.search(full_text)
    if m:
        info["opening_balance"]          = _clean_amount_dbs(m.group(1))
        info["statement_period"]["from"] = _reformat_date(m.group(2))

    # Ledger balance + period TO date
    m = _LEDGERBAL_RE.search(full_text)
    if m:
        info["closing_balance"]        = _clean_amount_dbs(m.group(1))
        info["statement_period"]["to"] = _reformat_date(m.group(2))

    # Statement request date (Printed On)
    m = _PRINTDATE_RE.search(full_text)
    if m:
        info["statement_request_date"] = _reformat_date(m.group(1))

    return info


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from a DBS Bank PDF statement.

    6-column table:
        Date | Value Date | Transaction Details | Debit | Credit | Running Balance

    Date format   : 'DD-Mon-YYYY' → DD-MM-YYYY
    Balance       : plain Indian comma float (no Dr/Cr suffix)
    Details field : multi-line, heavily wrapping — joined with space
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

                    row_text = " ".join((cell or "") for cell in row)

                    # Skip footer/printed-by rows
                    if _SKIP_ROW_RE.search(row_text.strip()):
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

                    # Continuation row — no valid date, extend last txn description
                    if not date_raw or not _is_txn_date(date_raw):
                        if last_txn:
                            extra = _get("description")
                            if extra:
                                last_txn["description"] = (
                                    (last_txn["description"] or "") + " " + extra
                                ).strip()
                        continue

                    desc = _get("description")
                    if desc:
                        desc = re.sub(r"\s+", " ", desc).strip()

                    txn = {
                        "date":        _reformat_date(date_raw),  # DD-Mon-YYYY → DD-MM-YYYY
                        "description": desc,
                        "debit":       _clean_amount_dbs(_get("debit")),
                        "credit":      _clean_amount_dbs(_get("credit")),
                        "balance":     _clean_amount_dbs(_get("balance")),
                    }
                    transactions.append(txn)
                    last_txn = txn

    # Sort chronologically oldest → newest
    transactions.sort(key=_sort_key)
    return transactions