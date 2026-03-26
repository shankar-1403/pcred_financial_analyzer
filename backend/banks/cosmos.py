import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns,
)

BANK_KEY          = "cosmos"
BANK_DISPLAY_NAME = "The Cosmos Co-op. Bank Ltd."


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
IFSC_PATTERN   = r"\b(COSB[A-Z0-9]{7})\b"
PERIOD_PATTERN = r"period\s+of\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})"

# Date format used in Cosmos transaction rows: DD/MM/YYYY
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# Statement request date on page header: e.g. "14-Jan-2025"
_REQ_DATE_RE = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{4}")

# Footer / summary rows — skip entirely
_SKIP_ROW_RE = re.compile(
    r"sub\s*total|grandtotal|grand\s*total|\*+\s*end\s*of\s*statement",
    re.I,
)

# Balance cells always end with " CR" — strip before float-parsing
_CR_SUFFIX_RE = re.compile(r"\s*cr\s*$", re.I)


# ---------------------------------
# DATE REFORMAT
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert DD/MM/YYYY → DD-MM-YYYY."""
    if not date_str:
        return date_str
    return date_str.replace("/", "-")


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_cosmos(value):
    if value is None:
        return None
    value = str(value).strip()
    value = _CR_SUFFIX_RE.sub("", value).strip()
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
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Statement period — reformat both dates
    m = re.search(PERIOD_PATTERN, full_text, re.I)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    # Statement request date — "14-Jan-2025" (already dash-separated, keep as-is)
    m = _REQ_DATE_RE.search(full_text)
    if m:
        info["statement_request_date"] = m.group()

    # IFSC
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    for line in lines[:5]:
        line_s = (line or "").strip()
        if not line_s:
            continue

        if info["customer_id"] is None:
            m = re.search(r"customer\s*id\s+(\d+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)
                continue

        if info["account_number"] is None:
            m = re.search(r"account\s*number\s+(\d+)", line_s, re.I)
            if m:
                info["account_number"] = m.group(1)
                continue

        if info["account_holder"] is None:
            m = re.search(r"account\s*holder\s*name\s+(.+)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()
                continue

    return info


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    transactions   = []
    column_mapping = None
    last_txn       = None

    cosmos_header_map = {
        "date": [
            "date",
        ],
        "description": [
            "transaction particulars",
            "particulars",
            "narration",
            "description",
        ],
        "cheque": [
            "cheque no",
            "cheque no.",
            "chequeno",
        ],
        "debit": [
            "withdrawal",
            "withdrawal amt",
        ],
        "credit": [
            "deposit",
            "deposit amt",
        ],
        "balance": [
            "available balance",
            "balance",
            "closing balance",
        ],
    }

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

                    if all((cell or "").strip() == "" for cell in row):
                        continue

                    row_text = " ".join((cell or "") for cell in row)
                    if _SKIP_ROW_RE.search(row_text):
                        continue

                    row_lower = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    detected = detect_columns(row_lower, cosmos_header_map)
                    if detected and "date" in detected:
                        column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    if _is_continuation(row, column_mapping):
                        if last_txn is not None and "description" in column_mapping:
                            desc_idx = column_mapping["description"]
                            if desc_idx < len(row):
                                extra = (row[desc_idx] or "").replace("\n", " ").strip()
                                if extra:
                                    last_txn["description"] = (
                                        (last_txn["description"] or "") + " " + extra
                                    ).strip()
                        continue

                    txn = _build_txn(row, column_mapping)
                    if txn:
                        transactions.append(txn)
                        last_txn = txn

    return transactions


# ---------------------------------
# HELPERS
# ---------------------------------
def _is_continuation(row, col):
    def _get(key):
        idx = col.get(key)
        return (row[idx] or "").strip() if idx is not None and idx < len(row) else ""

    has_date    = bool(_get("date"))
    has_amounts = any(bool(_get(k)) for k in ("debit", "credit", "balance"))
    return not has_date and not has_amounts


def _build_txn(row, col):
    """
    Columns: [Date, Transaction Particulars, Cheque No., Withdrawal, Deposit, Available Balance]
    Date input: DD/MM/YYYY → output: DD-MM-YYYY
    """
    def _get(key):
        idx = col.get(key)
        if idx is None or idx >= len(row):
            return None
        return (row[idx] or "").replace("\n", " ").strip() or None

    date_raw = _get("date")
    if not date_raw or not _DATE_RE.match(date_raw):
        return None

    desc = _get("description")
    if desc:
        desc = re.sub(r"\s+", " ", desc).strip()

    cheque_no = _get("cheque") or None
    debit     = _clean_amount_cosmos(_get("debit"))
    credit    = _clean_amount_cosmos(_get("credit"))
    balance   = _clean_amount_cosmos(_get("balance"))

    return {
        "date":        _reformat_date(date_raw),   # DD/MM/YYYY → DD-MM-YYYY
        "description": desc,
        "cheque_no":   cheque_no,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }