import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "svc"
BANK_DISPLAY_NAME = "SVC Co-operative Bank Ltd."


# =============================================================================
# SVC CO-OPERATIVE BANK LTD. — PDF FORMAT (Account Statement)
# =============================================================================
#
# INFO BLOCK (page 1, plain text):
#   "Account No: 111304180000062 - JALNA Branch"
#   "SHRI PUNAGRI TRADERS(CKYC-70094871528579)"    ← account holder (standalone line)
#   "D 45 Ring Road, Market Yard..."                ← address
#   "MICR: 431089052  IFSC SVCB0000113"
#   "Customer Id: 101459570"
#   "From: 01-Apr-2025  To: 24-Nov-2025"
#   "Opening Balance as on : 01-Apr-2025  Rs. 15,87,807.29 Cr"
#
# TRANSACTION TABLE (7 columns):
#   Tran Date | Value Date | Particulars | Chq No. | Debit | Credit | Balance
#
# DATE FORMAT  : "01-Apr-2025"  (DD-Mon-YYYY)  → normalised to DD-MM-YYYY
# BALANCE      : "16,30,719.29 Cr"             → strip " Cr" suffix, parse float
# DEBIT/CREDIT : Indian comma format e.g. "17,358.00" — blank = None
# =============================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_IFSC_RE    = re.compile(r"\bIFSC\s*(SVCB[A-Z0-9]{7})\b", re.I)
_MICR_RE    = re.compile(r"MICR[:\s]*(\d{9})", re.I)
_CUSTID_RE  = re.compile(r"customer\s*id[:\s]*(\d+)", re.I)
_ACCT_RE    = re.compile(r"account\s*no[:\s]*(\d{10,})", re.I)
_BRANCH_RE  = re.compile(r"\d{10,}\s*[-–]\s*(.+?)\s*(?:branch)?$", re.I)
_PERIOD_RE  = re.compile(
    r"from[:\s]+(\d{2}-[A-Za-z]{3}-\d{4})\s+to[:\s]+(\d{2}-[A-Za-z]{3}-\d{4})",
    re.I,
)
_OPENBAL_RE = re.compile(
    r"opening\s+balance\s+as\s+on\s*[:\s]+[\d\-A-Za-z]+\s+Rs\.?\s*([\d,]+\.\d{2})",
    re.I,
)
_CR_SUFFIX_RE = re.compile(r"\s*Cr\.?\s*$", re.I)
_DR_SUFFIX_RE = re.compile(r"\s*Dr\.?\s*$", re.I)

# Date: "01-Apr-2025"
_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")

# Header detection keywords
_HEADER_SKIP = re.compile(
    r"tran\s*date|value\s*date|particulars|chq\s*no|debit|credit|balance",
    re.I,
)


