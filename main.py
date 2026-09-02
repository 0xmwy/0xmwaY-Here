import streamlit as st
import requests
import pandas as pd
import numpy as np
import sqlite3
import time
from datetime import datetime, timedelta

import streamlit.components.v1 as components


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="0xmwY Kraken",
    page_icon="📊",
    layout="wide"
)

OKX_BASE = "https://www.okx.com"

DB_FILE = "screening_history.db"

TIMEFRAMES = {
    "15M": "15m",
    "30M": "30m",
    "1H": "1H"
}

# Token dan jumlah screening
TOKENS = {
    "KRAKEN-001": 100,
    "KRAKEN-002": 50,
    "KRAKEN-003": 25,
}


# ============================================================
# DATABASE
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS screening_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            timestamp_unix INTEGER NOT NULL,
            pair TEXT NOT NULL,
            movement REAL,
            volatility REAL,
            volume REAL,
            outlook TEXT,
            entry_low REAL,
            entry_high REAL,
            take_profit REAL
        )
    """)

    conn.commit()
    conn.close()


def cleanup_old_history():
    cutoff = int(time.time()) - (24 * 60 * 60)

    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        "DELETE FROM screening_history WHERE timestamp_unix < ?",
        (cutoff,)
    )

    conn.commit()
    conn.close()


def save_history(result):
    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        INSERT INTO screening_history (
            timestamp,
            timestamp_unix,
            pair,
            movement,
            volatility,
            volume,
            outlook,
            entry_low,
            entry_high,
            take_profit
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result["timestamp"],
        result["timestamp_unix"],
        result["pair"],
        result["movement"],
        result["volatility"],
        result["volume"],
        result["outlook"],
        result["entry_low"],
        result["entry_high"],
        result["take_profit"]
    ))

    conn.commit()
    conn.close()


def get_history():
    cleanup_old_history()

    conn = sqlite3.connect(DB_FILE)

    df = pd.read_sql_query("""
        SELECT
            timestamp,
            pair,
            movement,
            volatility,
            volume,
            outlook,
            entry_low,
            entry_high,
            take_profit
        FROM screening_history
        ORDER BY timestamp_unix DESC
    """, conn)

    conn.close()

    return df


# ============================================================
# API REQUEST
# ============================================================

def okx_get(endpoint, params=None):
    try:
        response = requests.get(
            OKX_BASE + endpoint,
            params=params,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        if data.get("code") != "0":
            return None

        return data.get("data")

    except Exception:
        return None


# ============================================================
# GET ALL USDT SWAPS
# ============================================================

@st.cache_data(ttl=300)
def get_symbols():

    data = okx_get(
        "/api/v5/public/instruments",
        {
            "instType": "SWAP"
        }
    )

    if not data:
        return []

    symbols = []

    for item in data:

        if item.get("state") != "live":
            continue

        if item.get("settleCcy") != "USDT":
            continue

        inst_id = item.get("instId")

        if not inst_id:
            continue

        symbols.append(inst_id)

    return symbols


# ============================================================
# GET TICKERS
# ============================================================

@st.cache_data(ttl=20)
def get_tickers():

    data = okx_get(
        "/api/v5/market/tickers",
        {
            "instType": "SWAP"
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for item in data:

        inst_id = item.get("instId", "")

        if not inst_id.endswith("-USDT-SWAP"):
            continue

        try:
            last = float(item.get("last", 0))
            open24 = float(item.get("open24h", 0))
            high24 = float(item.get("high24h", 0))
            low24 = float(item.get("low24h", 0))
            volume = float(item.get("vol24h", 0))

            if last <= 0 or open24 <= 0:
                continue

            change = ((last - open24) / open24) * 100

            volatility = ((high24 - low24) / open24) * 100

            rows.append({
                "instId": inst_id,
                "pair": inst_id.replace("-SWAP", ""),
                "price": last,
                "movement": change,
                "abs_movement": abs(change),
                "high24": high24,
                "low24": low24,
                "volatility": volatility,
                "volume": volume
            })

        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    return df


# ============================================================
# TOP MOVERS
# ============================================================

def get_top_movers(df, number=15):

    if df.empty:
        return df

    # Filter minimum activity supaya coin yang sangat sepi
    # tidak mendominasi hanya karena price range kecil/aneh.
    df = df[df["volume"] > 0].copy()

    # Score gabungan:
    # 60% absolute movement
    # 40% intraday volatility
    df["mover_score"] = (
        df["abs_movement"] * 0.60
        +
        df["volatility"] * 0.40
    )

    df = df.sort_values(
        "mover_score",
        ascending=False
    )

    return df.head(number).copy()


# ============================================================
# CANDLE DATA
# ============================================================

@st.cache_data(ttl=20)
def get_candles(inst_id, bar, limit=100):

    data = okx_get(
        "/api/v5/market/candles",
        {
            "instId": inst_id,
            "bar": bar,
            "limit": str(limit)
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for candle in reversed(data):

        try:

            rows.append({
                "timestamp": int(candle[0]),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5])
            })

        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


# ============================================================
# TECHNICAL CALCULATION
# ============================================================

def calculate_indicators(df):

    if df.empty or len(df) < 25:
        return df

    df = df.copy()

    # Moving averages
    df["ema20"] = df["close"].ewm(
        span=20,
        adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=50,
        adjust=False
    ).mean()

    # Bollinger-style bands
    df["basis"] = df["close"].rolling(20).mean()

    df["std"] = df["close"].rolling(20).std()

    df["upper"] = df["basis"] + (2 * df["std"])

    df["lower"] = df["basis"] - (2 * df["std"])

    # Candle momentum
    df["momentum"] = (
        df["close"].pct_change(5) * 100
    )

    # Candle range %
    df["range_pct"] = (
        (df["high"] - df["low"])
        /
        df["close"]
    ) * 100

    return df


# ============================================================
# ANALYZE ONE TIMEFRAME
# ============================================================

def analyze_timeframe(df):

    if df.empty or len(df) < 25:
        return {
            "direction": "NEUTRAL",
            "score": 0,
            "price": None,
            "lower": None,
            "upper": None,
            "basis": None
        }

    df = calculate_indicators(df)

    last = df.iloc[-1]

    price = last["close"]

    ema20 = last["ema20"]
    ema50 = last["ema50"]

    lower = last["lower"]
    upper = last["upper"]

    basis = last["basis"]

    score_long = 0
    score_short = 0

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if ema20 > ema50:
        score_long += 2

    elif ema20 < ema50:
        score_short += 2

    # --------------------------------------------------------
    # PRICE POSITION
    # --------------------------------------------------------

    if price > basis:
        score_long += 1

    elif price < basis:
        score_short += 1

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    momentum = last.get("momentum", 0)

    if pd.notna(momentum):

        if momentum > 0:
            score_long += 1

        elif momentum < 0:
            score_short += 1

    # --------------------------------------------------------
    # BAND POSITION
    # --------------------------------------------------------

    if pd.notna(lower) and pd.notna(upper):

        band_width = upper - lower

        if band_width > 0:

            position = (
                price - lower
            ) / band_width

            # Near lower band
            if position < 0.30:
                score_long += 1

            # Near upper band
            elif position > 0.70:
                score_short += 1

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    if score_long > score_short:
        direction = "LONG"

    elif score_short > score_long:
        direction = "SHORT"

    else:
        direction = "NEUTRAL"

    return {
        "direction": direction,
        "score_long": score_long,
        "score_short": score_short,
        "price": price,
        "lower": lower,
        "upper": upper,
        "basis": basis
    }


# ============================================================
# ANALYZE TOP MOVER
# ============================================================

def analyze_pair(row):

    inst_id = row["instId"]

    results = {}

    for name, bar in TIMEFRAMES.items():

        candles = get_candles(
            inst_id,
            bar,
            100
        )

        results[name] = analyze_timeframe(
            candles
        )

    long_votes = sum(
        1
        for x in results.values()
        if x["direction"] == "LONG"
    )

    short_votes = sum(
        1
        for x in results.values()
        if x["direction"] == "SHORT"
    )

    # --------------------------------------------------------
    # REQUIRE MAJORITY
    # --------------------------------------------------------

    if long_votes >= 2 and long_votes > short_votes:
        outlook = "LONG"

    elif short_votes >= 2 and short_votes > long_votes:
        outlook = "SHORT"

    else:
        outlook = "NEUTRAL"

    price = row["price"]

    tf15 = results["15M"]

    # --------------------------------------------------------
    # ENTRY / TP
    # --------------------------------------------------------

    if outlook == "LONG":

        lower = tf15.get("lower")

        if lower is not None and pd.notna(lower):

            entry_low = min(
                price,
                lower
            )

            entry_high = max(
                price,
                lower
            )

            # TP menuju basis
            basis = tf15.get("basis")

            if basis is not None and pd.notna(basis):
                tp = basis

                if tp <= price:
                    tp = price + (
                        abs(price - lower) * 1.5
                    )

            else:
                tp = price * 1.03

        else:

            entry_low = price * 0.995
            entry_high = price
            tp = price * 1.03

    elif outlook == "SHORT":

        upper = tf15.get("upper")

        if upper is not None and pd.notna(upper):

            entry_low = min(
                price,
                upper
            )

            entry_high = max(
                price,
                upper
            )

            basis = tf15.get("basis")

            if basis is not None and pd.notna(basis):
                tp = basis

                if tp >= price:
                    tp = price - (
                        abs(upper - price) * 1.5
                    )

            else:
                tp = price * 0.97

        else:

            entry_low = price
            entry_high = price * 1.005
            tp = price * 0.97

    else:

        entry_low = price
        entry_high = price
        tp = price

    return {
        "pair": row["pair"],
        "instId": inst_id,
        "price": price,
        "movement": row["movement"],
        "volatility": row["volatility"],
        "volume": row["volume"],
        "outlook": outlook,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "take_profit": tp,
        "timeframes": results,
        "long_votes": long_votes,
        "short_votes": short_votes
    }


# ============================================================
# RUN SCREENING
# ============================================================

def run_screening():

    tickers = get_tickers()

    if tickers.empty:
        return []

    top_movers = get_top_movers(
        tickers,
        number=15
    )

    results = []

    for _, row in top_movers.iterrows():

        result = analyze_pair(row)

        # Hanya simpan coin yang memiliki outlook
        if result["outlook"] in [
            "LONG",
            "SHORT"
        ]:

            now = datetime.now()

            result["timestamp"] = now.strftime(
                "%H:%M:%S"
            )

            result["timestamp_unix"] = int(
                time.time()
            )

            save_history(result)

            results.append(result)

    cleanup_old_history()

    return results


# ============================================================
# FORMAT PRICE
# ============================================================

def format_price(value):

    if value is None:
        return "-"

    try:

        value = float(value)

        if value >= 1000:
            return f"{value:,.2f}"

        elif value >= 1:
            return f"{value:.4f}"

        elif value >= 0.01:
            return f"{value:.6f}"

        else:
            return f"{value:.10f}"

    except Exception:
        return "-"


# ============================================================
# TRADINGVIEW
# ============================================================

def show_tradingview(inst_id, interval="15"):

    symbol = inst_id.replace(
        "-SWAP",
        ""
    ).replace(
        "-",
        ""
    )

    tv_symbol = f"OKX:{symbol}.P"

    html = f"""
    <div class="tradingview-widget-container"
         style="height:700px;width:100%">
      <div id="tradingview_chart"
           style="height:700px;width:100%">
      </div>
    </div>

    <script
      type="text/javascript"
      src="https://s3.tradingview.com/tv.js">
    </script>

    <script>
    new TradingView.widget({{
        "autosize": true,
        "symbol": "{tv_symbol}",
        "interval": "{interval}",
        "timezone": "Asia/Jakarta",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#000000",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "hide_legend": false,
        "save_image": false,
        "container_id": "tradingview_chart"
    }});
    </script>
    """

    components.html(
        html,
        height=720
    )


# ============================================================
# SESSION STATE
# ============================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "token" not in st.session_state:
    st.session_state.token = None

if "remaining" not in st.session_state:
    st.session_state.remaining = 0

if "results" not in st.session_state:
    st.session_state.results = []

if "selected_chart" not in st.session_state:
    st.session_state.selected_chart = None


# ============================================================
# DATABASE INIT
# ============================================================

init_db()
cleanup_old_history()


# ============================================================
# HEADER
# ============================================================

st.title("0xmwY Kraken")

st.caption(
    "pengembang : Lutfi Andreyansah"
)

st.write(
    "Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"
)

st.divider()


# ============================================================
# LOGIN
# ============================================================

if not st.session_state.logged_in:

    st.subheader("🔐 Access")

    token_input = st.text_input(
        "Masukkan token",
        type="password",
        placeholder="KRAKEN-XXXX"
    )

    if st.button(
        "Masuk",
        use_container_width=True
    ):

        if token_input in TOKENS:

            st.session_state.logged_in = True
            st.session_state.token = token_input
            st.session_state.remaining = TOKENS[
                token_input
            ]

            st.success(
                "Token valid. Access granted."
            )

            st.rerun()

        else:

            st.error(
                "Token tidak valid."
            )

    st.stop()


# ============================================================
# ACCESS INFO
# ============================================================

col1, col2 = st.columns(2)

with col1:

    st.metric(
        "Remaining Screening",
        st.session_state.remaining
    )

with col2:

    if st.button(
        "Logout",
        use_container_width=True
    ):

        st.session_state.logged_in = False
        st.session_state.token = None
        st.session_state.remaining = 0
        st.session_state.results = []

        st.rerun()


# ============================================================
# SCREEN BUTTON
# ============================================================

st.subheader("🔥 Top Mover Scanner")

st.write(
    "Mencari coin yang sedang bergerak paling volatile "
    "kemudian menentukan outlook LONG atau SHORT."
)

if st.session_state.remaining <= 0:

    st.warning(
        "Limit screening kamu sudah habis."
    )

else:

    if st.button(
        "🚀 START SCREENING",
        type="primary",
        use_container_width=True
    ):

        with st.spinner(
            "Mencari Top Movers dan menganalisis..."
        ):

            results = run_screening()

        st.session_state.results = results

        st.session_state.remaining -= 1

        if results:

            st.success(
                f"{len(results)} coin berhasil dianalisis."
            )

        else:

            st.warning(
                "Belum ditemukan setup LONG/SHORT yang cukup kuat."
            )


# ============================================================
# CURRENT RESULTS
# ============================================================

results = st.session_state.results

if results:

    st.divider()

    st.subheader("📡 CURRENT SCREENING")

    long_results = [
        x for x in results
        if x["outlook"] == "LONG"
    ]

    short_results = [
        x for x in results
        if x["outlook"]
