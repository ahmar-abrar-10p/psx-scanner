"""
parse_kmi.py — Build KMI_top100.csv from KMIALLSHR.csv with name + sector enrichment.

Pipeline:
1. Parse the raw KMIALLSHR.csv (misaligned format from PSX export)
2. Join each symbol against SECTOR_MAP (manual best-effort, marked HIGH/MED/LOW confidence)
3. Apply EXCLUDED_SECTORS and EXCLUDED_SYMBOLS filters
4. Sort by market cap descending
5. Take top 100
6. Write KMI_top100.csv with columns: rank, symbol, name, sector, sector_confidence, price, market_cap_cr, ...

The SECTOR_MAP only needs entries for the ~150 largest stocks by market cap.
Anything not in the map is assigned UNKNOWN/UNKNOWN/LOW and is unlikely to enter the top 100 anyway.
User vets the resulting CSV — focus on rows where sector_confidence != HIGH.
"""
import csv
import re
import shutil
from pathlib import Path

INPUT_FILE = Path(__file__).parent / "KMIALLSHR.csv"
OUTPUT_FILE = Path(__file__).parent / "KMI_top100.csv"
BACKUP_FILE = Path(__file__).parent / "KMI_top100.csv.bak"
TOP_N = 100

# Sector exclusions: any stock whose sector matches will be filtered before ranking.
EXCLUDED_SECTORS = {
    "Sugar & Allied",
}

# Symbol exclusions: specific symbols to drop regardless of sector (personal preference).
EXCLUDED_SYMBOLS = {
    "NESTLE",   # user does not trade Nestle
    "UPFL",     # user exclusion
    "RMPL",     # user exclusion
    "SHFA",     # user exclusion
    "PSEL",     # user exclusion
    "STYLERS",  # user exclusion
    "JKSM",     # user exclusion
    "FML",      # user exclusion
    "TICL",     # user exclusion
    "ZAHID",    # user exclusion
    "BATA",     # user exclusion
    "GLPL",     # user exclusion
    "GVGL",     # user exclusion (unknown, removed)
    "MEHT",     # user exclusion (unknown, removed)
    "ATBA",     # user exclusion (unknown, removed)
    "CRTM",     # user exclusion (unknown, removed)
    "FZCM",     # user exclusion (unknown, removed)
    "KPUS",     # user exclusion (unknown, removed)
    "GGL",      # user exclusion (unknown, removed)
}

