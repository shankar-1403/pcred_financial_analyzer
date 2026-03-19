import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns        # imported but NOT used for BOI — see _detect_columns_boi below
)

BANK_KEY          = "boi"
BANK_DISPLAY_NAME = "Bank of India"


# ---------------------------------
# TABLE HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date": [
        "txn date",
        "transaction date",
        "date"
    ],
    "description": [
        "description",
        "narration",
        "particulars"
    ],
    "cheque": [
        "cheque no",
        "chq no",
        "cheque number",
        "ref no"
    ],
    "debit": [
        "withdrawal",
        "withdrawal\n(in rs.)",
        "withdrawal (in rs.)",
        "debit",
        "dr"
    ],
    "credit": [
        "deposits",
        "deposits\n(in rs.)",
        "deposits (in rs.)",
        "credit",
        "cr"
    ],
    "balance": [
        "balance",
        "balance\n(in rs.)",
        "balance (in rs.)",
        "running balance"
    ]
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
ACCOUNT_HOLDER_PATTERN   = r"name\s*[:\-]\s*(.+?)(?:\s{2,}|account\s*no|$)"
ACCOUNT_NO_PATTERN       = r"account\s*no\.?\s*[:\-]\s*(\d{10,})"
CUSTOMER_ID_PATTERN      = r"customer\s*id\s*[:\-]\s*(\d+)"
IFSC_PATTERN             = r"\bBKID[A-Z0-9]{7}\b"
MICR_PATTERN             = r"micr\s*(?:code)?\s*[:\-]\s*(\d{9})"
BRANCH_PATTERN           = r"^([A-Za-z ]+branch)"
ACCOUNT_TYPE_PATTERN     = r"account\s*type\s*[:\-]\s*(.+?)(?:\s{2,}|$)"
STATEMENT_DATE_PATTERN   = r"date\s*[:\-]\s*(\d{2}/\d{2}/\d{4})"
STATEMENT_PERIOD_PATTERN = (
    r"for\s+the\s+period\s+"
    r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})"
    r"\s+to\s+"
    r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})"
)
STATEMENT_PERIOD_PATTERN_V2 = (
    r"(?:statement\s+(?:period|from))\s*[:\-]?\s*"
    r"(\d{2}-\d{2}-\d{4})"
    r"\s+to\s+"
    r"(\d{2}-\d{2}-\d{4})"
)

ACC_TYPE_NOISE = re.compile(
    r"joint\s*holder|currency|nominee|mobile|e[\-\s]?mail|"
    r"account\s*(no|number)|ifsc|micr|branch|statement|"
    r"address|city|state|pin|customer",
    re.I
)


