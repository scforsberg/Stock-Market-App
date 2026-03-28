from __future__ import annotations

import json
import os
from io import StringIO
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

QUERY_BASE_URL = "https://www.alphavantage.co/query"
ANALYTICS_BASE_URL = "https://alphavantageapi.co/timeseries/analytics"

FUNCTIONS = {
    "Time Series": [
        "TIME_SERIES_INTRADAY","TIME_SERIES_DAILY","TIME_SERIES_DAILY_ADJUSTED",
        "TIME_SERIES_WEEKLY","TIME_SERIES_WEEKLY_ADJUSTED","TIME_SERIES_MONTHLY",
        "TIME_SERIES_MONTHLY_ADJUSTED","GLOBAL_QUOTE","SYMBOL_SEARCH","MARKET_STATUS",
    ],
    "Options & Intelligence": [
        "HISTORICAL_OPTIONS","NEWS_SENTIMENT","TOP_GAINERS_LOSERS","INSIDER_TRANSACTIONS",
        "ANALYTICS_FIXED_WINDOW","ANALYTICS_SLIDING_WINDOW",
    ],
    "Fundamentals": [
        "OVERVIEW","INCOME_STATEMENT","BALANCE_SHEET","CASH_FLOW","EARNINGS",
        "LISTING_STATUS","EARNINGS_CALENDAR","IPO_CALENDAR",
    ],
    "Forex & Crypto": [
        "FX_INTRADAY","FX_DAILY","FX_WEEKLY","FX_MONTHLY","CURRENCY_EXCHANGE_RATE",
        "CRYPTO_INTRADAY","DIGITAL_CURRENCY_DAILY","DIGITAL_CURRENCY_WEEKLY","DIGITAL_CURRENCY_MONTHLY",
    ],
    "Economics & Commodities": [
        "REAL_GDP","REAL_GDP_PER_CAPITA","TREASURY_YIELD","FEDERAL_FUNDS_RATE","CPI","INFLATION",
        "RETAIL_SALES","DURABLES","UNEMPLOYMENT","NONFARM_PAYROLL",
        "WTI","BRENT","NATURAL_GAS","COPPER","ALUMINUM","WHEAT","CORN","COTTON","SUGAR","COFFEE",
        "ALL_COMMODITIES","REALTIME_BULK_QUOTES","XAU_USD","XAG_USD","XAU_EUR","XAG_EUR",
    ],
    "Technical Indicators": [
        "SMA","EMA","WMA","DEMA","TEMA","TRIMA","KAMA","MAMA","VWAP","T3",
        "MACD","MACDEXT","STOCH","STOCHF","RSI","STOCHRSI","WILLR","ADX","ADXR",
        "APO","PPO","MOM","BOP","CCI","CMO","ROC","ROCR","AROON","AROONOSC",
        "MFI","TRIX","ULTOSC","DX","MINUS_DI","PLUS_DI","MINUS_DM","PLUS_DM",
        "BBANDS","MIDPOINT","MIDPRICE","SAR","TRANGE","ATR","NATR","AD","ADOSC",
        "OBV","HT_TRENDLINE","HT_SINE","HT_TRENDMODE","HT_DCPERIOD","HT_DCPHASE","HT_PHASOR",
    ],
}

PRESETS = {
    "symbol": "IBM",
    "interval": "5min",
    "outputsize": "compact",
    "datatype": "json",
    "adjusted": "true",
    "entitlement": "realtime",
    "series_type": "close",
    "time_period": "14",
    "from_symbol": "EUR",
    "to_symbol": "USD",
    "from_currency": "BTC",
    "to_currency": "USD",
    "market": "USD",
    "horizon": "3month",
    "apikey": "",
}

def flatten_json(payload: object) -> pd.DataFrame | None:
    if isinstance(payload, list) and payload and all(isinstance(x, dict) for x in payload):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                values = list(value.values())
                if values and all(isinstance(v, dict) for v in values):
                    df = pd.DataFrame.from_dict(value, orient="index")
                    try:
                        idx = pd.to_datetime(df.index, errors="coerce")
                        if idx.notna().mean() > 0.6:
                            df.index = idx
                            df = df.sort_index()
                    except Exception:
                        pass
                    for col in df.columns:
                        try:
                            num = pd.to_numeric(df[col], errors="coerce")
                            if num.notna().mean() > 0.6:
                                df[col] = num
                        except Exception:
                            pass
                    return df
        scalars = {k: v for k, v in payload.items() if isinstance(v, (str, int, float, bool)) or v is None}
        if scalars:
            return pd.DataFrame([scalars])
    return None

