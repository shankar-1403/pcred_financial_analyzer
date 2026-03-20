import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns
)

BANK_KEY          = "federal"
BANK_DISPLAY_NAME = "Federal Bank"


# ---------------------------------
# TABLE HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date": [
        "date",
    ],
    "description": [
        "particulars",
        "description",
        "narration",
    ],
    "debit": [
        "withdrawals",
        "withdrawal",
        "debit",
        "dr",
    ],
    "credit": [
        "deposits",
        "deposit",
        "credit",
        "cr",
    ],
    "balance": [
        "balance",
        "running balance",
    ],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
ACCT_NO_PATTERN   = r"account\s*number\s*[:\-]?\s*(\d{10,})"
CUSTOMER_PATTERN  = r"customer\s*id\s*[:\-]?\s*(\d+)"
IFSC_PATTERN      = r"ifsc\s*[:\-]?\s*([A-Z]{4}[0-9]{7})"
MICR_PATTERN      = r"micr\s*code\s*[:\-]?\s*(\d{9})"
BRANCH_PATTERN    = r"branch\s*name\s*[:\-]?\s*(.+)"
ACCT_TYPE_PATTERN = r"type\s*of\s*account\s*[:\-\s]+(\w+)"
PERIOD_PATTERN    = r"for\s+the\s+period\s+(\d{2}-[A-Z]{3}-\d{4})\s+to\s+(\d{2}-[A-Z]{3}-\d{4})"

# Date: "15/11/2023"
DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")


# ---------------------------------
# FEDERAL BANK-SPECIFIC COLUMN DETECTOR
# ---------------------------------
def _detect_columns_federal(row_clean):
    """
    Federal Bank-specific column detector.
    Uses exact match first, then guarded substring (4+ chars only).
    base.py is never modified.
    """
    mapping = {}
    for field, variants in HEADER_MAP.items():
        # Pass 1: exact match
        for idx, cell in enumerate(row_clean):
            if cell in variants:
                mapping[field] = idx
                break
        if field in mapping:
            continue
        # Pass 2: substring only for 4+ char aliases
        for idx, cell in enumerate(row_clean):
            if any(len(v) >= 4 and v in cell for v in variants):
                mapping[field] = idx
                break
    return mapping if len(mapping) >= 3 else None


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_federal(value):
    """
    Standard Indian comma format: '2,00,000.00', '5,73,439.00'
    Treats empty string / None as None.
    Returns float or None.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    value = re.sub(r"^(Rs\.?|INR|₹)\s*", "", value, flags=re.I).strip()
    value = value.replace(",", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------
# DATE HELPER
# ---------------------------------
def _is_txn_date(value):
    """Federal Bank date format: 'DD/MM/YYYY' e.g. '15/11/2023'"""
    if not value:
        return False
    return bool(DATE_PATTERN.match(str(value).strip()))


# ---------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines, pdf_path=None):
    """
    Extract account metadata from Federal Bank page 1.

    Federal Bank page 1 layout (key : value pairs):
      Name                        : ATIKUR RAHMAN
      Type of Account             : Current
      IFSC                        : FDRL0001674
      MICR Code                   : 781049003
      Account Number              : 18210200002249
      Customer Id                 : 4941758
      Branch Name                 : Guwahati / G S Road
      Statement period            : 12-NOV-2023 to 11-NOV-2024
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    for line in lines:
        text = line.strip()

        # Account Holder Name
        if info["account_holder"] is None:
            m = re.match(r"^name\s*[:\-]?\s*(.+)", text, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()

        # Account Number
        if info["account_number"] is None:
            m = re.search(ACCT_NO_PATTERN, text, re.I)
            if m:
                info["account_number"] = m.group(1)

        # Customer ID
        if info["customer_id"] is None:
            m = re.search(CUSTOMER_PATTERN, text, re.I)
            if m:
                info["customer_id"] = m.group(1)

        # IFSC
        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN, text, re.I)
            if m:
                info["ifsc"] = m.group(1)

        # MICR
        if info["micr"] is None:
            m = re.search(MICR_PATTERN, text, re.I)
            if m:
                info["micr"] = m.group(1)

        # Branch
        if info["branch"] is None:
            m = re.search(BRANCH_PATTERN, text, re.I)
            if m:
                candidate = m.group(1).strip().lstrip(":").strip()
                if candidate and len(candidate) > 2:
                    info["branch"] = candidate

        # Account Type
        if info["acc_type"] is None:
            m = re.search(ACCT_TYPE_PATTERN, text, re.I)
            if m:
                val = m.group(1).strip()
                if val.upper() not in ("OF", "THE", "AND", "FOR", "IN"):
                    info["acc_type"] = val

        # Statement Period
        if info["statement_period"]["from"] is None:
            m = re.search(PERIOD_PATTERN, text, re.I)
            if m:
                info["statement_period"]["from"] = m.group(1)
                info["statement_period"]["to"]   = m.group(2)

    return info


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    """
    Extract all transactions from a Federal Bank PDF statement.

    FEDERAL BANK PDF CHARACTERISTICS:
    ==================================
    - Text-based PDF (pdfplumber extracts chars)
    - 9-10 columns: Date | Value Date | Particulars | Tran Type | Tran ID |
                    Cheque Details | Withdrawals | Deposits | Balance | Dr/Cr
    - Date format: 'DD/MM/YYYY' (e.g. '15/11/2023')
    - Empty debit/credit cells are blank (not '-')
    - Balance format: standard Indian comma '2,00,029.12'
    - Particulars can span multiple lines within the cell
    - Grand Total row at the end has no date — skipped by _is_txn_date()
    """
    transactions   = []
    column_mapping = None

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

                # Federal Bank transaction table has 9 or 10 columns
                if len(table[0]) not in (9, 10):
                    continue

                for row in table:

                    if not row or len(row) < 9:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    # Detect header row
                    detected = _detect_columns_federal(row_clean)
                    if detected:
                        column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    # Validate date — also skips Grand Total row
                    date_cell = (row[column_mapping.get("date", 0)] or "").strip()
                    if not _is_txn_date(date_cell):
                        continue

                    # Description — join multi-line content
                    desc_raw    = row[column_mapping.get("description", 2)] or ""
                    description = re.sub(r"\s+", " ", desc_raw.replace("\n", " ")).strip()

                    debit   = _clean_amount_federal(row[column_mapping.get("debit",   6)])
                    credit  = _clean_amount_federal(row[column_mapping.get("credit",  7)])
                    balance = _clean_amount_federal(row[column_mapping.get("balance", 8)])

                    transactions.append({
                        "date":        date_cell,
                        "description": description,
                        "debit":       debit,
                        "credit":      credit,
                        "balance":     balance,
                    })

    return transactions