# ---------------------------------
# DATE REFORMAT
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert 'DD-Mon-YYYY' (01-Apr-2025) → 'DD-MM-YYYY' (01-04-2025)."""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d-%b-%Y").strftime("%d-%m-%Y")
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
def _clean_amount_svc(value) -> float | None:
    """
    Handles:
      - "17,358.00"           → 17358.0
      - "16,30,719.29 Cr"    → 1630719.29  (balance, strip Cr)
      - ""  / None            → None
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "", "None", "null"):
        return None
    # Strip Cr / Dr suffix (balance column)
    s = _CR_SUFFIX_RE.sub("", s).strip()
    s = _DR_SUFFIX_RE.sub("", s).strip()
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------
# COLUMN DETECTION  (exact match)
# ---------------------------------
def _detect_cols(row: list) -> dict:
    """
    Exact-match column detection for SVC's 7-column transaction table.
    Returns mapping dict if 'tran date' or 'date' found, else {}.
    """
    mapping = {}
    for idx, cell in enumerate(row):
        c = (cell or "").replace("\n", " ").strip().lower()
        if c in ("tran date", "transaction date", "date"):
            mapping["date"] = idx
        elif c == "value date":
            mapping["value_date"] = idx
        elif c in ("particulars", "description", "narration"):
            mapping["description"] = idx
        elif c in ("chq no.", "chq no", "cheque no", "cheque no.", "instrument no", "chq"):
            mapping["ref_no"] = idx
        elif c in ("debit", "withdrawal", "dr"):
            mapping["debit"] = idx
        elif c in ("credit", "deposit", "cr"):
            mapping["credit"] = idx
        elif c == "balance":
            mapping["balance"] = idx
    return mapping if "date" in mapping else {}


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str]) -> dict:
    """
    Extract account metadata from SVC Co-operative Bank statement.

    Page 1 layout:
        "Account No: 111304180000062 - JALNA Branch"
        "SHRI PUNAGRI TRADERS(CKYC-70094871528579)"
        "D 45 Ring Road, Market Yard. Jalna..."
        "MICR: 431089052  IFSC SVCB0000113"
        "Customer Id: 101459570"
        "From: 01-Apr-2025  To: 24-Nov-2025"
        "Opening Balance as on : 01-Apr-2025  Rs. 15,87,807.29 Cr"
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

    # Customer ID
    m = _CUSTID_RE.search(full_text)
    if m:
        info["customer_id"] = m.group(1)

    # Statement period
    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    # Opening balance
    m = _OPENBAL_RE.search(full_text)
    if m:
        info["opening_balance"] = _clean_amount_svc(m.group(1))

    # Line-by-line for account number, branch, holder name
    for line in lines:
        s = line.strip()
        if not s:
            continue

        # "Account No: 111304180000062 - JALNA Branch"
        if info["account_number"] is None:
            m = _ACCT_RE.search(s)
            if m:
                info["account_number"] = m.group(1)
                # Branch from same line: "111304180000062 - JALNA Branch"
                mb = _BRANCH_RE.search(s)
                if mb and info["branch"] is None:
                    info["branch"] = mb.group(1).strip()

        # Account holder: standalone ALL-CAPS / title-case line
        # "SHRI PUNAGRI TRADERS(CKYC-70094871528579)"
        if info["account_holder"] is None:
            # Strip CKYC suffix if present
            clean = re.sub(r"\(CKYC[-\s]?\d+\)", "", s).strip()
            if (
                clean
                and len(clean) > 3
                and not _ACCT_RE.search(s)
                and not _PERIOD_RE.search(s)
                and not _MICR_RE.search(s)
                and not _CUSTID_RE.search(s)
                and not _OPENBAL_RE.search(s)
                and not re.match(r"^\d", clean)           # doesn't start with digit
                and not re.match(r"^[A-Z]\s+\d", clean)  # not address-like
                and re.match(r"^[A-Z]", clean)            # starts with uppercase
                and "Branch" not in clean
                and "Floor" not in clean
                and "Road" not in clean
                and "Plot" not in clean
                and "Statement" not in clean
                and "Bank" not in clean
                and "Ground" not in clean
                and "Market" not in clean
            ):
                info["account_holder"] = clean

    return info


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from an SVC Co-operative Bank PDF statement.

    7-column table:
        Tran Date | Value Date | Particulars | Chq No. | Debit | Credit | Balance

    Date format  : 'DD-Mon-YYYY'  → normalised to DD-MM-YYYY
    Balance      : 'AMOUNT Cr'    → positive float (strip Cr suffix)
    Debit/Credit : Indian comma format; blank cell → None
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

                # SVC transaction table has 7 columns
                if len(table[0]) != 7:
                    continue

                for row in table:
                    if not row:
                        continue

                    # Skip header rows
                    row_text = " ".join((cell or "") for cell in row).lower()
                    if _HEADER_SKIP.search(row_text) and not _is_txn_date((row[0] or "").strip()):
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

                    # Continuation row — no date
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
                        "debit":       _clean_amount_svc(_get("debit")),
                        "credit":      _clean_amount_svc(_get("credit")),
                        "balance":     _clean_amount_svc(_get("balance")),
                    }
                    transactions.append(txn)
                    last_txn = txn

    # Sort chronologically oldest → newest
    transactions.sort(key=_sort_key)
    return transactions