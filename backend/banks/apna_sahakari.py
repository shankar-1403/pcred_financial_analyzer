import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "apna_sahakari"
BANK_DISPLAY_NAME = "Apna Sahakari Bank"


# =============================================================================
# APNA SAHAKARI BANK LTD. — PDF FORMAT (Statement of Accounts)
# =============================================================================
#
# INFO BLOCK (page 1, plain text):
#   "Branch   : 44 - BHIWANDI"
#   "Account  : CD/815"
#   "Name     : TANVEER TEXTILES"
#   "Address  : 979 12 MATHURA COMPOUND..."
#   "From Date: 01/09/2021   To Date : 29/09/2022"
#   "Opening Balance : 1,10,807.75"
#
# PAGE HEADER (every page — skip these):
#   "APNA SAHAKARI BANK LTD.  Page X of Y"
#   "BHIWANDI  User Id AVP  Printed On ..."
#   "R045006 - STATEMENT OF ACCOUNTS"
#   "From 44  To Branch 44  Product CD  FromAcctNo 815 ..."
#
# TRANSACTION TABLE COLUMNS:
#   Date | Particulars | Instruments | Dr Amount | Cr Amount | Total Amount
#   (pdfplumber table extraction FAILS — all text merges into 1 column)
#
# CRITICAL STRUCTURE — MULTI-LINE TRANSACTIONS:
#   Each transaction occupies 1–3 text lines:
#
#   Line 1 (ANCHOR):  <DD/MM/YYYY>  <particulars [instrument]>
#                     <dr_amt>  <cr_amt>  <total_amt>
#   Line 2 (cont):    <instrument_continuation> or <payee_name>
#   Line 3 (cont):    <payee_name> or <extra_ref>   (optional)
#
#   Examples:
#     "01/09/2021 IMPS/P2A/ 124411580742  2,000.00  0.00  807.75"
#     "124411580742/055091900010"                        ← cont line
#     "Ali ham"                                          ← cont line
#
#     "07/09/2021 NEFT R Y TEXTILE  0.00  60,342.00  60,686.28"
#     "249305002011"                                     ← cont line
#     "ICICOSF0002 2493857"                              ← cont line
#
#     "01/09/2021 INTEZAR ALAM 100051  1,08,000.00  0.00  2,807.75"
#     (single line — no continuation)
#
# PARSING STRATEGY:
#   1. Extract full text from all pages.
#   2. Skip known header/footer/metadata lines.
#   3. Detect ANCHOR lines by DD/MM/YYYY date at start + 3 amounts at end.
#   4. Collect continuation lines (no date, no amounts) into current txn.
#   5. Split the anchor's "rest" into (particulars, instrument_id).
#   6. Merge continuation into full description.
#   7. Extract ref_no from instrument_id or first 8+ digit number in description.
#
# AMOUNT NOTES:
#   Dr Amount: 0.00 when it's a credit txn — treat as None
#   Cr Amount: 0.00 when it's a debit txn — treat as None
#   Total Amount = running balance
# =============================================================================


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------

# Anchor line: date + any text + three amounts at end
_TXN_ANCHOR_RE = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+"    # DD/MM/YYYY date
    r"(.+?)\s+"                     # particulars + maybe instrument (non-greedy)
    r"([\d,]+\.\d{2})\s+"          # Dr Amount
    r"([\d,]+\.\d{2})\s+"          # Cr Amount
    r"([\d,]+\.\d{2})\s*$"         # Total Amount (balance)
)

# Split instrument ID from end of "rest" text
# Instrument: trailing token that is numeric or alphanumeric starting with digit, ≥6 chars
_INSTR_SPLIT_RE = re.compile(r"^(.*?)\s+(\d[A-Z0-9]{5,})\s*$")

# ref_no fallback: first 8+ digit sequence
_REF_LONG_RE = re.compile(r"\b(\d{8,})\b")

