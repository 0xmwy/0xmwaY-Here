import streamlit as st
import streamlit.components.v1 as components
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
# DATABASE
# =========================================================

def connect_db():
    return sqlite3.connect(DB)


def init_db():
    conn = connect_db()

    conn.execute("""
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
            status TEXT,
            pnl_pct REAL,
            resolved_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def migrate_db():
    conn = connect_db()

    columns = {
        "movement": "REAL",
        "volatility": "REAL",
        "entry_low": "REAL",
        "entry_high": "REAL",
        "tp": "REAL",
        "sl": "REAL",
        "confidence": "REAL",
        "status": "TEXT",
        "pnl_pct": "REAL",
        "resolved_at": "TEXT"
    }

    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(history)").fetchall()
    }

    for column, dtype in columns.items():
        if column not in existing:
            conn.execute(
                f"ALTER TABLE history ADD COLUMN {column} {dtype}"
            )

    conn.commit()
    conn.close()


def clean_db():
    conn = connect_db()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    conn.execute(
        "DELETE FROM history WHERE timestamp < ?",
        (cutoff.isoformat(),)
    )

    conn.commit()
    conn.close()


def save_results(results):
    if not results:
        return

    conn = connect_db()

    now = datetime.now(timezone.utc).isoformat()

    for r in results:
        conn.execute("""
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
                resolved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now,
            r["pair"],
            r["outlook"],
            r["movement"],
            r["volatility"],
            r["entry_low"],
            r["entry_high"],
            r["tp"],
            r["sl"],
            r["confidence"],
            "OPEN",
            None,
            None
        ))

    conn.commit()
    conn.close()


