import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, timezone

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
# DEMO PORTFOLIO
# =========================================================

DEMO_INITIAL_BALANCE = 10.0

# Margin maksimum seluruh posisi OPEN.
DEMO_MAX_MARGIN = 10.0

# Posisi yang terlalu kecil tidak dibuka.
DEMO_MIN_MARGIN = 0.10

LEVERAGE_MIN = 2
LEVERAGE_MAX = 20

PORTFOLIO_VERSION = "portfolio_v3"


# =========================================================
# HEADER
# =========================================================

st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
}

.title {
    font-size: 40px;
    font-weight: 800;
}

.sub {
    opacity: .7;
}
</style>
""", unsafe_allow_html=True)

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

def connect_db():
    return sqlite3.connect(DB)


def init_db():

    con = connect_db()

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
            sl REAL,
            confidence REAL,
            status TEXT DEFAULT 'OPEN',
            pnl_pct REAL DEFAULT 0,
            resolved_at TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    con.commit()
    con.close()


def migrate_db():

    con = connect_db()

    cols = [
        x[1]
        for x in con.execute(
            "PRAGMA table_info(history)"
        ).fetchall()
    ]

    additions = {
        "sl": "REAL",
        "status": "TEXT DEFAULT 'OPEN'",
        "pnl_pct": "REAL DEFAULT 0",
        "resolved_at": "TEXT",
        "leverage": "REAL DEFAULT 1",
        "margin_usd": "REAL DEFAULT 0",
        "trade_pnl_usd": "REAL DEFAULT 0",
        "entry_price": "REAL",
        "exit_price": "REAL"
    }

    for name, typ in additions.items():

        if name not in cols:

            con.execute(
                f"ALTER TABLE history ADD COLUMN {name} {typ}"
            )

    con.commit()
    con.close()


def reset_old_open_trades_once():

    con = connect_db()

    row = con.execute("""
        SELECT value
        FROM app_settings
        WHERE key = 'portfolio_version'
    """).fetchone()

    if row is None or row[0] != PORTFOLIO_VERSION:

        # Hapus posisi OPEN dari sistem demo lama.
        # History SUCCESS/LOSS tetap dipertahankan.
        con.execute("""
            DELETE FROM history
            WHERE status = 'OPEN'
        """)

        con.execute("""
            INSERT OR REPLACE INTO app_settings
            (key, value)
            VALUES ('portfolio_version', ?)
        """, (
            PORTFOLIO_VERSION,
        ))

        con.commit()

    con.close()


def clean_db():

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=24)
    ).isoformat()

    con = connect_db()

    con.execute(
        "DELETE FROM history WHERE timestamp < ?",
        (cutoff,)
    )

    con.commit()
    con.close()


def get_history():

    con = connect_db()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM history
        ORDER BY timestamp DESC
        """,
        con
    )

    con.close()

    return df


init_db()
migrate_db()
reset_old_open_trades_once()
clean_db()


# =========================================================
# API
# =========================================================

def api(path, params):

    try:

        r = requests.get(
            BASE + path,
            params=params,
            timeout=15
        )

        r.raise_for_status()

        data = r.json()

        if data.get("code") != "0":
            return None

        return data.get("data")

    except Exception:

        return None


# =========================================================
# LIVE PRICES
# =========================================================

