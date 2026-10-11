"""Print the balance of each account in a CSV file. The PR adds it, and no claim covers it."""

import csv
import sys


def main(path: str) -> int:
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            print(f"{row['account']}: {row['balance']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
