import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "bharat"
BANK_DISPLAY_NAME = "Bharat Co-operative Bank Ltd."


# ---------------------------------------------------------------------------
# REGEX PATTERNS
# ---------------------------------------------------------------------------
IFSC_PATTERN = r"\b(BCBM[A-Z0-9]{7})\b"
MICR_PATTERN = r"\bMICR\s+(\d{9})\b"

# Transaction line:
#   DD-MM-YY  DD-MM-YY  PARTICULARS [CHQ]  AMOUNT  (BALANCE) DR
_TXN_RE = re.compile(
    r"^(\d{2}-\d{2}-\d{2})\s+"        # TRAN DT  (DD-MM-YY)
    r"(\d{2}-\d{2}-\d{2})\s+"         # VALUE DT (DD-MM-YY)
    r"(.+?)\s+"                        # PARTICULARS (non-greedy)
    r"([\d,]+\.\d{2})\s+"             # single amount column
    r"\(([\d,]+\.\d{2})\)\s*DR\s*$",  # (balance) DR  — always overdraft
    re.I
)

# Continuation line that follows a CHARGES row: ":000035407"
_CONT_RE = re.compile(r"^:(\w+)$")

# 6-digit standalone cheque numbers in description
_CHQ_RE = re.compile(r"\b(\d{6})\b")

# Lines to skip entirely
_SKIP_RE = re.compile(
    r"^("
    r"TRAN\s*DT|"
    r"ACCOUNT\s*STATEMENT|"
    r"Totals\s*/\s*Balance|"
    r"Disclaimer|"
    r"Generated|"
    r"^\d{6}$"          # bare 6-digit number lines
    r")",
    re.I
)

# Opening balance pattern in period line
_OPENING_BAL_RE = re.compile(
    r"Opening\s+Balance\s+as\s+on\s*[:\-]?\s*\d{2}\s+\w+\s+\d{4}"
    r"\s+Currency\s*:\s*INR\s+"
    r"(-?[\d,]+\.\d{2})\s*DR",
    re.I
)

# Statement period: "From 01 Jan 2025 to 31 Jan 2025"
_PERIOD_RE = re.compile(
    r"From\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+to\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
    re.I
)

# Generated date: "03-Feb-25 07:46 p.m"
_GEN_DATE_RE = re.compile(r"(\d{2}-[A-Za-z]{3}-\d{2})\s+\d{2}:\d{2}")


# ---------------------------------------------------------------------------
# DATE HELPERS
# ---------------------------------------------------------------------------
def _expand_year(yy: str) -> str:
    """Convert 2-digit year to 4-digit (assumes 2000s)."""
    return f"20{yy}"


def _reformat_date_yy(date_str: str) -> str:
    """DD-MM-YY → DD-MM-YYYY"""
    parts = date_str.split("-")
    if len(parts) == 3 and len(parts[2]) == 2:
        return f"{parts[0]}-{parts[1]}-{_expand_year(parts[2])}"
    return date_str


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

    full_text = "\n".join(line for line in lines if line)

    # Account number — "Account No : 5.13150000025e+11 Mulund Branch"
    m = re.search(r"Account\s+No\s*[:\-]\s*([\d\.e\+]+)", full_text, re.I)
    if m:
        try:
            info["account_number"] = str(int(float(m.group(1))))
        except (ValueError, TypeError):
            info["account_number"] = m.group(1).strip()

    # Branch — on same line as "ACCOUNT STATEMENT Account No : ... Mulund Branch"
    m = re.search(
        r"Account\s+No\s*[:\-]\s*[\d\.e\+]+\s+(.+?branch)",
        full_text, re.I
    )
    if m:
        info["branch"] = m.group(1).strip()

    # Account holder — second line (first line after "ACCOUNT STATEMENT")
    for i, line in enumerate(lines):
        if re.match(r"^ACCOUNT\s+STATEMENT", line, re.I):
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = (lines[j] or "").strip()
                # Skip address-like lines (numbers, commas, known keywords)
                if candidate and not re.match(
                    r"^\d|^MICR|^From|^TRAN|,\s*(Mum|Mumbai|Delhi)",
                    candidate, re.I
                ):
                    info["account_holder"] = candidate
                    break
            break

    # IFSC
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    # MICR
    m = re.search(MICR_PATTERN, full_text)
    if m:
        info["micr"] = m.group(1)

    # Statement period — "From 01 Jan 2025 to 31 Jan 2025"
    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = m.group(1).strip()
        info["statement_period"]["to"]   = m.group(2).strip()

    # Statement request date — "Generated on ~Finx~ ... 03-Feb-25 07:46 p.m"
    m = _GEN_DATE_RE.search(full_text)
    if m:
        info["statement_request_date"] = _reformat_date_yy(m.group(1))

    # Opening balance (overdraft account — value is negative)
    m = _OPENING_BAL_RE.search(full_text)
    if m:
        raw = m.group(1).replace(",", "")
        try:
            info["opening_balance"] = -abs(float(raw))
        except (ValueError, TypeError):
            pass

    return info


