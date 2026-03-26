import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from banks import parse_bank_statement

pdf = "d:/BankStats&GST3B/CBI CA FY- 24-25.pdf"

data = parse_bank_statement(pdf)

print("\nACCOUNT INFO\n")
print(json.dumps(data["account"], indent=4))

transactions = data["transactions"]

chunk_size = 50
total = len(transactions)

# create ranges
ranges = []
for i in range(0, total, chunk_size):
    start = i + 1
    end = min(i + chunk_size, total)
    ranges.append((start, end))

print("\nAVAILABLE TRANSACTION RANGES\n")

for i, r in enumerate(ranges, 1):
    print(f"{i}. Transactions {r[0]} - {r[1]}")

while True:

    choice = input("\nEnter range number to view (or q to quit): ")

    if choice.lower() == "q":
        break

    try:
        idx = int(choice) - 1
        start, end = ranges[idx]

        print(f"\nTRANSACTIONS {start} - {end}\n")

        print(json.dumps(transactions[start-1:end], indent=4))

    except:
        print("Invalid choice")