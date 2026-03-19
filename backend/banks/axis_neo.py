import re
import pdfplumber
from .base import (
    default_account_info,
    DATE_PATTERN,
    clean_amount,
    detect_columns,
)
from datetime import datetime

BANK_KEY = "axis neo"
BANK_DISPLAY_NAME = "Axis Bank Neo"

# --- Account info patterns (edit for Axis statement layout) ---
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

JOINT_HOLDER_PATTERN = r"(jt\.?\s*holder|joint\s*holder)\s*:\s*(.*)"
MICR_PATTERN = r"micr\s*(code|no)?\s*[:\-]?\s*(\d{9})"
CUSTOMER_ID_PATTERNS = [
    r"cust\s*id\s*[:\-]?\s*(\d+)",
    r"customer\s*no\s*[:\-]?\s*(\d+)",
]
STATEMENT_REQ_PATTERN = r"statement\s*request.*date\s*[:\-]?\s*(" + DATE_PATTERN + ")"
IFSC_PATTERN = r"[A-Z]{4}0[A-Z0-9]{6}"

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

def extract_account_info(lines):
    """Extract account metadata from text lines. Edit patterns above if needed."""
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    for line in lines:
        lower = (line or "").lower().strip()

        if info["account_holder"] is None:
            for pattern in NAME_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    holder = m.group(1)
                    holder = re.split(r"a\/c\s*branch|branch\s*address", holder, flags=re.I)[0]
                    info["account_holder"] = holder.strip()

        if info["micr"] is None:
            m = re.search(MICR_PATTERN, line or "", re.I)
            if m:
                info["micr"] = m.group(2)

        if info["account_number"] is None:
            for pattern in ACCOUNT_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    info["account_number"] = m.group(1)
                    break

        if info["branch"] is None:
            for pattern in BRANCH_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    branch = m.group(1)
                    branch = re.split(r"branch\s*address|address", branch, flags=re.I)[0]
                    info["branch"] = branch.strip()

        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN, line or "")
            if m:
                info["ifsc"] = m.group()

        if "currency" in lower and "inr" in lower:
            info["currency"] = "INR"

        if info["acc_type"] is None:
            for acc_type, patterns in ACCOUNT_TYPE_KEYWORDS.items():
                for pattern in patterns:
                    if re.search(pattern, line or "", re.I):
                        info["acc_type"] = acc_type
                        break
                if info["acc_type"]:
                    break

        if info["joint_holder"] is None:
            m = re.search(JOINT_HOLDER_PATTERN, line or "", re.I)
            if m:
                value = re.split(
                    r"cust\s*id|scheme|branch\s*code|ifsc|a\/c\s*type",
                    m.group(2).strip(),
                    flags=re.I,
                )[0].strip()
                info["joint_holder"] = value or None

        if info["customer_id"] is None:
            for pattern in CUSTOMER_ID_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    info["customer_id"] = m.group(1)
                    break

        if info["statement_request_date"] is None:
            m = re.search(STATEMENT_REQ_PATTERN, line or "", re.I)
            if m:
                info["statement_request_date"] = m.group(1)

        if "transaction period" in lower or ("from" in lower and "to" in lower):
            dates = re.findall(DATE_PATTERN, line or "")
            if len(dates) >= 2:
                info["statement_period"]["from"] = dates[0]
                info["statement_period"]["to"] = dates[1]

    return info

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
    """Axis: single amount + debit/credit (DR/CR) column."""
    date_cell = row[column_mapping["date"]] if "date" in column_mapping else None
    if not date_cell and last_txn and "description" in column_mapping:
        desc = row[column_mapping["description"]] if column_mapping["description"] < len(row) else None
        if desc:
            desc = (desc or "").replace("\n", " ").strip()
            last_txn["description"] = (last_txn["description"] or "") + " " + desc
        return None

    txn = {"date": None, "description": None, "debit": None, "credit": None, "balance": None}
    try:
        if "date" in column_mapping and column_mapping["date"] < len(row) and row[column_mapping["date"]]:
            date_val = (row[column_mapping["date"]] or "").replace("\n", " ").strip().strip("'")
            date_val = date_val.split(" ")[0]
            txn["date"] = normalize_date(date_val)

        if "description" in column_mapping and column_mapping["description"] < len(row):
            desc = row[column_mapping["description"]]
            if desc:
                txn["description"] = (desc or "").replace("\n", " ").strip()

        if "amount" in column_mapping and "debit_credit" in column_mapping:
            amount = clean_amount(row[column_mapping["amount"]] if column_mapping["amount"] < len(row) else None)
            dc = (row[column_mapping["debit_credit"]] or "").strip().upper() if column_mapping["debit_credit"] < len(row) else ""
            if dc == "DR":
                txn["debit"] = amount
            elif dc == "CR":
                txn["credit"] = amount

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

                    # detect header rows on every page
                    detected = detect_columns(row_clean)

                    if detected:
                        if column_mapping is None:
                            column_mapping = detected
                        continue   # skip header row

                    if column_mapping is None:
                        continue

                    txn = _row_to_txn(row, column_mapping, last_txn)

                    if txn:
                        transactions.append(txn)
                        last_txn = txn

    return transactions