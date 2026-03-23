import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
    detect_columns,
)

BANK_KEY          = "bandhan"
BANK_DISPLAY_NAME = "Bandhan Bank"


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
IFSC_PATTERN   = r"\b(BDBL[A-Z0-9]{7})\b"
PERIOD_PATTERN = r"[Ss]tatement\s+period\s+[Ff]rom\s+(.+?)\s+to\s+(.+)"

# Date format used in Bandhan transaction rows: "April28, 2025" or "April28,2025"
# Normalized to DD/MM/YYYY on output
_TXN_DATE_RE = re.compile(
    r"^([A-Za-z]+)\s*(\d{1,2}),\s*(\d{4})$"
)

# Amount cells: "INR2,370.00" optionally followed by "\n<hash_overflow>"
# Strip leading INR, take only the first line
_INR_PREFIX_RE = re.compile(r"^INR", re.I)

# Summary / footer rows to skip
_SKIP_ROW_RE = re.compile(
    r"statement\s+summary|opening\s+balance|total\s+credits|"
    r"total\s+debits|closing\s+balance|statement\s+generated|"
    r"end\s+of\s+statement|transaction\s+date",
    re.I,
)

# Month name → number map
_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_bandhan(value):
    """
    Handles Bandhan amount format: 'INR2,370.00', 'INR1,50,000.00'
    Amount cell may have hash overflow after a newline — take only first line.
    Returns float or None.
    """
    if value is None:
        return None
    # Take only first line (second line is UPI hash overflow)
    value = str(value).split("\n")[0].strip()
    # Strip leading INR prefix
    value = _INR_PREFIX_RE.sub("", value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    value = value.replace(",", "").replace(" ", "")
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------
# DATE NORMALISER
# ---------------------------------
def _parse_txn_date(raw):
    """
    Convert Bandhan date format 'April28, 2025' → 'DD/MM/YYYY'.
    Returns None if not parseable.
    """
    if not raw:
        return None
    raw = raw.strip()
    m = _TXN_DATE_RE.match(raw)
    if not m:
        return None
    month_str = m.group(1).lower()
    day       = m.group(2).zfill(2)
    year      = m.group(3)
    month_num = _MONTH_MAP.get(month_str)
    if not month_num:
        return None
    return f"{day}/{month_num}/{year}"


# ---------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines):
    """
    Extract account metadata from Bandhan Bank statement.

    Bandhan page 1 text layout:

        'Current and Savings Account Statement'
        'ABHISHEK ANIL KOTHARI'          ← account holder name
        'HOUSE NO 412530 ...'            ← address lines
        ...
        'Account Statement as on May30, 2025'
        'Customer Account Details'
        'Account Number 10220012711474'
        'Account Type Current Account'
        'Branch Details Vaijapur, 1207, ...'
        'Customer ID / CIF 311177305'
        'IFSC BDBL0001207'
        'MICR Code 431750505'
        'Nomination Registered YES'
        'Joint Holder Names ABHISHEK ENTERPRISES'
        'Statement period From 01 May 2024 to 30 Apr 2025'

    All fields are label + value on the same line (pdfplumber table gives
    clean 2-col key/value pairs from the Customer Account Details table).
    We use raw text lines as fallback for fields not in the table.
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # IFSC
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    # Statement period: "From 01 May 2024 to 30 Apr 2025"
    m = re.search(PERIOD_PATTERN, full_text, re.I)
    if m:
        info["statement_period"]["from"] = m.group(1).strip()
        info["statement_period"]["to"]   = m.group(2).strip()

    # Parse first 25 lines — all metadata lives there
    for line in lines[:25]:
        line_s = (line or "").strip()
        if not line_s:
            continue

        # Account number
        if info["account_number"] is None:
            m = re.search(r"account\s*number\s+(\d{10,})", line_s, re.I)
            if m:
                info["account_number"] = m.group(1)

        # Account type
        if info["acc_type"] is None:
            m = re.search(r"account\s*type\s+(.+)", line_s, re.I)
            if m:
                info["acc_type"] = m.group(1).strip()

        # Customer ID / CIF
        if info["customer_id"] is None:
            m = re.search(r"customer\s*id\s*/\s*cif\s+(\d+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)

        # MICR
        if info["micr"] is None:
            m = re.search(r"micr\s*code\s+(\d{9})", line_s, re.I)
            if m:
                info["micr"] = m.group(1)

        # Joint holder
        if info["joint_holder"] is None:
            m = re.search(r"joint\s*holder\s*names?\s+(.+)", line_s, re.I)
            if m:
                info["joint_holder"] = m.group(1).strip()

        # Branch
        if info["branch"] is None:
            m = re.search(r"branch\s*details\s+(.+)", line_s, re.I)
            if m:
                info["branch"] = m.group(1).strip()

        # Statement request date: "Account Statement as on May30, 2025"
        if info["statement_request_date"] is None:
            m = re.search(r"account\s*statement\s*as\s*on\s+(.+)", line_s, re.I)
            if m:
                info["statement_request_date"] = m.group(1).strip()

    # Account holder name: first all-caps / title-case line after line 0
    # (line 0 is "Current and Savings Account Statement", line 1 is holder name)
    _LABEL_RE = re.compile(
        r"current\s+and\s+savings|account\s+(number|type|statement|details)|"
        r"customer|branch|ifsc|micr|nomination|joint|statement\s+period",
        re.I,
    )
    for line in lines[1:10]:
        line_s = (line or "").strip()
        if not line_s or _LABEL_RE.search(line_s):
            continue
        if line_s[0].isdigit():
            continue
        # Must look like a name: letters, spaces, dots
        if re.match(r"^[A-Za-z][A-Za-z\s\.]{3,}$", line_s):
            info["account_holder"] = line_s
            break

    return info


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    """
    Extract all transactions from a Bandhan Bank PDF statement.

    BANDHAN PDF CHARACTERISTICS:
    ============================
    - Text-based PDF; pdfplumber line strategy gives clean 6-column tables
    - Page 1 has 3 tables: address block, Customer Account Details (2-col),
      and Transactions (6-col) — identified by 6 columns
    - Pages 2-5 have 1 transaction table each
    - Pages 6-7 are insurance info — no transactions
    - 6 columns per row:
        [Transaction Date | Value Date | Description | Amount | Dr/Cr | Balance]
    - Amount format: "INR2,370.00" with optional hash overflow on second line
      after newline — take only first line and strip INR prefix
    - Balance format: "INR35,461.64" — strip INR prefix
    - Dr/Cr column: "Dr" = debit, "Cr" = credit
    - Date format: "April28, 2025" — convert to DD/MM/YYYY
    - Description wraps across lines (pdfplumber joins with \\n in cell)
    - Last page has Statement Summary table below transactions — skip it
    """
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )

            if not tables:
                continue

            for table in tables:

                if not table or len(table[0]) != 6:
                    continue  # only process 6-column transaction tables

                for row in table:

                    if not row or len(row) < 6:
                        continue

                    # Skip header and summary rows
                    row_text = " ".join((cell or "") for cell in row)
                    if _SKIP_ROW_RE.search(row_text):
                        continue

                    txn = _build_txn(row)
                    if txn:
                        transactions.append(txn)

    # Bandhan statements are printed newest-first — reverse to chronological order
    transactions.reverse()

    return transactions


# ---------------------------------
# HELPERS
# ---------------------------------
def _build_txn(row):
    """
    Build one transaction dict from a Bandhan table row.
    Columns: [Transaction Date, Value Date, Description, Amount, Dr/Cr, Balance]
    Returns None if row has no valid date.
    """
    def _cell(idx):
        if idx >= len(row):
            return None
        return (row[idx] or "").strip() or None

    date_raw = _cell(0)
    date_norm = _parse_txn_date(date_raw)
    if not date_norm:
        return None

    value_date_raw  = _cell(1)
    value_date_norm = _parse_txn_date(value_date_raw)

    # Description — join multiline, clean whitespace
    desc = _cell(2)
    if desc:
        desc = re.sub(r"\s+", " ", desc.replace("\n", " ")).strip()

    amount_raw = _cell(3)
    amount     = _clean_amount_bandhan(amount_raw)

    dr_cr = (_cell(4) or "").strip().upper()   # "Dr" or "Cr"

    balance_raw = _cell(5)
    balance     = _clean_amount_bandhan(balance_raw)

    # Split amount into debit / credit using Dr/Cr indicator
    debit  = amount if dr_cr == "DR" else None
    credit = amount if dr_cr == "CR" else None

    return {
        "date":        date_norm,
        "value_date":  value_date_norm,
        "description": desc,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }