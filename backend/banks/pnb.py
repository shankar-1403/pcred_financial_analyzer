import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "pnb"
BANK_DISPLAY_NAME = "Punjab National Bank"


# =============================================================================
# PUNJAB NATIONAL BANK — TWO PDF FORMATS
# =============================================================================
#
# FORMAT A  (internet banking download)
#   6-column ruled table:
#     Transaction Date | Cheque Number | Withdrawal | Deposit | Balance | Narration
#   Balance suffix : '4,761.79 Cr.'  or  '500.00 Dr.'
#   Account info   : "Account Statement For Account:XXXXXXXXXXXXXXXX"
#   Period         : "Statement Period : DD/MM/YYYY to DD/MM/YYYY"
#
# FORMAT B  (branch / passbook style)
#   6-column ruled table:
#     Date | Instrument ID | Amount | Type | Balance | Remarks
#   Type column    : 'DR' or 'CR'
#   Balance        : plain number, no suffix  e.g. '75,818.65'
#   Account info   : "Statement of Account:XXXXXXXXXXXXXXXX For Period: ..."
#
# Detection: header row contains 'withdrawal'/'deposit' → Format A
#            header row contains 'amount' + 'type'      → Format B
# =============================================================================


# ---------------------------------
# HEADER MAPS
# ---------------------------------
HEADER_MAP_A = {
    "date":        ["transaction date", "txn date", "date"],
    "cheque":      ["cheque number", "cheque no", "chq no", "instrument no"],
    "debit":       ["withdrawal", "debit", "dr", "withdrawal amt"],
    "credit":      ["deposit", "credit", "cr", "deposit amt"],
    "balance":     ["balance", "running balance", "closing balance"],
    "description": ["narration", "description", "particulars", "remarks"],
}

