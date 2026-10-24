# Marketscope

Screener, interest-rate simulator, and oil-flow map in one site (FMKT 256 extra credit).

- `index.html` is the whole site (no build step).
- `fetch_data.py` runs every 5 minutes in GitHub Actions and writes `data.json`; the page re-reads it on its own.
- Sources: Yahoo Finance (prices, fundamentals, yields, commodities), US Treasury (daily yield curve; FiscalData average rates pulled in the browser), US EIA (crude oil imports by country and exports by destination).
- Every tool also accepts a CSV import for your own historical data.
