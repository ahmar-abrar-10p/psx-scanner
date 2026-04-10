"""
parse_kmi.py — Build KMI_all.csv from KMIALLSHR.csv with name + sector enrichment.

Enrichment sources (in priority order):
1. psx_market_watch.csv  — maps symbol -> sector_id
2. sectors.txt           — maps sector_id -> sector name (HTML <option> tags from PSX)
3. stocks_data.json      — maps symbol -> company name (from Sarmaaya API)

Pipeline:
1. Parse the raw KMIALLSHR.csv (misaligned format from PSX export)
2. Load sector_id->name from sectors.txt, symbol->sector_id from psx_market_watch.csv,
   symbol->name from stocks_data.json
3. Enrich each KMI stock with name + sector from these sources
4. Apply EXCLUDED_SECTORS and EXCLUDED_SYMBOLS filters
5. Sort by market cap descending
6. Write ALL remaining stocks to KMI_all.csv
"""
import csv
import json
import re
import shutil
from html import unescape
from pathlib import Path

INPUT_FILE = Path(__file__).parent / "KMIALLSHR.csv"
OUTPUT_FILE = Path(__file__).parent / "KMI_all.csv"
BACKUP_FILE = Path(__file__).parent / "KMI_all.csv.bak"

# External enrichment sources
MARKET_WATCH_CSV = Path(__file__).parent / "psx_market_watch.csv"
SECTORS_TXT = Path(__file__).parent / "sectors.txt"
STOCKS_JSON = Path(__file__).parent / "stocks_data.json"

# Sector exclusions: any stock whose sector matches (case-insensitive substring) will be filtered.
EXCLUDED_SECTORS = {
    "SUGAR & ALLIED INDUSTRIES",
}

# Symbol exclusions: specific symbols to drop regardless of sector (personal preference).
EXCLUDED_SYMBOLS = {
    "NESTLE", "UPFL", "RMPL", "SHFA", "PSEL", "STYLERS", "JKSM", "FML",
    "TICL", "ZAHID", "BATA", "GLPL", "GVGL", "MEHT", "ATBA", "CRTM",
    "FZCM", "KPUS", "GGL",
}


def _load_sector_map() -> dict[str, str]:
    """Parse sectors.txt (HTML <option> tags) into {sector_id: sector_name}."""
    if not SECTORS_TXT.exists():
        return {}
    raw = SECTORS_TXT.read_text(encoding="utf-8")
    # Extract <option value="0801">AUTOMOBILE ASSEMBLER</option> patterns
    pairs = re.findall(r'<option\s+value="(\d+)">(.*?)</option>', raw)
    return {code: unescape(name).strip() for code, name in pairs}