HEADER_MAP_B = {
    "date":        ["date", "transaction date", "txn date"],
    "instrument":  ["instrument id", "instrument", "instr id", "instr. id"],
    "amount":      ["amount", "amt"],
    "type":        ["type", "dr/cr", "txn type"],
    "balance":     ["balance", "running balance"],
    "description": ["remarks", "narration", "description", "particulars"],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_DATE_RE     = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_IFSC_RE     = re.compile(r"ifsc\s*code\s*[:\-]?\s*(PUNB[A-Z0-9]{7})", re.I)
_MICR_RE     = re.compile(r"micr\s*(?:code)?\s*[:\-]?\s*(\d{9})", re.I)
_ACCT_A_RE   = re.compile(r"account\s*statement\s+for\s+account\s*[:\-]?\s*(\d{10,})", re.I)
_ACCT_B_RE   = re.compile(r"statement\s+of\s+account\s*[:\-]?\s*(\d{10,})", re.I)
_PERIOD_A_RE = re.compile(
    r"statement\s+period\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})", re.I
)
_PERIOD_B_RE = re.compile(
    r"for\s+period\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})", re.I
)
_BRANCH_RE   = re.compile(r"branch\s*name\s*[:\-]?\s*(.+)", re.I)
_CUST_RE     = re.compile(r"customer\s*name\s*[:\-]?\s*(.+)", re.I)


# ---------------------------------
# DATE HELPERS
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert 'DD/MM/YYYY' to 'DD-MM-YYYY'."""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


def _is_txn_date(value: str) -> bool:
    return bool(_DATE_RE.match((value or "").strip()))


def _sort_key(txn: dict):
    """Parse DD-MM-YYYY for chronological sort. Unparseable dates sort last."""
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


# ---------------------------------
# AMOUNT CLEANERS
# ---------------------------------
def _clean_amount_pnb(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "", "None", "null"):
        return None
    s = re.sub(r"\s*(Cr\.|Dr\.)\s*$", "", s, flags=re.I).strip()
    s = re.sub(r"^(Rs\.?|INR|₹)\s*", "", s, flags=re.I).strip()
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean_balance_a(value) -> float | None:
    """Format A: '4,761.79 Cr.' → +4761.79 | '500.00 Dr.' → -500.00"""
    if not value:
        return None
    s = str(value).strip()
    is_dr = bool(re.search(r"\bDr\.\s*$", s, re.I))
    amount = _clean_amount_pnb(s)
    if amount is None:
        return None
    return -amount if is_dr else amount


def _clean_balance_b(value) -> float | None:
    """Format B: plain positive number '75,818.65'"""
    return _clean_amount_pnb(value)


# ---------------------------------
# COLUMN DETECTORS
# ---------------------------------
def _detect_columns(row_clean: list[str], header_map: dict) -> dict | None:
    mapping = {}
    for field, variants in header_map.items():
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
    return mapping if len(mapping) >= 4 else None


def _identify_format(row_clean: list[str]) -> str | None:
    joined = " ".join(row_clean)
    if "withdrawal" in joined or "deposit" in joined:
        return "A"
    if "amount" in joined and "type" in joined:
        return "B"
    return None


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    m = _ACCT_A_RE.search(full_text) or _ACCT_B_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1)

    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    m = _MICR_RE.search(full_text)
    if m:
        info["micr"] = m.group(1)

    m = _PERIOD_A_RE.search(full_text) or _PERIOD_B_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if info["branch"] is None:
            m = _BRANCH_RE.search(s)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate) > 1:
                    info["branch"] = candidate
        if info["account_holder"] is None:
            m = _CUST_RE.search(s)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate) > 1:
                    info["account_holder"] = candidate

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
    fmt:            str  | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )
            if not tables:
                continue

            for table in tables:
                if not table or len(table[0]) != 6:
                    continue

                for row in table:
                    if not row or len(row) < 6:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    detected_fmt = _identify_format(row_clean)
                    if detected_fmt == "A":
                        col = _detect_columns(row_clean, HEADER_MAP_A)
                        if col:
                            column_mapping, fmt = col, "A"
                            continue
                    elif detected_fmt == "B":
                        col = _detect_columns(row_clean, HEADER_MAP_B)
                        if col:
                            column_mapping, fmt = col, "B"
                            continue

                    if column_mapping is None or fmt is None:
                        continue

                    date_raw = (row[column_mapping.get("date", 0)] or "").strip()
                    if not _is_txn_date(date_raw):
                        continue

                    txn = (
                        _build_txn_a(row, column_mapping, date_raw)
                        if fmt == "A"
                        else _build_txn_b(row, column_mapping, date_raw)
                    )
                    if txn:
                        transactions.append(txn)

    # Sort chronologically (oldest → newest) regardless of PDF order
    transactions.sort(key=_sort_key)

    return transactions


# ---------------------------------
# ROW BUILDERS
# ---------------------------------
def _build_txn_a(row, col, date_raw) -> dict:
    desc_raw    = row[col.get("description", 5)] or ""
    description = re.sub(r"\s+", " ", desc_raw.replace("\n", " ")).strip() or None
    cheque_no   = (row[col.get("cheque",   1)] or "").strip() or None
    debit       = _clean_amount_pnb(row[col.get("debit",   2)])
    credit      = _clean_amount_pnb(row[col.get("credit",  3)])
    balance     = _clean_balance_a( row[col.get("balance", 4)])
    return {
        "date":        _reformat_date(date_raw),
        "description": description,
        "ref_no":      cheque_no,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }


def _build_txn_b(row, col, date_raw) -> dict:
    desc_raw    = row[col.get("description", 5)] or ""
    description = re.sub(r"\s+", " ", desc_raw.replace("\n", " ")).strip() or None
    instr_id    = (row[col.get("instrument", 1)] or "").strip() or None
    amount      = _clean_amount_pnb(row[col.get("amount", 2)])
    txn_type    = (row[col.get("type",   3)] or "").strip().upper()
    balance     = _clean_balance_b( row[col.get("balance", 4)])
    debit       = amount if txn_type == "DR" else None
    credit      = amount if txn_type == "CR" else None
    return {
        "date":        _reformat_date(date_raw),
        "description": description,
        "ref_no":      instr_id,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }