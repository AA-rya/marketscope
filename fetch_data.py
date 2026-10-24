"""Collects public market data and writes data.json for the site.
Sources (no API keys): Yahoo Finance via yfinance, FRED public CSV, US Treasury."""
import csv, io, json, os, statistics, sys, datetime as dt, urllib.request

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

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read().decode()

def fred(series, n):
    rows = list(csv.reader(io.StringIO(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"))))[1:]
    pts = [[r[0], float(r[1])] for r in rows if len(r) > 1 and r[1] not in ("", ".")]
    return pts[-n:]

def num(v):
    return float(v) if isinstance(v, (int, float)) and v == v else None

def main():
    out = {"updated": dt.datetime.now(dt.timezone.utc).isoformat()}
    old = {}
    if os.path.exists("data.json"):
        try: old = json.load(open("data.json"))
        except Exception: pass

    # rates + oil from FRED (public CSV)
    out["rates"], out["oil"] = old.get("rates", {}), old.get("oil", {})
    for k, s, n in [("DGS10", "DGS10", 260), ("DGS2", "DGS2", 260), ("DFF", "DFF", 260)]:
        try: out["rates"][k] = fred(s, n)
        except Exception as e: print("fred fail", s, e)
    for k, s in [("wti", "DCOILWTICO"), ("brent", "DCOILBRENTEU")]:
        try: out["oil"][k] = fred(s, 130)
        except Exception as e: print("fred fail", s, e)

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
