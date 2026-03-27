import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "karnataka"
BANK_DISPLAY_NAME = "Karnataka Bank"


# =============================================================================
# KARNATAKA BANK — TWO PDF FORMATS
# =============================================================================
#
# ── FORMAT 1: Online Statement ──────────────────────────────────────────────
#   "A/c Number   1012500100716401"
#   "Name         RAMESH KOTUMAL PAHLAJANI"
#   "Branch Name  OVERSEAS, MUMBAI"
#   "IFSC Code    KARB0000101"
#   "Statement Generated for the period : 01-Aug-2024 - 21-Sep-2024"
#   Table: Date | Description | Chq/Ref No | Withdrawals | Deposits | Balance
#   Date format: DD-MM-YYYY
#
# ── FORMAT 2: Branch Account Statement ──────────────────────────────────────
#   "Account Statement"             ← page title
#   "General Details"               ← section header
#   "Number: 4752000100130101 Nickname: ROHAN CORPORATION INDIA PRIVATE LIMITED"
#   "Name: ROHAN CORPORATION Status: Active Account"
#   "INDIA PRIVATE LIMITED"         ← name continuation line
#   "Type: Current Category: CA-MONEY DIAMOND"
#   "Currency: INR Open Date: 11/12/10"
#   "Branch: MANGALORE - Drawing Power: INR 0.00"
#   "DONGERKERY"                    ← branch continuation line
#   "Date From(dd/MM/yyyy): 01/07/2023"
#   "Date To(dd/MM/yyyy): 31/08/2024"
#   Table header: "Transactions List - ROHAN CORPORATION (INR) - 4752000100130101"
#   Columns: Date | Description | Cheque No | Debit | Credit | Balance (INR)
#   Date format: DD/MM/YYYY   Balance: can be NEGATIVE (overdraft)
#
# QUIRKS:
#   1. Format 2 labels use COLON: "Number: 4752..." not "Number   4752..."
#   2. Name/Branch may span TWO lines — continuation absorbed
#   3. Bank has NO "Karnataka Bank" text in header — detected by KARB IFSC
#      or account number pattern (10 digits starting 47/10) or General Details
#   4. Indian number format: 1,05,473.36 — strip all commas
#   5. pdfplumber may split amounts onto separate line
# =============================================================================


# ---------------------------------
# SHARED PATTERNS
# ---------------------------------
_AMOUNT_PAT      = re.compile(r"-?[\d,]+\.\d{2}")
_OPENING_BAL_PAT = re.compile(r"opening\s+balance\s+([\d,]+\.\d{2})", re.I)
_IFSC_PAT        = re.compile(r"ifsc\s*(?:code)?\s*[:\-]?\s*(KARB[A-Z0-9]{7})", re.I)

_SKIP_PAT = re.compile(
    r"^(Account\s+Statement\s*$"
    r"|General\s+Details\s*$"
    r"|Page\s+\d+\s+of\s+\d+"
    r"|Statement\s+Generated\s+for\s+the\s+period"
    r"|Date\s+Description\s+Chq"
    r"|Date\s+Description\s+Cheque"
    r"|Transactions\s+List\s+-"
    r"|Withdrawal\s+Deposit\s+Balance"
    r"|Debit\s+Credit\s+Balance)",
    re.I,
)

# Lines that are pure label continuations — skip appending to description
_HEADER_CONT_PAT = re.compile(
    r"^(Nickname\s*:|Status\s*:|Category\s*:|Open\s+Date\s*:|Drawing\s+Power\s*:"
    r"|Sanction\s+Limit\s*:|Debit\s+Accrued|Credit\s+Accrued|Primary\s+Account"
    r"|Date\s+From|Date\s+To|Transactions\s+for|Last\s+N|Amount\s+From|Amount\s+Type)",
    re.I,
)