def build_request(function_name: str, params: dict[str, str], api_key: str) -> tuple[str, list[tuple[str, str]]]:
    clean = [(k, str(v)) for k, v in params.items() if str(v).strip()]
    if function_name == "ANALYTICS_FIXED_WINDOW":
        base = ANALYTICS_BASE_URL
        payload = [(k.upper(), v) for k, v in clean if k != "apikey"]
        payload.append(("apikey", api_key))
        return base, payload
    if function_name == "ANALYTICS_SLIDING_WINDOW":
        base = ANALYTICS_BASE_URL
        payload = [(k.upper(), v) for k, v in clean if k != "apikey"]
        payload.append(("apikey", api_key))
        return base, payload
    base = QUERY_BASE_URL
    payload = [("function", function_name)] + [(k, v) for k, v in clean if k != "apikey"] + [("apikey", api_key)]
    return base, payload

def make_request(function_name: str, params: dict[str, str], api_key: str):
    base, payload = build_request(function_name, params, api_key)
    resp = requests.get(base, params=payload, timeout=45)
    resp.raise_for_status()
    if params.get("datatype") == "csv" or "csv" in resp.headers.get("content-type", "").lower():
        df = pd.read_csv(StringIO(resp.text))
        return resp.url, df, resp.text
    data = resp.json()
    if isinstance(data, dict):
        for key in ("Error Message", "Information", "Note"):
            if data.get(key):
                raise RuntimeError(str(data[key]))
    return resp.url, data, json.dumps(data, indent=2)