# Account info
_ACCT_RE = re.compile(
    r"^account\s*[:\-]\s*(CD|SB|OD|CC|CA|RD)?[/\-]?\s*(\d+)", re.I
)
_NAME_RE    = re.compile(r"^name\s*[:\-]\s*(.+)", re.I)
_BRANCH_RE  = re.compile(r"^branch\s*[:\-]\s*(.+)", re.I)
_PERIOD_RE = re.compile(
    r"from\s*date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})"
    r"\s+to\s*date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
    re.I,
)
_OPEN_BAL_RE = re.compile(r"opening\s+balance\s*[:\-]?\s*([\d,]+\.\d{2})", re.I)

# Lines to skip (headers, footers, metadata printed on every page)
_SKIP_RE = re.compile(
    r"^("
    r"APNA\s+SAHAKARI\s+BANK"
    r"|BHIWANDI\s+User\s+Id"
    r"|R045006\s*-\s*STATEMENT"
    r"|From\s+\d+\s+To\s+Branch"
    r"|Product\s+CD"
    r"|FromAcctNo"
    r"|From\s+Date\s+\d"
    r"|Skip\s+Close"
    r"|Page\s+\d+\s+of\s+\d+"
    r"|User\s+Id"
    r"|Printed\s+On"
    r"|Date\s+Particulars"
    r"|[-=]{5,}"
    r")",
    re.I,
)

# Lines that are purely section headers inside the info block — skip
_INFO_SKIP_RE = re.compile(
    r"^(From\s+Branch|To\s+Acct\s+No|To\s+Date\s*:|"
    r"Address\s*:|MEGHALAYA|INDIA|\d{6}$)",   # ← removed "Branch\s*:\s*\d"
    re.I,
)


