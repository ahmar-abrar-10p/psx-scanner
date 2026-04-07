from curl_cffi import requests as curl_requests
import yfinance as yf

# Create a curl_cffi session with SSL verification disabled
session = curl_requests.Session(verify=False)

ticker = yf.Ticker('OGDC.KA', session=session)
hist = ticker.history(period='5d', interval='1d')
print(hist)
