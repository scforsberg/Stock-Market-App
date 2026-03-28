from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

TRADING_LIVE = "https://api.alpaca.markets"
TRADING_PAPER = "https://paper-api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"


@dataclass
class AlpacaConfig:
    key_id: str
    secret_key: str
    paper: bool = True

    @property
    def trading_base(self) -> str:
        return TRADING_PAPER if self.paper else TRADING_LIVE

    @property
    def headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
            "accept": "application/json",
        }


class AlpacaClient:
    def __init__(self, config: AlpacaConfig) -> None:
        self.config = config

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        cleaned_params = {k: v for k, v in (params or {}).items() if v not in ("", None, [])}
        cleaned_json = {k: v for k, v in (json or {}).items() if v not in ("", None, [])}

        response = requests.request(
            method=method,
            url=url,
            headers=self.config.headers,
            params=cleaned_params or None,
            json=cleaned_json or None,
            timeout=45,
        )
        if response.status_code == 204:
            return {"status": "ok", "status_code": 204}
        try:
            payload = response.json()
        except Exception:
            payload = {"raw_text": response.text}

        if not response.ok:
            raise RuntimeError(f"{response.status_code}: {payload}")
        return payload

    def trading_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", f"{self.config.trading_base}{path}", params=params)

    def trading_post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", f"{self.config.trading_base}{path}", json=payload)

    def trading_delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("DELETE", f"{self.config.trading_base}{path}", params=params)

    def data_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", f"{DATA_BASE}{path}", params=params)


def to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df
    for col in df.columns:
        if df[col].isna().all():
            continue
        first = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
        if isinstance(first, (dict, list)):
            continue
        maybe_dt = pd.to_datetime(df[col], errors="coerce", utc=True)
        if maybe_dt.notna().mean() > 0.8:
            df[col] = maybe_dt
            continue
        maybe_num = pd.to_numeric(df[col], errors="coerce")
        if maybe_num.notna().mean() > 0.8:
            df[col] = maybe_num
    return df


def bars_to_df(payload: dict[str, Any], symbol: str) -> pd.DataFrame:
    bars = payload.get("bars", [])
    if isinstance(bars, dict):
        bars = bars.get(symbol, [])
    df = to_dataframe(bars)
    if "t" in df.columns:
        df["t"] = pd.to_datetime(df["t"], utc=True)
        df = df.sort_values("t")
    return df


def portfolio_to_df(payload: dict[str, Any]) -> pd.DataFrame:
    timestamps = payload.get("timestamp", [])
    if not timestamps:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(payload.get("timestamp", []), unit="s", utc=True),
            "equity": payload.get("equity", []),
            "profit_loss": payload.get("profit_loss", []),
            "profit_loss_pct": payload.get("profit_loss_pct", []),
        }
    )


