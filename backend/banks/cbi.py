import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "cbi"
BANK_DISPLAY_NAME = "Central Bank of India"


# =============================================================================
# CENTRAL BANK OF INDIA — PDF CHARACTERISTICS
# =============================================================================
# - Text-based PDF; pdfplumber lines-strategy table extraction works cleanly.
# - 8-column ruled table (one per page, all pages):
#     Post Date | Value Date | Branch Code | Cheque Number |
#     Account Description | Debit | Credit | Balance
# - Date format : DD/MM/YYYY  →  output as DD-MM-YYYY
# - Empty amount cells : '' (empty string)
# - Balance format     : '100.00 CR' or '294730.85 CR'  (always CR in this format;
#   DR suffix possible for overdraft accounts — handled generically)
# - Description        : multi-line within cell, joined with space
# - Cheque Number col  : usually empty; populated for cheque transactions
# - Branch Code col    : 5-digit branch code (not needed for output)
# - Account info       : page 1 header text (no separate info table)
#     Line 0  = "Central Bank of India"
#     Line 1  = branch name
#     Line 2  = branch address
#     Line 3  = "Branch Code :XXXXX"
#     Line 4  = "IFSC Code :CBINXXXXXXX"
#     Line 5  = "Account Number : XXXXXXXXXX"
#     Line 6  = "Product type : ..."
#     Line 7  = account holder name
#     Line 10 = "Statement Date :..."
#     Last    = "STATEMENT OF ACCOUNT from DD/MM/YYYY to DD/MM/YYYY"
# =============================================================================


# ---------------------------------
# HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date":        ["post date", "postdate", "date"],
    "value_date":  ["value date", "valuedate"],
    "branch_code": ["branch code", "branchcode"],
    "cheque":      ["cheque number", "cheque no", "chequeno"],
    "description": ["account description", "description", "narration", "particulars"],
    "debit":       ["debit", "withdrawal", "dr"],
    "credit":      ["credit", "deposit", "cr"],
    "balance":     ["balance", "running balance"],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_DATE_RE    = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_IFSC_RE    = re.compile(r"ifsc\s*code\s*[:\-]?\s*(CBIN[A-Z0-9]{7})", re.I)
_ACCT_RE    = re.compile(r"account\s*number\s*[:\-]?\s*(\d{9,})", re.I)
_BRANCH_RE  = re.compile(r"branch\s*code\s*[:\-]?\s*(\d+)", re.I)
_PROD_RE    = re.compile(r"product\s*type\s*[:\-]?\s*(.+)", re.I)
_PERIOD_RE  = re.compile(
    r"statement\s+of\s+account\s+from\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})",
    re.I,
)
_EMAIL_RE   = re.compile(r"email\s*[:\-]?\s*(\S+@\S+)", re.I)


