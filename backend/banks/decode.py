import pdfplumber

with pdfplumber.open("d:/BankStats&GST3B/sib cc 2.pdf") as pdf:
    for page_num, page in enumerate(pdf.pages[:2]):  # first 2 pages
        print(f"\n{'='*60}")
        print(f"PAGE {page_num + 1} — RAW TEXT LINES")
        print('='*60)
        text = page.extract_text() or ""
        for i, line in enumerate(text.split("\n")[:50]):
            print(f"{i:02d}: {repr(line)}")

        print(f"\n--- PAGE {page_num + 1} TABLES ---")
        tables = page.extract_tables(
            {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
        )
        print(f"Total tables found: {len(tables) if tables else 0}")
        if tables:
            for t_idx, table in enumerate(tables):
                print(f"\nTable {t_idx} — {len(table)} rows x {len(table[0]) if table else 0} cols")
                for r_idx, row in enumerate(table[:5]):  # first 5 rows of each table
                    print(f"  Row {r_idx}: {row}")