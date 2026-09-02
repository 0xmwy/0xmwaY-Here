import streamlit as st
import requests
import pandas as pd
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from html import escape

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="0xmwY Kraken",
    page_icon="⚡",
    layout="wide"
)

# ============================================================
# CONFIG
# ============================================================

API_BASE = "https://www.okx.com"
DB_FILE = "screening_history.db"

TIMEFRAMES = {
    "15M": "15m",
    "30M": "30m",
    "1H": "1H"
}

MAX_COINS_TO_ANALYZE = 15

# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>
    .main-title {
        font-size: 42px;
        font-weight: 800;
        margin-bottom: 0px;
    }

    .subtitle {
        font-size: 16px;
        opacity: 0.75;
        margin-bottom: 4px;
    }

    .quote {
        font-size: 14px;
        font-style: italic;
        opacity: 0.65;
        margin-bottom: 25px;
    }

    .outlook-long {
        padding: 18px;
        border-radius: 12px;
        border: 1px solid rgba(0, 180, 100, 0.35);
        margin-bottom: 10px;
    }

    .outlook-short {
        padding: 18px;
        border-radius: 12px;
        border: 1px solid rgba(220, 70, 70, 0.35);
        margin-bottom: 10px;
    }

    .small-text {
        font-size: 13px;
        opacity: 0.7;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="main-title">0xmwY Kraken</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">pengembang : Lutfi Andreyansah</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="quote">"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"</div>',
    unsafe_allow_html=True
)

# ============================================================
# DATABASE
# ============================================================

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS screening_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            pair TEXT NOT NULL,
            outlook TEXT NOT NULL,
            movement REAL,
            volatility REAL,
            entry_low REAL,
            entry_high REAL,
            take_profit REAL,
            confidence REAL
        )
        """
    )

    conn.commit()
    conn.close()


def cleanup_old_history():
    conn = get_connection()

    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=24)
    ).isoformat()

    conn.execute(
        """
        DELETE FROM screening_history
        WHERE timestamp < ?
        """,
        (cutoff,)
    )

    conn.commit()
    conn.close()


def save_history(results):
    if not results:
        return

    conn = get_connection()

    for item in results:
        conn.execute(
            """
            INSERT INTO screening_history
            (
                timestamp,
                pair,
                outlook,
                movement,
                volatility,
                entry_low,
                entry_high,
                take_profit,
                confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["timestamp"],
                item["pair"],
                item["outlook"],
                item["movement"],
                item["volatility"],
                item["entry_low"],
                item["entry_high"],
                item["take_profit"],
                item["confidence"]
            )
        )

    conn.commit()
    conn.close()


def load_history():
    conn = get_connection()

    df = pd.read_sql_query(
        """
        SELECT
            timestamp,
            pair,
            outlook,
            movement,
            volatility,
            entry_low,
            entry_high,
            take_profit,
            confidence
        FROM screening_history
        ORDER BY timestamp DESC
        """,
        conn
    )

    conn.close()

    return df


init_database()
cleanup_old_history()

# ============================================================
# API FUNCTIONS
# ============================================================

