import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "idbi"
BANK_DISPLAY_NAME = "IDBI Bank"


# =============================================================================
# IDBI BANK — PDF FORMAT (Net Banking Statement)
# =============================================================================
#
# INFO BLOCK (page 1, plain text):
#   "Primary Account Holder Name : RAGHAV ROADLINES"
#   "Address : SHOP NO 6 MALAYA BLDG AT ROTH KHURDH PO VARSE"
#   "NR H P PETROL PUMP ROHA RAIGAD"
#   "RAIGAD"
#   "MAHARASHTRA"
#   "INDIA"
#   "402116"
#   "Account No : 1.597102000004442e+15"      ← scientific notation!
#   "Customer ID : 90691795"
#   "Account Branch : Roha-Raigad (Sol -1597)"
#   "Nominee Registered : : Yes"
#   "CKYC Number : NA"
#   "Transaction Date From : 01/04/2024 to: 31/03/2025 A/C NO: 1.597102000004442e+15"
#
# TRANSACTION TABLE HEADER:
#   "Srl Txn Date Value Date Description CR/DR Amount (INR) Balance (INR)"
#   "No Y"   ← second header line — skip it
#
# TRANSACTION ROWS — ALL on a SINGLE line per transaction:
#   "1 24/03/2025 05:10:55 PM 24/03/2025 UPI/8.8101195572e+10/MUSKAN A MALANI Dr. INR 75,000.00 5,117.55"
#   "7 21/03/2025 04:02:59 PM 21/03/2025 NEFT-HDFCN52025032129732834-VINATI ORGANICS Cr. INR 7,73,684.00 7,80,117.55"
#
#   Format:  <srl>  <DD/MM/YYYY HH:MM:SS AM/PM>  <DD/MM/YYYY>  <description>  <Dr.|Cr.>  INR  <amount>  <balance>
#
# QUIRKS:
#   1. Account number in scientific notation: 1.597102000004442e+15
#      → int(float(raw)) = 1597102000004442
#   2. Txn date has TIMESTAMP: "24/03/2025 05:10:55 PM" — strip the time part
#   3. Some rows have ISO timestamp: "2025-02-08 19:36:08.000 08/02/2025 ..."
#      → use the VALUE DATE (second date) for consistency
#   4. CR/DR is explicit: "Dr." = debit, "Cr." = credit — no delta math needed
#   5. Indian number format: 7,73,684.00 (lakh separator) — clean commas only
#   6. Statement summary at end: "Dr Count Cr Count Debits Credits" — skip it
#   7. Balance shown as Indian format: 7,80,117.55 → 780117.55
# =============================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------

# Transaction row:
# Group 1: serial number
# Group 2: txn date (DD/MM/YYYY or YYYY-MM-DD timestamp)
# Group 3: optional time (HH:MM:SS AM/PM) — may not exist
# Group 4: value date (DD/MM/YYYY)
# Group 5: description
# Group 6: CR/DR indicator (Dr. or Cr.)
# Group 7: amount
# Group 8: balance

_TXN_ROW_PAT = re.compile(
    r"^(\d+)\s+"
    # Txn date — either DD/MM/YYYY or YYYY-MM-DD ISO with optional timestamp
    r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2}\.\d+)?)"
    r"(?:\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM))?\s+"
    # Value date DD/MM/YYYY
    r"(\d{2}/\d{2}/\d{4})\s+"
    # Description (non-greedy, stops before Dr./Cr.)
    r"(.+?)\s+"
    # CR/DR
    r"(Dr\.|Cr\.)\s+INR\s+"
    # Amount (Indian format)
    r"([\d,]+\.\d{2})\s+"
    # Balance
    r"(-?[\d,]+\.\d{2})"
    r"\s*$"
)

# Account info
_HOLDER_PAT    = re.compile(r"primary\s+account\s+holder\s+name\s*[:\-]\s*(.+)", re.I)
_ACCT_NO_PAT   = re.compile(r"account\s*no\s*[:\-]\s*([\d.e+E]+)", re.I)
_CUST_ID_PAT   = re.compile(r"customer\s*id\s*[:\-]\s*(\d+)", re.I)
_BRANCH_PAT    = re.compile(r"account\s*branch\s*[:\-]\s*(.+)", re.I)
_PERIOD_PAT    = re.compile(
    r"transaction\s+date\s+from\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})\s+to\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
    re.I,
)

