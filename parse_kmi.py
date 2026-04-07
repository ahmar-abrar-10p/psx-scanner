import csv
import re

INPUT_FILE = "KMIALLSHR.csv"
OUTPUT_FILE = "KMI_top100.csv"
TOP_N = 100


def parse_market_cap(value: str) -> float:
    """Convert market cap string like '8750.52 Cr' or '134.73 Lac' to float (in Crores)."""
    if not value or value.strip() == "0":
        return 0.0
    value = value.strip()
    match = re.match(r"([\d.]+)\s*(Cr|Lac|K)?", value, re.IGNORECASE)
    if not match:
        return 0.0
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    if unit == "lac":
        return number / 100  # Lac → Crore
    elif unit == "k":
        return number / 100000  # K (thousands) → Crore (this would be tiny, likely data issue)
    return number  # already in Cr


def parse_csv(filepath: str) -> list[dict]:
    """
    The CSV has a misaligned structure:
      row N:   data row  (Points, Weight, Cur., Chg, Chg%, 52WK High, 52WK Low, Vol, Market Cap)
      row N+1: symbol row (symbol only, rest empty)
      row N+2: blank row

    So we read all rows, find data rows followed by a symbol row, and merge them.
    """
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Row 0 is header, skip it
    data_rows = rows[1:]

    stocks = []
    i = 0
    while i < len(data_rows):
        row = data_rows[i]

        # A data row: first column is empty, has numeric data
        if row[0].strip() == "" and any(col.strip() not in ("", "0") for col in row[1:]):
            # Next non-blank row should be the symbol
            symbol = ""
            if i + 1 < len(data_rows):
                next_row = data_rows[i + 1]
                if next_row[0].strip() != "":
                    symbol = next_row[0].strip()

            if symbol:
                try:
                    points = float(row[1]) if row[1].strip() else 0.0
                    weight = float(row[2]) if row[2].strip() else 0.0
                    price = float(row[3]) if row[3].strip() else 0.0
                    chg = float(row[4]) if row[4].strip() else 0.0
                    chg_pct = row[5].strip()
                    high_52w = float(row[6]) if row[6].strip() else 0.0
                    low_52w = float(row[7]) if row[7].strip() else 0.0
                    volume = row[8].strip()
                    market_cap_str = row[9].strip() if len(row) > 9 else ""
                    market_cap = parse_market_cap(market_cap_str)

                    stocks.append({
                        "symbol": symbol,
                        "price": price,
                        "chg": chg,
                        "chg_pct": chg_pct,
                        "high_52w": high_52w,
                        "low_52w": low_52w,
                        "volume": volume,
                        "weight": weight,
                        "market_cap_cr": market_cap,
                        "market_cap_raw": market_cap_str,
                    })
                except (ValueError, IndexError):
                    pass  # skip malformed rows

        i += 1

    return stocks


def main():
    print(f"Reading {INPUT_FILE}...")
    stocks = parse_csv(INPUT_FILE)
    print(f"Total stocks parsed: {len(stocks)}")

    # Filter out stocks with zero price or zero market cap (likely delisted/data issues)
    valid = [s for s in stocks if s["price"] > 0 and s["market_cap_cr"] > 0]
    print(f"Stocks with valid price & market cap: {len(valid)}")

    # Sort by market cap descending
    valid.sort(key=lambda x: x["market_cap_cr"], reverse=True)

    top100 = valid[:TOP_N]

    # Save to CSV
    fieldnames = ["rank", "symbol", "price", "chg", "chg_pct",
                  "high_52w", "low_52w", "volume", "weight", "market_cap_cr", "market_cap_raw"]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rank, stock in enumerate(top100, start=1):
            writer.writerow({"rank": rank, **stock})

    print(f"\nTop {TOP_N} stocks saved to {OUTPUT_FILE}")
    print("\nTop 10 preview:")
    print(f"{'Rank':<5} {'Symbol':<12} {'Price':>8} {'Market Cap (Cr)':>16} {'Raw':>14}")
    print("-" * 60)
    for s in top100[:10]:
        print(f"{top100.index(s)+1:<5} {s['symbol']:<12} {s['price']:>8.2f} {s['market_cap_cr']:>16.2f} {s['market_cap_raw']:>14}")


if __name__ == "__main__":
    main()