# ---------------------------------------------------------------------------
# TRANSACTION EXTRACTION — raw text based
#
# Bharat Co-op Bank PDF quirks:
#   1. Date format: DD-MM-YY (2-digit year) → converted to DD-MM-YYYY
#   2. Balance format: (59,45,476.35) DR — always overdraft, always in parens
#   3. Single amount column — debit/credit determined by balance delta
#      (overdraft account: higher balance = more debt = debit)
#   4. Continuation lines ":000035407" immediately after CHARGES rows
#      → appended to previous transaction description as REF
#   5. Account number in scientific notation in PDF text
# ---------------------------------------------------------------------------
def extract_transactions(pdf_path: str):
    raw      = _parse_raw_lines(pdf_path)
    return _assign_debit_credit(raw)


def _parse_raw_lines(pdf_path: str) -> list:
    results  = []
    last_txn = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # Skip header/footer/totals
                if _SKIP_RE.match(line):
                    continue

                # Continuation ref line: ":000035407"
                m_cont = _CONT_RE.match(line)
                if m_cont and last_txn is not None:
                    last_txn["description"] = (
                        last_txn["description"] + " | REF:" + m_cont.group(1)
                    ).strip()
                    continue

                # Transaction line
                m = _TXN_RE.match(line)
                if not m:
                    continue

                date_raw  = m.group(1)                          # DD-MM-YY
                desc_raw  = m.group(3).strip()
                amount    = float(m.group(4).replace(",", ""))
                balance   = float(m.group(5).replace(",", ""))  # always positive; account is OD

                date_fmt  = _reformat_date_yy(date_raw)         # DD-MM-YYYY

                # Extract 6-digit cheque number from description
                chq_m     = _CHQ_RE.search(desc_raw)
                cheque_no = chq_m.group(1) if chq_m else None
                desc_clean = desc_raw.replace(cheque_no, "").strip() if cheque_no else desc_raw
                desc_clean = re.sub(r"\s{2,}", " ", desc_clean).strip()

                txn = {
                    "date":        date_fmt,
                    "description": desc_clean,
                    "cheque_no":   cheque_no,
                    "amount":      amount,
                    "balance":     balance,
                }
                results.append(txn)
                last_txn = txn

    return results


def _assign_debit_credit(raw_txns: list) -> list:
    """
    Bharat Co-op is an OVERDRAFT account — balance is always stored as a
    positive number representing the debt amount (printed as DR in the PDF).

    Delta logic (opposite of normal accounts):
      balance INCREASED → overdraft grew   → DEBIT  (money went out)
      balance DECREASED → overdraft shrank → CREDIT (money came in)
    """
    transactions = []

    for i, t in enumerate(raw_txns):
        prev_bal = raw_txns[i - 1]["balance"] if i > 0 else None

        if prev_bal is not None:
            delta    = round(t["balance"] - prev_bal, 2)
            is_debit = delta > 0  # OD increased → debit
        else:
            # First transaction — use description keyword fallback
            is_debit = not bool(
                re.search(r"\bcr\.?\b|\bcredit\b|\bfor\s+neft\b|\bfor\s+utr\b",
                          t["description"], re.I)
            )

        transactions.append({
            "date":        t["date"],
            "description": t["description"],
            "cheque_no":   t["cheque_no"],
            "debit":       t["amount"] if is_debit else None,
            "credit":      None if is_debit else t["amount"],
            "balance":     -t["balance"],  # store as negative to reflect overdraft
        })

    transactions.sort(key=_sort_key)
    return transactions