# ---------------------------------
# DATE HELPERS
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert 'DD/MM/YYYY' → 'DD-MM-YYYY'."""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


def _is_txn_date(value: str) -> bool:
    return bool(_DATE_RE.match((value or "").strip()))


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_cbi(value) -> float | None:
    """
    Handles:
      - '20000.00'           plain debit/credit cell
      - '100.00 CR'          balance cell with CR suffix
      - '294730.85 CR'       balance with Indian comma format (commas stripped)
      - ''                   empty → None
    Returns float (always positive; sign logic handled by caller).
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    # Strip CR / DR suffix
    value = re.sub(r"\s*(CR|DR)\s*$", "", value, flags=re.I).strip()
    # Strip currency prefix
    value = re.sub(r"^(Rs\.?|INR|₹)\s*", "", value, flags=re.I).strip()
    value = value.replace(",", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _clean_balance_cbi(value) -> float | None:
    """
    Balance cell: '100.00 CR', '294730.85 CR', '930.85 CR'
    Returns signed float: positive for CR, negative for DR.
    """
    if not value:
        return None
    s = str(value).strip()
    is_dr = s.upper().endswith("DR")
    amount = _clean_amount_cbi(s)
    if amount is None:
        return None
    return -amount if is_dr else amount


# ---------------------------------
# COLUMN DETECTOR
# ---------------------------------
def _detect_columns(row_clean: list[str]) -> dict | None:
    """
    Map column indices from the 8-column header row.
    Pass 1: exact match. Pass 2: guarded substring (4+ chars).
    Returns mapping dict if ≥ 4 fields found, else None.
    """
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
    return mapping if len(mapping) >= 4 else None


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    """
    Extract account metadata from Central Bank of India statement page 1.

    Header layout (raw text lines):
        Central Bank of India
        JOGIA_JOGIA                         ← branch name
        VILLAGE JOGIA , P.O.GHUGHALI ...    ← branch address
        Branch Code :00206
        IFSC Code :CBIN0280206
        Account Number : 5715676469
        Product type : CD-GEN-PUB-IND-RURAL-INR
        MS HAMARA PUMP MITHAURA BAZAR       ← account holder
        273151                              ← PIN code
        Email : smt.durgadevi1@gmail.com
        Statement Date :Sat Apr 05 ...
        Cleared Balance :
        Drawing Power :0.00
        STATEMENT OF ACCOUNT from 01/04/2024 to 31/03/2025
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # ── IFSC
    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    # ── Account number
    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1)

    # ── Branch code
    m = _BRANCH_RE.search(full_text)
    if m:
        info["branch"] = m.group(1)

    # ── Product / account type
    m = _PROD_RE.search(full_text)
    if m:
        info["acc_type"] = m.group(1).strip()

    # ── Statement period
    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    # ── Account holder: first ALL-CAPS line after "Product type"
    found_product = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.search(r"product\s*type", s, re.I):
            found_product = True
            continue
        if found_product:
            # Account holder is the next non-empty line after product type
            if re.match(r"^[A-Z0-9][A-Z0-9\s\.\&\-]+$", s) and len(s) > 3:
                info["account_holder"] = s
                break

    # ── Branch name: line immediately after "Central Bank of India"
    for i, line in enumerate(lines):
        if "central bank of india" in line.lower():
            if i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if candidate and not re.search(r"branch|ifsc|account|product", candidate, re.I):
                    info["branch"] = candidate
            break

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Dispatcher-compatible wrapper."""
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from a Central Bank of India PDF statement.

    Strategy:
    - pdfplumber lines-strategy table extractor works reliably for this PDF.
    - Each page has exactly one 8-column table.
    - Page 1 includes the header row; subsequent pages repeat the header
      so _detect_columns() resets column_mapping on each header hit.
    - Date format: DD/MM/YYYY → output as DD-MM-YYYY.
    - Description (Account Description): multi-line, joined with space.
    - Cheque Number: populated only for cheque transactions, else empty.
    - Balance: 'AMOUNT CR' or 'AMOUNT DR' — positive for CR, negative for DR.
    - Empty debit/credit cell → None.
    """
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
                if not table or len(table[0]) != 8:
                    continue  # Only process the 8-column transaction table

                for row in table:
                    if not row or len(row) < 8:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    # Detect / re-detect header row on each page
                    detected = _detect_columns(row_clean)
                    if detected:
                        column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    # ── Date ──────────────────────────────────────────────
                    date_raw  = (row[column_mapping.get("date", 0)] or "").strip()
                    if not _is_txn_date(date_raw):
                        continue

                    # ── Description ───────────────────────────────────────
                    desc_raw    = row[column_mapping.get("description", 4)] or ""
                    description = re.sub(
                        r"\s+", " ", desc_raw.replace("\n", " ")
                    ).strip() or None

                    # ── Cheque number ─────────────────────────────────────
                    cheque_no = (row[column_mapping.get("cheque", 3)] or "").strip() or None

                    # ── Amounts ───────────────────────────────────────────
                    debit   = _clean_amount_cbi(row[column_mapping.get("debit",   5)])
                    credit  = _clean_amount_cbi(row[column_mapping.get("credit",  6)])
                    balance = _clean_balance_cbi(row[column_mapping.get("balance", 7)])

                    transactions.append({
                        "date":        _reformat_date(date_raw),   # DD-MM-YYYY
                        "description": description,
                        "ref_no":      cheque_no,
                        "debit":       debit,
                        "credit":      credit,
                        "balance":     balance,
                    })

    return transactions