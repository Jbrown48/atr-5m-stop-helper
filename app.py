import datetime as dt
import math

import pandas as pd
import yfinance as yf
from flask import Flask, render_template, request

app = Flask(__name__)


def download_data(ticker: str,
                  tf: str = "5m",
                  days_daily: int = 30,
                  days_intraday: int = 5):
    """
    Pull recent daily data (for ATR) and intraday data (for context).
    tf: "1m" or "5m" intraday timeframe.
    """
    end = dt.datetime.now()
    start_daily = end - dt.timedelta(days=days_daily)
    start_intra = end - dt.timedelta(days=days_intraday)

    daily = yf.download(
        ticker, start=start_daily, end=end, interval="1d", auto_adjust=False
    )
    intra = yf.download(
        ticker, start=start_intra, end=end, interval=tf, auto_adjust=False
    )

    if intra.empty or daily.empty:
        return daily, intra

    # yfinance intraday index is usually tz-aware (UTC); guard tz_localize.
    if intra.index.tz is None:
        intra = intra.tz_localize("UTC")
    intra = intra.tz_convert("US/Eastern")

    # Keep only regular trading hours
    intra = intra.between_time("09:30", "16:00")

    return daily, intra


def compute_atr(daily: pd.DataFrame, period: int = 14) -> float:
    """
    Compute Wilder-style ATR on daily OHLC.
    """
    high = daily["High"]
    low = daily["Low"]
    close = daily["Close"]

    tr0 = high - low
    tr1 = (high - close.shift(1)).abs()
    tr2 = (low - close.shift(1)).abs()
    tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    return float(atr.iloc[-1])


def intraday_tod_factor(timestamp: pd.Timestamp) -> float:
    """
    Simple U-shaped time-of-day factor (US/Eastern).
    """
    t = timestamp.time()
    if t < dt.time(10, 0):
        return 1.4   # high vol open
    elif t < dt.time(11, 0):
        return 1.15
    elif t < dt.time(13, 0):
        return 0.85  # lunch lull
    elif t < dt.time(14, 30):
        return 1.0
    else:
        return 1.3   # power hour


def atr_intraday_from_daily(atr_daily: float, ts: pd.Timestamp, tf: str) -> float:
    """
    Convert daily ATR to intraday ATR for a given timeframe (1m or 5m),
    adjusted for time-of-day.
    """
    minutes = 1 if tf == "1m" else 5
    baseline_factor = math.sqrt(minutes / 390)  # RTH 390 minutes
    baseline_tf = atr_daily * baseline_factor
    return baseline_tf * intraday_tod_factor(ts)


def compute_example_stops(ticker: str,
                          tf: str = "5m",
                          k_atr: float = 0.7,
                          dollar_risk: float | None = None):
    """
    Use the latest completed intraday bar as an example and compute:
    - daily ATR(14)
    - time-of-day adjusted intraday ATR (1m or 5m)
    - example long/short stops based on last bar low/high
    - optional position size from dollar_risk
    """
    daily, intra = download_data(ticker, tf=tf)
    if daily.empty or intra.empty:
        return None

    atr_daily = compute_atr(daily, period=14)

    # Use the most recent completed bar as the example
    if len(intra) < 2:
        return None

    last_bar = intra.iloc[-2]
    ts = last_bar.name
    entry = float(last_bar["Close"])
    swing_low = float(last_bar["Low"])
    swing_high = float(last_bar["High"])

    atr_tf = atr_intraday_from_daily(atr_daily, ts, tf)

    # Long: stop below swing low
    stop_long = swing_low - k_atr * atr_tf
    dist_long = entry - stop_long

    # Short: stop above swing high
    stop_short = swing_high + k_atr * atr_tf
    dist_short = stop_short - entry

    shares_long = shares_short = None
    if dollar_risk is not None and dollar_risk > 0:
        if dist_long > 0:
            shares_long = dollar_risk / dist_long
        if dist_short > 0:
            shares_short = dollar_risk / dist_short

    return {
        "ticker": ticker.upper(),
        "timestamp": ts,
        "entry_price": entry,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "atr_daily": atr_daily,
        "atr_tf": atr_tf,
        "tf": tf,
        "k_atr": k_atr,
        "stop_long": stop_long,
        "dist_long": dist_long,
        "stop_short": stop_short,
        "dist_short": dist_short,
        "dollar_risk": dollar_risk,
        "shares_long": shares_long,
        "shares_short": shares_short,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None
    # Defaults shown in the UI
    current_tf = "5m"
    current_dollar_risk = ""

    if request.method == "POST":
        ticker = request.form.get("ticker", "").strip()
        current_tf = request.form.get("timeframe", "5m")
        k_atr_str = request.form.get("k_atr", "0.7").strip()
        risk_str = request.form.get("dollar_risk", "").strip()
        current_dollar_risk = risk_str

        if ticker:
            try:
                k_atr = float(k_atr_str) if k_atr_str else 0.7
            except ValueError:
                k_atr = 0.7

            dollar_risk = None
            if risk_str:
                try:
                    dollar_risk = float(risk_str)
                except ValueError:
                    dollar_risk = None

            try:
                result = compute_example_stops(
                    ticker, tf=current_tf, k_atr=k_atr, dollar_risk=dollar_risk
                )
                if result is None:
                    error = "Could not compute ATR / intraday data for this ticker."
            except Exception as e:
                error = f"Error: {e}"
        else:
            error = "Please enter a ticker symbol."

    return render_template(
        "index.html",
        result=result,
        error=error,
        current_tf=current_tf,
        current_dollar_risk=current_dollar_risk,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