# Lines to skip
_SKIP_PAT = re.compile(
    r"^(IDBI\s+Bank\s+Ltd\."
    r"|Our\s+Toll"
    r"|Page\s+\d+\s+of\s+\d+"
    r"|Srl\s+Txn\s+Date"
    r"|No\s+Y$"
    r"|Statement\s+Summary"
    r"|Dr\s+Count\s+Cr\s+Count"
    r"|This\s+is\s+an\s+account\s+statement"
    r"|Important\s+Information"
    r"|Contents\s+of\s+this\s+statement"
    r"|DO\s+NOT\s+reply"
    r"|debit,\s*credit"
    r"|statement\.)",
    re.I,
)


# ---------------------------------
# HELPERS
# ---------------------------------
def _parse_sci_int(raw: str) -> str | None:
    """Convert scientific notation account number to string."""
    try:
        return str(int(float(raw.strip())))
    except (ValueError, TypeError):
        return None


def _parse_amount(s: str) -> float | None:
    """Parse Indian number format: 7,73,684.00 → 773684.0"""
    if not s:
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_txn_date(raw: str) -> str:
    """
    Convert transaction date to DD-MM-YYYY.
    Handles:
      DD/MM/YYYY             → DD-MM-YYYY
      YYYY-MM-DD HH:MM:SS... → DD-MM-YYYY  (use value date instead — see parser)
    """
    raw = raw.strip().split()[0]  # strip any timestamp suffix
    for fmt in ["%d/%m/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(raw, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return raw


def _parse_value_date(raw: str) -> str:
    """Convert DD/MM/YYYY → DD-MM-YYYY."""
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except ValueError:
        return raw.strip()


def _is_skip(line: str) -> bool:
    return bool(_SKIP_PAT.match(line.strip()))

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
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Account holder
    m = _HOLDER_PAT.search(full_text)
    if m:
        info["account_holder"] = m.group(1).strip()

    # Account number — scientific notation safe
    m = _ACCT_NO_PAT.search(full_text)
    if m:
        info["account_number"] = _parse_sci_int(m.group(1)) or m.group(1).strip()

    # Customer ID
    m = _CUST_ID_PAT.search(full_text)
    if m:
        info["customer_id"] = m.group(1).strip()

    # Branch
    m = _BRANCH_PAT.search(full_text)
    if m:
        info["branch"] = m.group(1).strip()

    # Statement period — DD/MM/YYYY → DD-MM-YYYY
    m = _PERIOD_PAT.search(full_text)
    if m:
        info["statement_period"]["from"] = _parse_value_date(m.group(1))
        info["statement_period"]["to"]   = _parse_value_date(m.group(2))

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Dispatcher-compatible wrapper."""
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Parse IDBI Bank PDF statement.

    Every transaction is on a SINGLE line:
      <srl>  <txn_date [time]>  <value_date>  <description>  <Dr.|Cr.>  INR  <amount>  <balance>

    CR/DR is explicit → no balance-delta math needed.
    Use VALUE DATE for the transaction date (more reliable, no timestamp noise).

    SORT ORDER FIX:
    ---------------
    Transactions are sorted by their PDF serial number (srl) in ASCENDING order.
    This preserves the bank's original intra-day ordering so the balance chain
    remains intact and opening/closing balances are correct.

    Previously, sorting by date alone caused same-date transactions to be
    reordered arbitrarily, breaking the balance sequence.
    """
    transactions = []

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

        m = _TXN_ROW_PAT.match(line)
        if not m:
            continue

        srl         = int(m.group(1))          # ← PDF serial number (bank's ordering)
        value_date  = _parse_value_date(m.group(3))
        description = m.group(4).strip()
        cr_dr       = m.group(5).strip()
        amount      = _parse_amount(m.group(6))
        balance     = _parse_amount(m.group(7))

        debit  = amount if cr_dr == "Dr." else None
        credit = amount if cr_dr == "Cr." else None

        transactions.append({
            "_srl":        srl,            # temporary — used for sorting, removed before return
            "date":        value_date,
            "description": description,
            "ref_no":      None,
            "debit":       debit,
            "credit":      credit,
            "balance":     balance,
        })

    # -------------------------------------------------------------------
    # Sort by PDF serial number (ascending) — preserves the bank's exact
    # intra-day ordering so the balance chain is always correct.
    # DO NOT sort by date: multiple transactions on the same date would
    # be reordered arbitrarily, breaking the running balance.
    # -------------------------------------------------------------------
    transactions.sort(key=lambda t: t["_srl"])

    # Assign row_id after sorting, then remove the internal _srl field
    for i, txn in enumerate(transactions, 1):
        txn["row_id"] = i
        del txn["_srl"]

    
    transactions.sort(key=lambda t: t["row_id"], reverse=True)
    return transactions