def metric_card(label: str, value: Any, delta: Any | None = None) -> None:
    st.metric(label=label, value=value, delta=delta)


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    latest_trade = snapshot.get("latestTrade", {})
    latest_quote = snapshot.get("latestQuote", {})
    minute_bar = snapshot.get("minuteBar", {})
    daily_bar = snapshot.get("dailyBar", {})
    prev_bar = snapshot.get("prevDailyBar", {})
    return {
        "trade_price": latest_trade.get("p"),
        "trade_size": latest_trade.get("s"),
        "bid_price": latest_quote.get("bp"),
        "ask_price": latest_quote.get("ap"),
        "minute_close": minute_bar.get("c"),
        "daily_close": daily_bar.get("c"),
        "prev_close": prev_bar.get("c"),
        "daily_volume": daily_bar.get("v"),
    }


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container{padding-top:1rem;padding-bottom:2rem;max-width:1500px;}
        .hero{
            padding:1.35rem 1.4rem;border-radius:22px;
            background:linear-gradient(135deg,#0b1220 0%,#13233d 45%,#1d4ed8 100%);
            color:white;box-shadow:0 18px 48px rgba(15,23,42,.22);margin-bottom:1rem
        }
        .warning{
            padding:.85rem 1rem;border-radius:16px;background:#fff7ed;border:1px solid #fdba74;color:#9a3412
        }
        .ok{
            padding:.85rem 1rem;border-radius:16px;background:#ecfeff;border:1px solid #67e8f9;color:#155e75
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar() -> tuple[AlpacaClient | None, bool]:
    with st.sidebar:
        st.header("Connection")
        mode = st.radio("Trading mode", ["Paper", "Live"], horizontal=True, index=0)
        key_id = st.text_input("Alpaca API Key ID", value=os.getenv("ALPACA_API_KEY_ID", ""), type="password")
        secret_key = st.text_input("Alpaca Secret Key", value=os.getenv("ALPACA_API_SECRET_KEY", ""), type="password")
        st.caption("Market data uses the same key/secret headers. Paper mode is the safer default.")
        can_trade = st.checkbox("Enable order entry controls", value=False)
        if mode == "Live":
            st.markdown('<div class="warning">Live mode can route real orders. Keep this off until you have confirmed your credentials and workflow.</div>', unsafe_allow_html=True)

    if not key_id or not secret_key:
        return None, can_trade

    config = AlpacaConfig(key_id=key_id, secret_key=secret_key, paper=(mode == "Paper"))
    return AlpacaClient(config), can_trade


def dashboard_tab(client: AlpacaClient) -> None:
    st.subheader("Account dashboard")
    left, right = st.columns([1.2, 1])
    account = client.trading_get("/v2/account")
    clock = client.trading_get("/v2/clock")
    portfolio = client.trading_get("/v2/account/portfolio/history", params={"period": "1M", "timeframe": "1D"})

    with left:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric_card("Equity", account.get("equity"))
        with c2:
            metric_card("Buying Power", account.get("buying_power"))
        with c3:
            metric_card("Cash", account.get("cash"))
        with c4:
            metric_card("PDT Flag", str(account.get("pattern_day_trader")))

        status_label = "Open" if clock.get("is_open") else "Closed"
        st.markdown(
            f'<div class="ok">Market status: <strong>{status_label}</strong> · Next open: {clock.get("next_open")} · Next close: {clock.get("next_close")}</div>',
            unsafe_allow_html=True,
        )

        pdf = portfolio_to_df(portfolio)
        if not pdf.empty:
            fig = px.line(pdf, x="timestamp", y="equity", title="Portfolio equity")
            fig.update_layout(height=360, margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(pdf, use_container_width=True, height=220)
        else:
            st.info("No portfolio history returned for the selected account.")
    with right:
        st.markdown("#### Account details")
        details = {
            "account_number": account.get("account_number"),
            "status": account.get("status"),
            "currency": account.get("currency"),
            "multiplier": account.get("multiplier"),
            "daytrade_count": account.get("daytrade_count"),
            "trading_blocked": account.get("trading_blocked"),
            "transfers_blocked": account.get("transfers_blocked"),
            "account_blocked": account.get("account_blocked"),
        }
        st.json(details)
        st.markdown("#### Market clock")
        st.json(clock)


def market_data_tab(client: AlpacaClient) -> None:
    st.subheader("Market data")
    symbol = st.text_input("Symbol", value="AAPL").upper().strip() or "AAPL"
    c1, c2, c3 = st.columns(3)
    with c1:
        timeframe = st.selectbox("Bar timeframe", ["1Min", "5Min", "15Min", "1Hour", "1Day"], index=4)
    with c2:
        start_date = st.date_input("Start date", value=date.today() - timedelta(days=30))
    with c3:
        end_date = st.date_input("End date", value=date.today())

    snapshot = client.data_get(f"/v2/stocks/{symbol}/snapshot")
    latest_quote = client.data_get(f"/v2/stocks/{symbol}/quotes/latest")
    latest_trade = client.data_get(f"/v2/stocks/{symbol}/trades/latest")
    bars = client.data_get(
        f"/v2/stocks/{symbol}/bars",
        params={
            "timeframe": timeframe,
            "start": f"{start_date.isoformat()}T00:00:00Z",
            "end": f"{end_date.isoformat()}T23:59:59Z",
            "limit": 500,
            "adjustment": "raw",
            "feed": "iex",
        },
    )
    news = client.data_get("/v1beta1/news", params={"symbols": symbol, "limit": 10})

    snap = normalize_snapshot(snapshot)
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        metric_card("Last Trade", snap.get("trade_price"))
    with m2:
        metric_card("Bid", snap.get("bid_price"))
    with m3:
        metric_card("Ask", snap.get("ask_price"))
    with m4:
        prev_close = snap.get("prev_close")
        daily_close = snap.get("daily_close")
        delta = None
        if daily_close is not None and prev_close not in (None, 0):
            delta = f"{((daily_close - prev_close) / prev_close) * 100:.2f}%"
        metric_card("Daily Close", daily_close, delta)

    bars_df = bars_to_df(bars, symbol)
    if not bars_df.empty:
        fig = px.line(bars_df, x="t", y="c", title=f"{symbol} close price")
        fig.update_layout(height=380, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(bars_df, use_container_width=True, height=260)
    else:
        st.info("No bar data returned for that symbol and date range.")

    q1, q2 = st.columns(2)
    with q1:
        st.markdown("#### Latest quote")
        st.json(latest_quote)
    with q2:
        st.markdown("#### Latest trade")
        st.json(latest_trade)

    st.markdown("#### News")
    news_items = news.get("news", []) if isinstance(news, dict) else news
    if news_items:
        news_df = to_dataframe(news_items)
        show_cols = [c for c in ["headline", "author", "created_at", "symbols", "summary"] if c in news_df.columns]
        st.dataframe(news_df[show_cols], use_container_width=True, height=300)
    else:
        st.info("No recent news returned for this symbol.")


def orders_tab(client: AlpacaClient, can_trade: bool) -> None:
    st.subheader("Orders")
    list_mode = st.radio("Order list", ["Open", "All"], horizontal=True)
    status = "open" if list_mode == "Open" else "all"
    orders = client.trading_get("/v2/orders", params={"status": status, "limit": 100, "direction": "desc"})
    orders_df = to_dataframe(orders if isinstance(orders, list) else [])
    if not orders_df.empty:
        display_cols = [c for c in ["submitted_at", "symbol", "side", "type", "qty", "notional", "limit_price", "status", "id"] if c in orders_df.columns]
        st.dataframe(orders_df[display_cols], use_container_width=True, height=280)
    else:
        st.info("No orders returned.")

    st.markdown("#### Place order")
    if not can_trade:
        st.warning("Enable order entry controls in the sidebar before sending orders.")
        return

    with st.form("place_order"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            symbol = st.text_input("Symbol", value="AAPL").upper()
            side = st.selectbox("Side", ["buy", "sell"])
        with c2:
            order_type = st.selectbox("Type", ["market", "limit", "stop", "stop_limit"])
            tif = st.selectbox("Time in force", ["day", "gtc", "ioc", "fok"])
        with c3:
            qty = st.text_input("Qty", value="1")
            notional = st.text_input("Notional (optional)", value="")
        with c4:
            limit_price = st.text_input("Limit price", value="")
            stop_price = st.text_input("Stop price", value="")
        extended_hours = st.checkbox("Extended hours eligible", value=False)
        submitted = st.form_submit_button("Submit order", type="primary", use_container_width=True)

    if submitted:
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "time_in_force": tif,
            "extended_hours": extended_hours,
        }
        if qty.strip():
            payload["qty"] = qty.strip()
        if notional.strip():
            payload["notional"] = notional.strip()
        if limit_price.strip():
            payload["limit_price"] = limit_price.strip()
        if stop_price.strip():
            payload["stop_price"] = stop_price.strip()

        response = client.trading_post("/v2/orders", payload)
        st.success("Order submitted.")
        st.json(response)

    st.markdown("#### Cancel order")
    cancel_order_id = st.text_input("Order ID to cancel")
    if st.button("Cancel selected order", use_container_width=True) and cancel_order_id.strip():
        response = client.trading_delete(f"/v2/orders/{cancel_order_id.strip()}")
        st.success("Cancel request accepted.")
        st.json(response)

    if st.button("Cancel all open orders", use_container_width=True):
        response = client.trading_delete("/v2/orders")
        st.success("Cancel-all request submitted.")
        st.json(response)


def positions_tab(client: AlpacaClient) -> None:
    st.subheader("Positions")
    positions = client.trading_get("/v2/positions")
    positions_df = to_dataframe(positions if isinstance(positions, list) else [])
    if positions_df.empty:
        st.info("No open positions.")
        return
    display_cols = [c for c in ["symbol", "qty", "avg_entry_price", "market_value", "cost_basis", "unrealized_pl", "unrealized_plpc", "side"] if c in positions_df.columns]
    st.dataframe(positions_df[display_cols], use_container_width=True, height=320)
    if "market_value" in positions_df.columns:
        chart_df = positions_df.copy()
        chart_df["market_value"] = pd.to_numeric(chart_df["market_value"], errors="coerce")
        fig = px.bar(chart_df, x="symbol", y="market_value", title="Position market value")
        fig.update_layout(height=360, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)


def watchlists_tab(client: AlpacaClient, can_trade: bool) -> None:
    st.subheader("Watchlists")
    watchlists = client.trading_get("/v2/watchlists")
    watchlists_df = to_dataframe(watchlists if isinstance(watchlists, list) else [])
    if not watchlists_df.empty:
        st.dataframe(watchlists_df[[c for c in ["name", "id", "created_at", "updated_at"] if c in watchlists_df.columns]], use_container_width=True, height=220)
    else:
        st.info("No watchlists yet.")

    if can_trade:
        st.markdown("#### Create watchlist")
        with st.form("create_watchlist"):
            name = st.text_input("Watchlist name", value="Core Holdings")
            symbols_raw = st.text_input("Symbols (comma separated)", value="AAPL,MSFT,NVDA")
            create = st.form_submit_button("Create watchlist", type="primary", use_container_width=True)
        if create and name.strip():
            symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
            response = client.trading_post("/v2/watchlists", {"name": name.strip(), "symbols": symbols})
            st.success("Watchlist created.")
            st.json(response)
    else:
        st.caption("Enable order entry controls to create watchlists from the app.")


def activity_tab(client: AlpacaClient) -> None:
    st.subheader("Activity and market schedule")
    c1, c2 = st.columns([1.15, 1])
    with c1:
        activities = client.trading_get("/v2/account/activities", params={"page_size": 100})
        activities_df = to_dataframe(activities if isinstance(activities, list) else [])
        if not activities_df.empty:
            cols = [c for c in ["transaction_time", "activity_type", "symbol", "qty", "price", "net_amount", "id"] if c in activities_df.columns]
            st.dataframe(activities_df[cols], use_container_width=True, height=320)
        else:
            st.info("No recent account activity returned.")
    with c2:
        start = date.today()
        end = date.today() + timedelta(days=10)
        calendar = client.trading_get("/v2/calendar", params={"start": start.isoformat(), "end": end.isoformat()})
        calendar_df = to_dataframe(calendar if isinstance(calendar, list) else [])
        if not calendar_df.empty:
            st.dataframe(calendar_df, use_container_width=True, height=320)
        else:
            st.info("No market calendar rows returned.")


def landing() -> None:
    st.markdown(
        """
        <div class="hero">
            <h1 style="margin:0;">Alpaca Trading Console</h1>
            <p style="margin:.35rem 0 0 0;">
                Hosted-ready Streamlit app for paper or live Alpaca accounts with account overview,
                market data, orders, positions, watchlists, portfolio history, and activity in one interface.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Alpaca Trading Console", page_icon="📈", layout="wide")
    inject_css()
    landing()
    client, can_trade = sidebar()

    st.caption("Start in paper mode. The same trading API schema works across paper and live; only the base domain and credentials change.")

    if client is None:
        st.info("Enter your Alpaca key ID and secret key in the sidebar to connect.")
        st.stop()

    try:
        tabs = st.tabs(["Dashboard", "Market Data", "Orders", "Positions", "Watchlists", "Activity"])
        with tabs[0]:
            dashboard_tab(client)
        with tabs[1]:
            market_data_tab(client)
        with tabs[2]:
            orders_tab(client, can_trade)
        with tabs[3]:
            positions_tab(client)
        with tabs[4]:
            watchlists_tab(client, can_trade)
        with tabs[5]:
            activity_tab(client)
    except Exception as exc:
        st.error(str(exc))
        st.stop()


if __name__ == "__main__":
    main()