# ---------------------------------
# FORMAT 1 PATTERNS
# ---------------------------------
_F1_PERIOD_PAT   = re.compile(
    r"period\s*[:\-]?\s*(\d{2}-[A-Za-z]{3}-\d{4})\s*[-–to]+\s*(\d{2}-[A-Za-z]{3}-\d{4})",
    re.I,
)
_F1_ACCT_PAT     = re.compile(r"a/?c\s*number\s*[:\-]?\s*(\d{10,20})", re.I)
_F1_NAME_PAT     = re.compile(r"^name\s+([A-Z].{3,60})$", re.I)
_F1_BRANCH_PAT   = re.compile(r"branch\s*name\s*[:\-]?\s*(.+)", re.I)
_F1_MICR_PAT     = re.compile(r"micr\s*[:\-]?\s*(\d{9})", re.I)
_F1_DATE_PAT     = re.compile(r"^(\d{2}-\d{2}-\d{4})\s+(.*)")
_F1_AMOUNTS_ONLY = re.compile(r"^[\d,]+\.\d{2}(\s+[\d,]+\.\d{2})*$")


# ---------------------------------
# FORMAT 2 PATTERNS  (colon-separated labels)
# ---------------------------------
_F2_ACCT_PAT     = re.compile(r"(?:^|\s)number\s*:\s*(\d{10,20})", re.I)
_F2_NAME_PAT     = re.compile(r"^name\s*:\s*(.+?)(?:\s+Status\s*:.*)?$", re.I)
_F2_TYPE_PAT     = re.compile(r"^type\s*:\s*([^\s:]+(?:\s+[^\s:]+)*?)(?:\s+Category\s*:|$)", re.I)
_F2_BRANCH_PAT   = re.compile(r"^branch\s*:\s*(.+?)(?:\s+Drawing\s+Power\s*:|$)", re.I)
_F2_CURRENCY_PAT = re.compile(r"^currency\s*:\s*([A-Z]{3})", re.I)
_F2_PERIOD_FROM  = re.compile(r"date\s+from\s*\(?dd/mm/yyyy\)?\s*:\s*(\d{2}/\d{2}/\d{2,4})", re.I)
_F2_PERIOD_TO    = re.compile(r"date\s+to\s*\(?dd/mm/yyyy\)?\s*:\s*(\d{2}/\d{2}/\d{2,4})", re.I)
_F2_DATE_PAT     = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.*)")
_F2_AMOUNTS_ONLY = re.compile(r"^-?[\d,]+\.\d{2}(\s+-?[\d,]+\.\d{2})*$")

