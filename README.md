# Marketscope

Screener, interest-rate simulator, and oil-flow map in one site (FMKT 256 extra credit).

- `index.html` is the whole site (no build step).
- `fetch_data.py` runs every 15 minutes in GitHub Actions and writes `data.json`; the page re-reads it on its own.
- Sources: Yahoo Finance (Treasury yields, WTI/Brent futures), US Treasury FiscalData (average interest rates, pulled in the browser).
- Every tool also accepts a CSV import for your own historical data.
