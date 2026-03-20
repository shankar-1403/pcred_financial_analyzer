import re
import pdfplumber

from .base import default_account_info

BANK_KEY          = "saraswat"
BANK_DISPLAY_NAME = "Saraswat Co-operative Bank Ltd."
IFSC_PATTERN      = r"\b(SRCB[A-Z0-9]{7})\b"

# ── OD FORMAT (saraswant2.pdf) ────────────────────────────────────────────
# Line: "31/05/2025 41,819.00 -39,41,933.21"
TXN_LINE_RE = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})$"
)

# Lines to discard for OD format
SKIP_RE = re.compile(
    r"account\s+details|general\s+details|balance\s+details|"
    r"stationery\s+limited|^garde$|^remarks$|"
    r"date\s+and\s+time|page\s+\d+\s+of\s+\d+|"
    r"primary\s+account|sanction\s+limit|total\s+value|"
    r"debit\s+card|date\s+from|date\s+to|"
    r"transactions\s+for|last\s+n\s+trans|amount\s+type|"
    r"amount\s+from|amount\s+to|instrument\s+id\s+from|"
    r"instrument\s+id\s+to|choose\s+statement|"
    r"transactions\s+list|\|\|rlc|rlc\d+|"
    r"number:|nickname:|iban:|status:|"
    r"type:|currency:|open\s+date:|branch:|drawing\s+power:|"
    r"debit\s+accrued|credit\s+accrued|available\s+balance:|"
    r"total\s+balance:|ledger\s+balance:|effective\s+available|"
    r"unclear\s+balance",
    re.I
)

# ── SAVINGS FORMAT (saraswat.pdf) table header skip ────────────────────────
SAVINGS_HEADER_RE = re.compile(
    r"^date$|particulars|instruments|dr\s*amount|"
    r"cr\s*amount|total\s*amount|narration|balance|remarks",
    re.I
)