st.set_page_config(page_title="Alpha Vantage Explorer", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1rem;padding-bottom:2rem;}
.hero{padding:1.3rem 1.4rem;border-radius:20px;background:linear-gradient(135deg,#0f172a 0%,#1e293b 40%,#2563eb 100%);color:white;box-shadow:0 18px 48px rgba(15,23,42,.18);margin-bottom:1rem}
.card{padding:1rem;border-radius:18px;border:1px solid rgba(148,163,184,.18);background:rgba(255,255,255,.85);box-shadow:0 10px 25px rgba(15,23,42,.05)}
.small{color:#64748b;font-size:.92rem}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1 style="margin:0;">Alpha Vantage Explorer</h1>
  <p style="margin:.35rem 0 0 0;">Hosted-ready Streamlit app for querying Alpha Vantage across market data, fundamentals, macro data, commodities, forex, crypto, technical indicators, and analytics endpoints from one clean interface.</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("Alpha Vantage API key", value=os.getenv("ALPHAVANTAGE_API_KEY", ""), type="password")
    family = st.selectbox("API family", list(FUNCTIONS.keys()))
    function_name = st.selectbox("Function", FUNCTIONS[family])
    st.caption("You can also override any parameter in the JSON box below for edge cases and less common endpoints.")

left, right = st.columns([1.2, 1])

with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Request builder")
    params = {}
    c1, c2 = st.columns(2)
    with c1:
        params["symbol"] = st.text_input("symbol", PRESETS["symbol"])
        params["interval"] = st.selectbox("interval", ["1min","5min","15min","30min","60min","daily","weekly","monthly"], index=1)
        params["outputsize"] = st.selectbox("outputsize", ["compact", "full"], index=0)
        params["datatype"] = st.selectbox("datatype", ["json", "csv"], index=0)
        params["series_type"] = st.selectbox("series_type", ["close", "open", "high", "low"], index=0)
        params["time_period"] = st.text_input("time_period", PRESETS["time_period"])
    with c2:
        params["from_symbol"] = st.text_input("from_symbol", PRESETS["from_symbol"])
        params["to_symbol"] = st.text_input("to_symbol", PRESETS["to_symbol"])
        params["from_currency"] = st.text_input("from_currency", PRESETS["from_currency"])
        params["to_currency"] = st.text_input("to_currency", PRESETS["to_currency"])
        params["market"] = st.text_input("market", PRESETS["market"])
        params["horizon"] = st.text_input("horizon", PRESETS["horizon"])

    raw_json = st.text_area(
        "Advanced JSON overrides",
        value=json.dumps({
            "month": "",
            "adjusted": "true",
            "extended_hours": "true",
            "entitlement": "realtime",
            "range": "2024-01-01",
            "calculations": "MEAN,STDDEV,CORRELATION",
            "window_size": "10",
            "ohlc": "close",
            "symbols": "IBM,MSFT"
        }, indent=2),
        height=220,
    )
    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("What this covers")
    st.markdown("""
- Stocks and time series  
- Options and Alpha Intelligence  
- Fundamentals and calendars  
- Forex and crypto  
- Macro and commodities  
- Technical indicators  
- Analytics endpoints  
""")
    st.markdown('<div class="small">For uncommon or premium endpoints, put the exact parameters in the override box and the app will send them through directly.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

try:
    overrides = json.loads(raw_json) if raw_json.strip() else {}
    if not isinstance(overrides, dict):
        overrides = {}
except Exception:
    overrides = {}
    st.warning("Advanced JSON overrides could not be parsed. Using the form fields only.")

merged = {**params, **overrides}
merged = {k: v for k, v in merged.items() if str(v).strip()}

c1, c2 = st.columns([1, 2])
with c1:
    run = st.button("Run request", type="primary", use_container_width=True)
with c2:
    if api_key:
        base, payload = build_request(function_name, merged, api_key)
        st.code(f"{base}?{urlencode(payload, doseq=True)}", language="text")

if run:
    if not api_key:
        st.error("Enter your Alpha Vantage API key in the sidebar.")
    else:
        try:
            url, payload, raw = make_request(function_name, merged, api_key)
            st.success("Request completed.")
            st.caption(url)

            tabs = st.tabs(["Table", "Chart", "Raw payload", "Downloads"])
            with tabs[0]:
                if isinstance(payload, pd.DataFrame):
                    df = payload
                else:
                    df = flatten_json(payload)
                if df is not None and not df.empty:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.json(payload)

            with tabs[1]:
                if isinstance(payload, pd.DataFrame):
                    df = payload
                else:
                    df = flatten_json(payload)
                if df is not None and not df.empty:
                    numeric_cols = list(df.select_dtypes(include="number").columns)
                    if numeric_cols:
                        default = numeric_cols[: min(3, len(numeric_cols))]
                        selected = st.multiselect("Metrics", numeric_cols, default=default)
                        chart_df = df.copy()
                        if not isinstance(chart_df.index, pd.DatetimeIndex):
                            for col in chart_df.columns:
                                try:
                                    dt = pd.to_datetime(chart_df[col], errors="coerce")
                                    if dt.notna().mean() > 0.6:
                                        chart_df = chart_df.set_index(col)
                                        break
                                except Exception:
                                    pass
                        if selected:
                            st.line_chart(chart_df[selected])
                        else:
                            st.info("Select at least one numeric metric.")
                    else:
                        st.info("No numeric columns were detected for charting.")
                else:
                    st.info("No table-like data was detected for charting.")

            with tabs[2]:
                if isinstance(payload, pd.DataFrame):
                    st.code(payload.to_json(orient="records", indent=2), language="json")
                else:
                    st.code(raw, language="json")

            with tabs[3]:
                if isinstance(payload, pd.DataFrame):
                    csv_bytes = payload.to_csv(index=False).encode("utf-8")
                    st.download_button("Download CSV", csv_bytes, "alphavantage_data.csv", "text/csv")
                    st.download_button("Download JSON", payload.to_json(orient="records", indent=2), "alphavantage_data.json", "application/json")
                else:
                    df = flatten_json(payload)
                    if df is not None and not df.empty:
                        st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"), "alphavantage_data.csv", "text/csv")
                    st.download_button("Download JSON", raw, "alphavantage_data.json", "application/json")

        except Exception as exc:
            st.error(str(exc))
