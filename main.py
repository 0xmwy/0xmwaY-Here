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
BARS = {"15M": "15m", "30M": "30m", "1H": "1H"}
MAX_MOVER = 12


# =========================
# STYLE
# =========================

st.markdown("""
<style>
.block-container{padding-top:2rem}
.card{
    border:1px solid rgba(128,128,128,.25);
    border-radius:12px;
    padding:15px;
    margin-bottom:10px;
}
</style>
""", unsafe_allow_html=True)

st.title("0xmwY Kraken")
st.caption("pengembang : Lutfi Andreyansah")
st.caption('"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"')


# =========================
# DATABASE
# =========================

def conn():
    return sqlite3.connect(DB)


def init_db():
    c = conn()
    c.execute("""
    CREATE TABLE IF NOT EXISTS history(
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
    c.commit()
    c.close()


def clean_db():
    cut = (
        datetime.now(timezone.utc)
        - timedelta(hours=24)
    ).isoformat()

    c = conn()
    c.execute(
        "DELETE FROM history WHERE timestamp < ?",
        (cut,)
    )
    c.commit()
    c.close()


def save_results(results):
    if not results:
        return

    c = conn()

    for x in results:
        c.execute("""
        INSERT INTO history(
            timestamp,pair,outlook,movement,volatility,
            entry_low,entry_high,tp,sl,confidence
        )
        VALUES(?,?,?,?,?,?,?,?,?,?)
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
            x["confidence"]
        ))

    c.commit()
    c.close()


def get_history():
    c = conn()

    df = pd.read_sql_query(
        "SELECT * FROM history ORDER BY timestamp DESC",
        c
    )

    c.close()
    return df


init_db()
clean_db()


# =========================
# API
# =========================

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


# =========================
# MARKET DATA
# =========================

@st.cache_data(ttl=30)
def tickers():
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

        move = (price - op) / op * 100
        vol = (high - low) / op * 100

        rows.append({
            "inst": inst,
            "pair": inst.replace("-SWAP", ""),
            "price": price,
            "movement": move,
            "abs_move": abs(move),
            "volatility": vol
        })

    return pd.DataFrame(rows)


