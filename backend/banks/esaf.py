import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "esaf"
BANK_DISPLAY_NAME = "ESAF Small Finance Bank"


# =============================================================================
# ESAF SMALL FINANCE BANK — PDF FORMAT
# =============================================================================
#
# INFO BLOCK (page 1, plain text — two-column layout):
#   Left column:
#     "Name     : SABINA PARIAT"
#     "Address  : BODY BASIC NL COMPLEX"
#                "DHANKHETI SHILLONG"
#                "MALKI DHANKHETI"
#                "793001"
#                "MEGHALAYA"
#                "INDIA"
#   Right column:
#     "Branch IFSC Code    : ESMF0001338"
#     "Account Number      : 5324001344594"
#     "Branch of Ownership : Shillong"
#     "Branch MICR Code    : 793760002"
#     "Date Opened         : 02/07/2024"
#     "Activation Date     : 20/07/2024"
#     "Currency Code       : INR"
#     "Account Status      : Active"
#     "CKYCR Number        : ************3676"
#   Branch line (top):
#     "Branch : Shillong G S ROAD, EAST KHASI HILLS, SHILLONG MEGHALAYA, 793002 ..."
#   Period:
#     "From:01/11/2024  To:25/11/2025"
#
# TRANSACTION TABLE (7 columns, ruled lines):
#   Date | Effective Date | Cheque Number | Description | Withdrawal Amt | Deposit Amt | Balance
#
# CHARACTERISTICS:
#   - Date format      : DD/MM/YYYY → output DD-MM-YYYY
#   - Description      : multi-line within cell (joined with space)
#   - Cheque Number    : usually empty; populated for cheque txns
#   - Withdrawal Amt   : populated for debits, empty for credits
#   - Deposit Amt      : populated for credits, empty for debits
#   - Balance          : Indian comma format e.g. '3,12,353.32', '4,49,510.92'
#                        No CR/DR suffix
#   - Empty cells      : empty string ''
#   - NEFT INDEP       : NEFT Inward Deposit (credit)
#   - NEFT OUTDEP      : NEFT Outward (debit)
# =============================================================================


# ---------------------------------
# HEADER MAP
# ---------------------------------
HEADER_MAP = {
    "date":        ["date"],
    "eff_date":    ["effective date", "effective\ndate", "value date"],
    "cheque":      ["cheque number", "cheque no", "chq no", "instrument no"],
    "description": ["description", "narration", "particulars", "remarks"],
    "debit":       ["withdrawal amt", "withdrawal", "debit", "dr", "withdrawal\namt."],
    "credit":      ["deposit amt", "deposit", "credit", "cr", "deposit\namt."],
    "balance":     ["balance", "closing balance", "running balance"],
}


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_DATE_RE      = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_IFSC_RE      = re.compile(r"\b(ESMF[A-Z0-9]{7})\b")
_MICR_RE      = re.compile(r"branch\s+micr\s+code\s*[:\-]?\s*(\d{9})", re.I)
_ACCT_RE      = re.compile(r"account\s+number\s*[:\-]?\s*(\d{10,})", re.I)
_HOLDER_RE    = re.compile(r"^name\s*[:\-]\s*(.+)", re.I)
_BRANCH_RE    = re.compile(r"branch\s+of\s+ownership\s*[:\-]?\s*(.+)", re.I)
_ACCTYPE_RE   = re.compile(r"account\s+type\s*[:\-]?\s*(.+)", re.I)
_STATUS_RE    = re.compile(r"account\s+status\s*[:\-]?\s*(.+)", re.I)
_OPENED_RE    = re.compile(r"date\s+opened\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", re.I)
_PERIOD_RE    = re.compile(
    r"from\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})\s+to\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
    re.I,
)

# Reference number extraction from description
_REF_PATTERNS = [
    # NEFT: NEFT/CMS<ref>/...  or  NEFT-<ref>-
    re.compile(r"NEFT[/\-]([A-Z0-9]{8,})", re.I),
    # IMPS: IMPS/<ref>/
    re.compile(r"IMPS[/\-](\d+)", re.I),
    # UPI: UPI/<ref>/
    re.compile(r"UPI[/\-]([\d.e+E]+)", re.I),
    # RTGS: RTGS-<ref>-
    re.compile(r"RTGS[/\-]([A-Z0-9]+)", re.I),
    # CHQ/<number>/
    re.compile(r"CHQ[/\-](\d+)", re.I),
    # Generic: any alphanumeric ref ≥ 10 chars after a slash
    re.compile(r"/([A-Z0-9]{10,})/", re.I),
]


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


def _is_txn_date(value: str) -> bool:
    return bool(_DATE_RE.match((value or "").strip()))


