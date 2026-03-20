import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "standard_chartered"
BANK_DISPLAY_NAME = "Standard Chartered Bank"

# =====================================================================
# STANDARD CHARTERED BANK — PDF Statement Parser
#
# LAYOUT (repeated on every page):
#   Header block:
#     "COMPANY NAME  Branch : STANDARD CHARTERED BANK"
#     "(Company Name)"
#     "Account Type  : CA"
#     "M/S ... (Account"
#     "Account Number : XXXXXXXXXX"
#     "Name)"
#     "Currency : INR"
#     "C/1, TRADE WORLD... (Address)"
#     "Statement Date : DD Mon YYYY to DD Mon YYYY"
#     "PAREL (W), . (Address)"
#     "Date  Description  Withdrawal  Deposit  Balance"
#
#   Opening line:
#     "Balance Brought Forward  -NNN,NNN.NN"
#
#   Transaction lines (two patterns):
#     WITH amount:
#       "DD Mon YYYY  DESC_START  AMOUNT  BALANCE"
#     WITHOUT amount (e.g. LIMIT CHANGED):
#       "DD Mon YYYY  DESC_START  BALANCE"
#
#   Continuation lines (no date prefix) append to current transaction.
#   The PDF duplicates the first word(s) of each description on the
#   first continuation line — deduplicated via _append_continuation().
#
#   Footer per page:
#     "Thank you for banking with Standard Chartered..."
#     "Page N of NNN"
#     "Generated on : DD Mon YYYY"
#
# DEBIT / CREDIT:
#   Determined by balance delta (balance increase → credit/deposit;
#   balance decrease → debit/withdrawal).
#   LIMIT CHANGED lines carry no amount — debit=None, credit=None.
#
# DATE FORMAT:
#   Input:  "DD Mon YYYY"  (e.g. "10 Apr 2025")
#   Output: "DD-MM-YYYY"
# =====================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------

# Transaction line WITH two amounts: date + desc + amount + balance
_TXN_RE = re.compile(
    r'^(\d{2}\s+\w{3}\s+\d{4})\s+'    # date: "DD Mon YYYY"
    r'(.+?)\s+'                          # description start (non-greedy)
    r'(-?[\d,]+\.\d{2})\s+'             # withdrawal or deposit amount
    r'(-?[\d,]+\.\d{2})\s*$'            # running balance
)

# Transaction line with ONE number only (balance, no dr/cr amount)
# e.g. "29 Apr 2025 LIMIT CHANGED TO ACTIVELIMITLIENAMT -88.50"
_TXN_NO_AMT_RE = re.compile(
    r'^(\d{2}\s+\w{3}\s+\d{4})\s+'
    r'(.+?)\s+'
    r'(-?[\d,]+\.\d{2})\s*$'
)

# Lines to skip (page headers, footers, column headers)
_SKIP_RE = re.compile(
    r'^Statement of Account$|'
    r'^Date\s+Description\s+Withdrawal|'
    r'^Thank you for banking|'
    r'^Page\s+\d+\s+of\s+\d+|'
    r'^Generated on\s*:|'
    r'^\(Company Name\)$|'
    r'^\(Account$|'                     # split across lines
    r'^Name\)$|'
    r'^\(Address\)$|'
    r'^Account\s+Type\s*:|'
    r'^Account\s+Number\s*:|'
    r'^Currency\s*:|'
    r'^Statement\s+Date\s*:|'
    r'^Branch\s*:',
    re.I
)

# Header content lines that repeat every page (address, company name row)
_HEADER_CONTENT_RE = re.compile(
    r'Branch\s*:\s*STANDARD CHARTERED|'
    r'C/1,\s*TRADE WORLD|'
    r'PAREL\s*\(W\)|'
    r'PAPIERUS PACKAGING AND PAPER PRIVATE LIMITED\s+Branch',
    re.I
)

# Opening / closing balance
_OPEN_BAL_RE  = re.compile(
    r'Balance\s+Brought\s+Forward\s+(-?[\d,]+\.\d{2})', re.I
)
_CLOSE_BAL_RE = re.compile(
    r'Closing\s+Balance\s+(-?[\d,]+\.\d{2})', re.I
)

# Account info patterns
_ACCT_NO_RE   = re.compile(r'Account\s+Number\s*:\s*(\d+)', re.I)
_ACCT_TYPE_RE = re.compile(r'Account\s+Type\s*:\s*(\S+)', re.I)
_CURRENCY_RE  = re.compile(r'Currency\s*:\s*([A-Z]{3})', re.I)
_BRANCH_RE    = re.compile(r'Branch\s*:\s*(.+)', re.I)
_STMT_DATE_RE = re.compile(
    r'Statement\s+Date\s*:\s*(\d{2}\s+\w+\s+\d{4})\s+to\s+(\d{2}\s+\w+\s+\d{4})',
    re.I
)
# Company name is first line before "(Company Name)"
# Account name is "M/S ... (Account" line before "Name)"


# ---------------------------------
# HELPERS
# ---------------------------------

def _ca(value):
    """Clean and parse a number string to float."""
    if not value:
        return None
    try:
        return float(str(value).strip().replace(',', ''))
    except ValueError:
        return None


def _parse_date(s):
    """Convert 'DD Mon YYYY' → 'DD-MM-YYYY'."""
    try:
        return datetime.strptime(s.strip(), '%d %b %Y').strftime('%d-%m-%Y')
    except ValueError:
        return s.strip()


