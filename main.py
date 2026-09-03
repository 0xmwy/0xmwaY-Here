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
# DEMO AUTO TRADE
# =========================================================

DEMO_MARGIN = 1.0

DEMO_MODE = True

LEVERAGE_MIN = 2
LEVERAGE_MAX = 20


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
        "margin_usd": "REAL DEFAULT 1",
        "trade_pnl_usd": "REAL DEFAULT 0",
        "entry_price": "REAL"
    }

    for name, typ in additions.items():

        if name not in cols:

            con.execute(
                f"ALTER TABLE history ADD COLUMN {name} {typ}"
            )

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
                entry_price
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, 'OPEN', 0,
                ?, ?, 0, ?
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
            x.get("leverage", 1),
            DEMO_MARGIN,
            x.get("entry_price")
        ))

    con.commit()
    con.close()


def get_history():

    con = connect_db()

    df = pd.read_sql_query(
        "SELECT * FROM history ORDER BY timestamp DESC",
        con
    )

    con.close()

    return df


init_db()
migrate_db()
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
# TICKERS
# =========================================================

@st.cache_data(ttl=30)
def get_tickers():

    data = api(
        "/api/v5/market/tickers",
        {"instType": "SWAP"}
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
def get_candles(inst, bar):

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
# DEMO LEVERAGE
# =========================================================

def calculate_demo_leverage(
    confidence,
    volatility
):

    if confidence >= 90 and volatility <= 5:
        return 20

    if confidence >= 90 and volatility <= 8:
        return 15

    if confidence >= 80 and volatility <= 5:
        return 12

    if confidence >= 80 and volatility <= 8:
        return 10

    if confidence >= 70 and volatility <= 5:
        return 8

    if confidence >= 70 and volatility <= 8:
        return 5

    if volatility > 12:
        return 2

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
        price * (vol / 100) * 0.20,
        price * 0.001
    )

    if side == "LONG":

        entry_low = price - distance
        entry_high = price
        tp = price + distance * 2
        sl = price - distance

    else:

        entry_low = price
        entry_high = price + distance
        tp = price - distance * 2
        sl = price + distance

    confidence = (
        max(longs, shorts)
        / len(tf)
        * 100
    )

    leverage = calculate_demo_leverage(
        confidence,
        vol
    )

    return {
        "outlook": side,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "tp": tp,
        "sl": sl,
        "confidence": confidence,
        "leverage": leverage,
        "entry_price": price
            }
    # =========================================================
# SCREENING
# =========================================================

