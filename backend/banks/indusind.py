import re
import pdfplumber
from .base import (
    default_account_info,
    DATE_PATTERN,
    clean_amount,
    detect_columns,
)
from datetime import datetime

BANK_KEY = "indusind"
BANK_DISPLAY_NAME = "IndusInd Bank"

# --- Account info patterns (edit for ICICI statement layout) ---
ACCOUNT_PATTERNS = [
    r"a\/c\s*no\.?\s*[:\-]?\s*(\d{9,18})",
    r"account\s*no\.?\s*[:\-]?\s*(\d{9,18})",
    r"account\s*number\s*[:\-]?\s*(\d{9,18})",
]
NAME_PATTERNS = [
    r"name\s*[:\-]\s*([A-Za-z0-9\s\.&]+)",
    r"customer\s*name.*[:\-]?\s*([A-Za-z0-9\s\.&]+)",
]
BRANCH_PATTERNS = [
    r"a\/c\s*branch\s*[:\-]\s*([A-Za-z\s,]+)",
    r"branch\s*[:\-]\s*([A-Za-z\s,]+)",
]
ACCOUNT_TYPE_KEYWORDS = {
    "Savings": [
        r"\bSavings\s*Account\b",
        r"\bSB\s*A/?C\b",
        r"\bSB\b"
    ],
    "Current": [
        r"\bCurrent\s*Account\b",
        r"\bCA\s*A/?C\b",
        r"\bCA\b"
    ],
    "Overdraft": [
        r"\bOver\s*Draft\b",
        r"\bOverdraft\b",
        r"\bOD\s*A/?C\b",
        r"\bOD\b"
    ],
    "Cash Credit": [
        r"\bCash\s*Credit\b",
        r"\bCC\s*A/?C\b",
        r"\bCC\b"
    ]
}
JOINT_HOLDER_PATTERN = r"(jt\.?\s*holder|joint\s*holder)\s*:\s*(.*)"
MICR_PATTERN = r"micr\s*(code|no)?\s*[:\-]?\s*(\d{9})"
CUSTOMER_ID_PATTERNS = [
    r"cust\s*id\s*[:\-]?\s*(\d+)",
    r"customer\s*no\s*[:\-]?\s*(\d+)",
]
STATEMENT_REQ_PATTERN = r"statement\s*request.*date\s*[:\-]?\s*(" + DATE_PATTERN + ")"
IFSC_PATTERN = r"[A-Z]{4}0[A-Z0-9]{6}"

# IndusInd uses "From Date 01-Apr-25 To Date 31-May-25" (DD-Mon-YY); may be split across lines
STATEMENT_PERIOD_DD_MON_YY = re.compile(
    r"from\s*date\s*(\d{1,2}-[A-Za-z]{3}-\d{2,4}).*?to\s*date\s*(\d{1,2}-[A-Za-z]{3}-\d{2,4})",
    re.I | re.DOTALL,
)

HEADER_MAP = {
    "date": [
        "txn date",
        "value date",
        "date",
        "transaction date",
    ],
    "cheque_ref": [
        "cheque no",
        "cheque number",
        "chq no",
        "cheque",
        "reference no",
        "ref no",
        "bank reference",
        "instrument no",
    ],
    "description": [
        "transaction details",
        "details",
        "payment narration",
        "particulars",
        "narration",
    ],
    "debit": [
        "debit",
        "debit amt.",
        "debit(₹)",
    ],
    "credit": [
        "credit",
        "credit amt.",
        "credit(₹)",
        "credit avail",
    ],
    "balance": [
        "balance",
        "balance(₹)",
        "available balance",
        "closing balance",
        "able balance",
    ],
}

# Page 2+ in this PDF use 11 columns: Ref, Day, Month, Year, Value Date, Time, Type, Narration, Debit, Credit, Balance
INDUSIND_11_COL_MAPPING = {"date": 4, "description": 7, "debit": 8, "credit": 9, "balance": 10}
_VALUE_DATE_PATTERN = re.compile(r"^'?\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}", re.I)


def extract_account_info(lines):

    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    full_text = "\n".join(lines)

    # -------------------------
    # Account Holder
    # -------------------------
    m = re.search(
        r"customer\s*name\s*\(?.*?\)?\s*\n?\s*([A-Za-z0-9\s\.\-&]+)",
        full_text,
        re.I,
    )
    if m:
        info["account_holder"] = m.group(1).strip()

    # -------------------------
    # Account Number
    # -------------------------
    m = re.search(r"account\s*no\s*[:\-]?\s*(\d{9,18})", full_text, re.I)
    if m:
        info["account_number"] = m.group(1)

    # -------------------------
    # Statement Period (IndusInd: "From Date 01-Apr-25 To Date 31-May-25" or numeric DD/MM/YYYY)
    # -------------------------
    m = STATEMENT_PERIOD_DD_MON_YY.search(full_text)
    if m:
        info["statement_period"]["from"] = m.group(1).strip()
        info["statement_period"]["to"] = m.group(2).strip()
    else:
        dates = re.findall(DATE_PATTERN, full_text)
        if len(dates) >= 2:
            info["statement_period"]["from"] = dates[0]
            info["statement_period"]["to"] = dates[1]
        else:
            info["statement_period"]["from"] = None
            info["statement_period"]["to"] = None

    # -------------------------
    # MICR
    # -------------------------
    m = re.search(MICR_PATTERN, full_text, re.I)
    if m:
        info["micr"] = m.group(2)

    # -------------------------
    # IFSC
    # -------------------------
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(0)

    # -------------------------
    # Customer ID
    # -------------------------
    for pattern in CUSTOMER_ID_PATTERNS:
        m = re.search(pattern, full_text, re.I)
        if m:
            info["customer_id"] = m.group(1)
            break

    # -------------------------
    # Account Type
    # -------------------------
    for acc_type, patterns in ACCOUNT_TYPE_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, full_text, re.I):
                info["acc_type"] = acc_type
                break
        if info["acc_type"]:
            break

    # -------------------------
    # Branch
    # -------------------------
    for pattern in BRANCH_PATTERNS:
        m = re.search(pattern, full_text, re.I)
        if m:
            info["branch"] = m.group(1).strip()
            break

    info["currency"] = "INR"

    return info


