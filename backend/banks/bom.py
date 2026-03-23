import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns,
)

BANK_KEY          = "bom"
BANK_DISPLAY_NAME = "Bank of Maharashtra"


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
IFSC_PATTERN   = r"\b(MAHB[A-Z0-9]{7})\b"
PERIOD_PATTERN = r"Statement for Account No\s+\d+\s+from\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})"

# Date format used in BOM transaction rows: DD/MM/YYYY
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# Summary / footer table rows — skip entirely
# Page 1 has 4 tables: [0]=Account Details, [1]=Customer Details,
# [2]=Home Branch Details, [3]=Transactions
# Last page has multiple summary tables after transactions end.
# We identify transaction tables by checking if first data row has a serial number.
_SKIP_PARTICULARS_RE = re.compile(
    r"no\s+accounts\s+available|total\s*:|opening\s+balance|"
    r"total\s+transaction|total\s+debit|total\s+credit|closing\s+balance|"
    r"\*\s*end\s+of\s+statement",
    re.I,
)


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_bom(value):
    """
    Handles Indian comma format: '5,000.00', '1,00,438.19'
    BOM uses '-' for empty debit or credit cells (not blank).
    Returns float or None.
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
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines):
    """
    Extract account metadata from Bank of Maharashtra statement.

    BOM uses structured tables on page 1 (extracted cleanly via pdfplumber).
    The raw text lines look like:

        'Account Details'
        'Account No 60435969304 Account Open Date 12/01/2023 Nomination Flag Y'
        'Account Type Cur-Gen-Pub-Corp-NonRural Nominee Name NEHA U NAGVEKAR'
        'Mode of Operation OPERATING SINGLY Total Balance 3.90Available Balance 3.90'
        'MAB Required 5000MAB Maintained 1790.566'
        'Account Holder Names AALEKH ASSOCIATES Primary GSTIN NA'
        'Customer Details'
        'Name AALEKH ASSOCIATES CIF Number 40258037325'
        ...
        'Branch No 01178 Branch Name SHREEKRISHNAGARBORIVLI E IFSC MAHB0001178'
        ...
        'A. Statement for Account No 60435969304 from 01/08/2024 to 04/02/2025'

    All fields are label + value on the same line.
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Statement period: "from 01/08/2024 to 04/02/2025"
    m = re.search(PERIOD_PATTERN, full_text, re.I)
    if m:
        info["statement_period"]["from"] = m.group(1)
        info["statement_period"]["to"]   = m.group(2)

    # IFSC
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    # Parse first 20 lines — all account metadata lives there
    for line in lines[:20]:
        line_s = (line or "").strip()
        if not line_s:
            continue

        # Account number: "Account No 60435969304 ..."
        if info["account_number"] is None:
            m = re.search(r"account\s*no\s+(\d{10,})", line_s, re.I)
            if m:
                info["account_number"] = m.group(1)

        # Account holder: "Account Holder Names AALEKH ASSOCIATES ..."
        if info["account_holder"] is None:
            m = re.search(r"account\s*holder\s*names?\s+(.+?)(?:\s{2,}|primary\s*gstin|$)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()

        # Account type: "Account Type Cur-Gen-Pub-Corp-NonRural ..."
        if info["acc_type"] is None:
            m = re.search(r"account\s*type\s+(.+?)(?:\s{2,}|nominee|$)", line_s, re.I)
            if m:
                info["acc_type"] = m.group(1).strip()

        # CIF number (customer ID): "CIF Number 40258037325"
        if info["customer_id"] is None:
            m = re.search(r"cif\s*number\s+(\d+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)

        # Branch name: "Branch Name SHREEKRISHNAGARBORIVLI E IFSC ..."
        if info["branch"] is None:
            m = re.search(r"branch\s*name\s+(.+?)(?:\s{2,}|ifsc|$)", line_s, re.I)
            if m:
                info["branch"] = m.group(1).strip()

        # Account open date used as statement_request_date proxy
        # Actual statement date: "Statement Date Tue Feb 04 17:56:33 GMT+05:30 2025"
        if info["statement_request_date"] is None:
            m = re.search(r"statement\s*date\s+\w+\s+(\w+\s+\d+\s+[\d:]+\s+\S+\s+\d{4})", line_s, re.I)
            if m:
                info["statement_request_date"] = m.group(1).strip()

    return info


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    """
    Extract all transactions from a Bank of Maharashtra PDF statement.

    BOM PDF CHARACTERISTICS:
    ========================
    - Text-based PDF; pdfplumber line strategy extracts tables cleanly
    - Page 1 has 4 tables: Account Details, Customer Details,
      Home Branch Details, and Transactions (table index 3)
    - Pages 2 onwards have 1 table each — all transactions
    - Last page has transaction table + multiple summary tables after it
    - 8 columns per row:
        [Sr No | Date | Particulars | Cheque/Reference No | Debit | Credit | Balance | Channel]
    - Debit and Credit use '-' for empty (not blank) — same as BOB
    - Balance has no CR/DR suffix — plain float string
    - Particulars can wrap across lines (pdfplumber joins with \\n in cell)
    - Some transactions split across page boundary:
        last row on page N has sr+date but particulars continues on page N+1 row 0
        (pdfplumber handles this within the table cell via \\n)
    - Summary tables on last page must be skipped (identified by non-numeric sr col)
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

                if not table:
                    continue

                # Skip non-transaction tables:
                # A transaction table's first data row has a numeric serial number.
                # Header row has 'Sr No' / 'Date' etc.
                # Summary tables (Account Details, Customer Details, etc.) don't.
                if not _is_transaction_table(table):
                    continue

                for row in table:

                    if not row or len(row) < 7:
                        continue

                    sr_raw = (row[0] or "").strip()

                    # Skip header row
                    if re.match(r"sr\s*no", sr_raw, re.I):
                        continue

                    # Skip summary / footer rows
                    particulars_raw = (row[2] or "").strip()
                    if _SKIP_PARTICULARS_RE.search(particulars_raw):
                        continue
                    if _SKIP_PARTICULARS_RE.search(sr_raw):
                        continue

                    # Serial number must be numeric
                    if not sr_raw.isdigit():
                        continue

                    txn = _build_txn(row)
                    if txn:
                        transactions.append(txn)

    # Sort by serial number to ensure correct order across pages
    transactions.sort(key=lambda t: t["serial_no"])

    return transactions


# ---------------------------------
# HELPERS
# ---------------------------------
def _is_transaction_table(table):
    """
    Returns True if this table contains transaction rows.
    Checks: header row has 'Sr No' + 'Date', OR first data row has numeric serial.
    """
    for row in table[:2]:
        if not row:
            continue
        row_text = " ".join((cell or "").lower() for cell in row)
        if "sr no" in row_text and "date" in row_text:
            return True
        # No header — check if first cell is a digit (continuation page)
        first = (row[0] or "").strip()
        if first.isdigit():
            return True
    return False


def _build_txn(row):
    """
    Build one transaction dict from a BOM table row.
    Columns: [Sr No, Date, Particulars, Cheque/Ref No, Debit, Credit, Balance, Channel]
    Returns None if row has no valid date.
    """
    def _cell(idx):
        if idx >= len(row):
            return None
        return (row[idx] or "").replace("\n", " ").strip() or None

    date_raw = _cell(1)
    if not date_raw or not _DATE_RE.match(date_raw):
        return None

    sr_raw = (_cell(0) or "")
    try:
        serial_no = int(sr_raw)
    except ValueError:
        return None

    desc = _cell(2)
    if desc:
        desc = re.sub(r"\s+", " ", desc).strip()

    cheque_no = _cell(3) or None
    debit     = _clean_amount_bom(_cell(4))
    credit    = _clean_amount_bom(_cell(5))
    balance   = _clean_amount_bom(_cell(6))
    channel   = _cell(7) or None

    return {
        "serial_no":   serial_no,
        "date":        date_raw,
        "description": desc,
        "cheque_no":   cheque_no,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
        "channel":     channel,
    }