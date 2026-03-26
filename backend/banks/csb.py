import re
import pdfplumber
from datetime import datetime

from .base import (
    default_account_info,
    clean_amount,
    detect_columns
)

BANK_KEY          = "csb"
BANK_DISPLAY_NAME = "CSB Bank"


# ---------------------------------
# TABLE HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date": [
        "date",
    ],
    "description": [
        "details",
        "description",
        "narration",
    ],
    "cheque": [
        "ref no./cheque no.",
        "ref no",
        "cheque no",
        "reference no",
    ],
    "debit": [
        "debit",
        "withdrawal",
        "dr",
    ],
    "credit": [
        "credit",
        "deposit",
        "cr",
    ],
    "balance": [
        "balance",
        "running balance",
    ],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
ACCT_NO_PATTERN  = r"account\s*number\s*[:\-]?\s*(\d{10,})"
CUSTOMER_PATTERN = r"customer\s*id\s*[:\-]?\s*(\d+)"
IFSC_PATTERN     = r"\bCSBK[A-Z0-9]{7}\b"
MICR_PATTERN     = r"micr\s*[:\-]?\s*(\d{9})"
BRANCH_PATTERN   = r"home\s*branch\s*[:\-]?\s*(.+)"
ACCT_TYPE_PATTERN= r"type\s*of\s*account\s*[:\-\s]+(\w+)"
PERIOD_PATTERN   = r"for\s+the\s+period[:\-]?\s*(\d{2}-\w{3}-\d{4})\s+to\s+(\d{2}-\w{3}-\d{4})"
HOLDER_PATTERN   = r"^([A-Z][A-Z\s]+(?:LINES|ENTERPRISES|TRADERS|INDUSTRIES|PVT|LTD|CO\.|COMPANY|ROAD|TRANSPORT|LOGISTICS|CARGO))$"

# Balance format: "-INR 6,99,69,45 8.94 Dr" or "-INR 6,89,69,45 8.94 Dr"
# The balance has a space inserted by pdfplumber splitting the number
BALANCE_PATTERN = re.compile(
    r"(-?)\s*INR\s+([\d,\s]+\.\d{2})\s*(Dr|Cr)?",
    re.I
)

# Date: "01 SEP 2025"
DATE_PATTERN = re.compile(r"^\d{2}\s+[A-Z]{3}\s+\d{4}$")

# Opening/Closing balance from summary block
OPEN_CLOSE_PATTERN = re.compile(
    r"(-?IN\s*R[\d,\s]+\.\d{2})\s*\+.*?(\bINR\s+[\d,\s]+\.\d{2})\s*-.*?"
    r"(\bINR\s+[\d,\s]+\.\d{2})\s*=.*?(-?IN\s*R[\d,\s]+\.\d{2})",
    re.DOTALL | re.I
)