def get_history():
    conn = connect_db()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM history
        ORDER BY timestamp DESC
        """,
        conn
    )

    conn.close()

    return df


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
# MARKET DATA
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

        inst_id = x.get("instId", "")

        if not inst_id.endswith("-USDT-SWAP"):
            continue

        try:
            last = float(x["last"])
            open24 = float(x["open24h"])
            high24 = float(x["high24h"])
            low24 = float(x["low24h"])

            if open24 <= 0:
                continue

            movement = ((last - open24) / open24) * 100

            volatility = (
                ((high24 - low24) / low24) * 100
                if low24 > 0
                else 0
            )

            pair = inst_id.replace("-SWAP", "")

            rows.append({
                "pair": pair,
                "inst_id": inst_id,
                "price": last,
                "movement": movement,
                "volatility": volatility
            })

        except Exception:
            continue

    return pd.DataFrame(rows)


def top_movers(df):

    if df.empty:
        return df

    temp = df.copy()

    movement_abs = temp["movement"].abs()

    if movement_abs.max() > 0:
        movement_score = (
            movement_abs / movement_abs.max()
        )
    else:
        movement_score = 0

    if temp["volatility"].max() > 0:
        volatility_score = (
            temp["volatility"] / temp["volatility"].max()
        )
    else:
        volatility_score = 0

    temp["score"] = (
        movement_score * 0.60
        + volatility_score * 0.40
    )

    return (
        temp
        .sort_values("score", ascending=False)
        .head(MAX_MOVER)
        .reset_index(drop=True)
    )


@st.cache_data(ttl=30)
def get_candles(inst_id, bar):

    data = api(
        "/api/v5/market/candles",
        {
            "instId": inst_id,
            "bar": bar,
            "limit": "80"
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for x in reversed(data):

        try:
            rows.append({
                "timestamp": int(x[0]),
                "open": float(x[1]),
                "high": float(x[2]),
                "low": float(x[3]),
                "close": float(x[4]),
                "volume": float(x[5])
            })
        except Exception:
            continue

    return pd.DataFrame(rows)


# =========================================================
# TIMEFRAME ANALYSIS
# =========================================================

def analyze_tf(inst_id, timeframe):

    df = get_candles(
        inst_id,
        TIMEFRAMES[timeframe]
    )

    if df.empty or len(df) < 25:
        return None

    df["ema9"] = (
        df["close"]
        .ewm(span=9, adjust=False)
        .mean()
    )

    df["ema21"] = (
        df["close"]
        .ewm(span=21, adjust=False)
        .mean()
    )

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    price = latest["close"]

    momentum = (
        (latest["close"] - previous["close"])
        / previous["close"]
        * 100
    )

    candle_direction = (
        "UP"
        if latest["close"] > latest["open"]
        else "DOWN"
    )

    ema_bullish = latest["ema9"] > latest["ema21"]

    ema_bearish = latest["ema9"] < latest["ema21"]

    bullish_points = 0
    bearish_points = 0

    if ema_bullish:
        bullish_points += 1

    if ema_bearish:
        bearish_points += 1

    if momentum > 0:
        bullish_points += 1

    if momentum < 0:
        bearish_points += 1

    if candle_direction == "UP":
        bullish_points += 1

    if candle_direction == "DOWN":
        bearish_points += 1

    if bullish_points > bearish_points:
        side = "LONG"
        confidence = bullish_points / 3

    elif bearish_points > bullish_points:
        side = "SHORT"
        confidence = bearish_points / 3

    else:
        side = "NEUTRAL"
        confidence = 0

    volatility = (
        (df["high"].tail(20).max()
         - df["low"].tail(20).min())
        / price
        * 100
    )

    return {
        "timeframe": timeframe,
        "side": side,
        "confidence": confidence,
        "price": price,
        "momentum": momentum,
        "volatility": volatility
    }


# =========================================================
# COIN ANALYSIS
# =========================================================

def analyze_coin(row):

    analyses = []

    for timeframe in TIMEFRAMES:

        result = analyze_tf(
            row["inst_id"],
            timeframe
        )

        if result:
            analyses.append(result)

    if len(analyses) < 2:
        return None

    long_count = sum(
        1 for x in analyses
        if x["side"] == "LONG"
    )

    short_count = sum(
        1 for x in analyses
        if x["side"] == "SHORT"
    )

    total = len(analyses)

    if long_count >= 2:

        outlook = "LONG"
        agreement = long_count

    elif short_count >= 2:

        outlook = "SHORT"
        agreement = short_count

    else:

        return None

    price = float(row["price"])

    avg_volatility = (
        sum(x["volatility"] for x in analyses)
        / len(analyses)
    )

    # Distance menggunakan volatility timeframe
    distance = price * (
        avg_volatility / 100
    ) * 0.10

    if distance <= 0:
        distance = price * 0.005

    if outlook == "LONG":

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

    confidence = agreement / total

    return {
        "pair": row["pair"],
        "outlook": outlook,
        "movement": row["movement"],
        "volatility": row["volatility"],
        "entry_low": entry_low,
        "entry_high": entry_high,
        "tp": tp,
        "sl": sl,
        "confidence": confidence,
        "analyses": analyses
    }


# =========================================================
# SCREENING
# =========================================================

def screening():

    market = get_tickers()

    if market.empty:
        return []

    movers = top_movers(market)

    results = []

    for _, row in movers.iterrows():

        try:
            result = analyze_coin(row)

            if result:
                results.append(result)

        except Exception:
            continue

    return results
    # =========================================================
# RESOLVE HISTORY
# =========================================================

def resolve_history():

    conn = connect_db()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM history
        WHERE status = 'OPEN'
        """,
        conn
    )

    if df.empty:
        conn.close()
        return

    for _, row in df.iterrows():

        try:

            pair = row["pair"]

            inst_id = pair + "-SWAP"

            candles = get_candles(
                inst_id,
                "15m"
            )

            if candles.empty:
                continue

            latest_price = float(
                candles.iloc[-1]["close"]
            )

            outlook = row["outlook"]

            tp = float(row["tp"])
            sl = float(row["sl"])
            entry = float(row["entry_high"])

            status = None
            pnl = None

            if outlook == "LONG":

                if latest_price >= tp:

                    status = "SUCCESS"

                    pnl = (
                        (tp - entry)
                        / entry
                        * 100
                    )

                elif latest_price <= sl:

                    status = "LOSS"

                    pnl = (
                        (sl - entry)
                        / entry
                        * 100
                    )

            elif outlook == "SHORT":

                if latest_price <= tp:

                    status = "SUCCESS"

                    pnl = (
                        (entry - tp)
                        / entry
                        * 100
                    )

                elif latest_price >= sl:

                    status = "LOSS"

                    pnl = (
                        (entry - sl)
                        / entry
                        * 100
                    )

            if status:

                conn.execute(
                    """
                    UPDATE history
                    SET
                        status = ?,
                        pnl_pct = ?,
                        resolved_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        pnl,
                        datetime.now(
                            timezone.utc
                        ).isoformat(),
                        row["id"]
                    )
                )

        except Exception:
            continue

    conn.commit()
    conn.close()


# =========================================================
# INIT
# =========================================================

init_db()
migrate_db()
clean_db()
resolve_history()


# =========================================================
# SESSION STATE
# =========================================================

if "results" not in st.session_state:
    st.session_state.results = []

if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = None

if "last_scan" not in st.session_state:
    st.session_state.last_scan = "-"


# =========================================================
# HEADER
# =========================================================

st.title("⚡ 0xmwY Kraken")

st.caption(
    "pengembang : Lutfi Andreyansah"
)

st.write(
    '"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"'
)


# =========================================================
# SCREEN BUTTON
# =========================================================

col1, col2 = st.columns([1, 4])

with col1:

    scan = st.button(
        "🔍 SCREEN NOW",
        use_container_width=True
    )

if scan:

    with st.spinner(
        "Scanning market..."
    ):

        results = screening()

        st.session_state.results = results

        st.session_state.last_scan = (
            datetime.now()
            .strftime("%Y-%m-%d %H:%M:%S")
        )

        if results:
            save_results(results)

        st.rerun()


with col2:

    st.caption(
        f"Last scan: {st.session_state.last_scan}"
    )


# =========================================================
# CURRENT OUTLOOK
# =========================================================

st.divider()

st.header("CURRENT OUTLOOK")

results = st.session_state.results

if not results:

    st.info(
        "Klik SCREEN NOW untuk mulai screening."
    )

else:

    for r in results:

        with st.container(border=True):

            top1, top2, top3 = st.columns(
                [2, 1, 1]
            )

            with top1:

                st.subheader(
                    r["pair"]
                )

                st.caption(
                    f"Movement 24H: "
                    f"{r['movement']:+.2f}%"
                )

            with top2:

                if r["outlook"] == "LONG":

                    st.success(
                        f"LONG  "
                        f"{r['confidence'] * 100:.0f}%"
                    )

                else:

                    st.error(
                        f"SHORT  "
                        f"{r['confidence'] * 100:.0f}%"
                    )

            with top3:

                if st.button(
                    "📈 Open Chart",
                    key=f"chart_{r['pair']}"
                ):

                    st.session_state.selected_pair = (
                        r["pair"]
                    )

                    st.rerun()

            c1, c2, c3, c4 = st.columns(4)

            with c1:

                st.metric(
                    "Entry",
                    f"{r['entry_low']:.8g} - "
                    f"{r['entry_high']:.8g}"
                )

            with c2:

                st.metric(
                    "TP",
                    f"{r['tp']:.8g}"
                )

            with c3:

                st.metric(
                    "SL",
                    f"{r['sl']:.8g}"
                )

            with c4:

                st.metric(
                    "Volatility",
                    f"{r['volatility']:.2f}%"
                )

            st.caption(
                "Timeframe agreement"
            )

            tf_cols = st.columns(3)

            for i, analysis in enumerate(
                r["analyses"][:3]
            ):

                with tf_cols[i]:

                    side = analysis["side"]

                    if side == "LONG":

                        st.success(
                            f"{analysis['timeframe']}: "
                            f"LONG"
                        )

                    elif side == "SHORT":

                        st.error(
                            f"{analysis['timeframe']}: "
                            f"SHORT"
                        )

                    else:

                        st.warning(
                            f"{analysis['timeframe']}: "
                            f"NEUTRAL"
                        )

                    st.caption(
                        f"Momentum: "
                        f"{analysis['momentum']:+.2f}%"
                    )


# =========================================================
# TRADINGVIEW CHART
# =========================================================

if st.session_state.selected_pair:

    st.divider()

    st.header(
        f"CHART — "
        f"{st.session_state.selected_pair}"
    )

    tv_symbol = (
        "OKX:"
        + st.session_state.selected_pair
        .replace("-USDT", "USDT")
        + ".P"
    )

    chart_html = f"""
    <div style="
        width:100%;
        height:650px;
        border-radius:12px;
        overflow:hidden;
    ">

        <iframe
            src="https://www.tradingview.com/widgetembed/?
            symbol={tv_symbol}
            &interval=15
            &hidesidetoolbar=0
            &symboledit=1
            &saveimage=1
            &toolbarbg=f1f3f6
            &studies=[]
            &theme=dark
            &style=1
            &timezone=Asia%2FJakarta"
            style="
                width:100%;
                height:100%;
                border:none;
            ">
        </iframe>

    </div>
    """

    components.html(
        chart_html,
        height=660
    )


# =========================================================
# HISTORY
# =========================================================

st.divider()

st.header("SCREENING HISTORY — 24H")

history = get_history()

if history.empty:

    st.info(
        "Belum ada history screening."
    )

else:

    display_history = history.copy()

    display_history["timestamp"] = (
        pd.to_datetime(
            display_history["timestamp"],
            errors="coerce"
        )
        .dt.strftime("%Y-%m-%d %H:%M")
    )

    display_history["confidence"] = (
        display_history["confidence"]
        .apply(
            lambda x:
            f"{x * 100:.0f}%"
            if pd.notna(x)
            else "-"
        )
    )

    display_history["movement"] = (
        display_history["movement"]
        .apply(
            lambda x:
            f"{x:+.2f}%"
            if pd.notna(x)
            else "-"
        )
    )

    display_history["volatility"] = (
        display_history["volatility"]
        .apply(
            lambda x:
            f"{x:.2f}%"
            if pd.notna(x)
            else "-"
        )
    )

    display_history["pnl_pct"] = (
        display_history["pnl_pct"]
        .apply(
            lambda x:
            f"{x:+.2f}%"
            if pd.notna(x)
            else "-"
        )
    )

    st.dataframe(
        display_history[
            [
                "timestamp",
                "pair",
                "outlook",
                "movement",
                "volatility",
                "entry_low",
                "entry_high",
                "tp",
                "sl",
                "confidence",
                "status",
                "pnl_pct"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 24H PERFORMANCE
# =========================================================

st.divider()

st.header("24H PERFORMANCE")

history = get_history()

if history.empty:

    st.info(
        "Belum ada data performance."
    )

else:

    success = int(
        (history["status"] == "SUCCESS")
        .sum()
    )

    loss = int(
        (history["status"] == "LOSS")
        .sum()
    )

    open_count = int(
        (history["status"] == "OPEN")
        .sum()
    )

    resolved = success + loss

    if resolved > 0:

        winrate = (
            success
            / resolved
            * 100
        )

    else:

        winrate = 0

    pnl_series = pd.to_numeric(
        history["pnl_pct"],
        errors="coerce"
    )

    total_pnl = (
        pnl_series
        .fillna(0)
        .sum()
    )

    perf1, perf2, perf3, perf4 = (
        st.columns(4)
    )

    with perf1:

        st.metric(
            "SUCCESS",
            success
        )

    with perf2:

        st.metric(
            "LOSS",
            loss
        )

    with perf3:

        st.metric(
            "WINRATE",
            f"{winrate:.2f}%"
        )

    with perf4:

        st.metric(
            "NET P/L",
            f"{total_pnl:+.2f}%"
        )

    st.subheader(
        "SUCCESS PAIRS"
    )

    success_pairs = (
        history[
            history["status"] == "SUCCESS"
        ]["pair"]
        .drop_duplicates()
        .tolist()
    )

    if success_pairs:

        st.write(
            ", ".join(success_pairs)
        )

    else:

        st.caption(
            "Belum ada pair yang TP."
        )

    st.subheader(
        "LOSS PAIRS"
    )

    loss_pairs = (
        history[
            history["status"] == "LOSS"
        ]["pair"]
        .drop_duplicates()
        .tolist()
    )

    if loss_pairs:

        st.write(
            ", ".join(loss_pairs)
        )

    else:

        st.caption(
            "Belum ada pair yang terkena SL."
        )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Informational scanner — DYOR."
    )