def _row_looks_like_header(row, column_mapping):
    """Skip row if date/description cells contain header keywords (repeated header on new page)."""
    try:
        if "date" in column_mapping and column_mapping["date"] < len(row):
            cell = (row[column_mapping["date"]] or "").strip().lower()
            if cell in ("date", "txn date", "value date", "transaction date"):
                return True
        if "description" in column_mapping and column_mapping["description"] < len(row):
            cell = (row[column_mapping["description"]] or "").strip().lower()
            if any(h in cell for h in ("transaction details", "details", "narration", "particulars")):
                return True
    except (IndexError, TypeError, KeyError):
        pass
    return False


def _use_11_col_mapping(row):
    if len(row) < 11:
        return False
    val_date = (row[4] or "").strip()
    narration = (row[7] or "").strip()
    # Data row: value date in col 4 and amounts in 8/9/10
    if _VALUE_DATE_PATTERN.search(val_date):
        if clean_amount(row[8]) is not None or clean_amount(row[9]) is not None or clean_amount(row[10]) is not None:
            return True
    # Continuation row: no date in col 4 but narration in col 7
    if not val_date and narration:
        return True
    return False


def _mapping_for_row(row, column_mapping):
    """Use 11-column mapping when row matches page-2+ layout, else existing mapping."""
    if _use_11_col_mapping(row):
        return INDUSIND_11_COL_MAPPING
    return column_mapping

def normalize_date(date_val):
    date_val = date_val.replace("\n", " ").strip()

    formats = [
        "%d-%b-%y %H:%M:%S",
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d/%m/%Y",
        "%d/%m/%y"
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_val, fmt)
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass

    print("DATE PARSE FAILED:", date_val)  # debug
    return date_val


def _row_to_txn(row, column_mapping, last_txn):
    date_cell = row[column_mapping["date"]] if "date" in column_mapping else None

    if not date_cell and last_txn and "description" in column_mapping:
        desc = row[column_mapping["description"]] if column_mapping["description"] < len(row) else None
        if desc:
            desc = (desc or "").replace("\n", " ").strip()
            last_txn["description"] = (last_txn["description"] or "") + " " + desc
        return None
        
    txn = {"date": None,"cheque_ref":None, "description": None, "debit": None, "credit": None, "balance": None}
    try:
        if "date" in column_mapping and column_mapping["date"] < len(row) and row[column_mapping["date"]]:
            date_val = (row[column_mapping["date"]] or "").replace("\n", " ").strip().strip("'")
            txn["date"] = normalize_date(date_val)

        if "description" in column_mapping and column_mapping["description"] < len(row):
            desc = row[column_mapping["description"]]
            if desc:
                txn["description"] = (desc or "").replace("\n", " ").strip()

        if "cheque_ref" in column_mapping and column_mapping["cheque_ref"] < len(row) and row[column_mapping["cheque_ref"]]:
            txn["cheque_ref"] = row[column_mapping["cheque_ref"]]

        if "debit" in column_mapping and column_mapping["debit"] < len(row) and row[column_mapping["debit"]]:
            txn["debit"] = clean_amount(row[column_mapping["debit"]])

        if "credit" in column_mapping and column_mapping["credit"] < len(row) and row[column_mapping["credit"]]:
            txn["credit"] = clean_amount(row[column_mapping["credit"]])

        if "balance" in column_mapping and column_mapping["balance"] < len(row) and row[column_mapping["balance"]]:
            txn["balance"] = clean_amount(row[column_mapping["balance"]])
    except (IndexError, TypeError, KeyError):
        return None
    return txn


def extract_transactions(pdf_path: str):

    transactions = []
    column_mapping = None
    last_txn = None

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines"
            })

            if not tables:
                continue

            for table in tables:

                for row in table:

                    if not row:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]
                
                    detected = detect_columns(row_clean, HEADER_MAP)

                    # Header row: 3+ columns matched. Use it so each page's header updates mapping
                    # (page 2 may have different columns e.g. Date | Time | Description | Debit | Credit | Balance)
                    if detected and len(detected) >= 3:
                        column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    # Use 11-column layout for page-2+ rows when applicable
                    mapping = _mapping_for_row(row, column_mapping)

                    # Skip data rows that look like header (e.g. "date" in date cell, "description" in desc cell)
                    if _row_looks_like_header(row, mapping):
                        continue

                    txn = _row_to_txn(row, mapping, last_txn)

                    if txn:
                        transactions.append(txn)
                        last_txn = txn

    return transactions