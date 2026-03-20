import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns
)

BANK_KEY = "au bank"
BANK_DISPLAY_NAME = "AU Small Finance Bank"


# ---------------------------------
# TABLE HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date": [
        "trans date",
        "txn date",
        "transaction date"
    ],
    "description": [
        "description",
        "description/narration",
        "narration",
        "descriptionnarration"
    ],
    "debit": [
        "debit(dr)",
        "debit",
        "debitdr. inr"
    ],
    "credit": [
        "credit(cr)",
        "credit",
        "creditcr. inr"
    ],
    "balance": [
        "balance",
        "balance inr",
        "running total",
        "amount"
    ]
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
CUSTOMER_PATTERN            = r"(customer\s*name|account\s*name)\s*[:\-]?\s*(.+)"
ACCOUNT_NO_PATTERN          = r"account\s*(no\.?|number)\s*[:\-]?\s*(\d{10,})"
CUSTOMER_ID_PATTERN         = r"(customer\s*id|primary\s*customer\s*id)\s*[:\-]?\s*(\d+)"
IFSC_PATTERN                = r"\bAUBL[A-Z0-9]{7}\b"
CUSTOMER_TYPE_PATTERN       = r"customer\s*type\s*[:\-]?\s*(.+)"

STATEMENT_PERIOD_PATTERN = (
    r"(?:statement\s*(?:period|from))\s*[:\-]?\s*"
    r"(\d{2}-[A-Za-z]{3}-\d{4})"
    r".*?(?:to|To)\s*"
    r"(\d{2}-[A-Za-z]{3}-\d{4})"
)
STATEMENT_PERIOD_PATTERN_V2 = (
    r"statement\s*period\s+"
    r"(\d{2}-[A-Za-z]{3}-\d{4})"
    r"\s+[Tt]o\s+"
    r"(\d{2}-[A-Za-z]{3}-\d{4})"
)

DATE_PATTERN = r"\d{2}-[A-Za-z]{3}-\d{4}|\d{4}-\d{2}-\d{2}"

# Keywords that confirm a value is a valid account type
ACC_TYPE_KEYWORDS = [
    "savings", "current", "business", "platinum", "gold",
    "salary", "nre", "nro", "fd", "recurring", "proprietorship",
    "individual", "corporate", "basic", "au "
]

# Patterns that are NOT account type values
ACC_TYPE_NOISE = re.compile(
    r"joint\s*holder|currency|nominee|mobile|e[\-\s]?mail|"
    r"account\s*(no|number|holder|name)|ifsc|micr|branch|"
    r"statement\s*(date|period|from)|address|city|state|pin",
    re.I
)