# Manually curated symbol -> (name, sector, confidence)
# Confidence: HIGH = certain, MED = reasonably confident, LOW = guess (vet manually)
# Sectors follow PSX official classification where possible.
SECTOR_MAP: dict[str, tuple[str, str, str]] = {
    # Oil & Gas Exploration
    "OGDC": ("Oil & Gas Development Company", "Oil & Gas Exploration", "HIGH"),
    "PPL": ("Pakistan Petroleum", "Oil & Gas Exploration", "HIGH"),
    "MARI": ("Mari Petroleum", "Oil & Gas Exploration", "HIGH"),
    "POL": ("Pakistan Oilfields", "Oil & Gas Exploration", "HIGH"),

    # Oil & Gas Marketing
    "PSO": ("Pakistan State Oil", "Oil & Gas Marketing", "HIGH"),
    "APL": ("Attock Petroleum", "Oil & Gas Marketing", "HIGH"),
    "SHEL": ("Shell Pakistan", "Oil & Gas Marketing", "HIGH"),
    "HASCOL": ("Hascol Petroleum", "Oil & Gas Marketing", "HIGH"),
    "SNGP": ("Sui Northern Gas Pipelines", "Oil & Gas Marketing", "HIGH"),
    "SSGC": ("Sui Southern Gas Company", "Oil & Gas Marketing", "HIGH"),

    # Refinery
    "ATRL": ("Attock Refinery", "Refinery", "HIGH"),
    "NRL": ("National Refinery", "Refinery", "HIGH"),
    "PRL": ("Pakistan Refinery", "Refinery", "HIGH"),
    "BYCO": ("Byco Petroleum", "Refinery", "HIGH"),

    # Power Generation & Distribution
    "HUBC": ("Hub Power Company", "Power Generation & Distribution", "HIGH"),
    "KEL": ("K-Electric", "Power Generation & Distribution", "HIGH"),
    "KAPCO": ("Kot Addu Power Company", "Power Generation & Distribution", "HIGH"),
    "NPL": ("Nishat Power", "Power Generation & Distribution", "HIGH"),
    "NCPL": ("Nishat Chunian Power", "Power Generation & Distribution", "HIGH"),
    "EPQL": ("Engro Powergen Qadirpur", "Power Generation & Distribution", "HIGH"),
    "LPL": ("Lalpir Power", "Power Generation & Distribution", "HIGH"),
    "PKGP": ("Pakgen Power", "Power Generation & Distribution", "HIGH"),
    "SPWL": ("Saif Power", "Power Generation & Distribution", "HIGH"),
    "SEPL": ("Sitara Energy", "Power Generation & Distribution", "MED"),
    "TGL": ("Tariq Glass Industries", "Glass & Ceramics", "HIGH"),  # not power despite the name pattern
    "POWER": ("Power Cement", "Cement", "HIGH"),  # name is misleading, this is cement

    # Cement
    "LUCK": ("Lucky Cement", "Cement", "HIGH"),
    "DGKC": ("D.G. Khan Cement", "Cement", "HIGH"),
    "FCCL": ("Fauji Cement", "Cement", "HIGH"),
    "MLCF": ("Maple Leaf Cement", "Cement", "HIGH"),
    "KOHC": ("Kohat Cement", "Cement", "HIGH"),
    "ACPL": ("Attock Cement", "Cement", "HIGH"),
    "PIOC": ("Pioneer Cement", "Cement", "HIGH"),
    "CHCC": ("Cherat Cement", "Cement", "HIGH"),
    "GWLC": ("Gharibwal Cement", "Cement", "HIGH"),
    "BWCL": ("Bestway Cement", "Cement", "HIGH"),
    "FECTC": ("Fecto Cement", "Cement", "HIGH"),
    "DCL": ("Dewan Cement", "Cement", "HIGH"),
    "SHCM": ("Safe Mix Concrete", "Cement", "MED"),
    "DCR": ("Dolmen City REIT", "Real Estate Investment Trust", "HIGH"),  # not cement
    "FLYNG": ("Flying Cement", "Cement", "HIGH"),
    "JSCL": ("JS Cement", "Cement", "MED"),
    "THCCL": ("Thatta Cement", "Cement", "HIGH"),

    # Fertilizer
    "FFC": ("Fauji Fertilizer Company", "Fertilizer", "HIGH"),
    "EFERT": ("Engro Fertilizers", "Fertilizer", "HIGH"),
    "FATIMA": ("Fatima Fertilizer", "Fertilizer", "HIGH"),
    "FFBL": ("Fauji Fertilizer Bin Qasim", "Fertilizer", "HIGH"),
    "DAWH": ("Dawood Hercules", "Fertilizer", "HIGH"),

    # Commercial Banks (Islamic shown first since this is KMI)
    "MEBL": ("Meezan Bank", "Commercial Banks", "HIGH"),
    "BIPL": ("BankIslami Pakistan", "Commercial Banks", "HIGH"),
    "FABL": ("Faysal Bank", "Commercial Banks", "HIGH"),

    # Holding Companies / Conglomerates
    "ENGROH": ("Engro Holdings", "Holding Company", "HIGH"),
    "DWAE": ("Dawood Equities", "Holding Company", "MED"),

    # Pharmaceuticals
    "GLAXO": ("GlaxoSmithKline Pakistan", "Pharmaceuticals", "HIGH"),
    "ABOT": ("Abbott Laboratories Pakistan", "Pharmaceuticals", "HIGH"),
    "SEARL": ("The Searle Company", "Pharmaceuticals", "HIGH"),
    "HINOON": ("Highnoon Laboratories", "Pharmaceuticals", "HIGH"),
    "AGP": ("AGP Limited", "Pharmaceuticals", "HIGH"),
    "FEROZ": ("Ferozsons Laboratories", "Pharmaceuticals", "HIGH"),
    "MACTER": ("Macter International", "Pharmaceuticals", "HIGH"),
    "HALEON": ("Haleon Pakistan", "Pharmaceuticals", "HIGH"),
    "IBLHL": ("IBL HealthCare", "Pharmaceuticals", "MED"),
    "CPHL": ("Citi Pharma", "Pharmaceuticals", "HIGH"),

    # Food & Personal Care
    "NESTLE": ("Nestle Pakistan", "Food & Personal Care Products", "HIGH"),
    "UPFL": ("Unilever Pakistan Foods", "Food & Personal Care Products", "HIGH"),
    "RMPL": ("Rafhan Maize Products", "Food & Personal Care Products", "HIGH"),
    "NATF": ("National Foods", "Food & Personal Care Products", "HIGH"),
    "FCEPL": ("Frieslandcampina Engro Pakistan", "Food & Personal Care Products", "HIGH"),
    "MFL": ("Mitchell's Fruit Farms", "Food & Personal Care Products", "HIGH"),
    "ISIL": ("International Steels", "Engineering", "HIGH"),  # not food
    "SHEZ": ("Shezan International", "Food & Personal Care Products", "HIGH"),
    "ASCL": ("Asian Stocks", "Food & Personal Care Products", "LOW"),
    "PMRS": ("Pakistan Mortgage Refinance", "Other", "MED"),
    "MUREB": ("Murree Brewery", "Food & Personal Care Products", "HIGH"),
    "QUICE": ("Quice Food Industries", "Food & Personal Care Products", "MED"),

    # Textile Composite & Spinning
    "NML": ("Nishat Mills", "Textile Composite", "HIGH"),
    "GATM": ("Gul Ahmed Textile Mills", "Textile Composite", "HIGH"),
    "ILP": ("Interloop", "Textile Composite", "HIGH"),
    "KTML": ("Kohinoor Textile Mills", "Textile Composite", "HIGH"),
    "AVN": ("Avanceon", "Engineering", "HIGH"),  # not textile despite name
    "AWTX": ("Al-Abbas Textile Mills", "Textile Spinning", "MED"),
    "INIL": ("International Industries", "Engineering", "HIGH"),  # pipes/steel
    "MUGHAL": ("Mughal Iron & Steel", "Engineering", "HIGH"),
    "ASL": ("Aisha Steel Mills", "Engineering", "HIGH"),
    "ISL": ("International Steels", "Engineering", "HIGH"),

    # Sugar & Allied (TO BE EXCLUDED)
    "AABS": ("Al-Abbas Sugar Mills", "Sugar & Allied", "HIGH"),
    "JDWS": ("JDW Sugar Mills", "Sugar & Allied", "HIGH"),
    "HABSM": ("Habib Sugar Mills", "Sugar & Allied", "HIGH"),
    "ALNRS": ("Al-Noor Sugar Mills", "Sugar & Allied", "HIGH"),
    "SHSML": ("Shahmurad Sugar Mills", "Sugar & Allied", "HIGH"),
    "NRSL": ("Noon Sugar Mills", "Sugar & Allied", "HIGH"),
    "MIRKS": ("Mirpurkhas Sugar Mills", "Sugar & Allied", "HIGH"),
    "SHJS": ("Shahtaj Sugar Mills", "Sugar & Allied", "HIGH"),
    "SANSM": ("Sanghar Sugar Mills", "Sugar & Allied", "HIGH"),
    "FRSM": ("Faran Sugar Mills", "Sugar & Allied", "HIGH"),
    "SNAI": ("Sindh Abadgar's Sugar Mills", "Sugar & Allied", "HIGH"),
    # CSAP is NOT sugar (per user) — Crescent Steel & Allied Products, engineering
    "CSAP": ("Crescent Steel & Allied Products", "Engineering", "HIGH"),

    # Chemicals
    "LCI": ("Lotte Chemical", "Chemicals", "HIGH"),
    "LOTCHEM": ("Lotte Chemical Pakistan", "Chemicals", "HIGH"),
    "EPCL": ("Engro Polymer & Chemicals", "Chemicals", "HIGH"),
    "ICL": ("ICI Pakistan", "Chemicals", "HIGH"),
    "BERG": ("Berger Paints", "Chemicals", "HIGH"),
    "SITC": ("Sitara Chemical Industries", "Chemicals", "HIGH"),
    "GHGL": ("Ghani Glass", "Glass & Ceramics", "HIGH"),
    "PAKOXY": ("Pakistan Oxygen", "Chemicals", "HIGH"),
    "ARPL": ("Archroma Pakistan", "Chemicals", "HIGH"),
    "DYNO": ("Dynea Pakistan", "Chemicals", "MED"),
    "AGIL": ("Agriauto Industries", "Automobile Parts & Accessories", "HIGH"),  # not chemical

    # Automobile Assembler
    "INDU": ("Indus Motor Company", "Automobile Assembler", "HIGH"),
    "HCAR": ("Honda Atlas Cars", "Automobile Assembler", "HIGH"),
    "PSMC": ("Pak Suzuki Motor", "Automobile Assembler", "HIGH"),
    "MTL": ("Millat Tractors", "Automobile Assembler", "HIGH"),
    "AGTL": ("Al-Ghazi Tractors", "Automobile Assembler", "HIGH"),
    "GHNI": ("Ghani Automobile Industries", "Automobile Assembler", "HIGH"),
    "SAZEW": ("Sazgar Engineering Works", "Automobile Assembler", "HIGH"),
    "HINO": ("Hino Pak Motors", "Automobile Assembler", "HIGH"),
    "ATLH": ("Atlas Honda", "Automobile Assembler", "HIGH"),

    # Automobile Parts & Accessories
    "THALL": ("Thal Limited", "Automobile Parts & Accessories", "HIGH"),
    "EXIDE": ("Exide Pakistan", "Automobile Parts & Accessories", "HIGH"),
    "GTYR": ("General Tyre & Rubber", "Automobile Parts & Accessories", "HIGH"),
    "BWHL": ("Baluchistan Wheels", "Automobile Parts & Accessories", "HIGH"),
    "LOADS": ("Loads Limited", "Automobile Parts & Accessories", "HIGH"),

    # Engineering
    "KSBP": ("KSB Pumps", "Engineering", "HIGH"),
    "SIEM": ("Siemens Pakistan Engineering", "Engineering", "HIGH"),
    "PAEL": ("Pak Elektron", "Cable & Electrical Goods", "HIGH"),

    # Cable & Electrical Goods
    "PAKD": ("Pak Datacom", "Telecommunication", "HIGH"),

    # Paper & Board
    "PKGS": ("Packages Limited", "Paper & Board", "HIGH"),
    "CEPB": ("Century Paper & Board", "Paper & Board", "HIGH"),
    "CPPL": ("Cherat Packaging", "Paper & Board", "HIGH"),
    "BWHL2": ("Pakages Convertors", "Paper & Board", "MED"),
    "BPL": ("Bawany Polypropelene", "Paper & Board", "MED"),
    "PSEL": ("Pakistan Services", "Misc.", "HIGH"),  # actually hospitality/tourism

    # Technology & Communication
    "SYS": ("Systems Limited", "Technology & Communication", "HIGH"),
    "NETSOL": ("NetSol Technologies", "Technology & Communication", "HIGH"),
    "AVN2": ("Avanceon Limited", "Technology & Communication", "HIGH"),
    "OCTOPUS": ("Octopus Digital", "Technology & Communication", "HIGH"),
    "TPLP": ("TPL Properties", "Real Estate Investment Trust", "HIGH"),  # not tech
    "PTC": ("Pakistan Telecommunication Company", "Telecommunication", "HIGH"),
    "AIRLINK": ("AirLink Communication", "Technology & Communication", "HIGH"),
    "TELE": ("Telecard", "Telecommunication", "HIGH"),
    "WTL": ("Worldcall Telecom", "Telecommunication", "HIGH"),

    # Insurance / Modarabas / Investment Banks (mostly non-Shariah, may not appear in KMI)
    "AICL": ("Adamjee Insurance", "Insurance", "HIGH"),

    # Tobacco (excluded in Shariah context but listing for completeness)

    # Glass & Ceramics
    "GHGL2": ("Ghani Glass Mills", "Glass & Ceramics", "HIGH"),
    "TGL2": ("Tariq Glass Industries", "Glass & Ceramics", "HIGH"),

    # Miscellaneous / Other
    "TREET": ("Treet Corporation", "Misc.", "HIGH"),
    "SHFA": ("Shifa International Hospitals", "Misc.", "HIGH"),  # healthcare/hospital
    "SAPT": ("Sapphire Textile Mills", "Textile Composite", "HIGH"),
    "FRCL": ("Frontier Ceramics", "Glass & Ceramics", "MED"),
    "IBFL": ("Ibrahim Fibres", "Textile Spinning", "HIGH"),
    "HPL": ("Hi-Tech Lubricants", "Oil & Gas Marketing", "HIGH"),
    "FFL": ("Fauji Foods Limited", "Food & Personal Care Products", "HIGH"),
    "JVDC": ("Javedan Corporation", "Property", "HIGH"),
    "PTL": ("Panther Tyres", "Automobile Parts & Accessories", "HIGH"),
    "IPAK": ("International Packaging Films", "Paper & Board", "HIGH"),
    "GAL": ("Ghandhara Automobiles", "Automobile Assembler", "HIGH"),
    "SGF": ("Service Global Footwear", "Leather & Tanneries", "HIGH"),
    "FCL": ("Fast Cables", "Cable & Electrical Goods", "HIGH"),
    "BFBIO": ("BF Biosciences", "Pharmaceuticals", "HIGH"),
    "BBFL": ("Big Bird Foods", "Food & Personal Care Products", "HIGH"),
    "BFAGRO": ("Barkat Frisian Agro", "Miscellaneous", "HIGH"),
    "PIBTL": ("Pakistan International Bulk Terminal", "Transport", "HIGH"),
    "CNERGY": ("Cnergyico PK", "Refinery", "HIGH"),
    "GCIL": ("Ghani Chemical Industries", "Chemicals", "HIGH"),
    "TGL": ("Tariq Glass Industries", "Glass & Ceramics", "HIGH"),
    "SPEL": ("SPEL Limited", "Paper & Board", "HIGH"),
    "GATI": ("Gatron Industries", "Synthetic & Rayon", "HIGH"),
    "TOMCL": ("The Organic Meat Company", "Food & Personal Care Products", "HIGH"),
    "SLGL": ("Secure Logistics-Trax Group", "Transport", "HIGH"),
    "PREMA": ("At-Tahur Limited", "Food & Personal Care Products", "HIGH"),
}


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
        return number / 100  # Lac -> Crore
    elif unit == "k":
        return number / 100000  # K (thousands) -> Crore
    return number  # already in Cr


