import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "standard_chartered"
BANK_DISPLAY_NAME = "Standard Chartered Bank"


# =============================================================================
# STANDARD CHARTERED BANK — PDF FORMAT
# =============================================================================
#
# INFO BLOCK (pdfplumber merges left + right columns per line):
#   "PAPIERUS PACKAGING AND PAPER PRIVATE LIMITED Branch : STANDARD CHARTERED BANK"
#   "(Company Name)  Account Type : CA"
#   "M/S PAPIERUS PACKAGING AND PAPER PR  (Account Name)  Account Number : 24105901302"
#   "C/1, TRADE WORLD, 7 TH FLOORKAMALA CITY,, LOWER PAREL (W), .  (Address)  Currency : INR"
#   "Statement Date :    09 Feb 2025   to   09 Feb 2026"
#
# TRANSACTION TABLE — pdfplumber splits each row across TWO lines:
#   Line 1: "10 Apr 2025  RTGS|UTIBR62025041010097002..."  ← date + desc start
#   Line 2: "267,315.00  -88.50"                           ← amounts only
#   Line 3: "PAPIERUS PACKAGING|AXIS BANK..."              ← desc continuation
#
#   Columns : Date | Description | Withdrawal | Deposit | Balance
#   Balance  : can be NEGATIVE (overdraft CA) e.g. -89,997,619.50
#
# QUIRKS:
#   1. Amounts land on a SEPARATE line below the date line → _is_amounts_only()
#   2. Last txn on a page bleeds into next page's header as continuation lines
#      → _PAGE_HEADER_BLEED_PAT silently discards those lines
#   3. "(Company Name)" is merged with right-column label on same line:
#      "PAPIERUS PACKAGING... Branch : STANDARD CHARTERED BANK"
#      "(Company Name)  Account Type : CA"
#      → company name = lines[i-1] truncated at first right-column label
#   4. "LIMIT CHANGED" rows have no txn amount → delta=0 → debit=credit=None
# =============================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_DATE_LINE_PAT         = re.compile(r"^(\d{2}\s+[A-Za-z]{3}\s+\d{4})\s+(.*)")
_AMOUNT_PAT            = re.compile(r"-?[\d,]+\.\d{2}")
_BALANCE_FWD_PAT       = re.compile(r"balance\s+brought\s+forward\s+(-?[\d,]+\.\d{2})", re.I)
_AMOUNTS_ONLY_PAT      = re.compile(r"^-?[\d,]+\.\d{2}(\s+-?[\d,]+\.\d{2})*$")

# Account info
_COMPANY_NAME_LABEL    = re.compile(r"^\(Company\s*Name\)", re.I)
_RIGHT_COL_LABEL       = re.compile(
    r"\s+(?:Branch|Account\s*Type|Account\s*Number|Account\s*Name|Currency|Statement\s*Date)\s*[:\-]",
    re.I,
)
_ACCT_NO_PAT           = re.compile(r"account\s*number\s*[:\-]?\s*(\d{8,20})", re.I)
_ACCT_TY_PAT           = re.compile(r"account\s*type\s*[:\-]?\s*(\w+)", re.I)
_CURRENCY_PAT          = re.compile(r"currency\s*[:\-]?\s*([A-Z]{3})", re.I)
_STMT_DATE_PAT         = re.compile(
    r"statement\s*date\s*[:\-]?\s*"
    r"(\d{2}\s+[A-Za-z]{3}\s+\d{4})\s+to\s+(\d{2}\s+[A-Za-z]{3}\s+\d{4})",
    re.I,
)

