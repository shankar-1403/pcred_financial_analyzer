"""
Extract transactions from PDF tables. Bank-specific handling for Axis (DR/CR) vs others.
"""
import pdfplumber
from .base import clean_amount, detect_columns


def _row_to_txn(row, column_mapping, last_txn, uses_debit_credit_column):
    """Build one transaction dict from a table row. Handles continuation rows (no date)."""
    date_cell = row[column_mapping["date"]] if "date" in column_mapping else None
    if not date_cell and last_txn and "description" in column_mapping:
        desc = row[column_mapping["description"]] if column_mapping["description"] < len(row) else None
        if desc:
            desc = (desc or "").replace("\n", " ").strip()
            last_txn["description"] = (last_txn["description"] or "") + " " + desc
        return None  # continuation row

    txn = {
        "date": None,
        "description": None,
        "debit": None,
        "credit": None,
        "balance": None,
    }
    try:
        if "date" in column_mapping and column_mapping["date"] < len(row) and row[column_mapping["date"]]:
            txn["date"] = (row[column_mapping["date"]] or "").replace("\n", " ").strip()
        if "description" in column_mapping and column_mapping["description"] < len(row):
            desc = row[column_mapping["description"]]
            if desc:
                txn["description"] = (desc or "").replace("\n", " ").strip()

        if uses_debit_credit_column and "amount" in column_mapping and "debit_credit" in column_mapping:
            amount = clean_amount(row[column_mapping["amount"]] if column_mapping["amount"] < len(row) else None)
            dc = (row[column_mapping["debit_credit"]] or "").strip().upper() if column_mapping["debit_credit"] < len(row) else ""
            if dc == "DR":
                txn["debit"] = amount
            elif dc == "CR":
                txn["credit"] = amount
        else:
            if "debit" in column_mapping and column_mapping["debit"] < len(row) and row[column_mapping["debit"]]:
                txn["debit"] = clean_amount(row[column_mapping["debit"]])
            if "credit" in column_mapping and column_mapping["credit"] < len(row) and row[column_mapping["credit"]]:
                txn["credit"] = clean_amount(row[column_mapping["credit"]])

        if "balance" in column_mapping and column_mapping["balance"] < len(row) and row[column_mapping["balance"]]:
            txn["balance"] = clean_amount(row[column_mapping["balance"]])
    except (IndexError, TypeError, KeyError):
        return None

    return txn


def _extract_transactions_loop(pdf_path: str, uses_debit_credit_column: bool):
    """Common loop for table extraction. Axis uses DR/CR column; others use separate debit/credit."""
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
                for row in table:
                    if not row:
                        continue
                    row_clean = [
                        (cell or "").replace("\n", " ").strip().lower()
                        for cell in row
                    ]
                    if column_mapping is None:
                        detected = detect_columns(row_clean)
                        if detected:
                            column_mapping = detected
                            continue
                    if column_mapping is None:
                        continue
                    txn = _row_to_txn(row, column_mapping, last_txn, uses_debit_credit_column)
                    if txn:
                        transactions.append(txn)
                        last_txn = txn
    return transactions


def extract_transactions_axis(pdf_path: str):
    """Axis Bank: single amount column + debit/credit (DR/CR) column."""
    return _extract_transactions_loop(pdf_path, uses_debit_credit_column=True)


def extract_transactions_generic(pdf_path: str):
    """ICICI, SBI, HDFC, etc.: separate debit and credit columns."""
    return _extract_transactions_loop(pdf_path, uses_debit_credit_column=False)