# ---------------------------------
# HELPERS
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert 'DD/MM/YYYY' → 'DD-MM-YYYY'."""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


def _clean_amount(s: str) -> float | None:
    """Indian comma format → float. Returns None if zero or empty."""
    if not s:
        return None
    try:
        v = float(str(s).replace(",", "").strip())
        return v if v != 0.0 else None
    except (ValueError, TypeError):
        return None


def _split_rest(rest: str) -> tuple[str, str | None]:
    """
    Split the "rest" portion of an anchor line into (particulars, instrument_id).

    Instrument ID is the trailing token that looks like a transaction reference:
    starts with a digit, ≥ 6 alphanumeric chars.

    Examples:
      "IMPS/P2A/ 124411580742"  → ("IMPS/P2A/", "124411580742")
      "NEFT R Y TEXTILE"        → ("NEFT R Y TEXTILE", None)
      "INTEZAR ALAM 100051"     → ("INTEZAR ALAM", "100051")
    """
    m = _INSTR_SPLIT_RE.match(rest)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return rest.strip(), None


def _extract_ref_no(description: str, instr_id: str | None) -> str | None:
    """
    Return the best transaction reference number.
    Priority: instrument_id (from anchor line) → first 8+ digit number in description.
    """
    if instr_id and len(instr_id) >= 6:
        return instr_id
    m = _REF_LONG_RE.search(description or "")
    return m.group(1) if m else None


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


def _should_skip(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if _SKIP_RE.match(s):
        return True
    return False


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    """
    Extract account metadata from Apna Sahakari Bank statement.

    The info block appears on every page before the table:
        Branch    : 44 - BHIWANDI
        Account   : CD/815
        Name      : TANVEER TEXTILES
        Address   : ...
        From Date : DD/MM/YYYY   To Date : DD/MM/YYYY
        Opening Balance : 1,10,807.75
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Opening balance
    m = _OPEN_BAL_RE.search(full_text)
    if m:
        try:
            info["opening_balance"] = float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # Statement period
    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    # Line-by-line for name, branch, account
    for line in lines:
        s = line.strip()
        if not s:
            continue

        if info["account_holder"] is None:
            m = _NAME_RE.match(s)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate) > 1:
                    info["account_holder"] = candidate

        if info["branch"] is None:
            m = _BRANCH_RE.match(s)
            if m:
                candidate = m.group(1).strip()
                # Strip leading "44 - " branch code prefix if present
                candidate = re.sub(r"^\d+\s*[-–]\s*", "", candidate).strip()
                if candidate and len(candidate) > 1:
                    info["branch"] = candidate

        if info["account_number"] is None:
            m = _ACCT_RE.match(s)   # ← .match() not .search()
            if m:
                prod = m.group(1) or ""
                num  = m.group(2) or ""
                info["account_number"] = f"{prod}/{num}".strip("/") if prod else num
                info["acc_type"] = prod if prod else None

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Dispatcher-compatible wrapper."""
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from an Apna Sahakari Bank PDF statement.

    WHY TEXT-LINE PARSING (not table extraction):
    pdfplumber's table extractor collapses all columns into a single merged
    column for this bank's monospace/fixed-width layout. Text-line parsing
    is the only reliable approach.

    ALGORITHM:
    1. Collect all text lines from every page.
    2. Skip header/footer/metadata lines.
    3. Match anchor lines: start with DD/MM/YYYY, end with 3 amounts.
    4. Accumulate continuation lines (no date prefix, no 3-amount suffix)
       into the current transaction's description.
    5. Post-process: merge continuation, build full description, extract ref_no.
    6. Sort ascending by date (oldest first).

    OUTPUT DICT:
        date        : DD-MM-YYYY
        description : full narration (particulars + continuation lines joined)
        ref_no      : instrument ID or first long numeric ref in description
        debit       : float or None  (Dr Amount, 0.00 → None)
        credit      : float or None  (Cr Amount, 0.00 → None)
        balance     : float          (Total Amount = running balance)
    """
    transactions: list[dict] = []
    current_txn:  dict | None = None

    # Extract all text lines from every page
    all_lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_lines.extend(text.split("\n"))

    for raw in all_lines:
        line = raw.strip()

        if _should_skip(line):
            if current_txn is not None and _SKIP_RE.match(line):
                # Page break — don't reset current_txn, just skip the header
                pass
            continue

        # Try to match a new transaction anchor line
        m = _TXN_ANCHOR_RE.match(line)
        if m:
            # Finalise previous transaction
            if current_txn is not None:
                transactions.append(_finalise_txn(current_txn))

            date_str = m.group(1)
            rest     = m.group(2).strip()
            dr_raw   = m.group(3)
            cr_raw   = m.group(4)
            bal_raw  = m.group(5)

            particulars, instr_id = _split_rest(rest)

            current_txn = {
                "date":        _reformat_date(date_str),
                "description": particulars,
                "_instr_id":   instr_id,
                "_cont":       [],
                "debit":       _clean_amount(dr_raw),
                "credit":      _clean_amount(cr_raw),
                "balance":     _clean_amount(bal_raw),
            }

        else:
            # Continuation line — append to current transaction's description
            if current_txn is not None and line:
                # Skip pure-header continuation noise
                if not re.match(r"^(Opening Balance|From Date|To Date|MEGHALAYA|INDIA|\d{6}$)", line, re.I):
                    current_txn["_cont"].append(line)

    # Don't forget the last transaction
    if current_txn is not None:
        transactions.append(_finalise_txn(current_txn))

    transactions.sort(key=_sort_key)
    return transactions


def _finalise_txn(txn: dict) -> dict:
    """
    Merge continuation lines into description, extract ref_no, clean up temp keys.
    """
    instr_id  = txn.pop("_instr_id", None)
    cont_list = txn.pop("_cont", [])

    if cont_list:
        txn["description"] = txn["description"] + " " + " ".join(cont_list)

    txn["description"] = re.sub(r"\s+", " ", txn["description"]).strip() or None
    txn["ref_no"]      = _extract_ref_no(txn["description"], instr_id)

    return txn