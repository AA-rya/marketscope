"""Collects public market data and writes data.json for the site.
Source (no API keys): Yahoo Finance via yfinance."""
import json, os, statistics, datetime as dt

UNIVERSE = """AAPL MSFT NVDA GOOGL META AVGO ORCL CRM ADBE CSCO INTC
NEE DUK SO D AEP XEL EXC
XOM CVX COP EOG SLB OXY PSX
JPM BAC WFC GS MS C SCHW
PLD AMT EQIX O SPG PSA
JNJ UNH PFE MRK ABBV LLY TMO
AMZN TSLA HD MCD NKE SBUX LOW
CAT HON UPS GE DE LMT RTX""".split()

# stated assumptions (not company data): share of debt that reprices with rates, and equity duration in years
FLOAT = {"Technology": .20, "Utilities": .25, "Energy": .30, "Financial Services": .60, "Real Estate": .45,
         "Healthcare": .25, "Consumer Cyclical": .35, "Industrials": .35}
DUR = {"Technology": 9.0, "Utilities": 14.0, "Energy": 6.5, "Financial Services": 5.0, "Real Estate": 15.0,
       "Healthcare": 8.0, "Consumer Cyclical": 9.5, "Industrials": 8.0}

def num(v):
    return float(v) if isinstance(v, (int, float)) and v == v else None

def main():
    out = {"updated": dt.datetime.now(dt.timezone.utc).isoformat()}
    old = {}
    if os.path.exists("data.json"):
        try: old = json.load(open("data.json"))
        except Exception: pass

    out["rates"], out["oil"] = old.get("rates", {}), old.get("oil", {})
    # yields and oil via Yahoo Finance (^TNX/^FVX/^IRX are quoted in percent)
    try:
        import yfinance as yf
        for key, sym, n in [("DGS10", "^TNX", 260), ("DGS5", "^FVX", 260), ("DGS3M", "^IRX", 260)]:
            try:
                s = yf.Ticker(sym).history(period="1y")["Close"].dropna().tail(n)
                if len(s) > 20: out["rates"][key] = [[d.strftime("%Y-%m-%d"), round(float(v), 3)] for d, v in s.items()]
            except Exception as e: print("rate fail", sym, e)
        for key, sym in [("wti", "CL=F"), ("brent", "BZ=F")]:
            try:
                s = yf.Ticker(sym).history(period="6mo")["Close"].dropna()
                if len(s) > 20: out["oil"][key] = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in s.items()]
            except Exception as e: print("oil fail", sym, e)
    except Exception as e:
        print("yfinance unavailable", e)

    # stocks via yfinance
    screen, raw = [], []
    try:
        import yfinance as yf
        for t in UNIVERSE:
            try:
                tk = yf.Ticker(t); i = tk.info; h = tk.history(period="1y")["Close"].dropna()
                price = num(i.get("currentPrice")) or (float(h.iloc[-1]) if len(h) else None)
                pe, roe, de = num(i.get("trailingPE")), num(i.get("returnOnEquity")), num(i.get("debtToEquity"))
                rate = num(i.get("dividendRate")) or 0.0
                if None in (price, pe, roe, de) or len(h) < 200 or not i.get("sector"): continue
                screen.append({"ticker": t, "sector": i["sector"], "price": round(price, 2), "pe": round(pe, 1),
                               "roe": round(roe * 100, 1), "debt_equity": round(de / 100, 2),
                               "div_yield": round(rate / price * 100, 2), "mom_1y": round((price / float(h.iloc[0]) - 1) * 100, 1)})
                debt, ebitda = num(i.get("totalDebt")), num(i.get("ebitda"))
                if debt and ebitda and ebitda > 0: raw.append((i["sector"], debt, ebitda))
            except Exception as e: print("skip", t, e)
    except Exception as e:
        print("yfinance unavailable", e)

    if len(screen) >= 20:
        out["screen"] = screen
        t10 = out["rates"].get("DGS10", [[0, 4.0]])[-1][1]; cod = (t10 + 2.0) / 100   # assumed cost of debt = 10y + 2pts
        sect = []
        for s in sorted({r[0] for r in raw}):
            rows = [r for r in raw if r[0] == s]
            if len(rows) < 2: continue
            de = statistics.median(r[1] / r[2] for r in rows)
            cover = statistics.median(r[2] / (r[1] * cod) for r in rows)
            sect.append({"sector": s, "debt_ebitda": round(de, 1), "floating_share": FLOAT.get(s, .3),
                         "interest_cover": round(cover, 1), "equity_duration": DUR.get(s, 8.0)})
        if len(sect) >= 4: out["sect"] = sect
        else: out["sect"] = old.get("sect")
    else:
        print("too few stocks fetched; keeping previous stock data")
        out["screen"], out["sect"] = old.get("screen"), old.get("sect")

    json.dump(out, open("data.json", "w"), separators=(",", ":"))
    print("ok", {k: (len(v) if hasattr(v, "__len__") else v) for k, v in out.items()})

if __name__ == "__main__":
    main()
