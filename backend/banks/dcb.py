import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "dcb"
BANK_DISPLAY_NAME = "DCB Bank"


# =============================================================================
# DCB BANK — PDF FORMAT (Scanned / OCR)
# =============================================================================
#
# FORMAT: Single format (scanned statement, OCR extracted)
#   6-column table:
#     Date | Particulars | Cheque No | Debit | Credit | Balance
#
#   Account info block:
#     Account No      : XXXXXXXXXXXXXXXX
#     Account Name    : Customer Name
#     Branch          : Branch Name
#     IFSC Code       : DCBL0XXXXXX
#     MICR Code       : XXXXXXXXX
#     Statement Period: DD/MM/YYYY To DD/MM/YYYY
#     Account Type    : Savings / Current
#     Currency        : INR
#
#   Date format  : DD/MM/YYYY  or  DD-MM-YYYY  or  DD Mon YYYY (OCR noise)
#   Balance      : plain positive number  e.g. "1,23,456.78"
#   Debit/Credit : plain numbers in separate columns; empty = None
#
# QUIRKS (OCR-specific):
#   1. Digits may be misread: 0→O, 1→I/l, 5→S etc — amount cleaner handles this
#   2. Column separators are inconsistent — fallback to text line parsing
#   3. Date formats vary due to OCR noise — multiple format attempts
#   4. Account number may have spaces inserted by OCR
# =============================================================================


# ---------------------------------
# HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date":        ["date", "txn date", "transaction date", "value date"],
    "description": ["particulars", "narration", "description", "transaction details", "remarks"],
    "cheque":      ["cheque no", "cheque number", "chq no", "ref no", "instrument no", "chq/ref no"],
    "debit":       ["debit", "withdrawal", "dr", "debit amount", "withdrawal amt"],
    "credit":      ["credit", "deposit", "cr", "credit amount", "deposit amt"],
    "balance":     ["balance", "closing balance", "running balance", "available balance"],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
# Date: DD/MM/YYYY or DD-MM-YYYY or DD MM YYYY (OCR splits separator)
_DATE_RE     = re.compile(r"^\d{2}[\/\-\s]\d{2}[\/\-\s]\d{4}$")
_DATE_NORM   = re.compile(r"(\d{2})[\/\-\s](\d{2})[\/\-\s](\d{4})")

# Account info — flexible for OCR noise (spaces, colons, dots misread)
_ACCT_RE     = re.compile(r"account\s*(?:no|number|num)[\s:.\-]*([0-9\s]{9,20})", re.I)
_CUST_RE     = re.compile(r"(?:account\s*(?:name|holder)|customer\s*name|name)\s*[:\-.\s]+([A-Za-z][^\n:]{2,40}?)(?:\s{2,}|\t|$)", re.I)
_BRANCH_RE   = re.compile(r"branch\s*(?:name)?\s*[:\-.\s]+([^\n:]{2,40}?)(?:\s{2,}|\t|$)", re.I)
_IFSC_RE     = re.compile(r"ifsc\s*(?:code)?\s*[:\-.\s]*(DCBL[A-Z0-9]{7})", re.I)
_MICR_RE     = re.compile(r"micr\s*(?:code)?\s*[:\-.\s]*(\d{9})", re.I)
_ACC_TYPE_RE = re.compile(r"account\s*type\s*[:\-.\s]+([^\n:]{2,30}?)(?:\s{2,}|\t|$)", re.I)
_CURRENCY_RE = re.compile(r"currency\s*[:\-.\s]*([A-Z]{3})", re.I)
_PERIOD_RE   = re.compile(
    r"(?:statement\s*period|period)\s*[:\-.\s]*"
    r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})\s*(?:to|To|TO)\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
    re.I,
)

# Known next-label lookahead — stops capture bleeding into adjacent field
_NEXT_LABEL_PAT = (
    r"(?=\s+(?:ACCOUNT\s+(?:NO|NAME|TYPE|NUMBER|HOLDER)|"
    r"BRANCH|IFSC|MICR|CURRENCY|STATEMENT|PERIOD|CUSTOMER|ADDRESS|PHONE|EMAIL)\b)"
)
_CUST_RE_SAFE     = re.compile(r"(?:account\s*(?:name|holder)|customer\s*name|name)\s*[:\-.\s]+(.+?)(?:" + _NEXT_LABEL_PAT + r"|\s*$)", re.I)
_BRANCH_RE_SAFE   = re.compile(r"branch\s*(?:name)?\s*[:\-.\s]+(.+?)(?:" + _NEXT_LABEL_PAT + r"|\s*$)", re.I)
_ACC_TYPE_RE_SAFE = re.compile(r"account\s*type\s*[:\-.\s]+(.+?)(?:" + _NEXT_LABEL_PAT + r"|\s*$)", re.I)

