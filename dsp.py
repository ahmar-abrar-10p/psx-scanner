import requests
import pandas as pd

# PSX Market Watch API endpoint
url = "https://dps.psx.com.pk/market-watch"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

response = requests.get(url, headers=headers)
data = response.json()

# Convert to DataFrame
df = pd.DataFrame(data)

# Rename columns (clean format)
df.rename(columns={
    'SYMBOL': 'symbol',
    'SECTOR': 'sector',
    'LDCP': 'ldcp',
    'OPEN': 'open',
    'HIGH': 'high',
    'LOW': 'low',
    'CURRENT': 'current',
    'CHANGE': 'change',
    'CHANGE (%)': 'change_percent',
    'VOLUME': 'volume'
}, inplace=True)

# Save CSV
df.to_csv("psx_market_watch_full.csv", index=False)

print("✅ Full CSV exported: psx_market_watch_full.csv")