def _load_symbol_sector_ids() -> dict[str, str]:
    """Parse psx_market_watch.csv into {symbol: sector_id}."""
    if not MARKET_WATCH_CSV.exists():
        return {}
    result = {}
    with open(MARKET_WATCH_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get("SYMBOL", "").strip()
            sector_id = row.get("SECTOR", "").strip()
            if sym and sector_id:
                result[sym] = sector_id
    return result


def _load_stock_names() -> dict[str, str]:
    """Parse stocks_data.json into {symbol: company_name}."""
    if not STOCKS_JSON.exists():
        return {}
    with open(STOCKS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    for item in data.get("response", []):
        sym = item.get("symbol", "").strip()
        name = item.get("name", "").strip()
        if sym and name:
            result[sym] = name
    return result


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
        return number / 100
    elif unit == "k":
        return number / 100000
    return number


def parse_kmiallshr(filepath: Path) -> list[dict]:
    """Parse the misaligned KMIALLSHR CSV format (data row + symbol row alternating)."""
    with open(filepath, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    data_rows = rows[1:]  # skip header
    stocks = []
    i = 0
    while i < len(data_rows):
        row = data_rows[i]

        if row[0].strip() == "" and any(col.strip() not in ("", "0") for col in row[1:]):
            symbol = ""
            if i + 1 < len(data_rows):
                next_row = data_rows[i + 1]
                if next_row[0].strip() != "":
                    symbol = next_row[0].strip()

            if symbol and len(symbol) > 1:
                try:
                    stocks.append({
                        "symbol": symbol,
                        "price": float(row[3]) if row[3].strip() else 0.0,
                        "chg": float(row[4]) if row[4].strip() else 0.0,
                        "chg_pct": row[5].strip(),
                        "high_52w": float(row[6]) if row[6].strip() else 0.0,
                        "low_52w": float(row[7]) if row[7].strip() else 0.0,
                        "volume": row[8].strip(),
                        "weight": float(row[2]) if row[2].strip() else 0.0,
                        "market_cap_cr": parse_market_cap(row[9].strip() if len(row) > 9 else ""),
                        "market_cap_raw": row[9].strip() if len(row) > 9 else "",
                    })
                except (ValueError, IndexError):
                    pass

        i += 1

    return stocks


def main():
    # Load enrichment data
    print("Loading enrichment sources...")
    sector_id_to_name = _load_sector_map()
    print(f"  sectors.txt: {len(sector_id_to_name)} sector mappings")

    symbol_to_sector_id = _load_symbol_sector_ids()
    print(f"  psx_market_watch.csv: {len(symbol_to_sector_id)} symbol->sector_id mappings")

    stock_names = _load_stock_names()
    print(f"  stocks_data.json: {len(stock_names)} symbol->name mappings")

    # Parse KMI index
    print(f"\nReading {INPUT_FILE.name}...")
    stocks = parse_kmiallshr(INPUT_FILE)
    print(f"  Total stocks parsed: {len(stocks)}")

    valid = [s for s in stocks if s["price"] > 0 and s["market_cap_cr"] > 0]
    print(f"  With valid price & market cap: {len(valid)}")

    # Enrich with name + sector from external sources
    missing_name = []
    missing_sector = []
    for stock in valid:
        sym = stock["symbol"]

        # Name from stocks_data.json
        name = stock_names.get(sym, "")
        stock["name"] = name if name else "UNKNOWN"
        if not name:
            missing_name.append(sym)

        # Sector: symbol -> sector_id (from CSV) -> sector_name (from sectors.txt)
        sector_id = symbol_to_sector_id.get(sym, "")
        sector_name = sector_id_to_name.get(sector_id, "") if sector_id else ""
        stock["sector"] = sector_name if sector_name else "UNKNOWN"
        if not sector_name:
            missing_sector.append(sym)

    if missing_name:
        print(f"  Missing name ({len(missing_name)}): {', '.join(missing_name[:20])}{'...' if len(missing_name) > 20 else ''}")
    if missing_sector:
        print(f"  Missing sector ({len(missing_sector)}): {', '.join(missing_sector[:20])}{'...' if len(missing_sector) > 20 else ''}")

    # Apply exclusions
    before = len(valid)
    excluded_by_sector = [s for s in valid if s["sector"].upper() in EXCLUDED_SECTORS]
    excluded_by_symbol = [s for s in valid if s["symbol"] in EXCLUDED_SYMBOLS]

    filtered = [
        s for s in valid
        if s["sector"].upper() not in EXCLUDED_SECTORS and s["symbol"] not in EXCLUDED_SYMBOLS
    ]
    print(f"  After exclusions: {len(filtered)} (removed {before - len(filtered)})")
    if excluded_by_sector:
        print(f"    Excluded by sector ({len(excluded_by_sector)}): {', '.join(s['symbol'] for s in excluded_by_sector)}")
    if excluded_by_symbol:
        print(f"    Excluded by symbol ({len(excluded_by_symbol)}): {', '.join(s['symbol'] for s in excluded_by_symbol)}")

    # Sort by market cap descending
    filtered.sort(key=lambda x: x["market_cap_cr"], reverse=True)

    # Backup existing output
    if OUTPUT_FILE.exists():
        shutil.copy(OUTPUT_FILE, BACKUP_FILE)
        print(f"  Backed up existing {OUTPUT_FILE.name} -> {BACKUP_FILE.name}")

    # Write CSV
    fieldnames = [
        "rank", "symbol", "name", "sector",
        "price", "chg", "chg_pct", "high_52w", "low_52w",
        "volume", "weight", "market_cap_cr", "market_cap_raw",
    ]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rank, stock in enumerate(filtered, start=1):
            writer.writerow({"rank": rank, **stock})

    print(f"\nWrote {len(filtered)} stocks to {OUTPUT_FILE.name}")

    # Summary
    unknowns = [s for s in filtered if s["name"] == "UNKNOWN" or s["sector"] == "UNKNOWN"]
    if unknowns:
        print(f"\n--- Still UNKNOWN ({len(unknowns)}) ---")
        for s in unknowns:
            print(f"  #{filtered.index(s)+1:>3} {s['symbol']:<10} name={'UNKNOWN' if s['name']=='UNKNOWN' else 'OK':<8} sector={'UNKNOWN' if s['sector']=='UNKNOWN' else 'OK'}")

    print(f"\nTop 10 preview:")
    print(f"{'Rank':<5} {'Symbol':<10} {'Name':<40} {'Sector':<35} {'MCap (Cr)':>12}")
    print("-" * 110)
    for i, s in enumerate(filtered[:10]):
        print(f"{i+1:<5} {s['symbol']:<10} {s['name'][:38]:<40} {s['sector'][:33]:<35} {s['market_cap_cr']:>12.2f}")


if __name__ == "__main__":
    main()
