import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY = "standard_chartered"
BANK_DISPLAY_NAME = "Standard Chartered Bank"

# ─────────────────────────────────────────────────────────────
# PATTERNS
# ─────────────────────────────────────────────────────────────

DATE_LINE_PAT   = re.compile(r"^(\d{2}\s+[A-Za-z]{3}\s+\d{4})\s+(.*)")
AMOUNT_PAT      = re.compile(r"-?[\d,]+\.\d{2}")
BALANCE_FWD_PAT = re.compile(r"Balance Brought Forward\s+(-?[\d,]+\.\d{2})", re.I)

# Account info — extracted from the first line which looks like:
# "PAPIERUS PACKAGING AND PAPER PRIVATE LIMITED Branch : STANDARD CHARTERED BANK"
HOLDER_PAT      = re.compile(r"^(.+?)\s+Branch\s*:", re.I)
ACCOUNT_NO_PAT  = re.compile(r"Account\s*Number\s*[:\-]?\s*(\d{8,20})", re.I)
ACCOUNT_TY_PAT  = re.compile(r"Account\s*Type\s*[:\-]?\s*(\w+)", re.I)
CURRENCY_PAT    = re.compile(r"Currency\s*[:\-]?\s*([A-Z]{3})", re.I)
STMT_DATE_PAT   = re.compile(
    r"Statement\s*Date\s*[:\-]?\s*"
    r"(\d{2}\s+[A-Za-z]{3}\s+\d{4})\s+to\s+(\d{2}\s+[A-Za-z]{3}\s+\d{4})",
    re.I
)

# Lines to skip when building descriptions (page boilerplate repeated on every page)
SKIP_LINE_PAT = re.compile(
    r"^(Statement of Account"
    r"|Thank you for banking"
    r"|Page \d+\s+of\s+\d+"
    r"|Generated on\s*:"
    r"|Date\s+Description\s+Withdrawal"
    r"|\(Company Name\)"
    r"|\(Address\)"
    r"|\(Account(\s*Name)?\)"
    r"|Name\)$"
    r"|M/S\s+[A-Z]"
    r"|C/1,"
    r"|PAREL\s*\(W\)"
    r"|Branch\s*:.*STANDARD CHARTERED"
    r"|Account\s*Type\s*:"
    r"|Account\s*Number\s*:"
    r"|Currency\s*:"
    r"|Statement\s*Date\s*:)",
    re.I
)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _parse_amount(s: str):
    try:    return float(str(s).replace(",", "").strip())
    except: return None

def _parse_date(s: str) -> str:
    try:    return datetime.strptime(s.strip(), "%d %b %Y").strftime("%d-%m-%Y")
    except: return s.strip()

def _strip_amounts(text: str) -> str:
    return re.sub(r"\s{2,}", " ", AMOUNT_PAT.sub("", text)).strip()

def _is_skip(line: str) -> bool:
    return bool(SKIP_LINE_PAT.match(line.strip()))

def _clean_desc(desc: str) -> str:
    """
    SCB repeats the first token on the same line:
    "RTGS|UTIBR... RTGS|UTIBR... PAPIERUS" → deduplicate.
    "PIPALIIN02A00001 PIPALIIN02A00001 JITO" → deduplicate.
    """
    desc = re.sub(r"\s{2,}", " ", desc).strip()
    m = re.match(r"^(\S+)\s+\1\s+(.*)", desc)
    if m:
        desc = m.group(1) + " " + m.group(2).strip()
    return desc


# ─────────────────────────────────────────────────────────────
# ACCOUNT INFO EXTRACTION
# ─────────────────────────────────────────────────────────────

