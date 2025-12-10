import datetime as dt
import math

import pandas as pd
import yfinance as yf
from flask import Flask, render_template, request

app = Flask(__name__)


def download_data(ticker: str, days_daily: int = 30, days_intraday: int = 5):
    """
    Pull recent daily data (for ATR) and 5-minute intraday data (for context),
    then convert intraday timestamps to US/Eastern and filter RTH.
    """
    end = dt.datetime.now()
    start_daily = end - dt.timedelta(days=days_daily)
    start_intra = end - dt.timedelta(days=days_intraday)

    daily = yf.download(
        ticker, start=start_daily, end=end, interval="1d", auto_adjust=False
    )
    intra = yf.download(
        ticker, start=start_intra, end=end, interval="5m", auto_adjust=False
    )

    if intra.empty or daily.empty:
        return daily, intra

    # yfinance intraday index is often already tz-aware (UTC).
    # If tz-naive, localize to UTC; then convert to US/Eastern.
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
    Simple U-shaped time-of-day factor for 5m bars (US/Eastern).
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


def atr_5m_from_daily(atr_daily: float, ts: pd.Timestamp) -> float:
    """
    Convert daily ATR to 5-minute ATR adjusted for time-of-day.
    """
    baseline_factor = math.sqrt(5 / 390)  # 5 min of 390-min RTH
    baseline_5m = atr_daily * baseline_factor
    return baseline_5m * intraday_tod_factor(ts)


def compute_example_stops(ticker: str, k_atr: float = 0.7):
    """
    Use the latest completed 5m bar as an example and compute:
    - daily ATR(14)
    - time-of-day adjusted 5m ATR
    - example long/short stops based on last bar low/high
    """
    daily, intra = download_data(ticker)
    if daily.empty or intra.empty:
        return None

    atr_daily = compute_atr(daily, period=14)

    # Use the most recent completed 5m bar as the example
    if len(intra) < 2:
        return None

    last_bar = intra.iloc[-2]
    ts = last_bar.name
    entry = float(last_bar["Close"])
    swing_low = float(last_bar["Low"])
    swing_high = float(last_bar["High"])

    atr_5m = atr_5m_from_daily(atr_daily, ts)

    # Long: stop below swing low
    stop_long = swing_low - k_atr * atr_5m
    dist_long = entry - stop_long

    # Short: stop above swing high
    stop_short = swing_high + k_atr * atr_5m
    dist_short = stop_short - entry

    return {
        "ticker": ticker.upper(),
        "timestamp": ts,
        "entry_price": entry,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "atr_daily": atr_daily,
        "atr_5m": atr_5m,
        "k_atr": k_atr,
        "stop_long": stop_long,
        "dist_long": dist_long,
        "stop_short": stop_short,
        "dist_short": dist_short,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None

    if request.method == "POST":
        ticker = request.form.get("ticker", "").strip()
        if ticker:
            try:
                result = compute_example_stops(ticker)
                if result is None:
                    error = "Could not compute ATR / intraday data for this ticker."
            except Exception as e:
                error = f"Error: {e}"
        else:
            error = "Please enter a ticker symbol."

    return render_template("index.html", result=result, error=error)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)    high = daily["High"]
    low = daily["Low"]
    close = daily["Close"]

    tr0 = high - low
    tr1 = (high - close.shift(1)).abs()
    tr2 = (low - close.shift(1)).abs()
    tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    return float(atr.iloc[-1])


def intraday_tod_factor(timestamp: pd.Timestamp) -> float:
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


def atr_5m_from_daily(atr_daily: float, ts: pd.Timestamp) -> float:
    baseline_factor = math.sqrt(5 / 390)  # 5 min of 390-min RTH
    baseline_5m = atr_daily * baseline_factor
    return baseline_5m * intraday_tod_factor(ts)


def compute_example_stops(ticker: str, k_atr: float = 0.7):
    daily, intra = download_data(ticker)
    if daily.empty or intra.empty:
        return None

    atr_daily = compute_atr(daily, period=14)

    # Use the most recent completed 5m bar as the example
    if len(intra) < 2:
        return None

    last_bar = intra.iloc[-2]
    ts = last_bar.name
    entry = float(last_bar["Close"])
    swing_low = float(last_bar["Low"])
    swing_high = float(last_bar["High"])

    atr_5m = atr_5m_from_daily(atr_daily, ts)

    # Long: stop below swing low
    stop_long = swing_low - k_atr * atr_5m
    dist_long = entry - stop_long

    # Short: stop above swing high
    stop_short = swing_high + k_atr * atr_5m
    dist_short = stop_short - entry

    return {
        "ticker": ticker.upper(),
        "timestamp": ts,
        "entry_price": entry,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "atr_daily": atr_daily,
        "atr_5m": atr_5m,
        "k_atr": k_atr,
        "stop_long": stop_long,
        "dist_long": dist_long,
        "stop_short": stop_short,
        "dist_short": dist_short,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None

    if request.method == "POST":
        ticker = request.form.get("ticker", "").strip()
        if ticker:
            try:
                result = compute_example_stops(ticker)
                if result is None:
                    error = "Could not compute ATR / intraday data for this ticker."
            except Exception as e:
                error = f"Error: {e}"
        else:
            error = "Please enter a ticker symbol."

    return render_template("index.html", result=result, error=error)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