# ---------------------------------
# DATE REFORMATTER
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert 'DD MON YYYY' (e.g. '01 SEP 2025') → 'DD-MM-YYYY' (e.g. '01-09-2025')."""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d %b %Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


# ---------------------------------
# CSB-SPECIFIC COLUMN DETECTOR
# ---------------------------------
def _detect_columns_csb(row_clean):
    """
    CSB-specific column detector — avoids base.detect_columns substring bug.
    Uses exact match first, then guarded substring (4+ chars only).
    base.py is never modified.
    """
    mapping = {}
    for field, variants in HEADER_MAP.items():
        # Pass 1: exact match
        for idx, cell in enumerate(row_clean):
            if cell in variants:
                mapping[field] = idx
                break
        if field in mapping:
            continue
        # Pass 2: substring only for 4+ char aliases
        for idx, cell in enumerate(row_clean):
            if any(len(v) >= 4 and v in cell for v in variants):
                mapping[field] = idx
                break
    return mapping if len(mapping) >= 3 else None


# ---------------------------------
# AMOUNT CLEANERS
# ---------------------------------
def _clean_amount_csb(value):
    """
    Standard Indian comma format: '1,00,624.00', '5,00,000.00'
    Treats '-' as None (CSB uses '-' for empty cells).
    Returns float or None.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    value = re.sub(r"^(Rs\.?|INR|₹)\s*", "", value, flags=re.I).strip()
    value = value.replace(",", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _clean_balance_csb(value):
    """
    CSB balance format: '-INR 6,99,69,45 8.94 Dr'
    The space inside the number is a PDF artifact (number split across lines).
    Also handles: '-INR 6,89,69,45 8.94 Dr', '-INR 7,01,43,19 5.11 Dr'

    Returns signed float (negative for Dr, positive for Cr).
    """
    if not value:
        return None
    value = str(value).strip()

    # Determine sign from leading '-' or trailing 'Dr'/'Cr'
    is_negative = value.startswith("-") or value.upper().endswith("DR")
    is_positive = value.upper().endswith("CR")

    # Extract all digit/comma/dot/space sequences and join
    # e.g. '-INR 6,99,69,45 8.94 Dr' → '6,99,69,45 8.94'
    m = BALANCE_PATTERN.search(value)
    if not m:
        return None

    raw = m.group(2)  # e.g. '6,99,69,45 8.94'

    # The number has a space splitting integer and decimal parts
    # e.g. '6,99,69,45 8.94' → integer='6,99,69,45' decimal='8.94' → '6,99,69,458.94'
    # BUT the real number is 6,99,69,458.94 (the space is an artifact)
    # Strategy: remove all spaces and commas, parse as float
    raw_clean = raw.replace(",", "").replace(" ", "")
    # raw_clean is now something like '69969458.94' — but we need to find the decimal point
    # The decimal is always the last '.XX' part
    if "." not in raw_clean:
        return None

    try:
        amount = float(raw_clean)
    except ValueError:
        return None

    # Apply sign
    if is_negative or (m.group(1) == "-"):
        amount = -amount
    elif is_positive:
        pass  # already positive

    return amount


# ---------------------------------
# DATE HELPER
# ---------------------------------
def _is_txn_date(value):
    """CSB date format: '01 SEP 2025'"""
    if not value:
        return False
    return bool(DATE_PATTERN.match(str(value).strip()))


# ---------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines, pdf_path=None):
    """
    Extract account metadata from CSB Bank page 1.

    Uses two sources:
    1. The 4-column account info table (most reliable — structured label/value)
    2. Raw text lines (for account holder name at top, statement period)

    CSB Bank page 1 account info table layout:
      Customer ID    | : 4986927      | Home Branch   | : MUMBAI FORT
      Account Number | : 0177020021597| Branch Address| : GR FLR ...
      Type of Account| : CURRENT      |               |
      IFSC Code      | : CSBK0000177  | MICR          | : 400047002
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # ── 1. Account Holder ── first non-empty, non-address line in raw text
    for line in lines[:8]:
        text = line.strip()
        if (text
                and len(text) > 3
                and re.match(r"^[A-Z]", text)
                and not re.search(r"near|petrol|pamp|plot|mumbai|\+91|@|csb", text, re.I)):
            info["account_holder"] = text
            break

    # ── 2. Parse the 4-col account info table via pdfplumber ──
    if pdf_path:
        try:
            import pdfplumber as _plumber
            with _plumber.open(pdf_path) as pdf:
                tables = pdf.pages[0].extract_tables(
                    {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
                )
                for table in tables:
                    if not table or len(table[0]) != 4:
                        continue
                    for row in table:
                        if not row or not row[0]:
                            continue
                        label = str(row[0]).strip().lower()
                        value = str(row[1] or "").strip().lstrip(":").strip()
                        label2 = str(row[2] or "").strip().lower()
                        value2 = str(row[3] or "").strip().lstrip(":").strip()

                        if "customer id" in label:
                            info["customer_id"] = value
                        if "account number" in label:
                            info["account_number"] = value
                        if "type of account" in label:
                            # Only take the type word, not trailing address text
                            info["acc_type"] = value.split("\n")[0].strip()
                        if "ifsc code" in label2:
                            info["ifsc"] = value2
                        if "micr" in label2:
                            m = re.search(r"(\d{9})", value2)
                            if m:
                                info["micr"] = m.group(1)
                        if "home branch" in label2:
                            info["branch"] = value2
        except Exception:
            pass

    # ── 3. Fallback: regex on text lines ──
    for line in lines:
        text = line.strip()

        if info["account_number"] is None:
            m = re.search(ACCT_NO_PATTERN, text, re.I)
            if m:
                info["account_number"] = m.group(1)

        if info["customer_id"] is None:
            m = re.search(CUSTOMER_PATTERN, text, re.I)
            if m:
                info["customer_id"] = m.group(1)

        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN, text)
            if m:
                info["ifsc"] = m.group()

        if info["micr"] is None:
            m = re.search(MICR_PATTERN, text, re.I)
            if m:
                info["micr"] = m.group(1)

        if info["branch"] is None:
            m = re.search(BRANCH_PATTERN, text, re.I)
            if m:
                candidate = m.group(1).strip().lstrip(":").strip()
                if candidate and len(candidate) > 2:
                    info["branch"] = candidate

        if info["statement_period"]["from"] is None:
            m = re.search(PERIOD_PATTERN, text, re.I)
            if m:
                info["statement_period"]["from"] = m.group(1)
                info["statement_period"]["to"]   = m.group(2)

        if info["acc_type"] is None:
            m = re.search(r"type\s*of\s*account\s*[:\-\s]+(\w+)", text, re.I)
            if m:
                val = m.group(1).strip()
                # Exclude noise words that bleed in from address column
                if val.upper() not in ("OF", "THE", "AND", "FOR", "IN"):
                    info["acc_type"] = val

    # ── 4. Opening / Closing Balance ──
    _extract_summary_from_text(full_text, info)

    # Override with reliable values from transactions if parsing failed
    if info["opening_balance"] is None or abs(info.get("opening_balance", 0)) < 1000:
        info["opening_balance"] = None  # will be patched by extract_summary_balances

    return info


def _extract_summary_from_text(full_text, info):
    """
    Extract opening/closing balances from the summary block on page 1.
    The summary text looks like:
      'Opening Balance  Total Credits  Total Debits  Closing Balance'
      '+   -   ='
      '-IN R7,04,  INR 3,42,  INR 3,38,  -IN R7,00,'
      '69,458.94   72,413.10  82,368.81  79,414.65'
    """
    # Look for lines with balance-like numbers after the summary header
    opening_pattern = re.compile(r"opening\s*balance", re.I)
    if not opening_pattern.search(full_text):
        return

    # Try to find the numeric values below the summary header
    # They appear as: '-IN R7,04,' on one line, '69,458.94' on the next
    # Combined: -7,04,69,458.94 = -70469458.94
    lines = full_text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r"opening\s*balance.*closing\s*balance", line, re.I):
            # Numbers are 2 lines below
            num_line1 = lines[i+2].strip() if i+2 < len(lines) else ""
            num_line2 = lines[i+3].strip() if i+3 < len(lines) else ""
            # Parse: '-IN R7,04,  INR 3,42,  INR 3,38,  -IN R7,00,'
            # and: '69,458.94   72,413.10  82,368.81  79,414.65'
            # The first and last numbers on each line are opening/closing
            parts1 = re.findall(r"-?INR?\s*[\d,]+", num_line1, re.I)
            parts2 = re.findall(r"[\d,]+\.\d{2}", num_line2)
            if parts1 and parts2:
                try:
                    # Opening = parts1[0] + '.' + parts2[0]
                    open_int  = re.sub(r"[^0-9]", "", parts1[0])
                    open_dec  = parts2[0].replace(",", "")
                    open_neg  = "-" in parts1[0]
                    open_val  = float(open_int + "." + open_dec.split(".")[-1])
                    info["opening_balance"] = -open_val if open_neg else open_val
                except Exception:
                    pass
                try:
                    close_int = re.sub(r"[^0-9]", "", parts1[-1])
                    close_dec = parts2[-1].replace(",", "")
                    close_neg = "-" in parts1[-1]
                    close_val = float(close_int + "." + close_dec.split(".")[-1])
                    info["closing_balance"] = -close_val if close_neg else close_val
                except Exception:
                    pass
            break


# ---------------------------------
# OPENING / CLOSING BALANCE
# ---------------------------------
def extract_summary_balances(pdf_path, info):
    """
    CSB has explicit Opening/Closing Balance in the summary block on page 1.
    extract_account_info() handles this. Fallback: use first/last transaction balance.
    """
    if info.get("opening_balance") is None or info.get("closing_balance") is None:
        txns = extract_transactions(pdf_path)
        if txns:
            if info.get("closing_balance") is None:
                info["closing_balance"] = txns[-1].get("balance")


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    """
    Extract all transactions from a CSB Bank PDF statement.

    CSB BANK PDF CHARACTERISTICS:
    ==============================
    - Text-based PDF (pdfplumber extracts chars)
    - 6 columns: Date | Details | Ref No./Cheque No. | Debit | Credit | Balance
    - Date format: 'DD MON YYYY' (e.g. '01 SEP 2025') → output as 'DD-MM-YYYY'
    - Empty cells use '-' (not blank)
    - Balance format: '-INR 6,99,69,45 8.94 Dr' (space is PDF artifact in the number)
    - Details (description) spans multiple lines within one cell (\n separated)
    - Account info table is on page 1 (separate 4-col table above the txn table)
    - Lines strategy works reliably across all pages

    KEY CHALLENGES:
    1. Balance parsing: number has an injected space e.g. '6,99,69,45 8.94'
       which means '6,99,69,458.94' — handled by _clean_balance_csb()
    2. Multi-line descriptions: joined with space after stripping \n
    3. Ref No has spaces in it: 'SBINR120250903975765 60' → kept as-is
    """
    transactions   = []
    column_mapping = None

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )

            if not tables:
                continue

            for table in tables:

                # Skip the account info table (4 cols) — only process 6-col txn table
                if not table or len(table[0]) != 6:
                    continue

                for row in table:

                    if not row or len(row) < 6:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    # Detect header row
                    detected = _detect_columns_csb(row_clean)
                    if detected:
                        column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    # Validate date column
                    date_cell = (row[column_mapping.get("date", 0)] or "").strip()
                    if not _is_txn_date(date_cell):
                        continue

                    # Description — join multi-line content
                    desc_raw = row[column_mapping.get("description", 1)] or ""
                    description = re.sub(r"\s+", " ", desc_raw.replace("\n", " ")).strip()

                    # Ref / Cheque number — keep spaces (PDF artifact but part of ref)
                    ref_no = (row[column_mapping.get("cheque", 2)] or "").strip() or None

                    debit   = _clean_amount_csb(row[column_mapping.get("debit", 3)])
                    credit  = _clean_amount_csb(row[column_mapping.get("credit", 4)])
                    balance = _clean_balance_csb(row[column_mapping.get("balance", 5)])

                    transactions.append({
                        "date":        _reformat_date(date_cell),  # DD MON YYYY → DD-MM-YYYY
                        "description": description,
                        "ref_no":      ref_no,
                        "debit":       debit,
                        "credit":      credit,
                        "balance":     balance,
                    })

    return transactions