"""Collects public market data and writes data.json for the site. No API keys.
Sources: Yahoo Finance (via yfinance), US Treasury (daily yield curve), US EIA (oil import/export tables)."""
import json, os, re, statistics, urllib.request, warnings, datetime as dt
warnings.filterwarnings("ignore")
DIAG = []
from html.parser import HTMLParser

UNIVERSE = """AAPL MSFT NVDA GOOGL META AVGO ORCL CRM ADBE CSCO INTC
NEE DUK SO D AEP XEL EXC
XOM CVX COP EOG SLB OXY PSX
JPM BAC WFC GS MS C SCHW
PLD AMT EQIX O SPG PSA
JNJ UNH PFE MRK ABBV LLY TMO
AMZN TSLA HD MCD NKE SBUX LOW
CAT HON UPS GE DE LMT RTX""".split()

QUOTES = [("S&P 500", "^GSPC"), ("Nasdaq", "^IXIC"), ("Dow", "^DJI"), ("Russell 2000", "^RUT"), ("VIX", "^VIX"),
          ("US dollar index", "DX-Y.NYB"), ("Gold", "GC=F"), ("Copper", "HG=F"), ("Natural gas", "NG=F"),
          ("WTI crude", "CL=F"), ("Brent crude", "BZ=F"), ("Bitcoin", "BTC-USD"), ("10-yr yield", "^TNX")]

# stated assumptions (not company data): share of debt that reprices with rates, and equity duration in years
FLOAT = {"Technology": .20, "Utilities": .25, "Energy": .30, "Financial Services": .60, "Real Estate": .45,
         "Healthcare": .25, "Consumer Cyclical": .35, "Industrials": .35, "Communication Services": .30}
DUR = {"Technology": 9.0, "Utilities": 14.0, "Energy": 6.5, "Financial Services": 5.0, "Real Estate": 15.0,
       "Healthcare": 8.0, "Consumer Cyclical": 9.5, "Industrials": 8.0, "Communication Services": 8.0}

IMP_URL = "https://www.eia.gov/dnav/pet/pet_move_impcus_a2_nus_epc0_im0_mbblpd_m.htm"
EXP_URL = "https://www.eia.gov/dnav/pet/pet_move_expc_a_EPC0_EEX_mbblpd_m.htm"
LATAM = set("""Argentina|Bahamas|Bahama Islands|Barbados|Belize|Bermuda|Bolivia|Brazil|Cayman Islands|Chile|Colombia|Costa Rica|Curacao|
Dominica|Dominican Republic|Ecuador|El Salvador|French Guiana|Guatemala|Guyana|Haiti|Honduras|Jamaica|Martinique|Mexico|Nicaragua|Panama|
Paraguay|Peru|Puerto Rico|Suriname|Trinidad and Tobago|Uruguay|Virgin Islands (U.S.)|Aruba|Netherlands Antilles""".replace("\n", "").split("|"))
AFRICA = set("""Algeria|Angola|Benin|Cameroon|Chad|Congo (Brazzaville)|Congo (Kinshasa)|Egypt|Equatorial Guinea|Eswatini|Gabon|Ghana|Guinea|
Ivory Coast|Libya|Mauritania|Morocco|Mozambique|Namibia|Nigeria|Senegal|South Africa|South Sudan|Togo|Tunisia|Liberia""".replace("\n", "").split("|"))
EUROPE = set("""Albania|Austria|Belarus|Belgium|Bosnia and Herzegovina|Bulgaria|Croatia|Cyprus|Czechia|Denmark|Estonia|Finland|France|Germany|
Gibralter|Gibraltar|Greece|Hungary|Ireland|Italy|Latvia|Lithuania|Malta|Netherlands|Norway|Poland|Portugal|Romania|Russia|Serbia|
Serbia (Excludes Kosovo)|Slovakia|Slovenia|Spain|Sweden|Switzerland|Ukraine|United Kingdom|Iceland""".replace("\n", "").split("|"))
APAC = set("""Australia|Bangladesh|Brunei|Burma|China|Hong Kong|India|Indonesia|Japan|Korea, South|Malaysia|New Zealand|Pakistan|Papua New Guinea|
Philippines|Singapore|Sri Lanka|Taiwan|Thailand|Vietnam|Spatly Islands|Cook Islands|Niue|Midway Islands|Marshall Islands""".replace("\n", "").split("|"))
GULF = {"Saudi Arabia", "Iraq", "Kuwait", "United Arab Emirates", "Qatar", "Bahrain", "Iran"}
SKIP = {"All Countries", "Persian Gulf", "OPEC*", "Non OPEC*", "Total All Countries"}


def num(v):
    return float(v) if isinstance(v, (int, float)) and v == v else None