# ---------------------------------
# BOI-SPECIFIC COLUMN DETECTOR
# ---------------------------------
def _detect_columns_boi(row_clean):
    """
    BOI-specific column detector — replaces base.detect_columns for this file only.

    WHY this exists instead of using base.detect_columns:
      base.detect_columns uses pure substring matching ('a in cell').
      For BOI headers this causes two silent bugs:
        1. alias 'cr'      (2 chars) matches inside 'des-CR-iption' → credit=col2
        2. alias 'deposit' (7 chars) matches inside 'deposits'      → works but fragile

      This local version uses exact-match-first, then guards substring matches
      to aliases of 4+ characters, so short aliases like 'cr' and 'dr' can
      never steal the wrong column.

      base.detect_columns is left completely untouched so all other bank
      modules (icici, sbi, hdfc, axis, etc.) continue working as before.
    """
    mapping = {}

    for field, variants in HEADER_MAP.items():

        # Pass 1: exact cell match (e.g. 'deposits' == 'deposits')
        for idx, cell in enumerate(row_clean):
            if cell in variants:
                mapping[field] = idx
                break
        if field in mapping:
            continue

        # Pass 2: alias contained in cell, but only for aliases 4+ chars long
        #         blocks 'cr' (2) and 'dr' (2) from matching 'description'
        for idx, cell in enumerate(row_clean):
            if any(len(v) >= 4 and v in cell for v in variants):
                mapping[field] = idx
                break

    return mapping if len(mapping) >= 3 else None


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_boi(value):
    """
    Handles Indian comma format: '2,33,869.00', '10,00,000.00'
    Also handles Rs. / INR / rupee prefixes.
    Returns float or None.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null", "(in rs.)"):
        return None
    value = re.sub(r"^(Rs\.?|INR|₹)\s*", "", value, flags=re.I).strip()
    value = value.replace(",", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------
# ROW HELPERS
# ---------------------------------
def _is_date(value):
    """Return True if value contains a dd-mm-yyyy date."""
    if not value:
        return False
    return bool(re.search(r"\d{2}-\d{2}-\d{4}", str(value).strip()))


def _is_valid_cheque(value):
    """
    Accept only clean digit-only cheque/ref numbers (3-9 digits).
    Rejects PDF artifacts like '/Z', 'LE', 'TERN A L A C C O'.
    """
    if not value:
        return False
    return bool(re.match(r"^\d{3,9}$", str(value).strip()))


# ---------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines):

    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    for i, line in enumerate(lines):

        if not line:
            continue

        text = line.strip()

        # Branch (usually the first line)
        if info["branch"] is None:
            m = re.search(BRANCH_PATTERN, text, re.I)
            if m:
                info["branch"] = m.group(1).strip()

        # Statement request date
        if info["statement_request_date"] is None:
            m = re.search(STATEMENT_DATE_PATTERN, text, re.I)
            if m:
                info["statement_request_date"] = m.group(1).replace("/", "-")

        # Account Holder
        if info["account_holder"] is None:
            m = re.search(ACCOUNT_HOLDER_PATTERN, text, re.I)
            if m:
                holder = m.group(1).strip()
                holder = re.split(
                    r"\s{2,}|account\s*no|customer|ifsc|micr|address",
                    holder, flags=re.I
                )[0].strip()
                if holder and len(holder) > 3:
                    info["account_holder"] = holder

        # Account Number
        if info["account_number"] is None:
            m = re.search(ACCOUNT_NO_PATTERN, text, re.I)
            if m:
                info["account_number"] = m.group(1)

        # Customer ID
        if info["customer_id"] is None:
            m = re.search(CUSTOMER_ID_PATTERN, text, re.I)
            if m:
                info["customer_id"] = m.group(1)

        # IFSC
        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN, text)
            if m:
                info["ifsc"] = m.group()

        # MICR
        if info["micr"] is None:
            m = re.search(MICR_PATTERN, text, re.I)
            if m:
                info["micr"] = m.group(1)

        # Account Type
        if info["acc_type"] is None:
            m = re.search(ACCOUNT_TYPE_PATTERN, text, re.I)
            if m:
                candidate = re.split(ACC_TYPE_NOISE, m.group(1).strip())[0].strip()
                if candidate and len(candidate) > 2:
                    info["acc_type"] = candidate

        # Currency
        if info.get("currency") is None:
            if re.search(r"\bINR\b|in\s*rs\.", text, re.I):
                info["currency"] = "INR"

        # Statement Period
        if info["statement_period"]["from"] is None:
            for pattern in (STATEMENT_PERIOD_PATTERN_V2, STATEMENT_PERIOD_PATTERN):
                m = re.search(pattern, text, re.I)
                if m:
                    info["statement_period"]["from"] = m.group(1).strip()
                    info["statement_period"]["to"]   = m.group(2).strip()
                    break

    return info


# ---------------------------------
# OPENING / CLOSING BALANCE
# ---------------------------------
def extract_summary_balances(pdf_path, info):
    """
    BOI statements don't have an explicit opening/closing balance row.
    Scans all tables for those keywords; if not found, caller should
    derive from first/last transaction balance.
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue
            for table in tables:
                for row in table:
                    if not row:
                        continue
                    row_text = " ".join([str(x) for x in row if x]).lower()
                    if info.get("opening_balance") is None and "opening balance" in row_text:
                        m = re.search(r"([\d,]+\.\d+)", row_text)
                        if m:
                            info["opening_balance"] = _clean_amount_boi(m.group(1))
                    if info.get("closing_balance") is None and "closing balance" in row_text:
                        m = re.search(r"([\d,]+\.\d+)", row_text)
                        if m:
                            info["closing_balance"] = _clean_amount_boi(m.group(1))