def extract_account_info(lines):
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["branch"]    = "Standard Chartered Bank"

    full_text = " ".join(line.strip() for line in lines if line)

    # Account holder: SCB always puts it on the SECOND line (index 1) as:
    # "PAPIERUS PACKAGING AND PAPER PRIVATE LIMITED Branch : STANDARD CHARTERED BANK"
    # We extract everything before "Branch :" on that line.
    # We do NOT loop all lines because later lines like "LIMIT CHANGED TO ACTIVELIMITLIENAMT"
    # could accidentally match if iterated.
    for line in lines[1:5]:   # check lines 1-4 only (true header block)
        line = line.strip()
        if not line:
            continue
        m = HOLDER_PAT.match(line)
        if m:
            candidate = m.group(1).strip()
            # Reject noise lines — must be at least 10 chars and not a system message
            # Note: check "ACTIVELIMIT" not "LIMIT" — company names can end in "LIMITED"
            if len(candidate) >= 10 and "ACTIVELIMIT" not in candidate.upper():
                info["account_holder"] = candidate
                break

    # Account number
    m = ACCOUNT_NO_PAT.search(full_text)
    if m:
        info["account_number"] = m.group(1).strip()

    # Account type
    m = ACCOUNT_TY_PAT.search(full_text)
    if m:
        raw = m.group(1).strip()
        # Map short codes to full names
        type_map = {"CA": "Current Account", "SA": "Savings Account", "CC": "Cash Credit"}
        info["acc_type"] = type_map.get(raw.upper(), raw)

    # Currency
    m = CURRENCY_PAT.search(full_text)
    if m:
        info["currency"] = m.group(1).strip()

    # Statement period
    m = STMT_DATE_PAT.search(full_text)
    if m:
        info["statement_period"]["from"] = m.group(1).strip()
        info["statement_period"]["to"]   = m.group(2).strip()

    return info


# ─────────────────────────────────────────────────────────────
# OPENING / CLOSING BALANCE
# ─────────────────────────────────────────────────────────────

def extract_summary_balances(pdf_path, info):
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                m = BALANCE_FWD_PAT.search(line)
                if m and info.get("opening_balance") is None:
                    info["opening_balance"] = _parse_amount(m.group(1))


# ─────────────────────────────────────────────────────────────
# TRANSACTION EXTRACTION
# ─────────────────────────────────────────────────────────────

def extract_transactions(pdf_path: str):
    """
    Parse Standard Chartered Bank PDF statement via raw text.

    Format:
      DD Mon YYYY  <description_part>  [txn_amount]  <balance>
      [continuation lines...]

    Debit vs Credit → balance delta vs previous balance.
    LIMIT CHANGED rows → delta=0 → no debit/credit.
    """
    transactions = []
    current      = None
    last_balance = None

    with pdfplumber.open(pdf_path) as pdf:
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split("\n"))

    for raw in all_lines:
        line = raw.strip()
        if not line or _is_skip(line):
            continue

        # Opening balance
        m = BALANCE_FWD_PAT.search(line)
        if m:
            last_balance = _parse_amount(m.group(1))
            continue

        # ── New transaction ──
        m = DATE_LINE_PAT.match(line)
        if m:
            if current is not None:
                current["description"] = _clean_desc(current["description"])
                transactions.append(current)

            date_str  = _parse_date(m.group(1))
            remainder = m.group(2).strip()
            amounts   = AMOUNT_PAT.findall(remainder)

            balance = txn_amount = None
            if len(amounts) >= 2:
                balance    = _parse_amount(amounts[-1])
                txn_amount = _parse_amount(amounts[-2])
            elif len(amounts) == 1:
                balance = _parse_amount(amounts[-1])

            debit = credit = None
            if balance is not None and last_balance is not None:
                delta = round(balance - last_balance, 2)
                if txn_amount is None and delta != 0:
                    txn_amount = abs(delta)
                if delta > 0 and txn_amount:
                    credit = txn_amount
                elif delta < 0 and txn_amount:
                    debit = txn_amount

            current = {
                "date":        date_str,
                "description": _strip_amounts(remainder),
                "debit":       debit,
                "credit":      credit,
                "balance":     balance,
            }
            last_balance = balance

        else:
            # ── Continuation line ──
            if current is not None and not _is_skip(line):
                current["description"] = (current["description"] + " " + line).strip()

    if current is not None:
        current["description"] = _clean_desc(current["description"])
        transactions.append(current)

    return transactions