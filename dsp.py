"""
dsp.py — Standalone script to download PSX market watch data as CSV.
Usage: python dsp.py
"""
import requests
import pandas as pd


def main():
    url = "https://dps.psx.com.pk/market-watch"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    df = pd.DataFrame(data)
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

    df.to_csv("psx_market_watch_full.csv", index=False)
    print(f"Exported {len(df)} stocks to psx_market_watch_full.csv")


if __name__ == "__main__":
    main()
