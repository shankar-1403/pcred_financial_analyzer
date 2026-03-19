import re

DATE_PATTERN = r"\d{2}[/-]\d{2}[/-]\d{2,4}"
AMOUNT_PATTERN = r"-?\d[\d,]*\.?\d*"

HEADER_MAP = {
    "description": [
        "description",
        "narration",
        "transaction remarks",
        "payment narration",
        "details",
        "particulars",
        "transaction details",
    ],
    "amount": [
        "amount",
        "amount(inr)",
    ],
    "debit_credit": [
        "debit/credit",
        "debit/credit (₹)",
    ],
    "debit": [
        "withdrawal",
        "withdrawal amt",
        "withdrawal(dr)",
        "withdrawal(cr)",
        "withdra",
        "debit",
    ],
    "credit": [
        "deposit",
        "deposit amt",
        "deposit(cr)",
        "deposit (cr)",
        "credit",
    ],
    "balance": [
        "balance",
        "balance (₹)",
        "closing balance",
        "available balance",
    ],
    "date": [
        "date",
        "txn date",
        "transaction date",
        "transaction date & time",
        "value date",
        "transaction posted date",
    ],
}


def clean_amount(val):
    if not val:
        return None
    val = str(val).replace("\n", "").replace(",", "")
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def detect_columns(header_row,header_map=None):
    if header_map is None:
        header_map = HEADER_MAP
    mapping = {}
    for idx, col in enumerate(header_row):
        if not col:
            continue
        col_lower = (col or "").lower().replace("\n", " ").strip()
        col_lower = re.sub(r"\s+", " ", col_lower)
        for key, aliases in header_map.items():
            for a in aliases:
                if a in col_lower:
                    mapping[key] = idx
    return mapping


def parse_table_rows(rows, mapping):
    """Convert table rows to list of transaction dicts using column mapping."""
    transactions = []
    for row in rows:
        txn = {
            "date": None,
            "description": None,
            "debit": None,
            "credit": None,
            "balance": None,
        }
        try:
            if "date" in mapping and len(row) > mapping["date"] and row[mapping["date"]]:
                txn["date"] = str(row[mapping["date"]]).replace("\n", " ").strip()
            if "description" in mapping and len(row) > mapping["description"]:
                desc = row[mapping["description"]]
                if desc:
                    desc = str(desc).replace("\n", " ").strip()
                    desc = re.sub(r"\s+", " ", desc)
                    txn["description"] = desc
            if "debit" in mapping and len(row) > mapping["debit"] and row[mapping["debit"]]:
                txn["debit"] = clean_amount(row[mapping["debit"]])
            if "credit" in mapping and len(row) > mapping["credit"] and row[mapping["credit"]]:
                txn["credit"] = clean_amount(row[mapping["credit"]])
            if "balance" in mapping and len(row) > mapping["balance"] and row[mapping["balance"]]:
                txn["balance"] = clean_amount(row[mapping["balance"]])
        except (IndexError, TypeError):
            continue
        transactions.append(txn)
    return transactions


def default_account_info():
    return {
        "bank_name": None,
        "account_holder": None,
        "account_number": None,
        "branch": None,
        "acc_type": None,
        "joint_holder": None,
        "statement_request_date": None,
        "customer_id": None,
        "ifsc": None,
        "micr": None,
        "currency": "INR",
        "statement_period": {"from": None, "to": None},
    }