def parse_csv(filepath: Path) -> list[dict]:
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

            if symbol and len(symbol) > 1:  # skip single-char noise rows
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
                    pass

        i += 1

    return stocks


def enrich_with_sector(stock: dict) -> dict:
    """Add name, sector, sector_confidence from SECTOR_MAP."""
    sym = stock["symbol"]
    if sym in SECTOR_MAP:
        name, sector, confidence = SECTOR_MAP[sym]
    else:
        name, sector, confidence = "UNKNOWN", "UNKNOWN", "LOW"
    stock["name"] = name
    stock["sector"] = sector
    stock["sector_confidence"] = confidence
    return stock


def main():
    print(f"Reading {INPUT_FILE.name}...")
    stocks = parse_csv(INPUT_FILE)
    print(f"  Total stocks parsed: {len(stocks)}")

    # Filter out stocks with zero price or zero market cap (likely delisted/data issues)
    valid = [s for s in stocks if s["price"] > 0 and s["market_cap_cr"] > 0]
    print(f"  With valid price & market cap: {len(valid)}")

    # Enrich with sector info
    enriched = [enrich_with_sector(s) for s in valid]

    # Apply exclusions
    before = len(enriched)
    excluded_by_sector = [s for s in enriched if s["sector"] in EXCLUDED_SECTORS]
    excluded_by_symbol = [s for s in enriched if s["symbol"] in EXCLUDED_SYMBOLS]

    filtered = [
        s for s in enriched
        if s["sector"] not in EXCLUDED_SECTORS and s["symbol"] not in EXCLUDED_SYMBOLS
    ]
    print(f"  After exclusions: {len(filtered)} (removed {before - len(filtered)})")
    if excluded_by_sector:
        print(f"    Excluded by sector ({len(excluded_by_sector)}): {', '.join(s['symbol'] for s in excluded_by_sector)}")
    if excluded_by_symbol:
        print(f"    Excluded by symbol ({len(excluded_by_symbol)}): {', '.join(s['symbol'] for s in excluded_by_symbol)}")

    # Sort by market cap descending and take top N
    filtered.sort(key=lambda x: x["market_cap_cr"], reverse=True)
    top = filtered[:TOP_N]

    # Backup the existing output if it exists
    if OUTPUT_FILE.exists():
        shutil.copy(OUTPUT_FILE, BACKUP_FILE)
        print(f"  Backed up existing {OUTPUT_FILE.name} -> {BACKUP_FILE.name}")

    # Write new CSV
    fieldnames = [
        "rank", "symbol", "name", "sector", "sector_confidence",
        "price", "chg", "chg_pct", "high_52w", "low_52w",
        "volume", "weight", "market_cap_cr", "market_cap_raw",
    ]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rank, stock in enumerate(top, start=1):
            writer.writerow({"rank": rank, **stock})

    print(f"\nWrote top {len(top)} stocks to {OUTPUT_FILE.name}")

    # Confidence summary
    high = sum(1 for s in top if s["sector_confidence"] == "HIGH")
    med = sum(1 for s in top if s["sector_confidence"] == "MED")
    low = sum(1 for s in top if s["sector_confidence"] == "LOW")
    print(f"\nSector confidence breakdown:")
    print(f"  HIGH: {high}")
    print(f"  MED:  {med}  (verify these)")
    print(f"  LOW:  {low}  (definitely verify these)")

    # Show LOW/MED rows for quick review
    needs_review = [s for s in top if s["sector_confidence"] != "HIGH"]
    if needs_review:
        print(f"\n--- Rows needing review ({len(needs_review)}) ---")
        for s in needs_review:
            print(f"  #{top.index(s)+1:>3} {s['symbol']:<10} {s['name'][:35]:<35} -> {s['sector']:<35} ({s['sector_confidence']})")

    print(f"\nTop 10 preview:")
    print(f"{'Rank':<5} {'Symbol':<10} {'Name':<35} {'Sector':<30} {'MCap (Cr)':>12}")
    print("-" * 100)
    for s in top[:10]:
        print(f"{top.index(s)+1:<5} {s['symbol']:<10} {s['name'][:33]:<35} {s['sector'][:28]:<30} {s['market_cap_cr']:>12.2f}")


if __name__ == "__main__":
    main()