def screening():

    tickers = get_tickers()

    if tickers.empty:
        return []

    movers = top_movers(tickers)

    results = []

    for _, mover in movers.iterrows():

        result = analyze_coin(
            mover["inst"]
        )

        if not result:
            continue

        now = datetime.now(timezone.utc)

        results.append({
            "timestamp": now.isoformat(),
            "pair": mover["pair"],
            "outlook": result["outlook"],
            "movement": mover["movement"],
            "volatility": mover["volatility"],
            "entry_low": result["entry_low"],
            "entry_high": result["entry_high"],
            "tp": result["tp"],
            "sl": result["sl"],
            "confidence": result["confidence"],
            "leverage": result["leverage"],
            "entry_price": result["entry_price"]
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
# DEMO AUTO TRADE
# =========================================================

def demo_trade_info(
    outlook,
    entry_price,
    current_price,
    leverage
):

    if entry_price <= 0:
        return 0

    if outlook == "LONG":

        price_change = (
            current_price - entry_price
        ) / entry_price

    else:

        price_change = (
            entry_price - current_price
        ) / entry_price

    pnl_pct = (
        price_change
        * leverage
        * 100
    )

    return pnl_pct


# =========================================================
# CHECK PROFIT / LOSS
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

    for row in rows:

        trade_id = row[0]
        pair = row[1]
        side = row[2]
        entry_low = row[3]
        entry_high = row[4]
        tp = row[5]
        sl = row[6]
        leverage = row[7] or 1
        margin_usd = row[8] or DEMO_MARGIN
        entry_price = row[9]

        if sl is None:
            continue

        if entry_price is None:

            if side == "LONG":
                entry_price = entry_high
            else:
                entry_price = entry_low

        df = get_candles(
            pair + "-SWAP",
            "15m"
        )

        if df.empty:
            continue

        current = float(
            df["close"].iloc[-1]
        )

        status = None
        pnl_pct = 0

        if side == "LONG":

            if current >= tp:

                status = "SUCCESS"

                raw_move = (
                    tp - entry_price
                ) / entry_price

                pnl_pct = (
                    raw_move
                    * leverage
                    * 100
                )

            elif current <= sl:

                status = "LOSS"

                raw_move = (
                    sl - entry_price
                ) / entry_price

                pnl_pct = (
                    raw_move
                    * leverage
                    * 100
                )

        else:

            if current <= tp:

                status = "SUCCESS"

                raw_move = (
                    entry_price - tp
                ) / entry_price

                pnl_pct = (
                    raw_move
                    * leverage
                    * 100
                )

            elif current >= sl:

                status = "LOSS"

                raw_move = (
                    entry_price - sl
                ) / entry_price

                pnl_pct = (
                    raw_move
                    * leverage
                    * 100
                )

        trade_pnl_usd = (
            margin_usd
            * pnl_pct
            / 100
        )

        if status:

            con.execute("""
                UPDATE history
                SET
                    status = ?,
                    pnl_pct = ?,
                    trade_pnl_usd = ?,
                    resolved_at = ?
                WHERE id = ?
            """, (
                status,
                pnl_pct,
                trade_pnl_usd,
                datetime.now(
                    timezone.utc
                ).isoformat(),
                trade_id
            ))

    con.commit()
    con.close()


# =========================================================
# DEMO ACCOUNT SUMMARY
# =========================================================

def get_demo_summary():

    history = get_history()

    if history.empty:

        return {
            "trades": 0,
            "success": 0,
            "loss": 0,
            "open": 0,
            "profit_pct": 0,
            "loss_pct": 0,
            "net_pnl": 0
        }

    success = history[
        history["status"] == "SUCCESS"
    ]

    losses = history[
        history["status"] == "LOSS"
    ]

    opened = history[
        history["status"] == "OPEN"
    ]

    profit_pct = (
        success["pnl_pct"].sum()
        if not success.empty
        else 0
    )

    loss_pct = (
        losses["pnl_pct"].sum()
        if not losses.empty
        else 0
    )

    net_pnl = (
        history["trade_pnl_usd"].sum()
        if "trade_pnl_usd" in history.columns
        else 0
    )

    return {
        "trades": len(history),
        "success": len(success),
        "loss": len(losses),
        "open": len(opened),
        "profit_pct": profit_pct,
        "loss_pct": loss_pct,
        "net_pnl": net_pnl
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
        "Mencari coin volatile..."
    ):

        results = screening()

    st.session_state.results = results

    st.session_state.last_scan = (
        datetime.now().strftime(
            "%H:%M:%S"
        )
    )

    save_results(results)

    clean_db()

    st.rerun()


st.caption(
    f"Last screening: "
    f"{st.session_state.last_scan}"
)


# =========================================================
# UPDATE PROFIT / LOSS
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

def show_card(x, key, icon):

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
            f"Demo Leverage: "
            f"{x.get('leverage', 1):.0f}x"
        )

        st.caption(
            f"Demo Margin: "
            f"${DEMO_MARGIN:.2f}"
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

    for i, x in enumerate(longs):

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

    for i, x in enumerate(shorts):

        show_card(
            x,
            f"short_{i}_{x['pair']}",
            "📉"
        )


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
# HISTORY 24 HOURS
# =========================================================

st.divider()

st.subheader(
    "Screening History — 24 Hours"
)

clean_db()

history = get_history()

if history.empty:

    st.info(
        "Belum ada history screening."
    )

else:

    display = history.copy()

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
            "timestamp": "Time",
            "pair": "Pair",
            "outlook": "Outlook",
            "movement": "Movement %",
            "volatility": "Volatility %",
            "entry_low": "Entry Low",
            "entry_high": "Entry High",
            "tp": "Take Profit",
            "sl": "Stop Loss",
            "confidence": "Confidence %",
            "status": "Status",
            "pnl_pct": "P/L %",
            "leverage": "Leverage",
            "margin_usd": "Margin $",
            "trade_pnl_usd": "Trade P/L $"
        }
    )

    display["Movement %"] = (
        display["Movement %"].round(2)
    )

    display["Volatility %"] = (
        display["Volatility %"].round(2)
    )

    display["Confidence %"] = (
        display["Confidence %"].round(0)
    )

    display["P/L %"] = (
        display["P/L %"].round(2)
    )

    display["Leverage"] = (
        display["Leverage"].round(0)
    )

    display["Margin $"] = (
        display["Margin $"].round(2)
    )

    display["Trade P/L $"] = (
        display["Trade P/L $"].round(4)
    )

    st.dataframe(
        display[
            [
                "Time",
                "Pair",
                "Outlook",
                "Movement %",
                "Volatility %",
                "Entry Low",
                "Entry High",
                "Take Profit",
                "Stop Loss",
                "Confidence %",
                "Leverage",
                "Margin $",
                "Status",
                "P/L %",
                "Trade P/L $"
            ]
        ],
        use_container_width=True,
        hide_index=True
            )
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

    total_profit = (
        success["pnl_pct"].sum()
    )

    total_loss = (
        losses["pnl_pct"].sum()
    )

    net_pnl = (
        perf["trade_pnl_usd"].sum()
        if "trade_pnl_usd" in perf.columns
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
            f"+{total_profit:.2f}%"
        )

    with e:

        st.metric(
            "NET P/L",
            f"${net_pnl:+.4f}"
        )

    st.caption(
        f"Open trades: {len(opened)}"
    )


    # =====================================================
    # SUCCESS PAIRS
    # =====================================================

    st.markdown(
        "### ✅ Pair Sukses"
    )

    if success.empty:

        st.info(
            "Belum ada pair yang mencapai TP."
        )

    else:

        s = success[
            [
                "pair",
                "outlook",
                "pnl_pct",
                "trade_pnl_usd",
                "leverage",
                "resolved_at"
            ]
        ].copy()

        s.columns = [
            "Pair",
            "Outlook",
            "Profit %",
            "Profit $",
            "Leverage",
            "Resolved"
        ]

        s["Profit %"] = (
            s["Profit %"].round(2)
        )

        s["Profit $"] = (
            s["Profit $"].round(4)
        )

        s["Leverage"] = (
            s["Leverage"].round(0)
        )

        s["Resolved"] = (
            pd.to_datetime(
                s["Resolved"],
                utc=True
            )
            .dt.tz_convert(
                "Asia/Jakarta"
            )
            .dt.strftime(
                "%H:%M:%S"
            )
        )

        st.dataframe(
            s,
            use_container_width=True,
            hide_index=True
        )


    # =====================================================
    # LOSS PAIRS
    # =====================================================

    st.markdown(
        "### ❌ Pair Loss"
    )

    if losses.empty:

        st.info(
            "Belum ada pair yang terkena SL."
        )

    else:

        l = losses[
            [
                "pair",
                "outlook",
                "pnl_pct",
                "trade_pnl_usd",
                "leverage",
                "resolved_at"
            ]
        ].copy()

        l.columns = [
            "Pair",
            "Outlook",
            "Loss %",
            "Loss $",
            "Leverage",
            "Resolved"
        ]

        l["Loss %"] = (
            l["Loss %"].round(2)
        )

        l["Loss $"] = (
            l["Loss $"].round(4)
        )

        l["Leverage"] = (
            l["Leverage"].round(0)
        )

        l["Resolved"] = (
            pd.to_datetime(
                l["Resolved"],
                utc=True
            )
            .dt.tz_convert(
                "Asia/Jakarta"
            )
            .dt.strftime(
                "%H:%M:%S"
            )
        )

        st.dataframe(
            l,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# DEMO AUTO TRADE STATUS
# =========================================================

st.divider()

st.subheader(
    "🤖 Auto Trade — Demo"
)

summary = get_demo_summary()

x1, x2, x3, x4 = st.columns(4)

with x1:

    st.metric(
        "Demo Trades",
        summary["trades"]
    )

with x2:

    st.metric(
        "Profit %",
        f"+{summary['profit_pct']:.2f}%"
    )

with x3:

    st.metric(
        "Loss %",
        f"{summary['loss_pct']:.2f}%"
    )

with x4:

    st.metric(
        "PNL 24H",
        f"${summary['net_pnl']:+.4f}"
    )

st.caption(
    "LBank status: DEMO / SIMULATED"
)

st.caption(
    f"Margin per trade: ${DEMO_MARGIN:.2f} • "
    f"Leverage: {LEVERAGE_MIN}x–{LEVERAGE_MAX}x • "
    "No real orders are sent."
)


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Informational scanner — DYOR."
        )
