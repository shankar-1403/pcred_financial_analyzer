import re
import pdfplumber
from datetime import datetime
from collections import defaultdict

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "boi"
BANK_DISPLAY_NAME = "Bank of India"


# ---------------------------------------------------------------------------
# HEADER MAP — covers both BOI formats:
#   Format A (Personal): SNO | TRAN DATE | INST NO | DESCRIPTION | DEBITS | CREDITS | BALANCE
#   Format B (CA):       SI No | Txn Date | Description | Cheque No | Withdrawal (in Rs.) | Deposits (in Rs.) | Balance (in Rs.)
# ---------------------------------------------------------------------------
HEADER_MAP = {
    "sno":         ["sno", "si no", "sl no", "sr no"],
    "date":        ["tran date", "txn date", "transaction date", "date"],
    "description": ["description", "narration", "particulars"],
    "cheque":      ["cheque no", "chq no", "cheque number", "ref no", "inst no"],
    "debit":       ["debits", "debit", "withdrawal (in rs.)", "withdrawal", "dr"],
    "credit":      ["credits", "credit", "deposits (in rs.)", "deposits", "deposit", "cr"],
    "balance":     ["balance (in rs.)", "balance", "running balance"],
}


# ---------------------------------------------------------------------------
# REGEX PATTERNS
# ---------------------------------------------------------------------------
ACCOUNT_NO_PATTERN       = r"(?:a/c\s*no|account\s*no\.?)\s*[:\-]\s*([\d\.e\+]+)"
CUSTOMER_ID_PATTERN      = r"(?:custid|customer\s*id)\s*[:\-]\s*(\d+)"
IFSC_PATTERN             = r"\bBKID[A-Z0-9]{7}\b"
MICR_PATTERN             = r"micr\s*(?:code)?\s*[:\-]\s*(\d{9})"
ACCOUNT_TYPE_PATTERN     = r"(?:account\s*type|type)\s*[:\-]\s*(.+?)(?:\s{2,}|\n|$)"
STATEMENT_DATE_PATTERN   = r"date\s+(\d{2}-\d{2}-\d{4})"

# Matches "FROM 01-04-2024 TO 31-03-2025"  (BOI personal)
STATEMENT_PERIOD_PERSONAL = (
    r"(?:from)\s+(\d{2}-\d{2}-\d{4})\s+to\s+(\d{2}-\d{2}-\d{4})"
)
# Matches "Statement Period: 01-04-2024 to 31-03-2025"
STATEMENT_PERIOD_PATTERN_V2 = (
    r"(?:statement\s+(?:period|from))\s*[:\-]?\s*"
    r"(\d{2}-\d{2}-\d{4})"
    r"\s+to\s+"
    r"(\d{2}-\d{2}-\d{4})"
)
# Matches "For the period April 1, 2025 to ..."  (BOI CA)
STATEMENT_PERIOD_PATTERN = (
    r"for\s+the\s+period\s+"
    r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[\s\-][A-Za-z]+[\s\-]\d{4}|\d{2}-\d{2}-\d{4})"
    r"\s+to\s+"
    r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[\s\-][A-Za-z]+[\s\-]\d{4}|\d{2}-\d{2}-\d{4})"
)

ACC_TYPE_NOISE = re.compile(
    r"joint\s*holder|currency|nominee|mobile|e[\-\s]?mail|"
    r"account\s*(no|number)|ifsc|micr|branch|statement|"
    r"address|city|state|pin|customer",
    re.I
)

_DATE_RE = re.compile(r"\d{2}-\d{2}-\d{4}")


# ---------------------------------------------------------------------------
# BOI-SPECIFIC COLUMN DETECTOR
# Exact match first → then substring (min 4 chars) to prevent
# 'cr' / 'dr' (2 chars) from stealing the description column.
# ---------------------------------------------------------------------------
def _detect_columns_boi(row_clean):
    mapping = {}

    for field, variants in HEADER_MAP.items():
        # Pass 1: exact cell match
        for idx, cell in enumerate(row_clean):
            if cell in variants:
                mapping[field] = idx
                break
        if field in mapping:
            continue

        # Pass 2: alias contained in cell, alias must be ≥4 chars
        for idx, cell in enumerate(row_clean):
            if any(len(v) >= 4 and v in cell for v in variants):
                mapping[field] = idx
                break

    # Need at least date + one amount column to be valid
    return mapping if ("date" in mapping and
                       ("debit" in mapping or "credit" in mapping)) else None