_TYPE_MAP = {
    "SB":        "Savings Account",
    "CA":        "Current Account",
    "CURRENT":   "Current Account",
    "SAVINGS":   "Savings Account",
    "OVERDRAFT": "Overdraft",
    "OD":        "Overdraft",
    "CC":        "Cash Credit",
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


def _fmt_date_dmy_dash(s: str) -> str:
    s = s.strip()
    for fmt in ["%d-%m-%Y", "%d-%b-%Y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return s


def _fmt_date_dmy_slash(s: str) -> str:
    """DD/MM/YYYY or DD/MM/YY → DD-MM-YYYY."""
    s = s.strip()
    for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return s


def _is_skip(line: str) -> bool:
    return bool(_SKIP_PAT.match(line.strip()))


def _assign_amounts_f1(
    amounts: list[str], last_balance: float | None
) -> tuple[float | None, float | None, float | None]:
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


def _assign_amounts_f2(
    amounts: list[str], last_balance: float | None
) -> tuple[float | None, float | None, float | None]:
    debit = credit = balance = None
    if not amounts:
        return debit, credit, balance
    if len(amounts) >= 3:
        d = _parse_amount(amounts[-3])
        c = _parse_amount(amounts[-2])
        balance = _parse_amount(amounts[-1])
        debit  = d if d else None
        credit = c if c else None
    elif len(amounts) == 2:
        balance = _parse_amount(amounts[-1])
        txn_amt = _parse_amount(amounts[-2])
        if txn_amt is not None and last_balance is not None and balance is not None:
            delta = round(balance - last_balance, 2)
            if delta < 0:
                debit = abs(txn_amt)
            elif delta > 0:
                credit = txn_amt
    elif len(amounts) == 1:
        balance = _parse_amount(amounts[0])
    return debit, credit, balance


def _detect_format(lines: list[str]) -> str:
    header = "\n".join(lines[:40]).lower()

    # Format 2 signals
    if any(x in header for x in [
        "general details",
        "transactions list -",
        "date from(dd/mm/yyyy)",
        "date from(dd/mm",
        "overdraft general",
        "drawing power",
        "sanction limit",
        "open date",
        "ca-money",
    ]):
        return "f2"

    # Format 1 signals
    if any(x in header for x in [
        "statement generated for the period",
        "a/c number",
        "upi id",
        "joint holder",
    ]):
        return "f1"

    # Last resort: detect from first transaction date format in body
    for line in lines[:100]:
        s = line.strip()
        if re.match(r"^\d{2}/\d{2}/\d{4}\s+", s):
            return "f2"
        if re.match(r"^\d{2}-\d{2}-\d{4}\s+", s):
            return "f1"

    return "f1"


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
    fmt = _detect_format(lines)

    # IFSC (both formats)
    m = _IFSC_PAT.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    m = _F1_MICR_PAT.search(full_text)
    if m:
        info["micr"] = m.group(1)

    if fmt == "f1":
        m = _F1_ACCT_PAT.search(full_text)
        if m:
            info["account_number"] = m.group(1).strip()

        m = _F1_PERIOD_PAT.search(full_text)
        if m:
            info["statement_period"]["from"] = _fmt_date_dmy_dash(m.group(1))
            info["statement_period"]["to"]   = _fmt_date_dmy_dash(m.group(2))

        for line in lines[:40]:
            s = line.strip()
            if info["account_holder"] is None:
                m2 = _F1_NAME_PAT.match(s)
                if m2:
                    info["account_holder"] = m2.group(1).strip()
            if info["branch"] is None:
                m2 = _F1_BRANCH_PAT.match(s)
                if m2:
                    info["branch"] = m2.group(1).strip()

    else:  # fmt == "f2"
        # Account number
        m = _F2_ACCT_PAT.search(full_text)
        if m:
            info["account_number"] = m.group(1).strip()

        # Statement period
        m = _F2_PERIOD_FROM.search(full_text)
        if m:
            info["statement_period"]["from"] = _fmt_date_dmy_slash(m.group(1))
        m = _F2_PERIOD_TO.search(full_text)
        if m:
            info["statement_period"]["to"] = _fmt_date_dmy_slash(m.group(1))

        # Line-by-line with multi-line value absorption
        prev_field = None
        for line in lines[:50]:
            s = line.strip()
            if not s:
                prev_field = None
                continue

            # Name: "Name: ROHAN CORPORATION" — next line may be "INDIA PRIVATE LIMITED"
            if info["account_holder"] is None:
                m2 = _F2_NAME_PAT.match(s)
                if m2:
                    raw = m2.group(1).strip()
                    # Strip trailing Status: bleed
                    raw = re.split(r"\s+Status\s*:", raw)[0].strip()
                    info["account_holder"] = raw
                    prev_field = "name"
                    continue
                elif prev_field == "name" and not re.match(
                    r"^(Type|Currency|Branch|Status|Category|Open|Date|Nickname|Number)\s*:", s, re.I
                ) and not _is_skip(s):
                    # Continuation of name
                    info["account_holder"] = (info["account_holder"] + " " + s).strip()
                    continue

            # Branch: "Branch: MANGALORE -" — next line may be "DONGERKERY"
            if info["branch"] is None:
                m2 = _F2_BRANCH_PAT.match(s)
                if m2:
                    raw = m2.group(1).strip().rstrip("-").strip()
                    info["branch"] = raw
                    prev_field = "branch"
                    continue
                elif prev_field == "branch" and not re.match(
                    r"^(Type|Currency|Name|Status|Date|Nickname|Number|Drawing|Sanction)\s*:", s, re.I
                ) and not _is_skip(s):
                    info["branch"] = (info["branch"] + " " + s).strip()
                    prev_field = None
                    continue

            if info["acc_type"] is None:
                m2 = _F2_TYPE_PAT.match(s)
                if m2:
                    raw = m2.group(1).strip().upper()
                    info["acc_type"] = _TYPE_MAP.get(raw, m2.group(1).strip())
                    prev_field = "type"
                    continue

            if info["currency"] == "INR":
                m2 = _F2_CURRENCY_PAT.match(s)
                if m2:
                    info["currency"] = m2.group(1).strip()
                    prev_field = None
                    continue

            prev_field = None

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split("\n"))

    fmt = _detect_format(all_lines)
    if fmt == "f1":
        return _extract_f1(all_lines)
    else:
        return _extract_f2(all_lines)


# =============================================================================
# FORMAT 1 PARSER
# =============================================================================
def _extract_f1(all_lines: list[str]) -> list[dict]:
    transactions = []
    current      = None
    last_balance = None

    for raw in all_lines:
        line = raw.strip()
        if not line or _is_skip(line):
            continue

        m = _OPENING_BAL_PAT.search(line)
        if m:
            last_balance = _parse_amount(m.group(1))
            continue

        if _F1_AMOUNTS_ONLY.match(line):
            if current is not None and current["balance"] is None:
                amounts = _AMOUNT_PAT.findall(line)
                d, c, b = _assign_amounts_f1(amounts, last_balance)
                current["debit"]   = d
                current["credit"]  = c
                current["balance"] = b
                last_balance = b
            continue

        m = _F1_DATE_PAT.match(line)
        if m:
            if current is not None:
                transactions.append(current)

            date_str  = _fmt_date_dmy_dash(m.group(1))
            remainder = m.group(2).strip()
            amounts   = _AMOUNT_PAT.findall(remainder)

            if amounts:
                d, c, b = _assign_amounts_f1(amounts, last_balance)
                last_balance = b
            else:
                d = c = b = None

            desc_clean = re.sub(r"\s{2,}", " ", _AMOUNT_PAT.sub("", remainder)).strip()
            ref_no = None
            ref_m  = re.search(r"\s+(\d{5,10})\s*$", desc_clean)
            if ref_m:
                ref_no     = ref_m.group(1)
                desc_clean = desc_clean[:ref_m.start()].strip()

            current = {
                "date":        date_str,
                "description": desc_clean,
                "ref_no":      ref_no,
                "debit":       d,
                "credit":      c,
                "balance":     b,
            }

        else:
            if current is not None and not _is_skip(line):
                current["description"] = (current["description"] + " " + line).strip()

    if current is not None:
        transactions.append(current)

    transactions.sort(key=_sort_key)
    return transactions


# =============================================================================
# FORMAT 2 PARSER
# =============================================================================
def _extract_f2(all_lines: list[str]) -> list[dict]:
    transactions = []
    current      = None
    last_balance = None
    in_txn_table = False

    for raw in all_lines:
        line = raw.strip()
        if not line:
            continue

        if not in_txn_table:
            if re.match(r"^transactions\s+list\s+-", line, re.I):
                in_txn_table = True
                continue
            if re.match(r"^date\s+description\s+cheque", line, re.I):
                in_txn_table = True
                continue
            # Auto-enable on first DD/MM/YYYY date line (handles missing header)
            if re.match(r"^\d{2}/\d{2}/\d{4}\s+\S", line):
                in_txn_table = True
                # fall through to process this line

        if not in_txn_table:
            continue

        if _is_skip(line):
            continue

        if _F2_AMOUNTS_ONLY.match(line):
            if current is not None and current["balance"] is None:
                amounts = _AMOUNT_PAT.findall(line)
                d, c, b = _assign_amounts_f2(amounts, last_balance)
                current["debit"]   = d
                current["credit"]  = c
                current["balance"] = b
                last_balance = b
            continue

        m = _F2_DATE_PAT.match(line)
        if m:
            if current is not None:
                transactions.append(current)

            date_str  = _fmt_date_dmy_slash(m.group(1))
            remainder = m.group(2).strip()
            amounts   = _AMOUNT_PAT.findall(remainder)

            if amounts:
                d, c, b = _assign_amounts_f2(amounts, last_balance)
                last_balance = b
            else:
                d = c = b = None

            desc_clean = re.sub(r"\s{2,}", " ", _AMOUNT_PAT.sub("", remainder)).strip()
            ref_no = None
            ref_m  = re.search(r"\b(\d{5,10})\s*$", desc_clean)
            if ref_m:
                ref_no     = ref_m.group(1)
                desc_clean = desc_clean[:ref_m.start()].strip()

            current = {
                "date":        date_str,
                "description": desc_clean,
                "ref_no":      ref_no,
                "debit":       d,
                "credit":      c,
                "balance":     b,
            }

        else:
            if current is not None and not _is_skip(line) and not _HEADER_CONT_PAT.match(line):
                current["description"] = (current["description"] + " " + line).strip()

    if current is not None:
        transactions.append(current)

    transactions.sort(key=_sort_key)
    return transactions