def top_movers(df):
    if df.empty:
        return df

    df = df.copy()

    mm = max(df.abs_move.max(), 0.000001)
    vm = max(df.volatility.max(), 0.000001)

    df["score"] = (
        df.abs_move / mm * .60
        + df.volatility / vm * .40
    )

    return (
        df.sort_values(
            "score",
            ascending=False
        )
        .head(MAX_MOVER)
        .reset_index(drop=True)
    )


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

    for x in data:
        try:
            rows.append({
                "open": float(x[1]),
                "high": float(x[2]),
                "low": float(x[3]),
                "close": float(x[4]),
                "volume": float(x[5])
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


# =========================
# ANALYSIS
# =========================

def analyze_tf(df):
    if len(df) < 30:
        return None

    close = df.close

    e9 = close.ewm(
        span=9,
        adjust=False
    ).mean()

    e21 = close.ewm(
        span=21,
        adjust=False
    ).mean()

    momentum = (
        (close.iloc[-1] - close.iloc[-6])
        / close.iloc[-6]
    ) * 100

    bull = 0
    bear = 0

    if e9.iloc[-1] > e21.iloc[-1]:
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

    side = "LONG" if bull > bear else "SHORT"
    confidence = max(bull, bear) / 3 * 100

    high = close.tail(20).max()
    low = close.tail(20).min()

    volatility = (
        (high - low)
        / close.iloc[-1]
    ) * 100

    return {
        "side": side,
        "price": close.iloc[-1],
        "confidence": confidence,
        "volatility": volatility
    }


def analyze_coin(inst):
    results = {}

    for name, bar in BARS.items():
        df = candles(inst, bar)
        r = analyze_tf(df)

        if r:
            results[name] = r

    if len(results) < 2:
        return None

    longs = sum(
        r["side"] == "LONG"
        for r in results.values()
    )

    shorts = sum(
        r["side"] == "SHORT"
        for r in results.values()
    )

    if longs >= 2:
        side = "LONG"
    elif shorts >= 2:
        side = "SHORT"
    else:
        return None

    price = list(results.values())[-1]["price"]

    vol = sum(
        r["volatility"]
        for r in results.values()
    ) / len(results)

    distance = max(
        price * vol / 100 * .20,
        price * .001
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
        / len(results)
        * 100
    )

    return {
        "outlook": side,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "tp": tp,
        "sl": sl,
        "confidence": confidence
    }


# =========================
# SCREENING
# =========================

def screening():
    df = tickers()

    if df.empty:
        return []

    movers = top_movers(df)
    results = []

    for _, m in movers.iterrows():
        r = analyze_coin(m["inst"])

        if not r:
            continue

        now = datetime.now(timezone.utc)

        results.append({
            "timestamp": now.isoformat(),
            "pair": m["pair"],
            "outlook": r["outlook"],
            "movement": m["movement"],
            "volatility": m["volatility"],
            "entry_low": r["entry_low"],
            "entry_high": r["entry_high"],
            "tp": r["tp"],
            "sl": r["sl"],
            "confidence": r["confidence"]
        })

    return sorted(
        results,
        key=lambda x: (
            x["confidence"],
            abs(x["movement"])
        ),
        reverse=True
    )


# =========================
# CHECK SUCCESS / LOSS
# =========================

def resolve_history():
    c = conn()

    rows = c.execute("""
    SELECT
        id,pair,outlook,
        entry_low,entry_high,tp,sl
    FROM history
    WHERE status='OPEN'
    """).fetchall()

    for row in rows:
        trade_id, pair, side, elo, ehi, tp, sl = row

        df = candles(
            pair + "-SWAP",
            "15m"
        )

        if df.empty:
            continue

        price = float(df.close.iloc[-1])

        result = None
        pnl = 0

        if side == "LONG":
            if price >= tp:
                result = "SUCCESS"
                pnl = (tp - ehi) / ehi * 100
            elif price <= sl:
                result = "LOSS"
                pnl = (sl - ehi) / ehi * 100

        else:
            if price <= tp:
                result = "SUCCESS"
                pnl = (elo - tp) / elo * 100
            elif price >= sl:
                result = "LOSS"
                pnl = (elo - sl) / elo * 100

        if result:
            c.execute("""
            UPDATE history
            SET status=?,
                pnl_pct=?,
                resolved_at=?
            WHERE id=?
            """, (
                result,
                pnl,
                datetime.now(
                    timezone.utc
                ).isoformat(),
                trade_id
            ))

    c.commit()
    c.close()


# =========================
# SESSION
# =========================

if "results" not in st.session_state:
    st.session_state.results = []

if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = None

if "last_scan" not in st.session_state:
    st.session_state.last_scan = "-"


# =========================
# SCREEN BUTTON
# =========================

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
        datetime.now().strftime("%H:%M:%S")
    )

    save_results(result)
    st.rerun()

st.caption(
    f"Last screening: {st.session_state.last_scan}"
)


# =========================
# UPDATE TRADE STATUS
# =========================

resolve_history()


# =========================
# OUTLOOK
# =========================

st.divider()
st.subheader("Current Outlook")

results = st.session_state.results

longs = [
    x for x in results
    if x["outlook"] == "LONG"
]

shorts = [
    x for x in results
    if x["outlook"] == "SHORT"
]

left, right = st.columns(2)


def show_card(x, key, icon):
    with st.container(border=True):

        st.markdown(
            f"### {x['pair']}"
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
            f"Movement {x['movement']:.2f}%  •  "
            f"Volatility {x['volatility']:.2f}%  •  "
            f"Confidence {x['confidence']:.0f}%"
        )

        if st.button(
            f"{icon} Open Chart • {x['pair']}",
            key=key,
            use_container_width=True
        ):
            st.session_state.selected_pair = x["pair"]
            st.rerun()


with left:
    st.markdown("### 🟢 OUTLOOK LONG")

    if not longs:
        st.info("Belum ada setup LONG.")

    for i, x in enumerate(longs):
        show_card(
            x,
            f"long_{i}_{x['pair']}",
            "📈"
        )


with right:
    st.markdown("### 🔴 OUTLOOK SHORT")

    if not shorts:
        st.info("Belum ada setup SHORT.")

    for i, x in enumerate(shorts):
        show_card(
            x,
            f"short_{i}_{x['pair']}",
            "📉"
        )


# =========================
# TRADINGVIEW
# =========================

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
    <div id="tv" style="height:650px;width:100%"></div>

    <script src="https://s3.tradingview.com/tv.js"></script>

    <script>
    new TradingView.widget({{
        autosize:true,
        symbol:"{symbol}",
        interval:"15",
        timezone:"Asia/Jakarta",
        theme:"dark",
        style:"1",
        locale:"en",
        enable_publishing:false,
        hide_top_toolbar:false,
        hide_legend:false,
        save_image:false,
        container_id:"tv"
    }});
    </script>
    """

    components.html(
        html,
        height=670
    )


# =========================
# HISTORY 24H
# =========================

st.divider()
st.subheader(
    "Screening History — 24 Hours"
)

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
            "pnl_pct": "P/L %"
        }
    )

    for col in [
        "Movement %",
        "Volatility %",
        "P/L %"
    ]:
        display[col] = display[col].round(2)

    display["Confidence %"] = (
        display["Confidence %"].round(0)
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
                "Status",
                "P/L %"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )


# =========================
# 24H PERFORMANCE
# =========================

st.divider()
st.subheader("24H Performance")

perf = get_history()

if perf.empty:

    st.info(
        "Belum ada data performance."
    )

else:

    success = perf[
        perf.status == "SUCCESS"
    ]

    loss = perf[
        perf.status == "LOSS"
    ]

    opened = perf[
        perf.status == "OPEN"
    ]

    closed = len(success) + len(loss)

    winrate = (
        len(success) / closed * 100
        if closed else 0
    )

    profit = success.pnl_pct.sum()
    loss_total = loss.pnl_pct.sum()
    net = profit + loss_total

    a, b, c, d, e = st.columns(5)

    a.metric("SUCCESS", len(success))
    b.metric("LOSS", len(loss))
    c.metric("WIN RATE", f"{winrate:.2f}%")
    d.metric("PROFIT", f"+{profit:.2f}%")
    e.metric("NET P/L", f"{net:+.2f}%")

    st.caption(
        f"Open trades: {len(opened)}"
    )

    # -------------------------
    # SUCCESS
    # -------------------------

    st.markdown("### ✅ Pair Sukses")

    if success.empty:

        st.info(
            "Belum ada pair yang sukses."
        )

    else:

        s = success[
            [
                "pair",
                "outlook",
                "pnl_pct",
                "resolved_at"
            ]
        ].copy()

        s.columns = [
            "Pair",
            "Outlook",
            "Profit %",
            "Resolved"
        ]

        s["Profit %"] = s["Profit %"].round(2)

        s["Resolved"] = (
            pd.to_datetime(
                s["Resolved"],
                utc=True
            )
            .dt.tz_convert(
                "Asia/Jakarta"
            )
            .dt.strftime("%H:%M:%S")
        )

        st.dataframe(
            s,
            use_container_width=True,
            hide_index=True
        )

    # -------------------------
    # LOSS
    # -------------------------

    st.markdown("### ❌ Pair Loss")

    if loss.empty:

        st.info(
            "Belum ada pair yang loss."
        )

    else:

        l = loss[
            [
                "pair",
                "outlook",
                "pnl_pct",
                "resolved_at"
            ]
        ].copy()

        l.columns = [
            "Pair",
            "Outlook",
            "Loss %",
            "Resolved"
        ]

        l["Loss %"] = l["Loss %"].round(2)

        l["Resolved"] = (
            pd.to_datetime(
                l["Resolved"],
                utc=True
            )
            .dt.tz_convert(
                "Asia/Jakarta"
            )
            .dt.strftime("%H:%M:%S")
        )

        st.dataframe(
            l,
            use_container_width=True,
            hide_index=True
        )


# =========================
# FOOTER
# =========================

st.divider()
st.caption("Informational scanner — DYOR.")
