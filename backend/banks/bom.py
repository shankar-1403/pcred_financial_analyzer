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

_SKIP_PARTICULARS_RE = re.compile(
    r"no\s+accounts\s+available|total\s*:|opening\s+balance|"
    r"total\s+transaction|total\s+debit|total\s+credit|closing\s+balance|"
    r"\*\s*end\s+of\s+statement",
    re.I,
)


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
def _clean_amount_bom(value):
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
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Statement period: "from 01/08/2024 to 04/02/2025" → reformat both dates
    m = re.search(PERIOD_PATTERN, full_text, re.I)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    # IFSC
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    for line in lines[:20]:
        line_s = (line or "").strip()
        if not line_s:
            continue

        if info["account_number"] is None:
            m = re.search(r"account\s*no\s+(\d{10,})", line_s, re.I)
            if m:
                info["account_number"] = m.group(1)

        if info["account_holder"] is None:
            m = re.search(r"account\s*holder\s*names?\s+(.+?)(?:\s{2,}|primary\s*gstin|$)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()

        if info["acc_type"] is None:
            m = re.search(r"account\s*type\s+(.+?)(?:\s{2,}|nominee|$)", line_s, re.I)
            if m:
                info["acc_type"] = m.group(1).strip()

        if info["customer_id"] is None:
            m = re.search(r"cif\s*number\s+(\d+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)

        if info["branch"] is None:
            m = re.search(r"branch\s*name\s+(.+?)(?:\s{2,}|ifsc|$)", line_s, re.I)
            if m:
                info["branch"] = m.group(1).strip()

        if info["statement_request_date"] is None:
            m = re.search(r"statement\s*date\s+\w+\s+(\w+\s+\d+\s+[\d:]+\s+\S+\s+\d{4})", line_s, re.I)
            if m:
                info["statement_request_date"] = m.group(1).strip()

    return info


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
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

                if not _is_transaction_table(table):
                    continue

                for row in table:

                    if not row or len(row) < 7:
                        continue

                    sr_raw = (row[0] or "").strip()

                    if re.match(r"sr\s*no", sr_raw, re.I):
                        continue

                    particulars_raw = (row[2] or "").strip()
                    if _SKIP_PARTICULARS_RE.search(particulars_raw):
                        continue
                    if _SKIP_PARTICULARS_RE.search(sr_raw):
                        continue

                    if not sr_raw.isdigit():
                        continue

                    txn = _build_txn(row)
                    if txn:
                        transactions.append(txn)

    transactions.sort(key=lambda t: t["serial_no"])

    return transactions


# ---------------------------------
# HELPERS
# ---------------------------------
def _is_transaction_table(table):
    for row in table[:2]:
        if not row:
            continue
        row_text = " ".join((cell or "").lower() for cell in row)
        if "sr no" in row_text and "date" in row_text:
            return True
        first = (row[0] or "").strip()
        if first.isdigit():
            return True
    return False


def _build_txn(row):
    """
    Columns: [Sr No, Date, Particulars, Cheque/Ref No, Debit, Credit, Balance, Channel]
    Date input: DD/MM/YYYY → output: DD-MM-YYYY
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
        "date":        _reformat_date(date_raw),   # DD/MM/YYYY → DD-MM-YYYY
        "description": desc,
        "cheque_no":   cheque_no,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
        "channel":     channel,
    }