# ---------------------------------------------------------------------------
# AMOUNT CLEANER
# Handles Indian comma format + "Cr." / "Dr." suffix (BOI personal format)
# "2,33,869.00"  → 233869.0
# "5,000.00 Cr." → 5000.0
# "3,820.00 Dr." → 3820.0
# ---------------------------------------------------------------------------
def _clean_amount_boi(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    value = re.sub(r"^(Rs\.?|INR|₹)\s*", "", value, flags=re.I).strip()
    value = re.sub(r"\s*(Cr\.|Dr\.|CR|DR)$", "", value, flags=re.I).strip()
    value = value.replace(",", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _is_date(value):
    return bool(_DATE_RE.search(str(value or "").strip()))


def _is_valid_cheque(value):
    """Accept only numeric cheque/ref numbers (3–9 digits)."""
    return bool(re.match(r"^\d{3,9}$", str(value or "").strip()))


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


def _sno_key(txn: dict):
    """Secondary sort key using SNO so same-date transactions stay in PDF order."""
    try:
        return int(txn.get("_sno") or 0)
    except (ValueError, TypeError):
        return 0


def _parse_account_number(raw: str) -> str | None:
    """
    BOI personal stores account number as scientific notation in PDF text:
    '8.410100027021e+12' → '8410100027021'
    Also handles plain digit strings.
    """
    raw = (raw or "").strip()
    try:
        return str(int(float(raw)))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------------------------------------------------
def extract_account_info(lines):
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    for i, line in enumerate(lines):
        if not line:
            continue
        text = line.strip()

        # ── Branch ──────────────────────────────────────────────────────────
        # CA format:       "Motijheel Branch"  (has word "branch")
        # Personal format: "Bank Of India MALAD EAST"  (no word "branch")
        if info["branch"] is None:
            m = re.search(r"^([A-Za-z ]+branch)", text, re.I)
            if m:
                info["branch"] = m.group(1).strip()
            elif re.match(r"^bank\s+of\s+india\s+(.+)$", text, re.I):
                m = re.match(r"^bank\s+of\s+india\s+(.+)$", text, re.I)
                location = m.group(1).strip()
                if location and not re.match(r"^bank", location, re.I):
                    info["branch"] = location

        # ── Statement Request Date ───────────────────────────────────────────
        if info["statement_request_date"] is None:
            m = re.search(STATEMENT_DATE_PATTERN, text, re.I)
            if m:
                info["statement_request_date"] = m.group(1).replace("/", "-")

        # ── Account Holder ───────────────────────────────────────────────────
        # CA format:       "Name : M3I RETAIL PRIVATE LIMITED"
        # Personal format: "MR KANBEHARI DEVKINANDAN AGRAWAL CUSTID : 001559769"
        if info["account_holder"] is None:
            # CA: explicit Name label
            m = re.search(r"name\s*[:\-]\s*(.+?)(?:\s{2,}|account\s*no|$)", text, re.I)
            if m:
                holder = re.split(
                    r"\s{2,}|account\s*no|customer|ifsc|micr|address",
                    m.group(1).strip(), flags=re.I
                )[0].strip()
                if holder and len(holder) > 3:
                    info["account_holder"] = holder

            # Personal: line starts with MR/MRS/MS/DR/SHRI/SMT + name, ends with CUSTID
            if not info["account_holder"]:
                m = re.match(
                    r"^((?:MR|MRS|MS|DR|SHRI|SMT)\.?\s+[\w\s]+?)(?:\s{2,}|\bCUSTID\b|\bA/C\b)",
                    text, re.I
                )
                if m:
                    info["account_holder"] = m.group(1).strip()

        # ── Account Number ───────────────────────────────────────────────────
        if info["account_number"] is None:
            # CA format: "Account No : 465520110000865"
            # Personal:  "A/C NO : 8.410100027021e+12"
            m = re.search(ACCOUNT_NO_PATTERN, text, re.I)
            if m:
                parsed = _parse_account_number(m.group(1))
                if parsed:
                    info["account_number"] = parsed

            # Personal fallback: "Statement of Account 8.410100027021e+12 FROM..."
            if not info["account_number"]:
                m = re.search(r"statement\s+of\s+account\s+([\d\.e\+]+)", text, re.I)
                if m:
                    parsed = _parse_account_number(m.group(1))
                    if parsed:
                        info["account_number"] = parsed

        # ── Customer ID ──────────────────────────────────────────────────────
        # CA: "Customer ID : 202156371"   Personal: "CUSTID : 001559769"
        if info["customer_id"] is None:
            m = re.search(CUSTOMER_ID_PATTERN, text, re.I)
            if m:
                info["customer_id"] = m.group(1)

        # ── IFSC ─────────────────────────────────────────────────────────────
        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN, text)
            if m:
                info["ifsc"] = m.group()

        # ── MICR ─────────────────────────────────────────────────────────────
        if info["micr"] is None:
            m = re.search(MICR_PATTERN, text, re.I)
            if m:
                info["micr"] = m.group(1)

        # ── Account Type ─────────────────────────────────────────────────────
        # CA: "Account Type : Current Account"   Personal: "TYPE : SAVINGS BANK GENERAL"
        if info["acc_type"] is None:
            m = re.search(ACCOUNT_TYPE_PATTERN, text, re.I)
            if m:
                candidate = re.split(ACC_TYPE_NOISE, m.group(1).strip())[0].strip()
                if candidate and len(candidate) > 2:
                    info["acc_type"] = candidate

        # ── Currency ─────────────────────────────────────────────────────────
        if info.get("currency") is None:
            if re.search(r"\bINR\b|in\s*rs\.", text, re.I):
                info["currency"] = "INR"

        # ── Statement Period ─────────────────────────────────────────────────
        # Personal: "Statement of Account ... FROM 01-04-2024 TO 31-03-2025"
        # CA:       "Account Statement: For the period April 1, 2025 to December 13, 2025"
        if info["statement_period"]["from"] is None:
            for pattern in (
                STATEMENT_PERIOD_PERSONAL,    # FROM DD-MM-YYYY TO DD-MM-YYYY
                STATEMENT_PERIOD_PATTERN_V2,  # Statement Period: DD-MM-YYYY to DD-MM-YYYY
                STATEMENT_PERIOD_PATTERN,     # For the period Month DD, YYYY to ...
            ):
                m = re.search(pattern, text, re.I)
                if m:
                    info["statement_period"]["from"] = m.group(1).strip()
                    info["statement_period"]["to"]   = m.group(2).strip()
                    break

        # ── Joint Holder ─────────────────────────────────────────────────────
        # Personal: "JOINT HOLDER:" on one line, name on NEXT line
        if info["joint_holder"] is None:
            if re.search(r"joint\s*holder\s*:", text, re.I):
                m = re.search(r"joint\s*holder\s*:\s*(.+)", text, re.I)
                if m and m.group(1).strip() and "nominee" not in m.group(1).lower():
                    info["joint_holder"] = m.group(1).strip()
                elif i + 1 < len(lines):
                    next_line = (lines[i + 1] or "").strip()
                    if next_line and not re.search(
                        r"nominee|opening|statement|ifsc|micr|currency",
                        next_line, re.I
                    ):
                        info["joint_holder"] = next_line

    if info.get("currency") is None:
        info["currency"] = "INR"

    return info


# ---------------------------------------------------------------------------
# OPENING / CLOSING BALANCE
# ---------------------------------------------------------------------------
def extract_summary_balances(pdf_path, info):
    """
    Scans all tables for opening/closing balance rows.
    If not found, caller should derive from first/last transaction balance.
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


# ---------------------------------------------------------------------------
# ROW → TRANSACTION
# ---------------------------------------------------------------------------
def _row_to_txn(row, column_mapping, last_txn):
    if not row or len(row) <= max(column_mapping.values()):
        return None
    if "date" not in column_mapping:
        return None

    date_val = str(row[column_mapping["date"]] or "").strip()
    if not _is_date(date_val):
        return None

    m = _DATE_RE.search(date_val)
    date_val = m.group() if m else date_val

    txn = {
        "date":        date_val,
        "description": None,
        "cheque_no":   None,
        "debit":       None,
        "credit":      None,
        "balance":     None,
        "_sno":        None,  # temp — stable sort tiebreaker; removed in _finalise
    }

    try:
        # SNO — stable sort tiebreaker for same-date transactions
        if "sno" in column_mapping:
            sno_raw = str(row[column_mapping["sno"]] or "").strip()
            if sno_raw.isdigit():
                txn["_sno"] = int(sno_raw)

        # Description
        if "description" in column_mapping:
            desc = row[column_mapping["description"]]
            if desc:
                txn["description"] = str(desc).replace("\n", " ").strip()

        # Cheque / Inst No — numeric only, otherwise append to description
        if "cheque" in column_mapping:
            chq = str(row[column_mapping["cheque"]] or "").strip()
            if chq:
                if _is_valid_cheque(chq):
                    txn["cheque_no"] = chq
                elif chq not in ("0", ""):
                    txn["description"] = (
                        (txn["description"] or "") + " " + chq
                    ).strip()

        raw_balance_cell = str(row[column_mapping["balance"]] or "").strip() \
            if "balance" in column_mapping else ""
        raw_debit_cell   = str(row[column_mapping["debit"]]   or "").strip() \
            if "debit"   in column_mapping else ""
        raw_credit_cell  = str(row[column_mapping["credit"]]  or "").strip() \
            if "credit"  in column_mapping else ""

        debit_amt  = _clean_amount_boi(raw_debit_cell)
        credit_amt = _clean_amount_boi(raw_credit_cell)
        balance    = _clean_amount_boi(raw_balance_cell)

        txn["balance"] = balance

        # Non-amount text in amount cells → append to description
        if debit_amt is None and raw_debit_cell and raw_debit_cell not in ("0", "0.00", ""):
            txn["description"] = (
                (txn["description"] or "") + " " + raw_debit_cell
            ).strip()
        if credit_amt is None and raw_credit_cell and raw_credit_cell not in ("0", "0.00", ""):
            txn["description"] = (
                (txn["description"] or "") + " " + raw_credit_cell
            ).strip()

        # Assign debit / credit — skip 0.00 (BOI personal always fills unused column with 0)
        if debit_amt is not None and debit_amt != 0.0:
            txn["debit"] = debit_amt
        if credit_amt is not None and credit_amt != 0.0:
            txn["credit"] = credit_amt

        # Last resort: derive from balance delta
        if txn["debit"] is None and txn["credit"] is None:
            if (balance is not None
                    and last_txn is not None
                    and last_txn.get("balance") is not None):
                delta = round(balance - last_txn["balance"], 2)
                if delta >= 0:
                    txn["credit"] = delta
                else:
                    txn["debit"] = abs(delta)

    except (IndexError, TypeError):
        return None

    if (txn["debit"] is None and txn["credit"] is None
            and txn["balance"] is None and not txn["description"]):
        return None

    return txn


# ---------------------------------------------------------------------------
# CONTINUATION ROW
# ---------------------------------------------------------------------------
def _apply_continuation(last_txn, row, column_mapping):
    if "description" in column_mapping:
        cont = str(row[column_mapping["description"]] or "").replace("\n", " ").strip()
        if cont:
            last_txn["description"] = (
                (last_txn["description"] or "") + " " + cont
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


# ---------------------------------------------------------------------------
# FINALISE — strip internal temp keys before returning
# ---------------------------------------------------------------------------
def _finalise(txn: dict) -> dict:
    txn.pop("_sno", None)
    return txn


# ---------------------------------------------------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------------------------------------------------
def extract_transactions(pdf_path):
    """
    Extract all transactions from a BOI PDF bank statement.

    Handles two BOI formats:
      • Personal  — DEBITS/CREDITS columns, "5000.00 Cr." balance suffix
      • CA / Corporate — Withdrawal/Deposits columns, plain balance

    BOI PDFs are OLDEST-FIRST (SNO=1 on page 1) so NO reverse() needed.
    SNO is used as a stable tiebreaker so same-date transactions preserve
    their original PDF sequence after sorting.
    Final sort: date ASC → SNO ASC.
    """
    transactions   = []
    column_mapping = None
    last_txn       = None

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

                    # Detect column header row
                    detected = _detect_columns_boi(row_clean)
                    if detected:
                        column_mapping = detected
                        continue

                    # Skip sub-header rows like "(in Rs.)"
                    if all(re.match(r"^\(in\s*rs\.?\)$|^$", c) for c in row_clean):
                        continue

                    if column_mapping is None:
                        continue

                    date_col  = column_mapping.get("date", 1)
                    date_cell = str(row[date_col] or "").strip() \
                        if len(row) > date_col else ""

                    # Continuation row (no date) → merge into previous txn
                    if last_txn is not None and not _is_date(date_cell):
                        _apply_continuation(last_txn, row, column_mapping)
                        continue

                    txn = _row_to_txn(row, column_mapping, last_txn)
                    if txn:
                        transactions.append(txn)
                        last_txn = txn

    # BOI is oldest-first — stable sort by date ASC, SNO ASC for same-date ties
    transactions.sort(key=lambda t: (_sort_key(t), _sno_key(t)))

    return [_finalise(t) for t in transactions]