# ---------------------------------
# ROW → TRANSACTION
# ---------------------------------
def _row_to_txn(row, column_mapping, last_txn):
    """
    Convert one raw PDF table row into a transaction dict.

    BOI PDF quirks handled:
      - _is_valid_cheque() rejects non-numeric PDF artifacts that bleed
        from the description column into the cheque column
      - When both debit and credit columns have a value, both are recorded
      - When only the credit/deposit column has a value, a balance-delta
        check confirms whether it is truly a credit or a misclassified debit
      - Last resort: derive debit/credit from balance delta when no amount
        is found in either column
    """
    if not row or len(row) <= max(column_mapping.values()):
        return None

    if "date" not in column_mapping:
        return None

    date_val = str(row[column_mapping["date"]] or "").strip()
    if not _is_date(date_val):
        return None

    txn = {
        "date":        date_val,
        "description": None,
        "cheque_no":   None,
        "debit":       None,
        "credit":      None,
        "balance":     None
    }

    try:

        # Description
        if "description" in column_mapping:
            desc = row[column_mapping["description"]]
            if desc:
                txn["description"] = str(desc).replace("\n", " ").strip()

        # Cheque — real cheque numbers stored; artifacts appended to description
        if "cheque" in column_mapping:
            chq = row[column_mapping["cheque"]]
            if chq:
                if _is_valid_cheque(chq):
                    txn["cheque_no"] = str(chq).strip()
                else:
                    txn["description"] = ((txn["description"] or "") + " " + str(chq).strip()).strip()

        raw_debit_cell  = str(row[column_mapping["debit"]]  or "").strip() if "debit"   in column_mapping else ""
        raw_credit_cell = str(row[column_mapping["credit"]] or "").strip() if "credit"  in column_mapping else ""

        raw_withdrawal = _clean_amount_boi(raw_debit_cell)
        raw_deposits   = _clean_amount_boi(raw_credit_cell)
        raw_balance    = _clean_amount_boi(row[column_mapping["balance"]]) if "balance" in column_mapping else None

        # If debit/credit cell has text but is NOT an amount, it is a
        # description artifact (e.g. "UNTS" completing "JSFBIN...ACCOUNTS")
        if raw_withdrawal is None and raw_debit_cell:
            txn["description"] = ((txn["description"] or "") + " " + raw_debit_cell).strip()
        if raw_deposits is None and raw_credit_cell:
            txn["description"] = ((txn["description"] or "") + " " + raw_credit_cell).strip()

        txn["balance"] = raw_balance

        if raw_withdrawal is not None and raw_deposits is not None:
            txn["debit"]  = raw_withdrawal
            txn["credit"] = raw_deposits

        elif raw_withdrawal is not None:
            txn["debit"] = raw_withdrawal

        elif raw_deposits is not None:
            if (last_txn is not None
                    and last_txn.get("balance") is not None
                    and raw_balance is not None):
                delta = round(raw_balance - last_txn["balance"], 2)
                if abs(delta + raw_deposits) < 1.0:
                    txn["debit"]  = raw_deposits
                else:
                    txn["credit"] = raw_deposits
            else:
                txn["credit"] = raw_deposits

        # Last resort: derive from balance delta
        if (txn["debit"] is None and txn["credit"] is None
                and raw_balance is not None
                and last_txn is not None
                and last_txn.get("balance") is not None):
            delta = round(raw_balance - last_txn["balance"], 2)
            if delta >= 0:
                txn["credit"] = round(delta, 2)
            else:
                txn["debit"]  = round(abs(delta), 2)

    except (IndexError, TypeError):
        return None

    if (txn["debit"] is None and txn["credit"] is None
            and txn["balance"] is None and not txn["description"]):
        return None

    return txn


# ---------------------------------
# CONTINUATION ROW HANDLER
# ---------------------------------
def _apply_continuation(last_txn, row, column_mapping):
    """
    Merge a continuation row (no date) into the previous transaction.
    Appends any description text and fills in any missing amount fields.
    """
    if "description" in column_mapping:
        cont_desc = (row[column_mapping["description"]] or "").replace("\n", " ").strip()
        if cont_desc:
            last_txn["description"] = (
                (last_txn["description"] or "") + " " + cont_desc
            ).strip()

    if "balance" in column_mapping and last_txn["balance"] is None:
        amt = _clean_amount_boi(row[column_mapping["balance"]])
        if amt is not None:
            last_txn["balance"] = amt

    if "debit" in column_mapping and last_txn["debit"] is None:
        amt = _clean_amount_boi(row[column_mapping["debit"]])
        if amt is not None:
            last_txn["debit"] = amt

    if "credit" in column_mapping and last_txn["credit"] is None:
        amt = _clean_amount_boi(row[column_mapping["credit"]])
        if amt is not None:
            last_txn["credit"] = amt


# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    """
    Extract all transactions from a BOI PDF bank statement.

    Uses _detect_columns_boi() instead of base.detect_columns() to avoid
    the substring-matching bug in base that maps 'cr'/'deposit' to the
    wrong column for BOI's specific header layout.
    All other bank modules continue using base.detect_columns unchanged.
    """
    transactions   = []
    column_mapping = None
    last_txn       = None   # persists across every page and table

    EXTRACT_SETTINGS = [
        {"vertical_strategy": "lines",  "horizontal_strategy": "lines"},
        {"vertical_strategy": "text",   "horizontal_strategy": "text"},
    ]

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            tables = None
            for settings in EXTRACT_SETTINGS:
                candidate = page.extract_tables(settings)
                if candidate:
                    tables = candidate
                    break

            if not tables:
                continue

            for table in tables:

                for row in table:

                    if not row:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    # ↓ Use BOI-specific detector, NOT base.detect_columns
                    detected = _detect_columns_boi(row_clean)
                    if detected:
                        column_mapping = detected
                        continue

                    # Skip sub-header rows like "(in Rs.)"
                    if all(re.match(r"^\(in\s*rs\.?\)$|^$", c) for c in row_clean):
                        continue

                    if column_mapping is None:
                        continue

                    # Check date cell to distinguish new txn vs continuation row
                    date_col  = column_mapping.get("date", 1)
                    date_cell = (
                        str(row[date_col] or "").strip()
                        if len(row) > date_col else ""
                    )

                    if last_txn is not None and not _is_date(date_cell):
                        _apply_continuation(last_txn, row, column_mapping)
                        continue

                    txn = _row_to_txn(row, column_mapping, last_txn)

                    if txn:
                        transactions.append(txn)
                        last_txn = txn

    return transactions