class Rows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows, self.stack, self.cell = [], [], None
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.stack.append([])
        elif tag in ("td", "th") and self.stack: self.cell = [dict(attrs).get("class", ""), ""]
    def handle_data(self, d):
        if self.cell is not None: self.cell[1] += d
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.stack:
            self.stack[-1].append((self.cell[0], self.cell[1].strip())); self.cell = None
        elif tag == "tr" and self.stack: self.rows.append(self.stack.pop())


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "text/html,application/xhtml+xml,text/csv,*/*", "Accept-Language": "en-US,en;q=0.9"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


def eia_table(url):
    p = Rows(); p.feed(get(url))
    months, data = [], {}
    for r in p.rows:
        texts = [t for _, t in r]
        if not months and sum(bool(re.fullmatch(r"[A-Z][a-z]{2}-\d\d", t)) for t in texts) >= 3:
            months = [t for t in texts if re.fullmatch(r"[A-Z][a-z]{2}-\d\d", t)]
        if r and r[0][0] == "DataStub" and months:
            vals = []
            for _, t in r[1:1 + len(months)]:
                t = t.replace(",", "")
                vals.append(float(t) if re.fullmatch(r"-?\d+(\.\d+)?", t) else 0.0)
            data[r[0][1]] = vals
    return months, data


def region_in(name, gulf_from_row):
    if name == "Canada": return "Canada"
    if name == "Mexico": return "Mexico"
    if name == "Venezuela": return "Venezuela"
    if name in GULF: return None  # counted via the Persian Gulf row
    if name in LATAM: return "Other Latin America"
    if name in AFRICA: return "Africa"
    if name in EUROPE: return "Europe"
    return "Asia & other"


def build_flow():
    m1, imp = eia_table(IMP_URL); m2, exp = eia_table(EXP_URL)
    n = min(len(m1), len(m2)); months = m1[:n]
    if n < 3 or "Canada" not in imp: raise RuntimeError("EIA table not parsed")
    imports = {"Persian Gulf": imp.get("Persian Gulf", [0] * n)[:n]}
    for name, v in imp.items():
        if name in SKIP: continue
        r = region_in(name, None)
        if r is None: continue
        imports.setdefault(r, [0.0] * n)
        imports[r] = [a + b for a, b in zip(imports[r], v[:n])]
    exports = {}
    for name, v in exp.items():
        if name in SKIP: continue
        if name == "Canada": r = "Canada"
        elif name == "Mexico": r = "Mexico"
        elif name in LATAM: r = "Other Latin America"
        elif name in EUROPE: r = "Europe"
        elif name in APAC: r = "Asia-Pacific"
        else: r = "Middle East, Africa & other"
        exports.setdefault(r, [0.0] * n)
        exports[r] = [a + b for a, b in zip(exports[r], v[:n])]
    # EIA reports thousand bbl/day; convert to million bbl/day
    cv = lambda d: {k: [round(x / 1000, 3) for x in v] for k, v in d.items() if any(v)}
    return {"months": months, "imports": cv(imports), "exports": cv(exports),
            "source": "U.S. Energy Information Administration, crude oil only"}


