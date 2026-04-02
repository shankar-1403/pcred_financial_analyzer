import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "sib"
BANK_DISPLAY_NAME = "South Indian Bank"

# ---------------------------------------------------------------------------
# REGEX
# ---------------------------------------------------------------------------
_IFSC_RE    = re.compile(r"\b(SIBL[A-Z0-9]{7})\b", re.I)
_MICR_RE    = re.compile(r"MICR\s*[:\-]?\s*(\d{9})", re.I)
_ACCT_RE    = re.compile(r"A/C\s*No\s*[:\-]?\s*(\d{10,})", re.I)
_CUSTID_RE  = re.compile(r"customer\s*id\s*[:\-]?\s*(\S+)", re.I)
_TYPE_RE    = re.compile(r"TYPE\s*[:\-]?\s*(.+?)(?:\s+currency\s*:|\s*$)", re.I)
_BRANCH_RE  = re.compile(r"branch\s*name\s*[:\-]?\s*(.+)", re.I)
_REQDATE_RE = re.compile(r"DATE\s*[:\-]?\s*(\d{2}-\d{2}-\d{4})", re.I)
_PERIOD_RE  = re.compile(
    r"for\s+the\s+period\s+from\s+(\d{2}-\d{2}-\d{4})\s+to\s+(\d{2}-\d{2}-\d{4})",
    re.I,
)

# Transaction anchor:
# "03-04-2024 BKIDN24094546264/... 15000.00 5519039.39 Dr"
# "13-06-2024 LIMIT CLOSURE ...    5589179.51 0.00"
_TXN_ANCHOR_RE = re.compile(
    r"^(\d{2}-\d{2}-\d{4})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})(?:\s+(Cr|Dr))?\s*$",
    re.I,
)

# Lines that mark the START of a new page header — stop continuation here
_PAGE_HEADER_RE = re.compile(
    r"^(Branch\s+Name\s*:|\d+$|Page\s+Total|Page\s+\d+\s+of|"
    r"This\s+is\s+a\s+system|Visit\s+us\s+at|"
    r"STATEMENT\s+OF\s+ACCOUNT\s+FOR|"
    r"DATE\s+PARTICULARS|[-=]{5,})",
    re.I,
)

# Rows to completely ignore
_IGNORE_RE = re.compile(
    r"^(page\s+total|b/f|brought\s+forward|[-=]{5,}|"
    r"date\s+particulars|this\s+is\s+a\s+system|"
    r"visit\s+us|page\s+\d+\s+of|grand\s+total|"
    r"branch\s+name|ifsc|ground\s+and|s\.v\.road|"
    r"mumbai\s+suburban|maharashtra\s+\d|ph:\s*0|"
    r"swift\s+code|mode\s+of\s+opr|"
    r"statement\s+of\s+account|"
    r"\d+$)",
    re.I,
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _parse_date(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%d-%m-%Y")
    except (ValueError, TypeError):
        return datetime.max


def _clean_amount(value) -> float | None:
    if value is None:
        return None
    s = re.sub(r"\s*(Dr|Cr)\.?\s*$", "", str(value), flags=re.I).strip()
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean_balance(raw_amt: str, suffix: str | None) -> float | None:
    amt = _clean_amount(raw_amt)
    if amt is None:
        return None
    if suffix and suffix.upper() == "DR":
        return -amt
    return amt


# ---------------------------------------------------------------------------
# ACCOUNT INFO
# ---------------------------------------------------------------------------
def extract_account_info(lines: list[str]) -> dict:
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    m = _MICR_RE.search(full_text)
    if m:
        info["micr"] = m.group(1)

    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1)

    m = _CUSTID_RE.search(full_text)
    if m:
        info["customer_id"] = m.group(1).strip()

    m = _TYPE_RE.search(full_text)
    if m:
        candidate = m.group(1).strip()
        if candidate and "ANY" not in candidate.upper() and len(candidate) > 3:
            info["acc_type"] = candidate

    m = _BRANCH_RE.search(full_text)
    if m:
        info["branch"] = m.group(1).strip()

    m = _REQDATE_RE.search(full_text)
    if m:
        info["statement_request_date"] = m.group(1)

    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = m.group(1)
        info["statement_period"]["to"]   = m.group(2)

    # Example raw line:
    # "M/S. AGRAWAL ASSOCIATES DATE: 30-12-2025"
    for line in lines[:25]:
        s = line.strip()
        if not s:
            continue
        if re.match(r"^M/S\.\s+", s, re.I):
            name = re.sub(r"\s+DATE\s*:.*$", "", s, flags=re.I).strip()
            if name:
                info["account_holder"] = name
                break

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    return extract_account_info(lines)


# ---------------------------------------------------------------------------
# TRANSACTIONS
# ---------------------------------------------------------------------------
def extract_transactions(pdf_path: str) -> list[dict]:
    transactions = []
    current_txn = None
    in_header = False
    prev_balance = None

    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_lines.extend(text.split("\n"))

    for raw in all_lines:
        line = raw.strip()
        if not line:
            continue

        if _PAGE_HEADER_RE.match(line):
            in_header = True

        if re.match(r"^DATE\s+PARTICULARS", line, re.I):
            in_header = False
            continue

        if _IGNORE_RE.match(line):
            continue

        if in_header:
            continue

        m = _TXN_ANCHOR_RE.match(line)
        if m:
            if current_txn is not None:
                transactions.append(current_txn)

            date_str   = m.group(1)
            desc_part  = m.group(2).strip()
            amt1_raw   = m.group(3)
            amt2_raw   = m.group(4)
            bal_suffix = m.group(5)

            balance = _clean_balance(amt2_raw, bal_suffix)

            debit = None
            credit = None

            if re.match(r"^b/?f$", desc_part, re.I):
                prev_balance = balance
                current_txn = None
                continue

            if prev_balance is not None and balance is not None:
                diff = round(balance - prev_balance, 2)
                if diff > 0:
                    credit = abs(diff)
                elif diff < 0:
                    debit = abs(diff)
            else:
                debit = _clean_amount(amt1_raw)

            current_txn = {
                "date": date_str,
                "description": desc_part,
                "ref_no": None,
                "debit": debit,
                "credit": credit,
                "balance": balance,
            }
            prev_balance = balance

        else:
            if current_txn is not None and not in_header:
                current_txn["description"] = (
                    current_txn["description"] + " " + line
                ).strip()

    if current_txn is not None:
        transactions.append(current_txn)

    _FOOTER_NOISE_RE = re.compile(
        r"\s*(Grand\s+Total|Page\s+Total|This\s+is\s+a).*$", re.I
    )
    for txn in transactions:
        txn["description"] = _FOOTER_NOISE_RE.sub("", txn["description"]).strip()

    transactions.sort(key=lambda t: _parse_date(t["date"]))

    for i, txn in enumerate(transactions):
        txn["_idx"] = i

    return transactions