_FIELD_LABELS = re.compile(
    r"\b(account\s*(?:no|number|name|holder|type|branch)|branch(?:\s*name)?|"
    r"ifsc(?:\s*code)?|micr(?:\s*code)?|currency|statement\s*period|"
    r"customer\s*name|address|phone|email|period)\b",
    re.I,
)


# ---------------------------------
# DATE HELPERS
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """
    Normalize OCR date to DD-MM-YYYY.
    Handles: DD/MM/YYYY, DD-MM-YYYY, DD MM YYYY
    """
    if not date_str:
        return date_str
    s = date_str.strip()
    m = _DATE_NORM.match(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Try named month formats too (OCR sometimes gives "01 Dec 2024")
    for fmt, out in [
        ("%d/%m/%Y", "%d-%m-%Y"),
        ("%d-%m-%Y", "%d-%m-%Y"),
        ("%d %m %Y", "%d-%m-%Y"),
        ("%d %b %Y", "%d-%m-%Y"),
        ("%d-%b-%Y", "%d-%m-%Y"),
    ]:
        try:
            return datetime.strptime(s, fmt).strftime(out)
        except ValueError:
            continue
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
# OCR may misread digits: O→0, l/I→1, S→5, B→8
_OCR_DIGIT_FIX = str.maketrans("OoIlSsBb", "00115588")

def _clean_amount_dcb(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "", "None", "null"):
        return None
    # Fix common OCR digit misreads
    s = s.translate(_OCR_DIGIT_FIX)
    s = re.sub(r"^(Rs\.?|INR|₹)\s*", "", s, flags=re.I)
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------
# CAPTURED VALUE SANITIZER
# ---------------------------------
def _clean_captured(value: str) -> str | None:
    if not value:
        return None
    m = _FIELD_LABELS.search(value)
    if m:
        value = value[:m.start()]
    value = re.sub(r"\s+", " ", value).strip(" :.-")
    return value if len(value) > 1 else None


def _clean_account_number(raw: str) -> str | None:
    """Strip OCR-inserted spaces from account number."""
    if not raw:
        return None
    cleaned = re.sub(r"\s+", "", raw).strip()
    return cleaned if len(cleaned) >= 9 else None


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
    required = {"date", "balance", "description"}
    if not required.issubset(mapping):
        return None
    if "debit" not in mapping and "credit" not in mapping:
        return None
    return mapping


def _is_header_row(row_clean: list[str]) -> bool:
    joined = " ".join(row_clean)
    return (
        ("date" in joined)
        and ("balance" in joined)
        and ("debit" in joined or "withdrawal" in joined or "credit" in joined or "deposit" in joined)
    )


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = _clean_account_number(m.group(1))

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

    for line in lines:
        s = line.strip()
        if not s:
            continue

        if info["account_holder"] is None:
            m = _CUST_RE_SAFE.search(s)
            if m:
                candidate = _clean_captured(m.group(1).strip())
                if candidate:
                    info["account_holder"] = candidate

        if info["branch"] is None:
            m = _BRANCH_RE_SAFE.search(s)
            if m:
                candidate = _clean_captured(m.group(1).strip())
                if candidate:
                    info["branch"] = candidate

        if info["acc_type"] is None:
            m = _ACC_TYPE_RE_SAFE.search(s)
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
                    if not row or len(row) < 4:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

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
    desc_raw    = row[col.get("description", 1)] or ""
    description = re.sub(r"\s+", " ", desc_raw.replace("\n", " ")).strip() or None
    cheque_no   = (row[col.get("cheque", 2)] or "").strip() or None
    debit       = _clean_amount_dcb(row[col.get("debit",   3)]) if "debit"   in col else None
    credit      = _clean_amount_dcb(row[col.get("credit",  4)]) if "credit"  in col else None
    balance     = _clean_amount_dcb(row[col.get("balance", 5)]) if "balance" in col else None

    return {
        "date":        _reformat_date(date_raw),
        "description": description,
        "ref_no":      cheque_no,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }