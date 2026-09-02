import streamlit as st
import requests
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, timezone

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="0xmwY Kraken",
    page_icon="⚡",
    layout="wide"
)

BASE = "https://www.okx.com"
DB = "screening_history.db"

TIMEFRAMES = {
    "15M": "15m",
    "30M": "30m",
    "1H": "1H"
}

MAX_MOVER = 12

# =========================================================
# STYLE
# =========================================================

st.markdown("""
<style>

.title {
    font-size: 40px;
    font-weight: 800;
}

.sub {
    opacity: 0.7;
}

.card {
    padding: 16px;
    border-radius: 12px;
    border: 1px solid rgba(128,128,128,.3);
    margin-bottom: 10px;
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="title">0xmwY Kraken</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub">pengembang : Lutfi Andreyansah</div>',
    unsafe_allow_html=True
)

st.caption(
    '"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"'
)

# =========================================================
# DATABASE
# =========================================================

def db():
    return sqlite3.connect(DB)


def init_db():

    con = db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            pair TEXT,
            outlook TEXT,
            movement REAL,
            volatility REAL,
            entry_low REAL,
            entry_high REAL,
            tp REAL,
            confidence REAL,
            sl REAL,
            status TEXT DEFAULT 'OPEN',
            pnl_pct REAL DEFAULT 0,
            resolved_at TEXT
        )
    """)

    # Migration database lama
    existing = [
        row[1]
        for row in con.execute(
            "PRAGMA table_info(history)"
        ).fetchall()
    ]

    columns = [
        ("sl", "REAL"),
        ("status", "TEXT DEFAULT 'OPEN'"),
        ("pnl_pct", "REAL DEFAULT 0"),
        ("resolved_at", "TEXT")
    ]

    for name, dtype in columns:

        if name not in existing:

            con.execute(
                f"ALTER TABLE history ADD COLUMN {name} {dtype}"
            )

    con.commit()
    con.close()


def clean_db():

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=24)
    ).isoformat()

    con = db()

    con.execute(
        "DELETE FROM history WHERE timestamp < ?",
        (cutoff,)
    )

    con.commit()
    con.close()


def save_results(results):

    if not results:
        return

    con = db()

    for x in results:

        con.execute("""
            INSERT INTO history
            (
                timestamp,
                pair,
                outlook,
                movement,
                volatility,
                entry_low,
                entry_high,
                tp,
                confidence,
                sl,
                status,
                pnl_pct
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 0)
        """, (
            x["timestamp"],
            x["pair"],
            x["outlook"],
            x["movement"],
            x["volatility"],
            x["entry_low"],
            x["entry_high"],
            x["tp"],
            x["confidence"],
            x["sl"]
        ))

    con.commit()
    con.close()


def get_history():

    con = db()

    df = pd.read_sql_query(
        """
        SELECT
            id,
            timestamp,
            pair,
            outlook,
            movement,
            volatility,
            entry_low,
            entry_high,
            tp,
            confidence,
            sl,
            status,
            pnl_pct,
            resolved_at
        FROM history
        ORDER BY timestamp DESC
        """,
        con
    )

    con.close()

    return df


init_db()
clean_db()

# =========================================================
# API
# =========================================================

def api(path, params):

    try:

        response = requests.get(
            BASE + path,
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

# =========================================================
# TICKERS
# =========================================================

@st.cache_data(ttl=30)
def get_tickers():

    data = api(
        "/api/v5/market/tickers",
        {
            "instType": "SWAP"
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for x in data:

        inst = x.get("instId", "")

        if not inst.endswith("-USDT-SWAP"):
            continue

        try:

            price = float(x["last"])
            op = float(x["open24h"])
            high = float(x["high24h"])
            low = float(x["low24h"])

        except Exception:
            continue

        if price <= 0 or op <= 0:
            continue

        movement = (
            (price - op)
            / op
        ) * 100

        volatility = (
            (high - low)
            / op
        ) * 100

        rows.append({
            "inst": inst,
            "pair": inst.replace("-SWAP", ""),
            "price": price,
            "movement": movement,
            "abs_move": abs(movement),
            "volatility": volatility
        })

    return pd.DataFrame(rows)

# =========================================================
# TOP MOVER
# =========================================================

def top_movers(df):

    if df.empty:
        return df

    df = df.copy()

    move_max = max(
        df["abs_move"].max(),
        0.000001
    )

    vol_max = max(
        df["volatility"].max(),
        0.000001
    )

    df["score"] = (
        (
            df["abs_move"]
            / move_max
        ) * 0.60
        +
        (
            df["volatility"]
            / vol_max
        ) * 0.40
    )

    return (
        df
        .sort_values(
            "score",
            ascending=False
        )
        .head(MAX_MOVER)
        .reset_index(drop=True)
    )

# =========================================================
# CANDLES
# =========================================================

@st.cache_data(ttl=30)
def candles(inst, bar):

    data = api(
        "/api/v5/market/candles",
        {
            "instId": inst,
            "bar": bar,
            "limit": "80"
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for c in data:

        try:

            rows.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5])
            })

        except Exception:
            pass

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .iloc[::-1]
        .reset_index(drop=True)
    )

