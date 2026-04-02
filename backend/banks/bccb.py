import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "bccb"
BANK_DISPLAY_NAME = "Bassein Catholic Co-operative Bank Ltd."


# =============================================================================
# BASSEIN CATHOLIC CO-OPERATIVE BANK LTD. — PDF FORMAT (Account Statement)
# =============================================================================
#
# INFO BLOCK (page 1):
#   Account Number       : 012110100006711
#   Customer Name        : A 1 POLYMER
#   IFSC Code / MICR Code: BACB0000012 / 400238012
#   From Date - To Date  : 30-05-2023 To 29-05-2024
#
# TRANSACTION TABLE (7 columns):
#   Transaction Date | Description | Reference Number | Value Date | Debit | Credit | Balance
#
# DATE FORMAT  : "29 May 2023"  (DD Mon YYYY) → DD-MM-YYYY
# BALANCE      : plain Indian comma format "49,690.36" (no Cr/Dr suffix)
# =============================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------

# IFSC: just find BACB prefix anywhere in text
_IFSC_RE   = re.compile(r"\b(BACB[A-Z0-9]{7})\b", re.I)

# MICR: standalone 9-digit number
_MICR_RE   = re.compile(r"\b(\d{9})\b")

_ACCT_RE   = re.compile(r"account\s*number\s*[:\-]?\s*(\d{10,})", re.I)
_NAME_RE   = re.compile(r"customer\s*name\s*[:\-]?\s*(.+)", re.I)
_PERIOD_RE = re.compile(
    r"from\s*date\s*[-–]\s*to\s*date\s*[:\-]?\s*"
    r"(\d{2}-\d{2}-\d{4})\s+[Tt]o\s+(\d{2}-\d{2}-\d{4})",
    re.I,
)

# Date: "29 May 2023"
_DATE_RE = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$")

_SKIP_ROW_RE = re.compile(
    r"opening\s+balance|closing\s+balance|total\s+debit|"
    r"total\s+credit|end\s+of\s+statement",
    re.I,
)


# ---------------------------------
# DATE REFORMAT
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert 'DD Mon YYYY' (29 May 2023) → 'DD-MM-YYYY' (29-05-2023)."""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d %b %Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


def _is_txn_date(value: str) -> bool:
    return bool(_DATE_RE.match((value or "").strip()))


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_bccb(value) -> float | None:
    """Indian comma format '1,21,687.50' → 121687.50. Blank → None."""
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
    Detect column mapping from a header row.
    Returns mapping dict if 'date' key found, else {}.
    Works regardless of total column count.
    """
    mapping = {}
    for idx, cell in enumerate(row):
        c = (cell or "").replace("\n", " ").strip().lower()
        if c in ("transaction date", "tran date", "date"):
            mapping["date"] = idx
        elif c in ("description", "particulars", "narration"):
            mapping["description"] = idx
        elif c in ("reference number", "reference no", "ref no",
                   "ref. no", "chq no", "chq no.", "chq number"):
            mapping["ref_no"] = idx
        elif c in ("value date",):
            mapping["value_date"] = idx
        elif c in ("debit", "withdrawal", "dr"):
            mapping["debit"] = idx
        elif c in ("credit", "deposit", "cr"):
            mapping["credit"] = idx
        elif c == "balance":
            mapping["balance"] = idx
    return mapping if "date" in mapping else {}


def _is_header_row(row: list) -> bool:
    """True if this row looks like a transaction table header."""
    joined = " ".join((cell or "").replace("\n", " ").strip().lower() for cell in row)
    return (
        ("transaction date" in joined or "tran date" in joined)
        and "balance" in joined
        and ("debit" in joined or "credit" in joined)
    )


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str]) -> dict:
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # IFSC — find BACB prefix anywhere
    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    # MICR — find 9-digit number that is NOT a substring of the IFSC code
    ifsc_val = m.group(1) if m else ""
    for mm in _MICR_RE.finditer(full_text):
        val = mm.group(1)
        if val in ifsc_val:   # skip digits that appear inside IFSC string
            continue
        info["micr"] = val
        break

    # Statement period
    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = m.group(1)
        info["statement_period"]["to"]   = m.group(2)

    # Line-by-line
    for line in lines:
        s = line.strip()
        if not s:
            continue

        if info["account_number"] is None:
            m = _ACCT_RE.search(s)
            if m:
                info["account_number"] = m.group(1)

        if info["account_holder"] is None:
            m = _NAME_RE.search(s)
            if m:
                candidate = m.group(1).strip()
                if (
                    candidate
                    and len(candidate) > 1
                    and not re.match(r"^\d", candidate)
                    and "Statement" not in candidate
                    and "Bank" not in candidate
                ):
                    info["account_holder"] = candidate

    return info


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from a BCCB PDF statement.

    Uses header-based column detection (no strict column count filter)
    to handle cases where pdfplumber merges or splits columns differently.

    7-column table (typical):
        Transaction Date | Description | Reference Number | Value Date | Debit | Credit | Balance
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

                    # Skip summary/footer rows
                    row_text = " ".join((cell or "") for cell in row)
                    if _SKIP_ROW_RE.search(row_text):
                        continue

                    # Detect header row — no strict col count, just check content
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

                    # Continuation row — no valid date
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
                        "date":        _reformat_date(date_raw),
                        "description": desc,
                        "ref_no":      _get("ref_no") or None,
                        "debit":       _clean_amount_bccb(_get("debit")),
                        "credit":      _clean_amount_bccb(_get("credit")),
                        "balance":     _clean_amount_bccb(_get("balance")),
                    }
                    transactions.append(txn)
                    last_txn = txn

    transactions.sort(key=_sort_key)
    return transactions