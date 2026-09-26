import yfinance as yf

tickers = [
    "MCD.NE", "MCD", "MCD.TO",
    "GLD", "NLR", "HUG.TO", "XEN.TO", "QQU.TO", "DLR.TO", "CASH.TO", "CBIL.TO", "TBIL",
    "COST.NE", "COST",
    "AEM.TO", "AEM",
    "H.TO",
]
for t in tickers:
    try:
        info = yf.Ticker(t).info
        print(t)
        for k in ["shortName", "longName", "sector", "industry", "country", "exchange", "quoteType", "fundFamily", "category"]:
            print(f"  {k}: {info.get(k)}")
    except Exception as e:
        print(t, "ERROR", e)
    print()