def api_get(endpoint, params=None):
    url = API_BASE + endpoint

    try:
        response = requests.get(
            url,
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
# GET SWAP INSTRUMENTS
# ============================================================

@st.cache_data(ttl=300)
def get_instruments():
    data = api_get(
        "/api/v5/public/instruments",
        {
            "instType": "SWAP"
        }
    )

    if not data:
        return []

    pairs = []

    for item in data:
        inst_id = item.get("instId", "")
        state = item.get("state", "")

        if (
            inst_id.endswith("-USDT-SWAP")
            and state == "live"
        ):
            pairs.append(inst_id)

    return pairs


# ============================================================
# GET TICKERS
# ============================================================

@st.cache_data(ttl=30)
def get_tickers():
    data = api_get(
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
            volume = float(item.get("volCcy24h", 0))

            if last <= 0 or open24 <= 0:
                continue

            movement = (
                (last - open24) / open24
            ) * 100

            volatility = (
                (high24 - low24) / open24
            ) * 100

            rows.append(
                {
                    "inst_id": inst_id,
                    "pair": inst_id.replace("-SWAP", ""),
                    "price": last,
                    "open24h": open24,
                    "high24h": high24,
                    "low24h": low24,
                    "volume": volume,
                    "movement": movement,
                    "abs_movement": abs(movement),
                    "volatility": volatility
                }
            )

        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


# ============================================================
# TOP MOVER
# ============================================================

def get_top_movers(tickers, limit=MAX_COINS_TO_ANALYZE):
    if tickers.empty:
        return pd.DataFrame()

    df = tickers.copy()

    # Kombinasi pergerakan harga + volatilitas
    max_movement = max(
        df["abs_movement"].max(),
        0.000001
    )

    max_volatility = max(
        df["volatility"].max(),
        0.000001
    )

    df["movement_score"] = (
        df["abs_movement"] / max_movement
    )

    df["volatility_score"] = (
        df["volatility"] / max_volatility
    )

    df["top_mover_score"] = (
        df["movement_score"] * 0.60
        + df["volatility_score"] * 0.40
    )

    df = df.sort_values(
        "top_mover_score",
        ascending=False
    )

    return df.head(limit).reset_index(drop=True)


# ============================================================
# CANDLE DATA
# ============================================================

@st.cache_data(ttl=60)
def get_candles(inst_id, bar, limit=100):
    data = api_get(
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

    for candle in data:
        try:
            rows.append(
                {
                    "timestamp": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5])
                }
            )
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

def calculate_outlook(df):
    if df.empty or len(df) < 30:
        return None

    close = df["close"]

    # Moving averages
    ema_fast = close.ewm(
        span=9,
        adjust=False
    ).mean()

    ema_slow = close.ewm(
        span=21,
        adjust=False
    ).mean()

    # Momentum
    recent_return = (
        (close.iloc[-1] - close.iloc[-6])
        / close.iloc[-6]
    ) * 100

    # Volatility
    rolling_high = close.rolling(20).max().iloc[-1]
    rolling_low = close.rolling(20).min().iloc[-1]

    current_price = close.iloc[-1]

    if current_price <= 0:
        return None

    range_percent = (
        (rolling_high - rolling_low)
        / current_price
    ) * 100

    bullish = 0
    bearish = 0

    # EMA direction
    if ema_fast.iloc[-1] > ema_slow.iloc[-1]:
        bullish += 1
    else:
        bearish += 1

    # Momentum
    if recent_return > 0:
        bullish += 1
    else:
        bearish += 1

    # Candle direction
    if close.iloc[-1] > close.iloc[-2]:
        bullish += 1
    else:
        bearish += 1

    if bullish > bearish:
        outlook = "LONG"
        confidence = (
            bullish / 3
        ) * 100
    else:
        outlook = "SHORT"
        confidence = (
            bearish / 3
        ) * 100

    return {
        "outlook": outlook,
        "confidence": confidence,
        "price": current_price,
        "range_percent": range_percent,
        "recent_return": recent_return
    }


# ============================================================
# ANALYZE ONE COIN
# ============================================================

def analyze_coin(inst_id):
    timeframe_results = {}

    for name, bar in TIMEFRAMES.items():
        candles = get_candles(
            inst_id,
            bar
        )

        analysis = calculate_outlook(candles)

        if analysis:
            timeframe_results[name] = analysis

    if len(timeframe_results) < 2:
        return None

    long_count = sum(
        1
        for result in timeframe_results.values()
        if result["outlook"] == "LONG"
    )

    short_count = sum(
        1
        for result in timeframe_results.values()
        if result["outlook"] == "SHORT"
    )

    # Harus ada minimal 2 timeframe yang searah
    if long_count >= 2:
        final_outlook = "LONG"
    elif short_count >= 2:
        final_outlook = "SHORT"
    else:
        return None

    prices = [
        result["price"]
        for result in timeframe_results.values()
    ]

    current_price = prices[-1]

    range_values = [
        result["range_percent"]
        for result in timeframe_results.values()
    ]

    avg_range = sum(range_values) / len(range_values)

    # Entry range sederhana berdasarkan volatilitas
    entry_distance = max(
        avg_range / 100 * current_price * 0.25,
        current_price * 0.001
    )

    if final_outlook == "LONG":
        entry_low = current_price - entry_distance
        entry_high = current_price

        take_profit = current_price + (
            entry_distance * 2
        )

    else:
        entry_low = current_price
        entry_high = current_price + entry_distance

        take_profit = current_price - (
            entry_distance * 2
        )

    confidence = max(
        long_count,
        short_count
    ) / len(timeframe_results) * 100

    return {
        "outlook": final_outlook,
        "confidence": confidence,
        "price": current_price,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "take_profit": take_profit,
        "timeframes": timeframe_results
    }


# ============================================================
# RUN SCREENING
# ============================================================

def run_screening():
    tickers = get_tickers()

    if tickers.empty:
        return [], pd.DataFrame()

    top_movers = get_top_movers(
        tickers,
        MAX_COINS_TO_ANALYZE
    )

    results = []

    for _, mover in top_movers.iterrows():
        inst_id = mover["inst_id"]

        analysis = analyze_coin(inst_id)

        if not analysis:
            continue

        now = datetime.now(
            timezone.utc
        )

        result = {
            "timestamp": now.isoformat(),
            "display_time": now.astimezone().strftime(
                "%H:%M:%S"
            ),
            "pair": mover["pair"],
            "outlook": analysis["outlook"],
            "movement": mover["movement"],
            "volatility": mover["volatility"],
            "entry_low": analysis["entry_low"],
            "entry_high": analysis["entry_high"],
            "take_profit": analysis["take_profit"],
            "confidence": analysis["confidence"],
            "price": analysis["price"],
            "timeframes": analysis["timeframes"]
        }

        results.append(result)

    # Urutkan berdasarkan confidence + movement
    results.sort(
        key=lambda x: (
            x["confidence"],
            abs(x["movement"])
        ),
        reverse=True
    )

    return results, top_movers


# ============================================================
# SESSION STATE
# ============================================================

if "results" not in st.session_state:
    st.session_state.results = []

if "last_screening" not in st.session_state:
    st.session_state.last_screening = None

# ============================================================
# SCREENING BUTTON
# ============================================================

st.subheader("Volatility Scanner")

col1, col2 = st.columns([1, 4])

with col1:
    scan_button = st.button(
        "⚡ SCREEN NOW",
        use_container_width=True
    )

with col2:
    if st.session_state.last_screening:
        st.caption(
            "Last screening: "
            + st.session_state.last_screening
        )

if scan_button:
    with st.spinner(
        "Scanning volatile coins..."
    ):
        results, top_movers = run_screening()

    st.session_state.results = results

    now_local = datetime.now().strftime(
        "%H:%M:%S"
    )

    st.session_state.last_screening = now_local

    # Simpan history
    if results:
        save_history(results)
        cleanup_old_history()

    st.rerun()

# ============================================================
# CURRENT RESULTS
# ============================================================

results = st.session_state.results

st.subheader("Current Outlook")

if not results:
    st.info(
        "Belum ada hasil screening. "
        "Tekan SCREEN NOW untuk memulai."
    )
else:

    long_results = [
        x for x in results
        if x["outlook"] == "LONG"
    ]

    short_results = [
        x for x in results
        if x["outlook"] == "SHORT"
    ]

    col_long, col_short = st.columns(2)

    # --------------------------------------------------------
    # LONG
    # --------------------------------------------------------

    with col_long:
        st.markdown("### 🟢 OUTLOOK LONG")

        if not long_results:
            st.write("Tidak ada setup LONG.")

        for item in long_results:
            st.markdown(
                f"""
                <div class="outlook-long">
                    <h3>{escape(item["pair"])}</h3>
                    <p>
                    Entry: {item["entry_low"]:.8g}
                    → {item["entry_high"]:.8g}
                    </p>
                    <p>
                    <b>Take Profit:</b>
                    {item["take_profit"]:.8g}
                    </p>
                    <p class="small-text">
                    Movement: {item["movement"]:.2f}% |
                    Volatility: {item["volatility"]:.2f}% |
                    Confidence: {item["confidence"]:.0f}%
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )

    # --------------------------------------------------------
    # SHORT
    # --------------------------------------------------------

    with col_short:
        st.markdown("### 🔴 OUTLOOK SHORT")

        if not short_results:
            st.write("Tidak ada setup SHORT.")

        for item in short_results:
            st.markdown(
                f"""
                <div class="outlook-short">
                    <h3>{escape(item["pair"])}</h3>
                    <p>
                    Entry: {item["entry_low"]:.8g}
                    → {item["entry_high"]:.8g}
                    </p>
                    <p>
                    <b>Take Profit:</b>
                    {item["take_profit"]:.8g}
                    </p>
                    <p class="small-text">
                    Movement: {item["movement"]:.2f}% |
                    Volatility: {item["volatility"]:.2f}% |
                    Confidence: {item["confidence"]:.0f}%
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )

# ============================================================
# TRADINGVIEW
# ============================================================

st.divider()
st.subheader("Chart")

if results:

    options = []

    for item in results:
        label = (
            f'{item["outlook"]} • {item["pair"]}'
        )
        options.append(label)

    selected = st.selectbox(
        "Pilih hasil screening",
        options
    )

    selected_item = None

    for item in results:
        label = (
            f'{item["outlook"]} • {item["pair"]}'
        )

        if label == selected:
            selected_item = item
            break

    if selected_item:

        pair = selected_item["pair"]

        tv_symbol = (
            "OKX:"
            + pair.replace("-", "")
            + ".P"
        )

        # TradingView official widget
        tv_html = f"""
        <div style="height:650px;width:100%;">
            <div id="tradingview_chart"
                 style="height:100%;width:100%;">
            </div>
        </div>

        <script
            type="text/javascript"
            src="https://s3.tradingview.com/tv.js">
        </script>

        <script type="text/javascript">
            new TradingView.widget({{
                "autosize": true,
                "symbol": "{tv_symbol}",
                "interval": "15",
                "timezone": "Asia/Jakarta",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "hide_top_toolbar": false,
             