# Page boilerplate lines — skip entirely
_SKIP_PAT = re.compile(
    r"^(Statement\s+of\s+Account"
    r"|Thank\s+you\s+for\s+banking"
    r"|Page\s+\d+\s+of\s+\d+"
    r"|Generated\s+on\s*:"
    r"|Date\s+Description\s+Withdrawal"
    r"|\(Company\s*Name\)"
    r"|\(Address\)"
    r"|\(Account(\s*Name)?\)"
    r"|Branch\s*:.*Standard\s+Chartered"
    r"|Account\s*Type\s*:"
    r"|Account\s*Number\s*:"
    r"|Currency\s*:"
    r"|Statement\s*Date\s*:)",
    re.I,
)

# Page header lines that bleed into last transaction's description
_PAGE_HEADER_BLEED_PAT = re.compile(
    r"(Branch\s*:\s*Standard\s+Chartered"
    r"|\(Company\s*Name\)"
    r"|\(Account(\s*Name)?\)"
    r"|\(Address\)"
    r"|Statement\s+of\s+Account"
    r"|Thank\s+you\s+for\s+banking"
    r"|Account\s*Type\s*:"
    r"|Account\s*Number\s*:"
    r"|Currency\s*:"
    r"|Statement\s*Date\s*:)",
    re.I,
)

_TYPE_MAP = {
    "CA": "Current Account",
    "SA": "Savings Account",
    "CC": "Cash Credit",
    "OD": "Overdraft",
}


# ---------------------------------
# HELPERS
# ---------------------------------
def _parse_amount(s: str) -> float | None:
    if not s:
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_date_str(s: str) -> str:
    """Convert 'DD Mon YYYY' → 'DD-MM-YYYY'."""
    try:
        return datetime.strptime(s.strip(), "%d %b %Y").strftime("%d-%m-%Y")
    except ValueError:
        return s.strip()


def _strip_amounts(text: str) -> str:
    """Remove amount strings from description text."""
    return re.sub(r"\s{2,}", " ", _AMOUNT_PAT.sub("", text)).strip()


def _is_skip(line: str) -> bool:
    return bool(_SKIP_PAT.match(line.strip()))


def _is_amounts_only(line: str) -> bool:
    """
    True if line contains ONLY amount values.
    e.g. "267,315.00  -88.50"  or  "-88.50"
    Rejects "INR|267315.00|1.00" (has pipe chars).
    """
    return bool(_AMOUNTS_ONLY_PAT.match(line.strip()))


def _assign_amounts(
    amounts: list[str], last_balance: float | None
) -> tuple[float | None, float | None, float | None]:
    """
    Given list of amount strings, return (debit, credit, balance).
    Uses balance delta vs last_balance to decide debit vs credit.
    delta == 0  → LIMIT CHANGED / no-money row → debit=credit=None
    """
    debit = credit = balance = None

    if not amounts:
        return debit, credit, balance

    balance = _parse_amount(amounts[-1])

    if len(amounts) >= 2:
        txn_amt = _parse_amount(amounts[-2])
        if txn_amt is not None and last_balance is not None and balance is not None:
            delta = round(balance - last_balance, 2)
            if delta > 0:
                credit = txn_amt
            elif delta < 0:
                debit = txn_amt

    return debit, credit, balance