@st.cache_data(ttl=2)
def get_live_prices():

    data = api(
        "/api/v5/market/tickers",
        {
            "instType": "SWAP"
        }
    )

    if not data:
        return {}

    prices = {}

    for x in data:

        inst = x.get(
            "instId",
            ""
        )

        if not inst.endswith(
            "-USDT-SWAP"
        ):
            continue

        try:

            prices[inst] = float(
                x["last"]
            )

        except Exception:

            continue

    return prices


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

        inst = x.get(
            "instId",
            ""
        )

        if not inst.endswith(
            "-USDT-SWAP"
        ):
            continue

        try:

            price = float(
                x["last"]
            )

            op = float(
                x["open24h"]
            )

            high = float(
                x["high24h"]
            )

            low = float(
                x["low24h"]
            )

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
            "pair": inst.replace(
                "-SWAP",
                ""
            ),
            "price": price,
            "movement": movement,
            "abs_move": abs(
                movement
            ),
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
        df["abs_move"]
        / move_max
        * 0.60
        +
        df["volatility"]
        / vol_max
        * 0.40
    )

    return (
        df.sort_values(
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
def get_candles(
    inst,
    bar
):

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

    if ema9.iloc[-1] > ema21.iloc[-1]:
        bull += 1
    else:
        bear += 1

    if momentum > 0:
        bull += 1
    else:
        bear += 1

    if close.iloc[-1] > close.iloc[-2]:
        bull += 1
    else:
        bear += 1

    if bull > bear:

        side = "LONG"
        confidence = bull / 3 * 100

    else:

        side = "SHORT"
        confidence = bear / 3 * 100

    high = close.tail(20).max()
    low = close.tail(20).min()

    volatility = (
        (high - low)
        / close.iloc[-1]
    ) * 100

    return {
        "side": side,
        "confidence": confidence,
        "price": close.iloc[-1],
        "volatility": volatility
        }
    # =========================================================
# LEVERAGE ENGINE
# =========================================================

def calculate_demo_leverage(
    confidence,
    volatility
):

    # Sangat volatile = leverage kecil.
    if volatility > 20:
        return 2

    if volatility > 12:
        return 3

    # Setup sangat kuat.
    if confidence >= 100 and volatility <= 5:
        return 20

    if confidence >= 100 and volatility <= 8:
        return 15

    if confidence >= 80 and volatility <= 5:
        return 12

    if confidence >= 80 and volatility <= 8:
        return 10

    if confidence >= 66.67 and volatility <= 5:
        return 8

    if confidence >= 66.67 and volatility <= 8:
        return 5

    return 3


# =========================================================
# COIN ANALYSIS
# =========================================================

def analyze_coin(inst):

    tf = {}

    for name, bar in TIMEFRAMES.items():

        df = get_candles(
            inst,
            bar
        )

        result = analyze_tf(
            df
        )

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
        price * (vol / 100) * 0.20,
        price * 0.001
    )

    if side == "LONG":

        entry_low = (
            price - distance
        )

        entry_high = price

        tp = (
            price
            + distance * 2
        )

        sl = (
            price
            - distance
        )

    else:

        entry_low = price

        entry_high = (
            price + distance
        )

        tp = (
            price
            - distance * 2
        )

        sl = (
            price
            + distance
        )

    confidence = (
        max(longs, shorts)
        / len(tf)
        * 100
    )

    leverage = (
        calculate_demo_leverage(
            confidence,
            vol
        )
    )

    return {
        "outlook": side,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "tp": tp,
        "sl": sl,
        "confidence": confidence,
        "leverage": leverage,
        "entry_price": price,
        "volatility": vol
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
                result["confidence"],

            "leverage":
                result["leverage"],

            "entry_price":
                result["entry_price"]
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
# PORTFOLIO STRENGTH
# =========================================================

def calculate_strength(row):

    confidence = max(
        float(row["confidence"]),
        0
    )

    volatility = max(
        float(row["volatility"]),
        0.01
    )

    movement = abs(
        float(row["movement"])
    )

    confidence_score = (
        confidence / 100
    )

    volatility_score = (
        1
        /
        (1 + volatility / 10)
    )

    movement_score = min(
        movement / 10,
        1
    )

    strength = (
        confidence_score * 0.55
        +
        volatility_score * 0.30
        +
        movement_score * 0.15
    )

    return max(
        strength,
        0.01
    )


# =========================================================
# GET USED MARGIN
# =========================================================

def get_used_margin():

    con = connect_db()

    row = con.execute("""
        SELECT
            COALESCE(
                SUM(margin_usd),
                0
            )
        FROM history
        WHERE status = 'OPEN'
    """).fetchone()

    con.close()

    return float(
        row[0] or 0
    )


# =========================================================
# ALLOCATE PORTFOLIO
# =========================================================

def allocate_portfolio(
    results,
    available
):

    if not results:
        return []

    if available <= 0:
        return []

    df = pd.DataFrame(
        results
    )

    df["strength"] = df.apply(
        calculate_strength,
        axis=1
    )

    df = df.sort_values(
        "strength",
        ascending=False
    ).reset_index(
        drop=True
    )

    # Jangan pernah melebihi available.
    budget = min(
        float(available),
        DEMO_MAX_MARGIN
    )

    if budget < DEMO_MIN_MARGIN:
        return []

    total_strength = df[
        "strength"
    ].sum()

    if total_strength <= 0:
        return []

    final = []

    for _, row in df.iterrows():

        margin = (
            budget
            * row["strength"]
            / total_strength
        )

        # Skip posisi yang terlalu kecil.
        if margin < DEMO_MIN_MARGIN:
            continue

        item = row.to_dict()

        item.pop(
            "strength",
            None
        )

        item["margin_usd"] = round(
            margin,
            4
        )

        final.append(
            item
        )

    # Safety check terakhir.
    total = sum(
        x["margin_usd"]
        for x in final
    )

    if total > budget and total > 0:

        scale = (
            budget / total
        )

        for x in final:

            x["margin_usd"] = round(
                x["margin_usd"]
                * scale,
                4
            )

    return final


# =========================================================
# PNL CALCULATION
# =========================================================

def calculate_pnl_pct(
    side,
    entry_price,
    current_price,
    leverage
):

    if not entry_price:
        return 0

    if entry_price <= 0:
        return 0

    if side == "LONG":

        price_change = (
            current_price
            - entry_price
        ) / entry_price

    else:

        price_change = (
            entry_price
            - current_price
        ) / entry_price

    return (
        price_change
        * leverage
        * 100
    )


def calculate_pnl_usd(
    pnl_pct,
    margin_usd
):

    return (
        margin_usd
        * pnl_pct
        / 100
    )
    # =========================================================
# SAVE RESULTS
# =========================================================

def save_results(results):

    if not results:
        return

    con = connect_db()

    for x in results:

        con.execute("""
            INSERT INTO history (
                timestamp,
                pair,
                outlook,
                movement,
                volatility,
                entry_low,
                entry_high,
                tp,
                sl,
                confidence,
                status,
                pnl_pct,
                leverage,
                margin_usd,
                trade_pnl_usd,
                entry_price,
                exit_price
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, 'OPEN', 0,
                ?, ?, 0, ?, NULL
            )
        """, (
            x["timestamp"],
            x["pair"],
            x["outlook"],
            x["movement"],
            x["volatility"],
            x["entry_low"],
            x["entry_high"],
            x["tp"],
            x["sl"],
            x["confidence"],
            x.get(
                "leverage",
                1
            ),
            x.get(
                "margin_usd",
                0
            ),
            x.get(
                "entry_price"
            )
        ))

    con.commit()
    con.close()


# =========================================================
# RESOLVE OPEN TRADES
# =========================================================

def resolve_history():

    con = connect_db()

    rows = con.execute("""
        SELECT
            id,
            pair,
            outlook,
            entry_low,
            entry_high,
            tp,
            sl,
            leverage,
            margin_usd,
            entry_price
        FROM history
        WHERE status = 'OPEN'
    """).fetchall()

    if not rows:

        con.close()
        return

    prices = get_live_prices()

    for row in rows:

        trade_id = row[0]
        pair = row[1]
        side = row[2]

        entry_low = row[3]
        entry_high = row[4]

        tp = row[5]
        sl = row[6]

        leverage = (
            row[7]
            if row[7] is not None
            else 1
        )

        margin = (
            row[8]
            if row[8] is not None
            else 0
        )

        entry = row[9]

        if entry is None:

            if side == "LONG":
                entry = entry_high
            else:
                entry = entry_low

        if not entry:
            continue

        current = prices.get(
            pair + "-SWAP"
        )

        if current is None:
            continue

        status = None
        exit_price = None

        if side == "LONG":

            if current >= tp:

                status = "SUCCESS"
                exit_price = tp

            elif current <= sl:

                status = "LOSS"
                exit_price = sl

        else:

            if current <= tp:

                status = "SUCCESS"
                exit_price = tp

            elif current >= sl:

                status = "LOSS"
                exit_price = sl

        if status is None:
            continue

        pnl_pct = calculate_pnl_pct(
            side,
            entry,
            exit_price,
            leverage
        )

        pnl_usd = calculate_pnl_usd(
            pnl_pct,
            margin
        )

        con.execute("""
            UPDATE history
            SET
                status = ?,
                pnl_pct = ?,
                trade_pnl_usd = ?,
                resolved_at = ?,
                exit_price = ?
            WHERE id = ?
        """, (
            status,
            pnl_pct,
            pnl_usd,
            datetime.now(
                timezone.utc
            ).isoformat(),
            exit_price,
            trade_id
        ))

    con.commit()
    con.close()


# =========================================================
# PORTFOLIO STATUS
# =========================================================

def get_portfolio_status():

    history = get_history()

    if history.empty:

        return {
            "initial": DEMO_INITIAL_BALANCE,
            "used": 0,
            "available": DEMO_MAX_MARGIN,
            "realized": 0,
            "floating": 0,
            "equity": DEMO_INITIAL_BALANCE,
            "open": 0
        }

    open_trades = history[
        history["status"] == "OPEN"
    ].copy()

    closed_trades = history[
        history["status"].isin(
            [
                "SUCCESS",
                "LOSS"
            ]
        )
    ].copy()

    used = (
        open_trades[
            "margin_usd"
        ]
        .fillna(0)
        .sum()
    )

    # Hard cap.
    used = min(
        float(used),
        DEMO_MAX_MARGIN
    )

    realized = (
        closed_trades[
            "trade_pnl_usd"
        ]
        .fillna(0)
        .sum()
    )

    floating = 0

    prices = get_live_prices()

    for _, trade in open_trades.iterrows():

        entry = trade.get(
            "entry_price"
        )

        if pd.isna(entry):
            continue

        current = prices.get(
            trade["pair"]
            + "-SWAP"
        )

        if current is None:
            continue

        leverage = float(
            trade.get(
                "leverage",
                1
            )
            or 1
        )

        margin = float(
            trade.get(
                "margin_usd",
                0
            )
            or 0
        )

        pnl_pct = calculate_pnl_pct(
            trade["outlook"],
            float(entry),
            current,
            leverage
        )

        floating += calculate_pnl_usd(
            pnl_pct,
            margin
        )

    # Equity bisa berubah karena PNL,
    # tetapi batas margin portfolio tetap $10.
    equity = (
        DEMO_INITIAL_BALANCE
        + realized
        + floating
    )

    # Available margin selalu berdasarkan
    # pool $10, bukan equity.
    available = max(
        DEMO_MAX_MARGIN - used,
        0
    )

    return {
        "initial": DEMO_INITIAL_BALANCE,
        "used": used,
        "available": available,
        "realized": realized,
        "floating": floating,
        "equity": equity,
        "open": len(open_trades)
    }


# =========================================================
# SESSION
# =========================================================

if "results" not in st.session_state:
    st.session_state.results = []

if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = None

if "last_scan" not in st.session_state:
    st.session_state.last_scan = "-"
    # =========================================================
# SCREEN NOW
# =========================================================

if st.button(
    "⚡ SCREEN NOW",
    use_container_width=True
):

    with st.spinner(
        "Menganalisis market & mengalokasikan portfolio $10..."
    ):

        results = screening()

    # Cek posisi OPEN saat ini.
    used_margin = get_used_margin()

    available = max(
        DEMO_MAX_MARGIN
        - used_margin,
        0
    )

    # Hanya gunakan margin yang benar-benar tersedia.
    allocated = allocate_portfolio(
        results,
        available
    )

    st.session_state.results = (
        allocated
    )

    st.session_state.last_scan = (
        datetime.now().strftime(
            "%H:%M:%S"
        )
    )

    save_results(
        allocated
    )

    clean_db()

    st.rerun()


st.caption(
    f"Last screening: "
    f"{st.session_state.last_scan}"
)


# =========================================================
# RESOLVE
# =========================================================

resolve_history()


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
# CARD
# =========================================================

def show_card(
    x,
    key,
    icon
):

    with st.container(border=True):

        st.subheader(
            x["pair"]
        )

        st.write(
            f"**Entry:** "
            f"{x['entry_low']:.8g}"
            f" → "
            f"{x['entry_high']:.8g}"
        )

        st.write(
            f"**Take Profit:** "
            f"{x['tp']:.8g}"
        )

        st.write(
            f"**Stop Loss:** "
            f"{x['sl']:.8g}"
        )

        st.caption(
            f"Movement: "
            f"{x['movement']:.2f}%"
        )

        st.caption(
            f"Volatility: "
            f"{x['volatility']:.2f}%"
        )

        st.caption(
            f"Confidence: "
            f"{x['confidence']:.0f}%"
        )

        st.caption(
            f"Portfolio Margin: "
            f"${x.get('margin_usd', 0):.4f}"
        )

        st.caption(
            f"Leverage: "
            f"{x.get('leverage', 1):.0f}x"
        )

        if st.button(
            f"{icon} Open Chart • {x['pair']}",
            key=key,
            use_container_width=True
        ):

            st.session_state.selected_pair = (
                x["pair"]
            )

            st.rerun()


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

    for i, x in enumerate(
        longs
    ):

        show_card(
            x,
            f"long_{i}_{x['pair']}",
            "📈"
        )


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

    for i, x in enumerate(
        shorts
    ):

        show_card(
            x,
            f"short_{i}_{x['pair']}",
            "📉"
        )


# =========================================================
# TRADINGVIEW
# =========================================================

if st.session_state.selected_pair:

    pair = (
        st.session_state.selected_pair
    )

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
        style="height:650px;width:100%;">
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
        "container_id": "tradingview_chart"
    }});
    </script>
    """

    components.html(
        html,
        height=670
    )


# =========================================================
# REALTIME DEMO AUTO TRADE
# =========================================================

@st.fragment(run_every="3s")
def realtime_demo():

    resolve_history()

    portfolio = get_portfolio_status()

    st.divider()

    st.subheader(
        "🤖 Demo Auto Trade"
    )

    a, b, c, d, e = st.columns(5)

    with a:

        st.metric(
            "Total Assets",
            f"${portfolio['initial']:.2f}"
        )

    with b:

        st.metric(
            "Used Margin",
            f"${portfolio['used']:.4f}"
        )

    with c:

        st.metric(
            "Available",
            f"${portfolio['available']:.4f}"
        )

    with d:

        st.metric(
            "Floating P/L",
            f"${portfolio['floating']:+.4f}"
        )

    with e:

        st.metric(
            "Equity",
            f"${portfolio['equity']:.4f}"
        )

    st.caption(
        f"Open positions: "
        f"{portfolio['open']}"
        f" • Maximum total margin: "
        f"${DEMO_MAX_MARGIN:.2f}"
    )

    st.caption(
        "LBank status: DEMO / SIMULATED"
        " • Tidak mengirim real order."
    )

    history = get_history()

    if history.empty:
        return

    open_trades = history[
        history["status"] == "OPEN"
    ].copy()

    prices = get_live_prices()

    rows = []

    for _, trade in open_trades.iterrows():

        entry = trade.get(
            "entry_price"
        )

        if pd.isna(entry):
            continue

        entry = float(entry)

        current = prices.get(
            trade["pair"]
            + "-SWAP"
        )

        if current is None:
            continue

        leverage = float(
            trade.get(
                "leverage",
                1
            )
            or 1
        )

        margin = float(
            trade.get(
                "margin_usd",
                0
            )
            or 0
        )

        pnl_pct = calculate_pnl_pct(
            trade["outlook"],
            entry,
            current,
            leverage
        )

        pnl_usd = calculate_pnl_usd(
            pnl_pct,
            margin
        )

        rows.append({
            "Pair":
                trade["pair"],

            "Side":
                trade["outlook"],

            "Entry":
                entry,

            "Current":
                current,

            "Margin $":
                margin,

            "Leverage":
                f"{leverage:.0f}x",

            "Profit %":
                pnl_pct,

            "PNL $":
                pnl_usd,

            "Status":
                "OPEN"
        })

    if rows:

        live_df = pd.DataFrame(
            rows
        )

        live_df["Entry"] = (
            live_df["Entry"].round(8)
        )

        live_df["Current"] = (
            live_df["Current"].round(8)
        )

        live_df["Margin $"] = (
            live_df["Margin $"].round(4)
        )

        live_df["Profit %"] = (
            live_df["Profit %"].round(2)
        )

        live_df["PNL $"] = (
            live_df["PNL $"].round(4)
        )

        st.dataframe(
            live_df[
                [
                    "Pair",
                    "Side",
                    "Entry",
                    "Current",
                    "Margin $",
                    "Leverage",
                    "Profit %",
                    "PNL $",
                    "Status"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Tidak ada posisi OPEN."
        )


realtime_demo()


# =========================================================
# 24H PERFORMANCE
# =========================================================

st.divider()

st.subheader(
    "24H Performance"
)

perf = get_history()

if perf.empty:

    st.info(
        "Belum ada data performance 24 jam."
    )

else:

    success = perf[
        perf["status"] == "SUCCESS"
    ]

    losses = perf[
        perf["status"] == "LOSS"
    ]

    opened = perf[
        perf["status"] == "OPEN"
    ]

    total_profit_usd = (
        success[
            "trade_pnl_usd"
        ]
        .fillna(0)
        .sum()
        if not success.empty
        else 0
    )

    total_loss_usd = (
        losses[
            "trade_pnl_usd"
        ]
        .fillna(0)
        .sum()
        if not losses.empty
        else 0
    )

    net_pnl_usd = (
        total_profit_usd
        + total_loss_usd
    )

    # =====================================================
    # PROFIT %
    #
    # ROI terhadap margin trade.
    # Contoh:
    # margin $2
    # profit $2
    # = +100%
    # =====================================================

    closed_margin = (
        perf[
            perf["status"].isin(
                [
                    "SUCCESS",
                    "LOSS"
                ]
            )
        ]["margin_usd"]
        .fillna(0)
        .sum()
    )

    profit_pct = (
        net_pnl_usd
        / closed_margin
        * 100
        if closed_margin > 0
        else 0
    )

    closed = (
        len(success)
        + len(losses)
    )

    winrate = (
        len(success)
        / closed
        * 100
        if closed
        else 0
    )

    a, b, c, d, e = st.columns(5)

    with a:

        st.metric(
            "SUCCESS",
            len(success)
        )

    with b:

        st.metric(
            "LOSS",
            len(losses)
        )

    with c:

        st.metric(
            "WIN RATE",
            f"{winrate:.2f}%"
        )

    with d:

        st.metric(
            "PROFIT",
            f"{profit_pct:+.2f}%"
        )

    with e:

        st.metric(
            "PNL 24H",
            f"${net_pnl_usd:+.4f}"
        )

    st.caption(
        f"Gross Profit: "
        f"${total_profit_usd:+.4f}"
        f" • "
        f"Gross Loss: "
        f"${total_loss_usd:+.4f}"
    )

    st.caption(
        f"Open trades: {len(opened)}"
    )


    # =====================================================
    # HISTORY TABLE
    # =====================================================

    display = perf.copy()

    display["timestamp"] = (
        pd.to_datetime(
            display["timestamp"],
            utc=True
        )
        .dt.tz_convert(
            "Asia/Jakarta"
        )
        .dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    display = display.rename(
        columns={
            "timestamp":
                "Time",

            "pair":
                "Pair",

            "outlook":
                "Outlook",

            "entry_price":
                "Entry",

            "exit_price":
                "Exit",

            "tp":
                "TP",

            "sl":
                "SL",

            "leverage":
                "Leverage",

            "margin_usd":
                "Margin $",

            "pnl_pct":
                "Profit %",

            "trade_pnl_usd":
                "PNL $",

            "status":
                "Status"
        }
    )

    for column in [
        "Entry",
        "Exit",
        "TP",
        "SL",
        "Leverage",
        "Margin $",
        "Profit %",
        "PNL $"
    ]:

        if column in display.columns:

            display[column] = pd.to_numeric(
                display[column],
                errors="coerce"
            )

    display["Entry"] = (
        display["Entry"].round(8)
    )

    display["Exit"] = (
        display["Exit"].round(8)
    )

    display["TP"] = (
        display["TP"].round(8)
    )

    display["SL"] = (
        display["SL"].round(8)
    )

    display["Leverage"] = (
        display["Leverage"].round(0)
    )

    display["Margin $"] = (
        display["Margin $"].round(4)
    )

    display["Profit %"] = (
        display["Profit %"].round(2)
    )

    display["PNL $"] = (
        display["PNL $"].round(4)
    )

    st.dataframe(
        display[
            [
                "Time",
                "Pair",
                "Outlook",
                "Entry",
                "Exit",
                "TP",
                "SL",
                "Leverage",
                "Margin $",
                "Status",
                "Profit %",
                "PNL $"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Informational scanner — DYOR."
)
