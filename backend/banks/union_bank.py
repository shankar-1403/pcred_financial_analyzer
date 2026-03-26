import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "union_bank"
BANK_DISPLAY_NAME = "Union Bank of India"


# =============================================================================
# UNION BANK PDF CHARACTERISTICS
# =============================================================================
# - Text-based PDF; pdfplumber table extraction works reliably.
# - 8-column ruled table:
#     Date | Remarks | Tran Id-1 | UTR Number | Instr. ID |
#     Withdrawals | Deposits | Balance
# - Date cell:  'DD-MM-YYYY\nHH:MM:SS'  →  keep only the date part.
# - Empty amount cells: '' (empty string), NOT '-'.
# - UTR Number column always contains '-' (literal dash, not an amount).
# - Instr. ID   = cheque / instrument number (may be empty).
# - Tran Id-1   = internal bank transaction reference (S-prefixed).
# - Remarks     = multi-line description joined with space.
# - No opening/closing balance row in the table; they are not printed.
# - Statement period: "Statement Period From -01/04/2024 To 31/03/2025"
# =============================================================================


# ---------------------------------
# HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date":        ["date"],
    "description": ["remarks", "description", "narration", "particulars"],
    "tran_id":     ["tran id-1", "tran id", "transaction id"],
    "utr":         ["utr number", "utr no", "utr"],
    "instr_id":    ["instr. id", "instr id", "instrument id", "cheque no"],
    "debit":       ["withdrawals", "withdrawal", "debit", "dr"],
    "credit":      ["deposits", "deposit", "credit", "cr"],
    "balance":     ["balance", "running balance"],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_IFSC_RE    = re.compile(r"\b(UBIN[A-Z0-9]{7})\b")
_DATE_RE    = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_PERIOD_RE  = re.compile(
    r"statement\s+period\s+from\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})",
    re.I,
)
_ACCT_RE    = re.compile(r"account\s+no\s+(\d{10,})", re.I)
_CUSTID_RE  = re.compile(r"customer\s+id\s+(\d+)", re.I)
_MICR_RE    = re.compile(r"micr\s+code\s+(\d{9})", re.I)
_ACCT_TYPE_RE = re.compile(r"account\s+type\s+(.+)", re.I)
_BRANCH_RE  = re.compile(r"branch\s+(.+)", re.I)
_CURRENCY_RE = re.compile(r"account\s+currency\s+([A-Z]{3})", re.I)


# ---------------------------------
# DATE HELPERS
# ---------------------------------
def _clean_date(cell: str) -> str:
    """'02-04-2024\n19:27:37' → '02-04-2024'"""
    return (cell or "").split("\n")[0].strip()