def _clean_desc(desc: str) -> str:
    """
    Deduplicate SCB repeated prefix in descriptions.
    "CAN#263920 PO CANCELLATION CAN#263920 PO CANCELLATION M/S..."
    "RTGS|UTIBR... RTGS|UTIBR... PAPIERUS..."
    """
    desc = re.sub(r"\s{2,}", " ", desc).strip()
    # Single token repeat
    m = re.match(r"^(\S+)\s+\1\b(.*)", desc, re.S)
    if m:
        return (m.group(1) + m.group(2)).strip()
    # Multi-word prefix repeat (up to 6 words)
    words = desc.split()
    for n in range(min(6, len(words) // 2), 0, -1):
        prefix = " ".join(words[:n])
        rest   = " ".join(words[n:])
        if rest.startswith(prefix):
            return (prefix + " " + rest[len(prefix):]).strip()
    return desc


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["branch"]    = "Standard Chartered Bank"

    full_text = "\n".join(lines)

    # Account holder:
    # pdfplumber merges left + right columns, so the line BEFORE "(Company Name)"
    # looks like: "PAPIERUS PACKAGING... Branch : STANDARD CHARTERED BANK"
    # We grab lines[i-1] and truncate at the first right-column label.
    for i, line in enumerate(lines[:10]):
        if _COMPANY_NAME_LABEL.match(line.strip()) and i > 0:
            candidate = lines[i - 1].strip()
            # Truncate at right-column label e.g. " Branch :"
            trunc = _RIGHT_COL_LABEL.split(candidate)[0].strip()
            if len(trunc) >= 5:
                info["account_holder"] = trunc
                break

    # Account number
    m = _ACCT_NO_PAT.search(full_text)
    if m:
        info["account_number"] = m.group(1).strip()

    # Account type
    m = _ACCT_TY_PAT.search(full_text)
    if m:
        raw = m.group(1).strip().upper()
        info["acc_type"] = _TYPE_MAP.get(raw, raw)

    # Currency
    m = _CURRENCY_PAT.search(full_text)
    if m:
        info["currency"] = m.group(1).strip()

    # Statement period — "DD Mon YYYY to DD Mon YYYY" → DD-MM-YYYY
    m = _STMT_DATE_PAT.search(full_text)
    if m:
        info["statement_period"]["from"] = _parse_date_str(m.group(1))
        info["statement_period"]["to"]   = _parse_date_str(m.group(2))

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Dispatcher-compatible wrapper."""
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Parse Standard Chartered Bank PDF statement via raw text lines.

    Key behaviour:
      - Amounts land on a SEPARATE line below the date+description line.
        Detected via _is_amounts_only() and assigned to the pending transaction.
      - Page header lines bleed into the last transaction of each page as
        continuation text. Detected via _PAGE_HEADER_BLEED_PAT and discarded.
      - Debit vs Credit determined by balance delta vs previous balance.
      - "LIMIT CHANGED" rows produce delta=0 → debit=None, credit=None.
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

        # ── Opening / carried-forward balance ──
        m = _BALANCE_FWD_PAT.search(line)
        if m:
            last_balance = _parse_amount(m.group(1))
            continue

        # ── Amounts-only line ──
        # pdfplumber splits "267,315.00  -88.50" onto its own line.
        # Assign to the pending transaction that still has balance=None.
        if _is_amounts_only(line):
            if current is not None and current["balance"] is None:
                amounts = _AMOUNT_PAT.findall(line)
                debit, credit, balance = _assign_amounts(amounts, last_balance)
                current["debit"]   = debit
                current["credit"]  = credit
                current["balance"] = balance
                last_balance = balance
            continue

        # ── New transaction date line ──
        m = _DATE_LINE_PAT.match(line)
        if m:
            if current is not None:
                current["description"] = _clean_desc(current["description"])
                transactions.append(current)

            date_str  = _parse_date_str(m.group(1))
            remainder = m.group(2).strip()
            amounts   = _AMOUNT_PAT.findall(remainder)

            if amounts:
                # Amounts present on same line as date (less common)
                debit, credit, balance = _assign_amounts(amounts, last_balance)
                last_balance = balance
            else:
                # Amounts expected on next line
                debit = credit = balance = None

            current = {
                "date":        date_str,
                "description": _strip_amounts(remainder),
                "ref_no":      None,
                "debit":       debit,
                "credit":      credit,
                "balance":     balance,
            }

        else:
            # ── Continuation line ──
            if current is None or _is_skip(line):
                continue

            # Discard page header lines bleeding into last txn of a page
            if _PAGE_HEADER_BLEED_PAT.search(line):
                continue

            current["description"] = (
                current["description"] + " " + line
            ).strip()

    # Flush last pending transaction
    if current is not None:
        current["description"] = _clean_desc(current["description"])
        transactions.append(current)

    transactions.sort(key=_sort_key)
    return transactions