# ─────────────────────────────────────────
# AMOUNT CLEANER
# ─────────────────────────────────────────
def _clean_amount(value):
    if value is None:
        return None
    v = str(value).strip().replace(",", "").replace(" ", "")
    if not v or v in ("-", "None", "null", "NIL", "-NIL-"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


# ─────────────────────────────────────────
# DATE NORMALIZER
# ─────────────────────────────────────────
def _normalize_date(raw):
    if not raw:
        return None
    raw = str(raw).strip()
    # DD/MM/YYYY → DD-MM-YYYY  (OD format)
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Already DD-MM-YYYY (savings format)
    if re.match(r"^\d{2}-\d{2}-\d{4}$", raw):
        return raw
    # Compact DDMMYYYY fallback
    m = re.match(r"^(\d{2})(\d{2})(\d{4})$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


# ─────────────────────────────────────────
# FORMAT DETECTION
# OD  → "Overdraft" / "ODA" in header
# Savings → "SBGEN" / "Savings" in header
# ─────────────────────────────────────────
def _detect_format(lines):
    text = " ".join(lines[:60])
    if re.search(r"\bODA\b|\bOverdraft\b", text, re.I):
        return "od"
    if re.search(r"\bSBGEN\b|\bSavings\b|\bStatement\s+of\s+Accounts\b", text, re.I):
        return "savings"
    # Fallback — check account number pattern
    if re.search(r"SBGEN/", text, re.I):
        return "savings"
    return "savings"  # default to savings


# ─────────────────────────────────────────
# ACCOUNT INFO EXTRACTION
# Handles BOTH formats from the same lines
# ─────────────────────────────────────────
def extract_account_info(lines):
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    fmt = _detect_format(lines)

    if fmt == "od":
        # ── OD: Account Number ──
        # Raw: "Number: 810000000024513 Nickname: NA"
        m = re.search(r"Number:\s*([\dA-Z]+)\s+Nickname", full_text, re.I)
        if m:
            info["account_number"] = m.group(1).strip()

        # ── OD: Account Holder ──
        # Raw: "IBAN: -NIL- Name: LUCKY PLASTICS AND\nSTATIONERY LIMITED\nStatus:"
        m = re.search(r"Name:\s*(.+?)(?:\nStatus:|\nType:|\nCurrency:|\nIBAN:)", full_text, re.I | re.S)
        if m:
            info["account_holder"] = re.sub(r"\s+", " ", m.group(1)).strip()

        # ── OD: Branch ──
        m = re.search(r"Branch:\s*([A-Z0-9][A-Z0-9\s/]+?)(?:\s+Drawing|\s+IFSC|\s+Address)", full_text, re.I)
        if m:
            info["branch"] = re.sub(r"\s+", " ", m.group(1)).strip()

        # ── OD: Account Type ──
        m = re.search(r"\bType:\s*(\w+)", full_text, re.I)
        if m:
            info["acc_type"] = m.group(1).strip()

        # ── OD: Statement Period ──
        # Raw: "Date From(dd/MM/yyyy): 01/01/2025 Date To(dd/MM/yyyy): 31/05/2025"
        m = re.search(r"Date\s+From[^:]*:\s*(\d{2}/\d{2}/\d{4})", full_text, re.I)
        if m:
            info["statement_period"]["from"] = _normalize_date(m.group(1))
        m = re.search(r"Date\s+To[^:]*:\s*(\d{2}/\d{2}/\d{4})", full_text, re.I)
        if m:
            info["statement_period"]["to"] = _normalize_date(m.group(1))

        # ── OD Specific ──
        m = re.search(r"Drawing\s+Power:\s*INR\s+([\d,]+\.\d{2})", full_text, re.I)
        if m:
            info["drawing_power"] = _clean_amount(m.group(1))

        m = re.search(r"Sanction\s+Limit:\s*INR\s+([\d,]+\.\d{2})", full_text, re.I)
        if m:
            info["sanction_limit"] = _clean_amount(m.group(1))

        m = re.search(r"Available\s+Balance:\s*INR\s+([\d,]+\.\d{2})", full_text, re.I)
        if m:
            info["available_balance"] = _clean_amount(m.group(1))

        m = re.search(r"Ledger\s+Balance:\s*INR\s+(-?[\d,]+\.\d{2})", full_text, re.I)
        if m:
            info["ledger_balance"] = _clean_amount(m.group(1))

    else:
        # ── SAVINGS: Account Number ──
        # Raw: "Account No. : SBGEN/402203100003932"
        m = re.search(r"Account\s+No\.?\s*[:\-]\s*(SBGEN/[\d]+|[\d]{10,})", full_text, re.I)
        if m:
            info["account_number"] = m.group(1).strip()

        # ── SAVINGS: Account Holder ──
        # Raw: "Name : SAYYED FAIYAZ GANI"
        m = re.search(r"\bName\s*[:\-]\s*([A-Z][A-Z\s]+?)(?:\s*\n|\s{2,}|Joint\s+Holder|Customer)", full_text, re.I)
        if m:
            info["account_holder"] = re.sub(r"\s+", " ", m.group(1)).strip()

        # ── SAVINGS: Branch ──
        # Raw: "Branch : KAMOTHE"
        m = re.search(r"\bBranch\s*[:\-]\s*([A-Z][A-Z\s]+?)(?:\s*\n|\s{2,}|Branch\s+IFSC)", full_text, re.I)
        if m:
            info["branch"] = re.sub(r"\s+", " ", m.group(1)).strip()

        # ── SAVINGS: Account Type ──
        info["acc_type"] = "Savings"

        # ── SAVINGS: Customer ID ──
        # Raw: "Customer ID : 9311853"
        m = re.search(r"Customer\s+ID\s*[:\-]\s*(\d+)", full_text, re.I)
        if m:
            info["customer_id"] = m.group(1)

        # ── SAVINGS: Statement Period ──
        # Raw: "From Date : 06/03/2024 To Date : 05/03/2025"
        m = re.search(r"From\s+Date\s*[:\-]\s*(\d{2}/\d{2}/\d{4})", full_text, re.I)
        if m:
            info["statement_period"]["from"] = _normalize_date(m.group(1))
        m = re.search(r"To\s+Date\s*[:\-]\s*(\d{2}/\d{2}/\d{4})", full_text, re.I)
        if m:
            info["statement_period"]["to"] = _normalize_date(m.group(1))

        # ── SAVINGS: Opening Balance ──
        # Raw: "Opening Balance As On 06/03/2024 : Rs. 596.12 CR"
        m = re.search(r"Opening\s+Balance\s+As\s+On[^:]*[:\-]\s*Rs\.\s*([\d,]+\.\d{2})\s*(CR|DR)?", full_text, re.I)
        if m:
            amt = _clean_amount(m.group(1))
            if amt and (m.group(2) or "").upper() == "DR":
                amt = -amt
            info["opening_balance"] = amt

        # ── SAVINGS: MICR ──
        # Raw: "Branch MICR Code : 400088122"
        m = re.search(r"MICR\s+Code\s*[:\-]\s*(\d{9})", full_text, re.I)
        if m:
            info["micr"] = m.group(1)

    # ── COMMON: IFSC ──
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    return info


# ─────────────────────────────────────────
# OD TRANSACTION EXTRACTOR
# Pattern confirmed from decode:
#   "31/05/2025 41,819.00 -39,41,933.21"   ← TXN LINE
#   "IMPS:515200128155:918..."              ← remarks (1..n lines)
# ─────────────────────────────────────────
def _extract_od_transactions(pdf_path):
    transactions = []

    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if SKIP_RE.search(line):
                    continue
                all_lines.append(line)

    i = 0
    while i < len(all_lines):
        line = all_lines[i]
        m = TXN_LINE_RE.match(line)

        if not m:
            i += 1
            continue

        date_raw   = m.group(1)
        raw_amount = _clean_amount(m.group(2))
        balance    = _clean_amount(m.group(3))
        date       = _normalize_date(date_raw)

        # Collect remarks until next TXN_LINE_RE match
        j = i + 1
        remark_parts = []
        while j < len(all_lines) and not TXN_LINE_RE.match(all_lines[j]):
            remark_parts.append(all_lines[j].strip())
            j += 1

        description = re.sub(r"\s+", " ", " ".join(remark_parts)).strip() or None

        # Debit / Credit from amount sign
        debit  = None
        credit = None
        if raw_amount is not None:
            if raw_amount < 0:
                debit  = abs(raw_amount)
            elif raw_amount > 0:
                credit = raw_amount
            else:
                if transactions:
                    prev_bal = transactions[-1]["balance"]
                    if prev_bal is not None and balance is not None:
                        delta = round(balance - prev_bal, 2)
                        if delta < 0:
                            debit  = abs(delta)
                        elif delta > 0:
                            credit = delta

        transactions.append({
            "date":        date,
            "description": description,
            "cheque_no":   None,
            "debit":       debit,
            "credit":      credit,
            "balance":     balance,
        })
        i = j

    return transactions


# ─────────────────────────────────────────
# SAVINGS TRANSACTION EXTRACTOR
# saraswat.pdf — 6-column table:
# Date | Particulars | Instruments | Dr Amount | Cr Amount | Total Amount
# Balance column has "CR" or "DR" suffix
# ─────────────────────────────────────────
def _parse_savings_row(row, prev_balance=None):
    if not row or len(row) < 6:
        return None

    date_raw = (row[0] or "").strip()
    date     = _normalize_date(date_raw)
    if not date:
        return None

    # Particulars — clean up broken spaces from pdfplumber
    description = re.sub(r"\s+", " ", (row[1] or "").replace("\n", " ")).strip()

    # Instruments (cheque number)
    cheque_no = (row[2] or "").strip() or None

    debit  = _clean_amount(row[3])
    credit = _clean_amount(row[4])

    # Total Amount column: "25,596.12 CR" or "50,645.64 DR"
    raw_bal = (row[5] or "").strip()
    is_dr   = bool(re.search(r"\bDR\b", raw_bal, re.I))
    raw_bal = re.sub(r"\s*(CR|DR)\s*$", "", raw_bal, flags=re.I).strip()
    balance = _clean_amount(raw_bal)
    if balance is not None and is_dr:
        balance = -balance

    # Balance delta fallback if debit/credit missing
    if debit is None and credit is None and prev_balance is not None and balance is not None:
        delta = round(balance - prev_balance, 2)
        if delta < 0:
            debit  = abs(delta)
        elif delta > 0:
            credit = delta

    if not description and debit is None and credit is None and balance is None:
        return None

    return {
        "date":        date,
        "description": description,
        "cheque_no":   cheque_no,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }


def _extract_savings_transactions(pdf_path):
    transactions = []
    prev_balance = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )
            if not tables:
                # Fallback to text strategy if no borders found
                tables = page.extract_tables(
                    {"vertical_strategy": "text", "horizontal_strategy": "text"}
                )
            if not tables:
                continue
            for table in tables:
                for row in table:
                    if not row:
                        continue
                    first_cell = (row[0] or "").strip()
                    # Skip header rows
                    if SAVINGS_HEADER_RE.search(first_cell):
                        continue
                    # Skip all-empty rows
                    if all((c or "").strip() == "" for c in row):
                        continue
                    # Skip opening balance row (no date, just balance)
                    if not first_cell and (row[5] or "").strip():
                        continue

                    txn = _parse_savings_row(row, prev_balance)
                    if txn:
                        prev_balance = txn["balance"]
                        transactions.append(txn)

    return transactions


# ─────────────────────────────────────────
# MAIN ENTRY POINTS
# ─────────────────────────────────────────
def extract_transactions(pdf_path):
    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_lines.extend(text.split("\n"))

    fmt = _detect_format(all_lines)

    if fmt == "od":
        return _extract_od_transactions(pdf_path)
    else:
        return _extract_savings_transactions(pdf_path)
