# Alpaca Trading Console

Hosted-ready Streamlit application for Alpaca paper or live trading accounts.

## What this app does

- Connects with Alpaca Trading API using `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`
- Defaults to **paper trading**
- Shows:
  - account equity, cash, buying power, and market clock
  - portfolio history chart
  - stock market data with snapshot, latest quote, latest trade, historical bars, and news
  - open/all orders
  - order entry and cancel controls
  - open positions
  - watchlists
  - account activity and market calendar

## Environment variables

Use these in Render or locally in a `.env` file:

```text
ALPACA_API_KEY_ID=your_key_id
ALPACA_API_SECRET_KEY=your_secret_key
```

## Local run

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Render

1. Create a new **Web Service**
2. Connect the repo `scforsberg/Stock-Market-App`
3. Let Render use the included `Dockerfile`
4. Add environment variables:
   - `ALPACA_API_KEY_ID`
   - `ALPACA_API_SECRET_KEY`
5. Deploy

## Safety note

Leave the app in **Paper** mode until you have fully validated your workflow. Live mode points to `https://api.alpaca.markets` and can send real orders.
