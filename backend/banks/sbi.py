import re
import pdfplumber
from .base import (
    default_account_info,
    DATE_PATTERN,
    clean_amount,
    detect_columns,
)

BANK_KEY = "sbi"
BANK_DISPLAY_NAME = "State Bank of India"

# --- Account info patterns (edit for SBI statement layout) ---
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
ACCOUNT_TYPE_PATTERNS = [
    r"a\/c\s*type\s*[:\-]?\s*([A-Za-z]+)",
    r"scheme\s*[:\-]?\s*([A-Za-z0-9\s\-]+)",
]
JOINT_HOLDER_PATTERN = r"(jt\.?\s*holder|joint\s*holder)\s*:\s*(.*)"
MICR_PATTERN = r"micr\s*(code|no)?\s*[:\-]?\s*(\d{9})"
CUSTOMER_ID_PATTERNS = [
    r"cust\s*id\s*[:\-]?\s*(\d+)",
    r"customer\s*no\s*[:\-]?\s*(\d+)",
]
STATEMENT_REQ_PATTERN = r"statement\s*request.*date\s*[:\-]?\s*(" + DATE_PATTERN + ")"
IFSC_PATTERN = r"[A-Z]{4}0[A-Z0-9]{6}"

HEADER_MAP = {
    "date": [
        "date",
        "value date"
    ],
    "description": [
        "narration",
        "particulars",
        "details",
        "description"
    ],
    "credit": [
        "deposit amt",
        "deposit amt.",
        "deposit amt (₹)",
        "deposit",
        "credit"
    ],
    "debit": [
        "withdrawal amt",
        "withdrawal amt.",
        "withdrawal amt (₹)",
        "withdrawal",
        "debit"
    ],
    "balance": [
        "closing balance",
        "balance",
        "closing bal"
    ]
}

def extract_account_info(lines):

    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    for line in lines:

        if not line:
            continue

        line = re.sub(r"\(cid:\d+\)", "", line).strip()

        if info["statement_period"]["from"] is None:

            m = re.search(
                r"from\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+to\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
                line,
                re.I
            )

            if m:
                info["statement_period"]["from"] = m.group(1)
                info["statement_period"]["to"] = m.group(2)

        # split key : value
        if ":" in line:
            parts = line.split(":", 1)

            key = parts[0].strip().lower()
            value = parts[1].strip()

            if not value:
                continue

            if "account number" in key:
                info["account_number"] = value

            elif key == "name":
                info["account_holder"] = value

            elif "branch" in key:
                info["branch"] = value

            elif "ifs code" in key or "ifsc" in key:
                info["ifsc"] = value

            elif "currency" in key:
                info["currency"] = value

            elif "date" in key and info["statement_request_date"] is None:
                info["statement_request_date"] = value

    return info


def _row_to_txn(row, column_mapping, last_txn):
    """SBI: separate debit and credit columns."""
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
            txn["date"] = (row[column_mapping["date"]] or "").replace("\n", " ").strip()
        if "description" in column_mapping and column_mapping["description"] < len(row):
            desc = row[column_mapping["description"]]
            if desc:
                txn["description"] = (desc or "").replace("\n", " ").strip()

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
    """Extract transactions from SBI PDF (separate debit/credit columns). Edit table logic above if needed."""
    transactions = []
    column_mapping = None
    last_txn = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )
            if not tables:
                continue
            for table in tables:
                for row in table:
                    if not row:
                        continue
                    row_clean = [(cell or "").replace("\n", " ").strip().lower() for cell in row]
                    detected = detect_columns(row_clean,HEADER_MAP)
                    if detected:
                        if column_mapping is None:
                            column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue
                    txn = _row_to_txn(row, column_mapping, last_txn)
                    if txn:
                        transactions.append(txn)
                        last_txn = txn
    return transactions