def _clean_amount_esaf(value) -> float | None:
    """
    Parse Indian comma format: '3,12,353.32', '4,49,510.92'
    Empty string or '-' → None.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "", "None", "null"):
        return None
    s = re.sub(r"^(Rs\.?|INR|₹)\s*", "", s, flags=re.I).strip()
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_ref_no(description: str) -> str | None:
    """
    Extract transaction reference from description.

    Common ESAF description patterns:
      NEFT INDEP
      NEFT/CMS4619995041/ICIC0099999/STLMT FOR QR. esafbank330359
      IMPS/405812345678/VENDOR
      UPI/<ref>/NAME
      CHQ/<number>/PAYEE
    """
    if not description:
        return None
    for pat in _REF_PATTERNS:
        m = pat.search(description)
        if not m:
            continue
        ref = m.group(1).strip()
        # Convert scientific notation UPI refs
        if re.match(r"^\d+\.?\d*[eE][+\-]?\d+$", ref):
            try:
                ref = str(int(float(ref)))
            except (ValueError, OverflowError):
                pass
        if len(ref) >= 6:
            return ref
    return None


def _detect_columns(row_clean: list[str]) -> dict | None:
    """
    Map column indices from header row.
    Pass 1: exact match. Pass 2: guarded substring (4+ chars).
    Returns mapping if ≥ 4 fields found, else None.
    """
    mapping = {}
    for field, variants in HEADER_MAP.items():
        for idx, cell in enumerate(row_clean):
            if cell in variants:
                mapping[field] = idx
                break
        if field in mapping:
            continue
        for idx, cell in enumerate(row_clean):
            if any(len(v) >= 4 and v in cell for v in variants):
                mapping[field] = idx
                break
    return mapping if len(mapping) >= 4 else None


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    """
    Extract account metadata from ESAF statement page 1.

    The header is a two-column text layout:
      Left  → Name, Address
      Right → IFSC, Account Number, Branch, MICR, Dates, Status
    Statement period appears as: "From:DD/MM/YYYY  To:DD/MM/YYYY"
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # IFSC
    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    # MICR
    m = _MICR_RE.search(full_text)
    if m:
        info["micr"] = m.group(1)

    # Account number
    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1)

    # Statement period
    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    # Line-by-line
    for line in lines:
        s = line.strip()
        if not s:
            continue

        if info["account_holder"] is None:
            m = _HOLDER_RE.match(s)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate) > 1:
                    info["account_holder"] = candidate

        if info["branch"] is None:
            m = _BRANCH_RE.search(s)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate) > 1:
                    info["branch"] = candidate

        if info["acc_type"] is None:
            m = _ACCTYPE_RE.search(s)
            if m:
                val = m.group(1).strip()
                if val and val.upper() not in ("INR", "ACTIVE"):
                    info["acc_type"] = val

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Dispatcher-compatible wrapper."""
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from an ESAF Small Finance Bank PDF statement.

    Strategy:
    - pdfplumber lines-strategy table extraction works for the ruled table.
    - 7-column table: Date | Effective Date | Cheque Number | Description |
                      Withdrawal Amt | Deposit Amt | Balance
    - Date format: DD/MM/YYYY → DD-MM-YYYY
    - Description: multi-line within cell, joined with space.
    - Cheque Number: populated only for cheque transactions, else empty.
    - Empty Withdrawal/Deposit → None (not 0).
    - Balance: Indian comma format, no CR/DR suffix — always positive running balance.
    - ref_no extracted from description via payment-type prefix patterns.

    Falls back to 6-column detection if the Cheque Number column is merged
    into Description in some PDF variants.
    """
    transactions:   list[dict] = []
    column_mapping: dict | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Try both lines strategy and text strategy
            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )
            if not tables:
                tables = page.extract_tables(
                    {"vertical_strategy": "text", "horizontal_strategy": "lines"}
                )
            if not tables:
                continue

            for table in tables:
                if not table:
                    continue

                # Accept 6-col or 7-col tables (some variants merge eff_date)
                ncols = len(table[0]) if table else 0
                if ncols not in (6, 7):
                    continue

                for row in table:
                    if not row or len(row) < 6:
                        continue

                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]

                    # Detect / re-detect header row
                    detected = _detect_columns(row_clean)
                    if detected:
                        column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    # Date
                    date_raw = (row[column_mapping.get("date", 0)] or "").strip()
                    if not _is_txn_date(date_raw):
                        continue

                    # Description — join multi-line
                    desc_raw    = row[column_mapping.get("description", 3)] or ""
                    description = re.sub(
                        r"\s+", " ", desc_raw.replace("\n", " ")
                    ).strip() or None

                    # Cheque number
                    cheque_no = (row[column_mapping.get("cheque", 2)] or "").strip() or None

                    # Amounts
                    debit   = _clean_amount_esaf(row[column_mapping.get("debit",   4)])
                    credit  = _clean_amount_esaf(row[column_mapping.get("credit",  5)])
                    balance = _clean_amount_esaf(row[column_mapping.get("balance", 6)])

                    # ref_no: use cheque number if present, else extract from description
                    ref_no = cheque_no or _extract_ref_no(description)

                    transactions.append({
                        "date":        _reformat_date(date_raw),
                        "description": description,
                        "ref_no":      ref_no,
                        "debit":       debit,
                        "credit":      credit,
                        "balance":     balance,
                    })

    transactions.sort(key=_sort_key)
    return transactions