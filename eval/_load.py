import pandas as pd, glob, os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
def num(s):
    return pd.to_numeric(s.astype(str).str.replace(" ", "", regex=False).str.replace("\u00a0","",regex=False).replace({"nan":None,"":None}), errors="coerce")
def dt(s):
    return pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")
def load():
    deals = pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False) for f in sorted(glob.glob(os.path.join(D, "deals_*.csv")))], ignore_index=True)
    con = pd.read_csv(os.path.join(D,"contracts.csv"), dtype=str, keep_default_na=False)
    par = pd.read_csv(os.path.join(D,"participants.csv"), dtype=str, keep_default_na=False)
    br = pd.read_csv(os.path.join(D,"brokers.csv"), dtype=str, keep_default_na=False)
    usd = pd.read_csv(os.path.join(D,"usd_rates.csv"), dtype=str, keep_default_na=False)
    return deals, con, par, br, usd