def _append_continuation(current_desc, cont_line):
    """
    Append a continuation line to the current description, removing any
    duplicate prefix that the PDF echoes from the transaction header line.

    Standard Chartered PDFs repeat the first token(s) of the description
    on the next line, e.g.:
      Header line desc:  "RTGS|UTIBR62025041010097002"
      Continuation line: "RTGS|UTIBR62025041010097002 PAPIERUS PACKAGING..."
    → result: "RTGS|UTIBR62025041010097002 PAPIERUS PACKAGING..."
    """
    cont = cont_line.strip()
    if not cont:
        return current_desc

    curr_words = current_desc.split()
    cont_words = cont.split()

    # Try longest-first prefix match of cont against the END of current_desc
    for n in range(min(8, len(curr_words), len(cont_words)), 0, -1):
        if curr_words[-n:] == cont_words[:n]:
            remaining = ' '.join(cont_words[n:])
            return (current_desc + ' ' + remaining).strip() if remaining else current_desc

    return (current_desc + ' ' + cont).strip()


# =============================================================
# ACCOUNT INFO EXTRACTION
# =============================================================

def extract_account_info(lines, pdf_path=None):
    """Extract account metadata from a Standard Chartered statement."""
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Account number
    m = _ACCT_NO_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1).strip()

    # Account type
    m = _ACCT_TYPE_RE.search(full_text)
    if m:
        info["acc_type"] = m.group(1).strip()

    # Currency
    m = _CURRENCY_RE.search(full_text)
    if m:
        info["currency"] = m.group(1).strip()

    # Branch
    m = _BRANCH_RE.search(full_text)
    if m:
        val = m.group(1).strip()
        # Avoid capturing the full repeated header line
        if len(val) < 60:
            info["branch"] = val

    # Statement period
    m = _STMT_DATE_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = m.group(1).strip()
        info["statement_period"]["to"]   = m.group(2).strip()

    # Company / account holder name — appears before "(Company Name)" tag
    for i, line in enumerate(lines):
        if re.match(r'^\(Company Name\)$', line.strip(), re.I):
            # Name is on the previous line, but that line also has "Branch : ..."
            # Extract just the company name part (before "Branch")
            prev = lines[i - 1].strip() if i > 0 else ''
            m2 = re.match(r'^(.+?)\s+Branch\s*:', prev, re.I)
            if m2:
                info["account_holder"] = m2.group(1).strip()
            elif prev:
                info["account_holder"] = prev
            break

    # Opening balance
    m = _OPEN_BAL_RE.search(full_text)
    if m:
        info["opening_balance"] = _ca(m.group(1))

    # Closing balance — from last transaction's balance if not explicit
    m = _CLOSE_BAL_RE.search(full_text)
    if m:
        info["closing_balance"] = _ca(m.group(1))

    return info


# =============================================================
# TRANSACTION EXTRACTION
# =============================================================

def extract_transactions(pdf_path, lines=None):
    """Extract all transactions from a Standard Chartered PDF statement."""
    if lines is None:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                lines = []
                for page in pdf.pages:
                    lines.extend((page.extract_text() or '').split('\n'))
        except Exception:
            lines = []

    transactions = []
    current      = None
    prev_balance = None

    # Find opening balance (Balance Brought Forward)
    for line in lines[:20]:
        m = _OPEN_BAL_RE.search(line)
        if m:
            prev_balance = _ca(m.group(1))
            break

    for line in lines:
        ls = line.strip()
        if not ls:
            continue

        # Skip header/footer lines
        if _SKIP_RE.search(ls) or _HEADER_CONTENT_RE.search(ls):
            continue

        # Skip "Balance Brought Forward" line (already captured above)
        if re.search(r'Balance\s+Brought\s+Forward', ls, re.I):
            continue

        # ── Transaction line with amount + balance ──────────────
        m2 = _TXN_RE.match(ls)
        if m2:
            if current:
                transactions.append(current)

            date_str = _parse_date(m2.group(1))
            desc     = m2.group(2).strip()
            amount   = _ca(m2.group(3))
            balance  = _ca(m2.group(4))

            # Determine debit/credit from balance delta
            debit = credit = None
            if prev_balance is not None and balance is not None and amount is not None:
                delta = round(balance - prev_balance, 2)
                if delta >= 0:
                    credit = amount
                else:
                    debit = amount

            current = {
                'date':        date_str,
                'description': desc,
                'ref_no':      None,
                'debit':       debit,
                'credit':      credit,
                'balance':     balance,
            }
            if balance is not None:
                prev_balance = balance
            continue

        # ── Transaction line with balance only (no dr/cr amount) ─
        m1 = _TXN_NO_AMT_RE.match(ls)
        if m1:
            if current:
                transactions.append(current)

            date_str = _parse_date(m1.group(1))
            desc     = m1.group(2).strip()
            balance  = _ca(m1.group(3))

            current = {
                'date':        date_str,
                'description': desc,
                'ref_no':      None,
                'debit':       None,
                'credit':      None,
                'balance':     balance,
            }
            if balance is not None:
                prev_balance = balance
            continue

        # ── Continuation line ───────────────────────────────────
        if current is not None:
            current['description'] = _append_continuation(
                current['description'], ls
            )

    # Flush last transaction
    if current:
        transactions.append(current)

    return transactions