# =========================================================
# TIMEFRAME ANALYSIS
# =========================================================

def analyze_tf(df):

    if len(df) < 30:
        return None

    close = df["close"]

    ema9 = close.ewm(
        span=9,
        adjust=False
    ).mean()

    ema21 = close.ewm(
        span=21,
        adjust=False
    ).mean()

    momentum = (
        (
            close.iloc[-1]
            - close.iloc[-6]
        )
        / close.iloc[-6]
    ) * 100

    bull = 0
    bear = 0

    # EMA
    if ema9.iloc[-1] > ema21.iloc[-1]:
        bull += 1
    else:
        bear += 1

    # Momentum
    if momentum > 0:
        bull += 1
    else:
        bear += 1

    # Candle direction
    if close.iloc[-1] > close.iloc[-2]:
        bull += 1
    else:
        bear += 1

    if bull > bear:

        side = "LONG"
        confidence = (
            bull / 3
        ) * 100

    else:

        side = "SHORT"
        confidence = (
            bear / 3
        ) * 100

    high = close.tail(20).max()
    low = close.tail(20).min()

    volatility = (
        (
            high - low
        )
        / close.iloc[-1]
    ) * 100

    return {
        "side": side,
        "confidence": confidence,
        "price": close.iloc[-1],
        "volatility": volatility
    }

# =========================================================
# COIN ANALYSIS
# =========================================================

def analyze_coin(inst):

    tf = {}

    for name, bar in TIMEFRAMES.items():

        df = candles(
            inst,
            bar
        )

        result = analyze_tf(df)

        if result:
            tf[name] = result

    if len(tf) < 2:
        return None

    longs = sum(
        x["side"] == "LONG"
        for x in tf.values()
    )

    shorts = sum(
        x["side"] == "SHORT"
        for x in tf.values()
    )

    if longs >= 2:

        side = "LONG"

    elif shorts >= 2:

        side = "SHORT"

    else:

        return None

    price = list(
        tf.values()
    )[-1]["price"]

    vol = sum(
        x["volatility"]
        for x in tf.values()
    ) / len(tf)

    distance = max(
        price
        * (vol / 100)
        * 0.20,

        price * 0.001
    )

    # Risk : Reward = 1 : 2

    if side == "LONG":

        entry_low = price - distance
        entry_high = price

        tp = price + (
            distance * 2
        )

        sl = price - distance

    else:

        entry_low = price
        entry_high = price + distance

        tp = price - (
            distance * 2
        )

        sl = price + distance

    confidence = (
        max(longs, shorts)
        / len(tf)
    ) * 100

    return {
        "outlook": side,
        "price": price,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "tp": tp,
        "sl": sl,
        "confidence": confidence
    }

# =========================================================
# SCREENING
# =========================================================

def screening():

    tickers = get_tickers()

    if tickers.empty:
        return []

    movers = top_movers(
        tickers
    )

    results = []

    for _, mover in movers.iterrows():

        result = analyze_coin(
            mover["inst"]
        )

        if not result:
            continue

        now = datetime.now(
            timezone.utc
        )

        results.append({

            "timestamp":
                now.isoformat(),

            "time":
                now.astimezone().strftime(
                    "%H:%M:%S"
                ),

            "pair":
                mover["pair"],

            "outlook":
                result["outlook"],

            "movement":
                mover["movement"],

            "volatility":
                mover["volatility"],

            "entry_low":
                result["entry_low"],

            "entry_high":
                result["entry_high"],

            "tp":
                result["tp"],

            "sl":
                result["sl"],

            "confidence":
                result["confidence"]
        })

    return sorted(
        results,
        key=lambda x: (
            x["confidence"],
            abs(x["movement"])
        ),
        reverse=True
    )

# =========================================================
# RESOLVE TRADE RESULT
# =========================================================

def resolve_history():

    clean_db()

    con = db()

    rows = con.execute("""
        SELECT
            id,
            timestamp,
            pair,
            outlook,
            entry_low,
            entry_high,
            tp,
            sl,
            status
        FROM history
        WHERE status = 'OPEN'
    """).fetchall()

    for row in rows:

        (
            trade_id,
            timestamp,
            pair,
            outlook,
            entry_low,
            entry_high,
            tp,
            sl,
            status
        ) = row

        inst = pair + "-SWAP"

        df = candles(
            inst,
            "15m"
        )

        if df.empty:
            continue

        current_price = float(
            df["close"].iloc[-1]
        )

        result = None
        pnl = 0

        # -------------------------------------------------
        # LONG
        # -------------------------------------------------

        if outlook == "LONG":

            if current_price >= tp:

                result = "SUCCESS"

                pnl = (
                    (
                        tp
                        - entry_high
                    )
                    / entry_high
                ) * 100

            elif current_price <= sl:

                result = "LOSS"

                pnl = (
                    (
                        sl
                        - entry_high
                    )
                    / entry_high
                ) * 100

        # -------------------------------------------------
        # SHORT
        # -------------------------------------------------

        elif outlook == "SHORT":

            if current_price <= tp:

                result = "SUCCESS"

                pnl = (
                    (
                        entry_low
                        - tp
                    )
                    / entry_low
                ) * 100

            elif current_price >= sl:

                result = "LOSS"

                pnl = (
                    (
                        entry_low
                        - sl
                    )
                    / entry_low
                ) * 100

        # -------------------------------------------------
        # SAVE RESULT
        # -------------------------------------------------

        if result:

            con.execute("""
                UPDATE history
                SET
                    status = ?,
                    pnl_pct = ?,
                    resolved_at = ?
                WHERE id = ?
            """, (

                result,
                pnl,

                datetime.now(
                    timezone.utc
                ).isoformat(),

                trade_id
            ))

    con.commit()
    con.close()