def build_curve():
    """Full US Treasury par yield curve (latest, ~1 month ago, ~1 year ago)."""
    y = dt.date.today().year; rows = []
    for yr in (y, y - 1):
        t = get(f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{yr}/all?type=daily_treasury_yield_curve&field_tdr_date_value={yr}&page&_format=csv")
        L = [l.split(",") for l in t.strip().splitlines()]; h = [c.strip('"') for c in L[0]]
        rows += [dict(zip(h, [c.strip('"') for c in r])) for r in L[1:]]
    rows.sort(key=lambda r: dt.datetime.strptime(r["Date"], "%m/%d/%Y"))
    labs = [c for c in rows[0] if c != "Date" and "1.5" not in c]
    pick = lambda i: rows[max(0, len(rows) - 1 - i)]
    out = {"labels": labs}
    for key, i in (("now", 0), ("m1", 21), ("y1", 250)):
        r = pick(i); out[key] = {"date": dt.datetime.strptime(r["Date"], "%m/%d/%Y").strftime("%Y-%m-%d"),
                                 "v": [float(r[c]) if r.get(c) else None for c in labs]}
    return out


def main():
    import yfinance as yf
    out = {"updated": dt.datetime.now(dt.timezone.utc).isoformat()}
    old = {}
    if os.path.exists("data.json"):
        try: old = json.load(open("data.json"))
        except Exception: pass
    for k in ("rates", "oil", "market", "curve", "flow", "screen", "sect"): out[k] = old.get(k)
    out["rates"], out["oil"] = out["rates"] or {}, out["oil"] or {}

    # yields + oil history
    for key, sym in [("DGS10", "^TNX"), ("DGS5", "^FVX"), ("DGS3M", "^IRX"), ("DGS30", "^TYX")]:
        try:
            s = yf.Ticker(sym).history(period="1y")["Close"].dropna().tail(260)
            if len(s) > 20: out["rates"][key] = [[d.strftime("%Y-%m-%d"), round(float(v), 3)] for d, v in s.items()]
        except Exception as e: print("rate fail", sym, e)
    for key, sym in [("wti", "CL=F"), ("brent", "BZ=F")]:
        try:
            s = yf.Ticker(sym).history(period="6mo")["Close"].dropna()
            if len(s) > 20: out["oil"][key] = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in s.items()]
        except Exception as e: print("oil fail", sym, e)

    # market board
    try:
        board = []
        for name, sym in QUOTES:
            try:
                s = yf.Ticker(sym).history(period="3mo")["Close"].dropna()
                if len(s) < 25: continue
                last = float(s.iloc[-1])
                board.append({"name": name, "sym": sym, "price": round(last, 2), "d1": round((last / float(s.iloc[-2]) - 1) * 100, 2),
                              "m1": round((last / float(s.iloc[-22]) - 1) * 100, 2), "spark": [round(float(v), 2) for v in s.tail(40)]})
            except Exception as e: print("quote fail", sym, e)
        if len(board) >= 6: out["market"] = board
    except Exception as e: print("market fail", e)

    # full Treasury curve
    try: out["curve"] = build_curve()
    except Exception as e: print("curve fail", e); DIAG.append("curve: " + repr(e)[:200])

    # real oil flows (EIA)
    try: out["flow"] = build_flow()
    except Exception as e: print("flow fail", e); DIAG.append("flow: " + repr(e)[:300])

    # stocks: fundamentals cached (slow), prices refreshed every run (fast)
    fund = {}
    try:
        fund = json.load(open("fundamentals.json"))
    except Exception: pass
    age = 1e9
    if fund.get("t"): age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(fund["t"])).total_seconds()
    if age > 6 * 3600 or not fund.get("d"):
        d = fund.get("d", {})
        for t in UNIVERSE:
            try:
                i = yf.Ticker(t).info
                d[t] = {"sector": i.get("sector"), "eps": num(i.get("trailingEps")), "roe": num(i.get("returnOnEquity")),
                        "de": num(i.get("debtToEquity")), "dps": num(i.get("dividendRate")) or 0.0,
                        "debt": num(i.get("totalDebt")), "ebitda": num(i.get("ebitda"))}
            except Exception as e: print("info skip", t, e)
        fund = {"t": out["updated"], "d": d}
        json.dump(fund, open("fundamentals.json", "w"), separators=(",", ":"))
    try:
        px = yf.download(UNIVERSE, period="1y", interval="1d", progress=False, auto_adjust=False, threads=True)["Close"]
        screen, raw = [], []
        for t in UNIVERSE:
            f = fund["d"].get(t)
            if not f or t not in px or not f.get("sector"): continue
            h = px[t].dropna()
            if len(h) < 200 or not f.get("eps") or f["eps"] <= 0 or f.get("roe") is None or f.get("de") is None: continue
            price = float(h.iloc[-1])
            screen.append({"ticker": t, "sector": f["sector"], "price": round(price, 2), "pe": round(price / f["eps"], 1),
                           "roe": round(f["roe"] * 100, 1), "debt_equity": round(f["de"] / 100, 2),
                           "div_yield": round(f["dps"] / price * 100, 2), "mom_1y": round((price / float(h.iloc[0]) - 1) * 100, 1)})
            if f.get("debt") and f.get("ebitda") and f["ebitda"] > 0: raw.append((f["sector"], f["debt"], f["ebitda"]))
        if len(screen) >= 20:
            out["screen"] = screen
            t10 = out["rates"].get("DGS10", [[0, 4.0]])[-1][1]; cod = (t10 + 2.0) / 100   # assumed cost of debt = 10y + 2pts
            sect = []
            for s in sorted({r[0] for r in raw}):
                rows = [r for r in raw if r[0] == s]
                if len(rows) < 2: continue
                sect.append({"sector": s, "debt_ebitda": round(statistics.median(r[1] / r[2] for r in rows), 1),
                             "floating_share": FLOAT.get(s, .3),
                             "interest_cover": round(statistics.median(r[2] / (r[1] * cod) for r in rows), 1),
                             "equity_duration": DUR.get(s, 8.0)})
            if len(sect) >= 4: out["sect"] = sect
        else: print("too few stocks; keeping previous")
    except Exception as e: print("stocks fail", e)

    out["diag"] = DIAG
    json.dump(out, open("data.json", "w"), separators=(",", ":"))
    print("ok", {k: (len(v) if hasattr(v, "__len__") else v) for k, v in out.items() if v is not None})


if __name__ == "__main__":
    main()
