import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns,
)

BANK_KEY          = "cosmos"
BANK_DISPLAY_NAME = "The Cosmos Co-op. Bank Ltd."


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
# Cosmos IFSC prefix is COSB (not always printed in statement body, kept for robustness)
IFSC_PATTERN   = r"\b(COSB[A-Z0-9]{7})\b"
PERIOD_PATTERN = r"period\s+of\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})"

# Date format used in Cosmos transaction rows: DD/MM/YYYY
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# Statement request date on page header: e.g. "14-Jan-2025"
_REQ_DATE_RE = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{4}")

# Footer / summary rows — skip entirely
_SKIP_ROW_RE = re.compile(
    r"sub\s*total|grandtotal|grand\s*total|\*+\s*end\s*of\s*statement",
    re.I,
)

# Balance cells always end with " CR" — strip before float-parsing
_CR_SUFFIX_RE = re.compile(r"\s*cr\s*$", re.I)


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_cosmos(value):
    """
    Handles Indian comma format: '21,521.81', '50000.00'
    Balance cells carry a trailing ' CR' suffix which is stripped first.
    Returns float or None. Blank / None treated as None.
    """
    if value is None:
        return None
    value = str(value).strip()
    # Strip balance CR suffix if present
    value = _CR_SUFFIX_RE.sub("", value).strip()
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
    """
    Extract account metadata from Cosmos Co-op Bank statement text lines.

    Actual pdfplumber text layout (first 5 lines of every page):

        line 0: "Statement of account for the period of 01/01/2024 to 30/06/2024 14-Jan-2025"
        line 1: "Customer Id 1222386"
        line 2: "Account Number 122100101410"
        line 3: "Account Holder Name AALEKH ASSOCIATES"
        line 4: "Date Transaction Particulars Cheque No. Withdrawal Deposit Available Balance"

    All fields are label + value on the SAME line — not separate lines.
    No IFSC, no branch, no MICR printed in this statement.
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Statement period — from line 0
    m = re.search(PERIOD_PATTERN, full_text, re.I)
    if m:
        info["statement_period"]["from"] = m.group(1)
        info["statement_period"]["to"]   = m.group(2)

    # Statement request date — also on line 0: "...to 30/06/2024 14-Jan-2025"
    m = _REQ_DATE_RE.search(full_text)
    if m:
        info["statement_request_date"] = m.group()

    # IFSC (rarely present; kept for robustness)
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    # Parse only the first 5 lines — all account metadata lives there
    for line in lines[:5]:
        line_s = (line or "").strip()
        if not line_s:
            continue

        # "Customer Id 1222386"
        if info["customer_id"] is None:
            m = re.search(r"customer\s*id\s+(\d+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)
                continue

        # "Account Number 122100101410"
        if info["account_number"] is None:
            m = re.search(r"account\s*number\s+(\d+)", line_s, re.I)
            if m:
                info["account_number"] = m.group(1)
                continue

        # "Account Holder Name AALEKH ASSOCIATES"
        if info["account_holder"] is None:
            m = re.search(r"account\s*holder\s*name\s+(.+)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()
                continue

    return info


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    """
    Extract all transactions from a Cosmos Co-op Bank PDF statement.

    COSMOS PDF CHARACTERISTICS:
    ===========================
    - Text-based PDF (pdfplumber line strategy works reliably)
    - 6 columns per row:
        [Date | Transaction Particulars | Cheque No. | Withdrawal | Deposit | Available Balance]
    - Separate Withdrawal (debit) and Deposit (credit) columns; no DR/CR indicator column
    - Balance always formatted as "XXXXX.XX CR" — strip " CR" suffix before parsing
    - Blank Withdrawal / Deposit cell means no movement on that side
    - Continuation rows: long narrations overflow onto the next PDF row with ONLY
      a description fragment and no date / amounts — append fragment to last txn
    - Footer rows to skip: "Sub Total", "GrandTotal", "**** END OF STATEMENT ****"
    """
    transactions = []
    column_mapping = None
    last_txn       = None

    # Cosmos-specific column aliases passed to detect_columns()
    cosmos_header_map = {
        "date": [
            "date",
        ],
        "description": [
            "transaction particulars",
            "particulars",
            "narration",
            "description",
        ],
        "cheque": [
            "cheque no",
            "cheque no.",
            "chequeno",
        ],
        "debit": [
            "withdrawal",
            "withdrawal amt",
        ],
        "credit": [
            "deposit",
            "deposit amt",
        ],
        "balance": [
            "available balance",
            "balance",
            "closing balance",
        ],
    }

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )

            if not tables:
                continue

            for table in tables:

                for row in table:

                    if not row:
                        continue

                    # Skip entirely blank rows
                    if all((cell or "").strip() == "" for cell in row):
                        continue

                    # Skip footer / summary rows
                    row_text = " ".join((cell or "") for cell in row)
                    if _SKIP_ROW_RE.search(row_text):
                        continue

                    # Normalise cells for header detection
                    row_lower = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    # Detect (or re-detect on new page) column mapping from header row
                    detected = detect_columns(row_lower, cosmos_header_map)
                    if detected and "date" in detected:
                        column_mapping = detected
                        continue  # this is the header row — not a transaction

                    if column_mapping is None:
                        continue

                    # Continuation row: description overflow, no date or amounts
                    if _is_continuation(row, column_mapping):
                        if last_txn is not None and "description" in column_mapping:
                            desc_idx = column_mapping["description"]
                            if desc_idx < len(row):
                                extra = (row[desc_idx] or "").replace("\n", " ").strip()
                                if extra:
                                    last_txn["description"] = (
                                        (last_txn["description"] or "") + " " + extra
                                    ).strip()
                        continue

                    # Regular transaction row
                    txn = _build_txn(row, column_mapping)
                    if txn:
                        transactions.append(txn)
                        last_txn = txn

    return transactions


# ---------------------------------
# HELPERS
# ---------------------------------
def _is_continuation(row, col):
    """
    A continuation row carries only a description fragment — no date,
    no withdrawal, no deposit, no balance.
    Example: the isolated cell "MOS" that overflows from "IMPS/.../BKID/COS"
    on the previous row (page 5 of the Cosmos statement).
    """
    def _get(key):
        idx = col.get(key)
        return (row[idx] or "").strip() if idx is not None and idx < len(row) else ""

    has_date    = bool(_get("date"))
    has_amounts = any(bool(_get(k)) for k in ("debit", "credit", "balance"))
    return not has_date and not has_amounts


def _build_txn(row, col):
    """
    Build one transaction dict from a table row using column_mapping.
    Returns None if the row does not contain a valid DD/MM/YYYY date.
    """
    def _get(key):
        idx = col.get(key)
        if idx is None or idx >= len(row):
            return None
        return (row[idx] or "").replace("\n", " ").strip() or None

    date_raw = _get("date")
    if not date_raw or not _DATE_RE.match(date_raw):
        return None

    desc = _get("description")
    if desc:
        desc = re.sub(r"\s+", " ", desc).strip()

    cheque_no = _get("cheque") or None
    debit     = _clean_amount_cosmos(_get("debit"))
    credit    = _clean_amount_cosmos(_get("credit"))
    balance   = _clean_amount_cosmos(_get("balance"))

    return {
        "date":        date_raw,
        "description": desc,
        "cheque_no":   cheque_no,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }   