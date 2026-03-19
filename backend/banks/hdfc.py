"""
HDFC Bank statement parsing.
Edit extract_account_info and extract_transactions below for HDFC-specific logic.
Uses separate debit/credit columns.
"""
import re
import pdfplumber
from .base import (
    default_account_info,
    DATE_PATTERN,
    clean_amount,
    detect_columns,
)

BANK_KEY = "hdfc"
BANK_DISPLAY_NAME = "HDFC Bank"

# --- Account info patterns (edit for HDFC statement layout) ---
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

HEADER_MAP = {
    "date": [
        "date"
    ],
    "description": [
        "narration",
        "particulars",
        "details"
    ],
    "cheque_ref":[
        "chq./ref.no.",
        "ref no",
        "cheque",
        "chq",
        "reference no",
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
    """Extract account metadata from text lines. Edit patterns above if needed."""
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    for line in lines:
        lower = (line or "").lower().strip()

        if info["account_holder"] is None:

            m = re.search(r"(m/s\.?\s*[A-Za-z0-9\s\.\-&]+)", line, re.I)

            if m:
                info["account_holder"] = m.group(1).strip()
                continue

        if info["account_holder"] is None:

            for i, line in enumerate(lines):

                if "statement of account" in line.lower():

                    # account holder usually appears a few lines above
                    for j in range(max(0, i-10), i):

                        candidate = lines[j].strip()

                        if candidate and len(candidate.split()) >= 2:
                            info["account_holder"] = candidate
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

def clean_description(text):

    # remove dates
    text = re.sub(r"\b\d{2}/\d{2}/\d{2}\b", "", text)

    # remove cheque numbers (pure numbers)
    text = re.sub(r"\b\d{5,}\b", "", text)

    # remove extra spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text

def extract_transactions(pdf_path):

    transactions = []
    current_txn = None

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            text = page.extract_text()

            if not text:
                continue

            lines = text.split("\n")

            for line in lines:

                line = line.strip()

                if re.match(r"^[-_]{5,}$", line):
                    break

                # transaction start
                if re.match(r"^\d{2}/\d{2}/\d{2}", line):

                    parts = line.split()

                    date = parts[0]

                    balance = clean_amount(parts[-1])
                    amount = clean_amount(parts[-2])
                    ref_no = parts[-4]
                    description = clean_description(" ".join(parts[1:-2]))

                    current_txn = {
                        "date": date,
                        "description": description,
                        "cheque_ref": ref_no,
                        "debit": None,
                        "credit": None,
                        "balance": balance
                    }

                    if amount is not None:
                        if "dr" in description.lower():
                            current_txn["debit"] = amount
                        else:
                            current_txn["credit"] = amount

                    transactions.append(current_txn)

                else:
                    # continuation narration line
                    if current_txn:

                        # stop if new transaction starts
                        if re.match(r"^\d{2}/\d{2}/\d{2}", line):
                            continue

                        # ignore cheque numbers
                        if re.match(r"^\d{6,}$", line):
                            continue

                        # ignore value date columns
                        if re.match(r"^\d{2}/\d{2}/\d{2}$", line):
                            continue

                        # ignore amount columns
                        if re.match(r"^\d{1,3}(,\d{3})*(\.\d{2})?$", line):
                            continue

                        # append narration
                        current_txn["description"] += " " + line.strip()

                        ref_match = re.search(r"[A-Z]{4,}\d{6,}", line)

                        if ref_match:
                            current_txn["ref_no"] = ref_match.group()

                        else:
                            current_txn["description"] += " " + line.strip()
    return transactions