# =====================================
# CLEAN AMOUNT — handles Rs. prefix
# and Indian comma format (4,00,000.00)
# =====================================
def _clean_amount_au(value):
    """
    AU bank uses Indian format: "Rs. 4,00,000.00" or "Rs.4,00,000.00"
    Falls back to base clean_amount if no Rs. prefix.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    # Strip Rs. / INR / ₹ prefix
    value = re.sub(r"^(Rs\.?|INR|₹)\s*", "", value, flags=re.I).strip()
    # Remove all commas
    value = value.replace(",", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# =====================================
# ACCOUNT INFO EXTRACTION
# =====================================
def extract_account_info(lines):

    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    for i, line in enumerate(lines):

        if not line:
            continue

        text = line.strip()

        # ---------------------------
        # Account Holder
        # ---------------------------
        if info["account_holder"] is None:
            m = re.search(CUSTOMER_PATTERN, text, re.I)
            if m:
                holder = m.group(2)
                holder = re.split(r"statement\s*date", holder, flags=re.I)[0]
                info["account_holder"] = holder.strip()

        # ---------------------------
        # Account Number
        # ---------------------------
        if info["account_number"] is None:
            m = re.search(ACCOUNT_NO_PATTERN, text, re.I)
            if m:
                info["account_number"] = m.group(2)

        # ---------------------------
        # Customer ID
        # ---------------------------
        if info["customer_id"] is None:
            m = re.search(CUSTOMER_ID_PATTERN, text, re.I)
            if m:
                info["customer_id"] = m.group(2)

        # ---------------------------
        # IFSC
        # ---------------------------
        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN, text)
            if m:
                info["ifsc"] = m.group()

        # ---------------------------
        # Account Type — multi-format
        # ---------------------------
        if info["acc_type"] is None:

            # ── au2: "Account Type :" label exists ──
            if re.search(r"account\s*type", text, re.I):

                acc_type = ""

                # Strategy A — colon on same line WITH a real value
                colon_match = re.search(
                    r"account\s*type\s*[:\-]\s*(.+)", text, re.I
                )
                if colon_match:
                    candidate = colon_match.group(1).strip()
                    candidate = re.split(ACC_TYPE_NOISE, candidate)[0].strip()
                    if candidate and len(candidate) > 4:
                        acc_type = candidate

                # Strategy B — value on next line (skip tiny fragments like "Accou")
                if not acc_type and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if (
                        next_line
                        and len(next_line) > 4
                        and not ACC_TYPE_NOISE.search(next_line)
                        and not re.search(r"\d{10,}|AUBL|@", next_line)
                        and any(kw in next_line.lower() for kw in ACC_TYPE_KEYWORDS)
                    ):
                        acc_type = next_line

                # Strategy C — au2 multi-column: real value is ABOVE the label
                # pdfplumber interleaves columns so value lands before label in line order
                if not acc_type:
                    for back in range(1, 7):
                        if i - back < 0:
                            break
                        prev_line = lines[i - back].strip()
                        if not prev_line:
                            continue
                        if ACC_TYPE_NOISE.search(prev_line):
                            continue
                        if re.search(
                            r"\d{10,}|AUBL|@|gmail|yahoo|\bINR\b|Rs\.",
                            prev_line, re.I
                        ):
                            continue
                        if any(kw in prev_line.lower() for kw in ACC_TYPE_KEYWORDS):
                            acc_type = prev_line
                            break

                if acc_type:
                    info["acc_type"] = acc_type.strip()

            # ── au3: no "Account Type" label — use "Customer Type" instead ──
            elif re.search(r"customer\s*type", text, re.I):
                m = re.search(CUSTOMER_TYPE_PATTERN, text, re.I)
                if m:
                    candidate = m.group(1).strip()
                    candidate = re.split(ACC_TYPE_NOISE, candidate)[0].strip()
                    if candidate:
                        info["acc_type"] = candidate

        # ---------------------------
        # Currency
        # ---------------------------
        if info.get("currency") is None:
            if "currency" in text.lower() and "inr" in text.lower():
                info["currency"] = "INR"

        # ---------------------------
        # Statement Period
        # ---------------------------
        if info["statement_period"]["from"] is None:
            for pattern in (STATEMENT_PERIOD_PATTERN_V2, STATEMENT_PERIOD_PATTERN):
                m = re.search(pattern, text, re.I)
                if m:
                    info["statement_period"]["from"] = m.group(1)
                    info["statement_period"]["to"]   = m.group(2)
                    break

    # ---------------------------
    # Post-process: drop trailing truncated word
    # e.g. "Current Accou" → "Current"
    # ---------------------------
    if info["acc_type"]:
        parts       = info["acc_type"].split()
        last        = parts[-1] if parts else ""
        known_short = {"nre", "nro", "fd", "od", "ca", "sa"}
        if len(parts) > 1 and len(last) < 5 and last.lower() not in known_short:
            info["acc_type"] = " ".join(parts[:-1]).strip()

    return info


# =====================================
# OPENING / CLOSING BALANCE
# =====================================
def extract_summary_balances(pdf_path, info):

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

                    if info.get("opening_balance") is None:
                        if "opening balance" in row_text:
                            m = re.search(r"([\d,]+\.\d+)", row_text)
                            if m:
                                info["opening_balance"] = _clean_amount_au(m.group(1))

                    if info.get("closing_balance") is None:
                        if "closing balance" in row_text:
                            m = re.search(r"([\d,]+\.\d+)", row_text)
                            if m:
                                info["closing_balance"] = _clean_amount_au(m.group(1))


# =====================================
# TRANSACTION PARSER
# =====================================
def _row_to_txn(row, column_mapping, last_txn):

    # Skip rows too short for the mapped columns
    if not row or len(row) <= max(column_mapping.values()):
        return None

    if "date" not in column_mapping:
        return None

    date_val = row[column_mapping["date"]]
    if not date_val:
        return None

    date_val = date_val.strip()
    if not re.search(DATE_PATTERN, date_val):
        return None

    txn = {
        "date":        date_val,
        "description": None,
        "debit":       None,
        "credit":      None,
        "balance":     None
    }

    try:

        # Description
        if "description" in column_mapping:
            desc = row[column_mapping["description"]]
            if desc:
                txn["description"] = desc.replace("\n", " ").strip()

        # ── Pattern 1: au2 — separate Debit(Dr.) / Credit(Cr.) columns ──
        if "debit" in column_mapping:
            txn["debit"] = _clean_amount_au(row[column_mapping["debit"]])

        if "credit" in column_mapping:
            txn["credit"] = _clean_amount_au(row[column_mapping["credit"]])

        # ── Pattern 2: au3 mini-statement — D/C flag + single Amount column ──
        # Row layout: [0]TxnDate [1]ValueDate [2]Desc [3]Chq.Ref [4]D/C [5]Amount [6]RunningTotal
        if txn["debit"] is None and txn["credit"] is None:
            if len(row) >= 6:
                dc     = str(row[4]).strip().upper()
                amount = _clean_amount_au(row[5])
                if dc == "D":
                    txn["debit"]  = amount
                elif dc == "C":
                    txn["credit"] = amount
                # Running Total → balance (col 6)
                if len(row) >= 7 and txn["balance"] is None:
                    txn["balance"] = _clean_amount_au(row[6])

        # Balance from mapped column (au2 format)
        if txn["balance"] is None and "balance" in column_mapping:
            txn["balance"] = _clean_amount_au(row[column_mapping["balance"]])

    except (IndexError, TypeError):
        return None

    return txn


# =====================================
# TRANSACTION EXTRACTION
# =====================================
def extract_transactions(pdf_path):

    transactions   = []
    column_mapping = None
    last_txn       = None

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables(
                {
                    "vertical_strategy":   "lines",
                    "horizontal_strategy": "lines"
                }
            )

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

                    detected = detect_columns(row_clean, HEADER_MAP)

                    if detected:
                        column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    txn = _row_to_txn(row, column_mapping, last_txn)

                    if txn:
                        transactions.append(txn)
                        last_txn = txn

    return transactions
