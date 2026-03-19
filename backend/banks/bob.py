import re
import pdfplumber

from .base import (
    default_account_info,
    clean_amount,
    detect_columns
)

BANK_KEY          = "bob"
BANK_DISPLAY_NAME = "Bank of Baroda"


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
IFSC_PATTERN   = r"\b(BARB[A-Z0-9]{7})\b"
PERIOD_PATTERN = r"Account\s+Statement\s+from\s+(\d{2}-\d{2}-\d{4})\s+to\s+(\d{2}-\d{2}-\d{4})"


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_bob(value):
    """
    Handles Indian comma format: '19,780.00', '21,417.00'
    Returns float or None. Treats '-' as None (BOB uses '-' for empty cells).
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    value = value.replace(",", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------
# COL[0] PARSER
# ---------------------------------
def _parse_col0(col0_raw):
    """
    BOB packs Serial No + Dates + Description into col[0].

    Three formats observed in this PDF:

    Format 1 — Description wraps around the serial+date line (most common):
      "UPI/description_part1\nN DD-MM-YYYY DD-MM-YYYY\ndescription_part2"
      e.g. "UPI/116497116869/11:57:47/UPI/gpay-\n2 01-01-2026 01-01-2026\n11262940024@ok"

    Format 2 — Short description inline after dates:
      "N DD-MM-YYYY DD-MM-YYYY SHORT DESCRIPTION"
      e.g. "28 11-01-2026 11-01-2026 SMS Charges for NOV 25"
           "34 12-01-2026 12-01-2026 BY CASH"

    Format 3 — Opening Balance (no value date):
      "1 01-01-2026 Opening Balance"

    Returns: (serial_no, txn_date, value_date, description)
    All are None if the row cannot be parsed.
    """
    if not col0_raw:
        return None, None, None, None

    col0  = col0_raw.strip()
    lines = [l.strip() for l in col0.split('\n') if l.strip()]

    serial_no       = None
    txn_date        = None
    value_date      = None
    desc_parts      = []
    serial_line_idx = None

    # Find the line containing serial number + transaction date
    for i, line in enumerate(lines):
        m = re.match(r"^(\d+)\s+(\d{2}-\d{2}-\d{4})(?:\s+(\d{2}-\d{2}-\d{4}))?", line)
        if m:
            serial_no       = int(m.group(1))
            txn_date        = m.group(2)
            value_date      = m.group(3)   # None for Opening Balance row
            serial_line_idx = i
            # Text after the dates on this same line = inline description
            after_dates = line[m.end():].strip()
            if after_dates:
                desc_parts.append(after_dates)
            break

    if serial_no is None:
        return None, None, None, None

    # Lines before the serial line = description prefix
    # Lines after  the serial line = description suffix
    for i, line in enumerate(lines):
        if i < serial_line_idx:
            desc_parts.insert(i, line)
        elif i > serial_line_idx:
            desc_parts.append(line)

    description = re.sub(r'\s+', ' ', " ".join(desc_parts)).strip()

    return serial_no, txn_date, value_date, description


# ---------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines):
   
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Statement period
    m = re.search(PERIOD_PATTERN, full_text, re.I)
    if m:
        info["statement_period"]["from"] = m.group(1)
        info["statement_period"]["to"]   = m.group(2)

    # IFSC — reliable anchor
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    # Account number — 14-digit number after "Account Number"
    m = re.search(r"Account\s+Number\s+IFSC\s+Code\s+(\d{10,})", full_text, re.I)
    if m:
        info["account_number"] = m.group(1)
    else:
        m = re.search(r"\b(\d{14,})\b", full_text)
        if m:
            info["account_number"] = m.group(1)

    # MICR — 9-digit number
    m = re.search(r"MICR\s+Code\s+\w+\s+(\d{9})\b", full_text, re.I)
    if m:
        info["micr"] = m.group(1)
    else:
        m = re.search(r"\b(\d{9})\b", full_text)
        if m:
            info["micr"] = m.group(1)

    # Account type — word(s) after "Account Type ... MICR Code"
    m = re.search(r"Account\s+Type\s+MICR\s+Code\s+(\w+)", full_text, re.I)
    if m:
        info["acc_type"] = m.group(1)

    # Account holder + branch — BOB two-column layout on page 1.
    # The holder name (left col) and branch name (right col) appear on the same
    # text line: e.g. "CHANDRAKANT SONU BENDAL MARINE DRIVE BR., MUMBAI"
    # We use the IFSC code line to locate where the right column starts,
    # then apply the same x-offset logic to the name line.
    for i, line in enumerate(lines):
        if re.search(r"account\s+name", line, re.I) and re.search(r"branch\s+name", line, re.I):
            for j in range(i+1, min(i+5, len(lines))):
                nxt = lines[j].strip()
                if nxt and not re.search(r"account\s+number|ifsc|micr|type|address", nxt, re.I):
                    # Strategy: right column starts where branch/city keywords appear
                    # after a gap. Split on 2+ spaces, or find branch keywords.
                    parts = re.split(r"\s{2,}", nxt)
                    if len(parts) >= 2:
                        info["account_holder"] = parts[0].strip()
                        info["branch"]         = " ".join(parts[1:]).strip()
                    else:
                        # No clear gap — use IFSC vicinity as right-col anchor
                        m_br = re.search(
                            r"(?:MARINE|BR\.|BRANCH|MUMBAI|DELHI|KOLKATA|CHENNAI|PUNE|ROAD).+$",
                            nxt, re.I
                        )
                        if m_br:
                            info["branch"]         = m_br.group(0).strip()
                            info["account_holder"] = nxt[:m_br.start()].strip()
                        else:
                            info["account_holder"] = nxt
                    break
            break
    return info



# ---------------------------------
# TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    """
    Extract all transactions from a Bank of Baroda PDF statement.

    BOB PDF CHARACTERISTICS:
    ========================
    - Text-based PDF (pdfplumber can extract chars directly, no OCR needed)
    - 5 columns per row: [col0, cheque_no, debit, credit, balance]
    - col[0] is special: Serial + TxnDate + ValueDate + Description
      are ALL packed into one cell with newlines separating parts
    - Debit and Credit use '-' for empty (not blank)
    - Balance present on every row including Opening Balance
    - Serial No 1 = "Opening Balance" (included as a transaction)
    - Lines extraction strategy works reliably across all 10 pages

    col[0] parsing is handled by _parse_col0() which finds the serial+date
    line and collects surrounding lines as the description.
    """
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )

            if not tables:
                continue

            for table in tables:

                for row in table:

                    if not row or len(row) < 5:
                        continue

                    col0 = row[0] or ""

                    # Skip header row
                    if re.search(r"serial|no\s+date|transaction\s+date", col0, re.I):
                        continue

                    # Skip footer / note rows
                    if re.search(r"note:|page\s+\d+|computer.generated|discrepancy", col0, re.I):
                        continue

                    # Parse col[0] → serial, txn_date, value_date, description
                    serial_no, txn_date, value_date, description = _parse_col0(col0)

                    if serial_no is None or txn_date is None:
                        continue

                    cheque_no = (row[1] or "").strip() or None
                    debit     = _clean_amount_bob(row[2])
                    credit    = _clean_amount_bob(row[3])
                    balance   = _clean_amount_bob(row[4])

                    transactions.append({
                        "serial_no":   serial_no,
                        "date":        txn_date,
                        "value_date":  value_date,
                        "description": description,
                        "cheque_no":   cheque_no,
                        "debit":       debit,
                        "credit":      credit,
                        "balance":     balance,
                    })

    # Sort by serial number to ensure correct order across pages
    transactions.sort(key=lambda t: t["serial_no"])

    return transactions