# =========================================================
# SESSION
# =========================================================

if "results" not in st.session_state:
    st.session_state.results = []

if "last_scan" not in st.session_state:
    st.session_state.last_scan = "-"

if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = None

# =========================================================
# SCREEN BUTTON
# =========================================================

if st.button(
    "⚡ SCREEN NOW",
    use_container_width=True
):

    with st.spinner(
        "Mencari coin volatile..."
    ):

        result = screening()

    st.session_state.results = result

    st.session_state.last_scan = (
        datetime.now().strftime(
            "%H:%M:%S"
        )
    )

    if result:
        save_results(result)

    clean_db()

    st.rerun()

st.caption(
    f"Last screening: "
    f"{st.session_state.last_scan}"
)

# =========================================================
# CURRENT OUTLOOK
# =========================================================

st.divider()

st.subheader(
    "Current Outlook"
)

results = st.session_state.results

longs = [
    x for x in results
    if x["outlook"] == "LONG"
]

shorts = [
    x for x in results
    if x["outlook"] == "SHORT"
]

col1, col2 = st.columns(2)

# =========================================================
# LONG
# =========================================================

with col1:

    st.markdown(
        "### 🟢 OUTLOOK LONG"
    )

    if not longs:

        st.info(
            "Belum ada setup LONG."
        )

    for x in longs:

        st.markdown(
            f"""
            <div class="card">

                <h3>{x["pair"]}</h3>

                <b>Entry:</b>
                {x["entry_low"]:.8g}
                →
                {x["entry_high"]:.8g}

                <br><br>

                <b>Take Profit:</b>
                {x["tp"]:.8g}

                <br><br>

                <b>Stop Loss:</b>
                {x["sl"]:.8g}

                <br><br>

                Movement:
                {x["movement"]:.2f}%

                <br>

                Volatility:
                {x["volatility"]:.2f}%

                <br>

                Confidence:
                {x["confidence"]:.0f}%

            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button(
            f"📈 Open Chart • {x['pair']}",
            key=f"long_{x['pair']}",
            use_container_width=True
        ):

            st.session_state.selected_pair = (
                x["pair"]
            )

            st.rerun()

# =========================================================
# SHORT
# =========================================================

with col2:

    st.markdown(
        "### 🔴 OUTLOOK SHORT"
    )

    if not shorts:

        st.info(
            "Belum ada setup SHORT."
        )

    for x in shorts:

        st.markdown(
            f"""
            <div class="card">

                <h3>{x["pair"]}</h3>

                <b>Entry:</b>
                {x["entry_low"]:.8g}
                →
                {x["entry_high"]:.8g}

                <br><br>

                <b>Take Profit:</b>
                {x["tp"]:.8g}

                <br><br>

                <b>Stop Loss:</b>
                {x["sl"]:.8g}

                <br><br>

                Movement:
                {x["movement"]:.2f}%

                <br>

                Volatility:
                {x["volatility"]:.2f}%

                <br>

                Confidence:
                {x["confidence"]:.0f}%

            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button(
            f"📉 Open Chart • {x['pair']}",
            key=f"short_{x['pair']}",
            use_container_width=True
        ):

            st.session_state.selected_pair = (
                x["pair"]
            )

            st.rerun()

# =========================================================
# TRADINGVIEW LIVE CHART
# =========================================================

if st.session_state.selected_pair:

    pair = st.session_state.selected_pair

    st.divider()

    st.subheader(
        f"Live Chart • {pair}"
    )

    symbol = (
        "OKX:"
        + pair.replace("-", "")
        + ".P"
    )

    html = f"""
    <div
        id="tradingview_chart"
        style="
            height:650px;
            width:100%;
        ">
    </div>

    <script
        src="https://s3.tradingview.com/tv.js">
    </script>

    <script>

    new TradingView.widget({{

        "autosize": true,

        "symbol": "{symbol}",

        "interval": "15",

        "timezone": "Asia/Jakarta",

        "theme": "dark",

        "style": "1",

        "locale": "en",

        "enable_publishing": false,

        "hide_top_toolbar": false,

        "hide_legend": false,

        "save_image": false,

        "container_id":
            "tradingview_chart"

    }});

    </script>
    """

    st.components.v1.html(
        html,
        height=670
    )

# =========================================================
# HISTORY 24 HOURS
# =========================================================

st.d
