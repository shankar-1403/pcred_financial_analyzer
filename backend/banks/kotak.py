import re
import pdfplumber
from .base import (
    default_account_info,
    DATE_PATTERN,
    clean_amount,
    detect_columns,
)

BANK_KEY = "kotak"
BANK_DISPLAY_NAME = "Kotak Bank"

# --- Account info patterns (edit for kotak statement layout) ---
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
    r"branch\s*([A-Za-z\s]+)"
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

HEADER_MAP = {
    "date": [
        "transaction date",
        "txn date",
        "value date",
        "date"
    ],
    "description": [
        "transaction details",
        "details",
        "narration",
        "particulars"
    ],
    "amount": [
        "debit/credit",
        "debit / credit",
        "debit/credit(₹)",
        "debit/credit (₹)"
    ],
    "balance": [
        "balance",
        "balance(₹)",
        "balance (₹)",
        "closing balance"
    ]
}

def extract_account_info(lines):
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    for i, line in enumerate(lines):
        lower = (line or "").lower().strip()

        if info["account_holder"] is None:

            # Kotak: name appears after statement period
            if re.search(r"\d{2}\s+[a-z]{3}\s+\d{4}\s*-\s*\d{2}\s+[a-z]{3}\s+\d{4}", lower):

                # next non-empty line is account holder
                for j in range(i+1, min(i+5, len(lines))):
                    name_line = (lines[j] or "").strip()

                    if name_line and not name_line.lower().startswith(("crn","ct","ifsc","micr")):
                        info["account_holder"] = name_line
                        break

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


def _row_to_txn(row, column_mapping, last_txn):
    date_cell = row[column_mapping["date"]] if "date" in column_mapping else None
    if not date_cell and last_txn and "description" in column_mapping:
        desc = row[column_mapping["description"]] if column_mapping["description"] < len(row) else None
        if desc:
            desc = (desc or "").replace("\n", " ").strip()
            last_txn["description"] = (last_txn["description"] or "") + " " + desc
        return None

    txn = {"date": None, "description": None, "debit": None, "credit": None, "balance": None}
    try:
        if "date" in column_mapping and column_mapping["date"] < len(row):
            val = row[column_mapping["date"]]
            if val:
                txn["date"] = val.replace("\n"," ").strip()

        if "description" in column_mapping and column_mapping["description"] < len(row):
            desc = row[column_mapping["description"]]
            if desc:
                txn["description"] = desc.replace("\n"," ").strip()

        if "amount" in column_mapping and column_mapping["amount"] < len(row):
            amount_val = clean_amount(row[column_mapping["amount"]])

            if amount_val is not None:
                if amount_val < 0:
                    txn["debit"] = abs(amount_val)
                else:
                    txn["credit"] = amount_val

        if "balance" in column_mapping and column_mapping["balance"] < len(row):
            txn["balance"] = clean_amount(row[column_mapping["balance"]])
    except (IndexError, TypeError, KeyError):
        return None
    return txn


def extract_transactions(pdf_path):

    transactions = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            text = page.extract_text()

            if not text:
                continue

            lines = text.split("\n")

            for line in lines:

                line = line.strip()

                # transaction rows start with serial number
                if not re.match(r"^\d+\s+\d{2}\s+[A-Za-z]{3}\s+\d{4}", line):
                    continue

                try:

                    parts = line.split()

                    date = " ".join(parts[1:4])

                    balance = clean_amount(parts[-1])
                    amount = clean_amount(parts[-2])

                    description = " ".join(parts[4:-2])

                    txn = {
                        "date": date,
                        "description": description,
                        "debit": None,
                        "credit": None,
                        "balance": balance
                    }

                    if amount is not None:
                        if amount < 0:
                            txn["debit"] = abs(amount)
                        else:
                            txn["credit"] = amount

                    transactions.append(txn)

                except:
                    continue

    return transactions