def _is_txn_date(value: str) -> bool:
    return bool(_DATE_RE.match(value))


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_ub(value) -> float | None:
    """
    Standard Indian comma format: '23,77,726.73', '1,941.00'
    Empty string or '-' → None.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    value = value.replace(",", "").replace(" ", "")
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------
# COLUMN DETECTOR
# ---------------------------------
def _detect_columns(row_clean: list[str]) -> dict | None:
    """
    Map column index from the 8-column header row.
    Uses exact match first, then guarded substring (4+ chars).
    Returns mapping dict if at least 4 fields found, else None.
    """
    mapping = {}
    for field, variants in HEADER_MAP.items():
        # Pass 1: exact
        for idx, cell in enumerate(row_clean):
            if cell in variants:
                mapping[field] = idx
                break
        if field in mapping:
            continue
        # Pass 2: substring (4+ chars only)
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
    Extract account metadata from Union Bank statement page 1.

    Page 1 layout (raw text):
        Statement of Account
        ELECTROVIBE SOLUTIONS LLP          ← account holder (line 1)
        Union Bank of India
        C/O ELECTROVIBE SOLUTIONS LLP
        Branch  GHOD BUNDER ROAD THANE     ← branch
        ...
        Customer Id  900724523
        Account No   549701010050942
        Account Currency  INR
        Account Type  Current Account
        MICR Code  400026116
        IFSC Code  UBIN0554979
        Statement Period From -01/04/2024 To 31/03/2025
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # ── Account holder: first ALL-CAPS non-empty line after "Statement of Account"
    found_header = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if "statement of account" in s.lower():
            found_header = True
            continue
        if found_header and re.match(r"^[A-Z][A-Z\s\.\&]+$", s) and len(s) > 3:
            info["account_holder"] = s
            break

    # ── Regex extractions from full text
    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1)

    m = _CUSTID_RE.search(full_text)
    if m:
        info["customer_id"] = m.group(1)

    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1)

    m = _MICR_RE.search(full_text)
    if m:
        info["micr"] = m.group(1)

    m = _CURRENCY_RE.search(full_text)
    if m:
        info["currency"] = m.group(1).upper()

    # ── Account type (take only the first word to avoid address bleed-in)
    m = _ACCT_TYPE_RE.search(full_text)
    if m:
        info["acc_type"] = m.group(1).strip().split("\n")[0].strip()

    # ── Branch
    m = _BRANCH_RE.search(full_text)
    if m:
        candidate = m.group(1).strip().split("\n")[0].strip()
        if candidate and len(candidate) > 2:
            info["branch"] = candidate

    # ── Statement period: "Statement Period From -01/04/2024 To 31/03/2025"
    # The raw text has a stray '-' before the from-date; normalise it.
    m = re.search(
        r"statement\s+period\s+from\s*-?\s*(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})",
        full_text, re.I,
    )
    if m:
        # Convert DD/MM/YYYY → DD-MM-YYYY for consistency
        def _slash_to_dash(s):
            try:
                return datetime.strptime(s, "%d/%m/%Y").strftime("%d-%m-%Y")
            except ValueError:
                return s
        info["statement_period"]["from"] = _slash_to_dash(m.group(1))
        info["statement_period"]["to"]   = _slash_to_dash(m.group(2))

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Dispatcher-compatible wrapper."""
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from a Union Bank of India PDF statement.

    Strategy:
    - pdfplumber's lines-strategy table extractor works reliably for this PDF.
    - Each page has exactly one 8-column table.
    - Page 1's table includes a header row; subsequent pages continue data only
      (no repeated header), so we re-use the column mapping across pages.
    - Date cell format: 'DD-MM-YYYY\nHH:MM:SS' — strip the time part.
    - Description (Remarks): multi-line, joined with space.
    - Instr. ID is used as the cheque/instrument reference (ref_no).
    - Tran Id-1 is the bank's internal transaction reference.
    - UTR Number column always contains '-' and is ignored.
    - Empty deposit/withdrawal cell → None (not 0).
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

                    # Detect / re-detect header row
                    detected = _detect_columns(row_clean)
                    if detected:
                        column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    # ── Date ──────────────────────────────────────────────
                    raw_date  = row[column_mapping.get("date", 0)] or ""
                    date_cell = _clean_date(raw_date)
                    if not _is_txn_date(date_cell):
                        continue

                    # ── Description (Remarks) ─────────────────────────────
                    desc_raw    = row[column_mapping.get("description", 1)] or ""
                    description = re.sub(r"\s+", " ", desc_raw.replace("\n", " ")).strip()

                    # ── References ────────────────────────────────────────
                    tran_id = (row[column_mapping.get("tran_id", 2)] or "").strip() or None
                    # UTR col (index 3) is always '-', skip it
                    instr_id = (row[column_mapping.get("instr_id", 4)] or "").strip() or None

                    # ── Amounts ───────────────────────────────────────────
                    debit   = _clean_amount_ub(row[column_mapping.get("debit",   5)])
                    credit  = _clean_amount_ub(row[column_mapping.get("credit",  6)])
                    balance = _clean_amount_ub(row[column_mapping.get("balance", 7)])

                    transactions.append({
                        "date":        date_cell,        # DD-MM-YYYY
                        "description": description,
                        "tran_id":     tran_id,          # e.g. 'S92303690'
                        "ref_no":      instr_id,         # cheque / instrument ID
                        "debit":       debit,
                        "credit":      credit,
                        "balance":     balance,
                    })

    return transactions