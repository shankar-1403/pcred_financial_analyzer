import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "cosmos"
BANK_DISPLAY_NAME = "The Cosmos Co-op. Bank Ltd."


# ---------------------------------------------------------------------------
# REGEX PATTERNS
# ---------------------------------------------------------------------------
IFSC_PATTERN   = r"\b(COSB[A-Z0-9]{7})\b"
PERIOD_PATTERN = r"period\s+of\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})"

_REQ_DATE_RE   = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{4}")

# Transaction line: starts with DD/MM/YYYY
_TXN_LINE_RE   = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.+)$")

# Amount + balance at end: "... 12,500.00  81592.99 CR"
_AMOUNT_BAL_RE = re.compile(
    r"^(.*?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+CR\s*$"
)

# Skip known header/footer lines before any date check
_SKIP_RE = re.compile(
    r"^("
    r"statement\s+of\s+account|"
    r"customer\s+id|"
    r"account\s+(number|holder)|"
    r"date\s+transaction|"
    r"sub\s*total|"
    r"grand\s*total|"
    r"\*+\s*end\s*of\s*statement|"
    r"head\s*office|"
    r"page\s*\d"
    r")",
    re.I
)

# Debit keyword fallback for first transaction (no prev balance to delta against)
_DEBIT_KEYWORDS_RE = re.compile(
    r"\b(withdrawal|debit|dr|charges?|cgst|sgst|payment|cwdr|"
    r"nach-10-dr|ib~to\s+trf|ib~.*card\s+payment)\b",
    re.I
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _reformat_date(date_str: str) -> str:
    """DD/MM/YYYY → DD-MM-YYYY"""
    return (date_str or "").replace("/", "-")


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


# ---------------------------------------------------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------------------------------------------------
def extract_account_info(lines):
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Statement period
    m = re.search(PERIOD_PATTERN, full_text, re.I)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    # Statement request date — "14-Jan-2025"
    m = _REQ_DATE_RE.search(full_text)
    if m:
        info["statement_request_date"] = m.group()

    # IFSC
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    # Branch / MICR (if present in this format)
    m = re.search(r"branch\s*[:\-]\s*([A-Za-z0-9\s,]+?)(?:\n|$)", full_text, re.I)
    if m:
        info["branch"] = m.group(1).strip()

    m = re.search(r"micr\s*(?:code)?\s*[:\-]\s*(\d{9})", full_text, re.I)
    if m:
        info["micr"] = m.group(1)

    # Header block fields — first 5 lines
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
            m = re.search(r"account\s*number\s+([\d\.e\+]+)", line_s, re.I)
            if m:
                try:
                    info["account_number"] = str(int(float(m.group(1))))
                except (ValueError, TypeError):
                    info["account_number"] = m.group(1).strip()
                continue

        if info["account_holder"] is None:
            m = re.search(r"account\s*holder\s*name\s+(.+)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()
                continue

    return info


# ---------------------------------------------------------------------------
# TRANSACTION EXTRACTION — raw text based (NOT table extraction)
#
# WHY raw text instead of pdfplumber tables:
#   Cosmos PDFs have severely broken table borders — each page produces 5-10
#   fragmented mini-tables, most with no header row. Table extraction silently
#   drops any row that falls between border fragments.
#
#   Raw text via page.extract_text() always contains every transaction line.
#   Each line is: DATE  DESCRIPTION  AMOUNT  BALANCE CR
#   Debit vs credit is determined by balance delta (prev → curr).
#
# DEDUP STRATEGY — (date, description, balance):
#   Using only (date, balance) is WRONG — 128 real transactions share
#   a balance value with another transaction (verified against GrandTotal).
#   Using (date, description, balance) has zero false positives.
# ---------------------------------------------------------------------------
def extract_transactions(pdf_path: str):
    raw = _parse_raw_lines(pdf_path)
    return _assign_debit_credit(raw)


def _parse_raw_lines(pdf_path: str) -> list:
    """
    Extract every transaction line from raw PDF text.
    Returns list of dicts: {date_raw, description, amount, balance}
    """
    results   = []
    seen_keys = set()   # (date, description, balance) — safe dedup, zero false positives

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # Skip known header/footer patterns
                if _SKIP_RE.match(line):
                    continue

                # Must start with DD/MM/YYYY
                m_line = _TXN_LINE_RE.match(line)
                if not m_line:
                    continue

                date_raw = m_line.group(1)
                rest     = m_line.group(2).strip()

                # Must end with <amount> <balance> CR
                m_amt = _AMOUNT_BAL_RE.match(rest)
                if not m_amt:
                    continue

                description = re.sub(r"\s+", " ", m_amt.group(1).strip())
                amount      = float(m_amt.group(2).replace(",", ""))
                balance     = float(m_amt.group(3).replace(",", ""))

                # Dedup using (date, description, balance)
                # NOTE: (date, balance) alone is NOT safe — verified 128 real
                # transactions share balance values with other transactions.
                key = (date_raw, description, balance)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                results.append({
                    "date_raw":    date_raw,
                    "description": description,
                    "amount":      amount,
                    "balance":     balance,
                })

    return results


def _assign_debit_credit(raw_txns: list) -> list:
    """
    Cosmos raw text has only ONE amount column (not separate debit/credit).
    Determine debit vs credit by comparing current balance to previous balance:
      balance went UP   → credit (money came in)
      balance went DOWN → debit  (money went out)

    First transaction has no previous balance — use description keywords as fallback.
    """
    transactions = []

    for i, t in enumerate(raw_txns):
        prev_balance = raw_txns[i - 1]["balance"] if i > 0 else None

        if prev_balance is not None:
            delta     = round(t["balance"] - prev_balance, 2)
            is_credit = delta >= 0
        else:
            # First transaction — no delta available, use keyword fallback
            is_credit = not bool(_DEBIT_KEYWORDS_RE.search(t["description"]))

        transactions.append({
            "date":        _reformat_date(t["date_raw"]),
            "description": t["description"],
            "cheque_no":   None,
            "debit":       None          if is_credit else t["amount"],
            "credit":      t["amount"]   if is_credit else None,
            "balance":     t["balance"],
        })

    # Cosmos PDFs are oldest-first — stable sort preserves same-day sequence
    transactions.sort(key=_sort_key)

    return transactions