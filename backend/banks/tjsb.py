import re
import pdfplumber
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "tjsb"
BANK_DISPLAY_NAME = "TJSB Sahakari Bank"


# =============================================================================
# TJSB SAHAKARI BANK — Statement of Account
# =============================================================================
#
# HEADER BLOCK:
#   Generated On          : 31-Dec-2023 05:51 PM
#   Account Number        : CC/115-SHREENAGAR-THANE
#   Customer Name         : M/S CHUR TEXTILES LIMITED
#   Address               : H NO J 277 SONAMOTI COMPOUND ...
#   Current ROI%          : 11.85
#   Limit Effective Date  : 31-Mar-2023
#   Expiry Date           : 29-Feb-2024
#   Total Sanction Limit  : 12,50,00,000.00
#   IFSC Code / MICR Code : TJSB0000011 / 400109011
#   Transaction Type      : All
#   From Date - To Date   : 01/12/2023 To 15/12/2023
#
# TRANSACTION TABLE:
#   Entry Date | Description | Chq No/Ref No | Value Date | Debit | Credit | Balance
#
# DATE FORMAT : 01-Dec-2023  → output as 01-12-2023
# BALANCE     : signed float, no Dr/Cr suffix, may already be negative
# OPENING ROW : "Opening Balance" → skip from transactions
# =============================================================================


# ---------------------------------------------------------------------------
# REGEX
# ---------------------------------------------------------------------------
_ACCT_RE    = re.compile(r"Account\s*Number\s*[:\-]?\s*(.+)", re.I)
_NAME_RE    = re.compile(r"Customer\s*Name\s*[:\-]?\s*(.+)", re.I)
_ADDR_RE    = re.compile(r"Address\s*[:\-]?\s*(.+)", re.I)
_IFSC_RE    = re.compile(r"IFSC\s*Code\s*/\s*MICR\s*Code\s*[:\-]?\s*(\S+)\s*/\s*(\S+)", re.I)
_MICR_RE    = re.compile(r"MICR\s*Code\s*[:\-]?\s*(\d{9})", re.I)
_LIMIT_RE   = re.compile(r"Total\s*Sanction\s*Limit\s*[:\-]?\s*([\d,]+\.\d+)", re.I)
_ROI_RE     = re.compile(r"Current\s*ROI%?\s*[:\-]?\s*([\d.]+)", re.I)
_FROM_TO_RE = re.compile(
    r"From\s*Date\s*-\s*To\s*Date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})\s*To\s*(\d{2}/\d{2}/\d{4})",
    re.I,
)
_GENON_RE   = re.compile(r"Generated\s*On\s*[:\-]?\s*(\d{2}-[A-Za-z]{3}-\d{4})", re.I)

_TXN_DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _reformat_date(date_str: str) -> str:
    if not date_str:
        return date_str
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return date_str.strip()


def _parse_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.max
    for fmt in ("%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.max


def _clean_amount(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "", "None", "null"):
        return None
    s = s.replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def _is_txn_date(value: str) -> bool:
    return bool(_TXN_DATE_RE.match((value or "").strip()))


def _sort_key(txn: dict):
    return _parse_date(txn.get("date"))


# ---------------------------------------------------------------------------
# COLUMN DETECTION
# ---------------------------------------------------------------------------
def _detect_cols(row: list) -> dict:
    mapping = {}
    for idx, cell in enumerate(row):
        c = (cell or "").replace("\n", " ").strip().lower()

        if c in ("entry date", "date", "txn date", "transaction date"):
            mapping["date"] = idx
        elif c in ("description", "particulars", "narration", "remarks"):
            mapping["description"] = idx
        elif "chq" in c or "ref" in c or "cheque" in c:
            mapping["ref_no"] = idx
        elif c in ("value date",):
            mapping["value_date"] = idx
        elif c in ("debit", "withdrawal", "withdrawals", "dr"):
            mapping["debit"] = idx
        elif c in ("credit", "deposit", "deposits", "cr"):
            mapping["credit"] = idx
        elif c == "balance":
            mapping["balance"] = idx

    return mapping if ("date" in mapping and "balance" in mapping) else {}


def _is_header_row(row: list) -> bool:
    joined = " ".join((cell or "").replace("\n", " ").strip().lower() for cell in row)
    return "entry date" in joined and "description" in joined and "balance" in joined


# ---------------------------------------------------------------------------
# ACCOUNT INFO
# ---------------------------------------------------------------------------
def extract_account_info(lines: list[str]) -> dict:
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"] = "INR"

    full_text = "\n".join(lines)

    m = _ACCT_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1).strip()

    m = _NAME_RE.search(full_text)
    if m:
        info["account_holder"] = m.group(1).strip()

    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).strip().upper()
        info["micr"] = m.group(2).strip()
    else:
        m = _MICR_RE.search(full_text)
        if m:
            info["micr"] = m.group(1)

    m = _FROM_TO_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"] = _reformat_date(m.group(2))

    m = _GENON_RE.search(full_text)
    if m:
        info["statement_request_date"] = _reformat_date(m.group(1))

    m = _LIMIT_RE.search(full_text)
    if m:
        info["sanction_limit"] = m.group(1).strip()

    m = _ROI_RE.search(full_text)
    if m:
        info["roi"] = m.group(1).strip()

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    return extract_account_info(lines)


# ---------------------------------------------------------------------------
# TRANSACTIONS
# ---------------------------------------------------------------------------
def extract_transactions(pdf_path: str) -> list[dict]:
    transactions = []
    column_mapping = None
    last_txn = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )
            if not tables:
                continue

            for table in tables:
                if not table:
                    continue

                for row in table:
                    if not row or all((c or "").strip() == "" for c in row):
                        continue

                    if _is_header_row(row):
                        detected = _detect_cols(row)
                        if detected:
                            column_mapping = detected
                        continue

                    if column_mapping is None:
                        continue

                    def _get(key):
                        idx = column_mapping.get(key)
                        if idx is None or idx >= len(row):
                            return None
                        return (row[idx] or "").replace("\n", " ").strip() or None

                    date_raw = _get("date")

                    # continuation row
                    if not date_raw or not _is_txn_date(date_raw):
                        if last_txn:
                            extra = _get("description")
                            if extra:
                                last_txn["description"] = (
                                    (last_txn["description"] or "") + " " + extra
                                ).strip()
                        continue

                    desc_raw = _get("description") or ""

                    # skip opening balance
                    if re.match(r"opening\s*balance", desc_raw.strip(), re.I):
                        continue

                    # skip totals/footer rows if they appear inside table
                    if re.match(r"(total|grand\s+total|closing)", desc_raw.strip(), re.I):
                        continue

                    txn = {
                        "date": _reformat_date(date_raw),
                        "value_date": _reformat_date(_get("value_date") or date_raw),
                        "description": re.sub(r"\s+", " ", desc_raw).strip() or None,
                        "ref_no": _get("ref_no") or None,
                        "debit": _clean_amount(_get("debit")),
                        "credit": _clean_amount(_get("credit")),
                        "balance": _clean_amount(_get("balance")),
                    }

                    transactions.append(txn)
                    last_txn = txn

    transactions.sort(key=_sort_key)

    for i, txn in enumerate(transactions):
        txn["_idx"] = i

    return transactions


