import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import sqlite3
import hashlib
import hmac
import secrets
import math
from datetime import datetime, timedelta, timezone


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="0xmwY Kraken",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

BASE = "https://www.okx.com"
LBANK_BASE = "https://lbkperp.lbank.com"
DB = "screening_history.db"

TIMEFRAMES = {
    "15M": "15m",
    "30M": "30m",
    "1H": "1H"
}


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(
        DB,
        check_same_thread=False
    )


def init_db():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS screening_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            pair TEXT,
            timeframe TEXT,
            outlook TEXT,
            entry_low REAL,
            entry_high REAL,
            take_profit REAL,
            stop_loss REAL,
            current_price REAL,
            movement REAL,
            volatility REAL,
            confidence REAL,
            status TEXT DEFAULT 'OPEN',
            pnl_percent REAL DEFAULT 0
        )
    """)

    conn.commit()

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=24)
    ).isoformat()

    cur.execute(
        """
        DELETE FROM screening_history
        WHERE timestamp < ?
        """,
        (cutoff,)
    )

    conn.commit()
    conn.close()


init_db()


# =========================================================
# HTTP SESSION
# =========================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9"
})


# =========================================================
# GENERIC GET
# =========================================================

def api_get(
    url,
    params=None,
    timeout=15
):

    try:

        r = session.get(
            url,
            params=params,
            timeout=timeout
        )

        if r.status_code != 200:
            return None

        return r.json()

    except Exception:
        return None


# =========================================================
# OKX MARKET DATA
# =========================================================

@st.cache_data(ttl=60)
def get_swap_instruments():

    data = api_get(
        f"{BASE}/api/v5/public/instruments",
        {
            "instType": "SWAP"
        }
    )

    if not data or data.get("code") != "0":
        return []

    symbols = []

    for item in data.get("data", []):

        inst_id = item.get("instId", "")

        if not inst_id.endswith(
            "-USDT-SWAP"
        ):
            continue

        if item.get("state") != "live":
            continue

        base_coin = inst_id.replace(
            "-USDT-SWAP",
            ""
        )

        symbols.append({
            "instId": inst_id,
            "pair": f"{base_coin}-USDT"
        })

    return symbols


@st.cache_data(ttl=30)
def get_tickers():

    data = api_get(
        f"{BASE}/api/v5/market/tickers",
        {
            "instType": "SWAP"
        }
    )

    if not data or data.get("code") != "0":
        return pd.DataFrame()

    rows = []

    for x in data.get("data", []):

        inst_id = x.get(
            "instId",
            ""
        )

        if not inst_id.endswith(
            "-USDT-SWAP"
        ):
            continue

        try:

            last = float(
                x.get("last", 0)
            )

            open24 = float(
                x.get("open24h", 0)
            )

            high24 = float(
                x.get("high24h", 0)
            )

            low24 = float(
                x.get("low24h", 0)
            )

            volume = float(
                x.get("volCcy24h", 0)
            )

            if last <= 0 or open24 <= 0:
                continue

            change = (
                (last - open24)
                / open24
            ) * 100

            range_pct = (
                (high24 - low24)
                / last
            ) * 100

            rows.append({
                "instId": inst_id,
                "pair": inst_id.replace(
                    "-SWAP",
                    ""
                ),
                "price": last,
                "change24h": change,
                "range24h": range_pct,
                "volume": volume
            })

        except Exception:
            continue

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return (
        df.sort_values(
            "volume",
            ascending=False
        )
        .reset_index(drop=True)
    )


@st.cache_data(ttl=30)
def get_candles(
    inst_id,
    bar="15m",
    limit=120
):

    data = api_get(
        f"{BASE}/api/v5/market/candles",
        {
            "instId": inst_id,
            "bar": bar,
            "limit": str(limit)
        }
    )

    if not data or data.get("code") != "0":
        return pd.DataFrame()

    rows = data.get(
        "data",
        []
    )

    if not rows:
        return pd.DataFrame()

    records = []

    for x in rows:

        try:

            records.append({
                "timestamp": int(x[0]),
                "open": float(x[1]),
                "high": float(x[2]),
                "low": float(x[3]),
                "close": float(x[4]),
                "volume": float(x[5])
            })

        except Exception:
            continue

    df = pd.DataFrame(records)

    if df.empty:
        return df

    return (
        df.sort_values(
            "timestamp"
        )
        .reset_index(drop=True)
    )


# =========================================================
# INDICATORS
# =========================================================

def calculate_atr(
    df,
    period=14
):

    prev_close = df["close"].shift(1)

    tr1 = (
        df["high"]
        - df["low"]
    )

    tr2 = (
        df["high"]
        - prev_close
    ).abs()

    tr3 = (
        df["low"]
        - prev_close
    ).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    return tr.rolling(
        period
    ).mean()


def calculate_indicators(df):

    if df.empty:
        return df

    out = df.copy()

    out["ema20"] = (
        out["close"]
        .ewm(
            span=20,
            adjust=False
        )
        .mean()
    )

    out["ema50"] = (
        out["close"]
        .ewm(
            span=50,
            adjust=False
        )
        .mean()
    )

    out["sma20"] = (
        out["close"]
        .rolling(20)
        .mean()
    )

    out["std20"] = (
        out["close"]
        .rolling(20)
        .std()
    )

    out["upper_band"] = (
        out["sma20"]
        + 2 * out["std20"]
    )

    out["lower_band"] = (
        out["sma20"]
        - 2 * out["std20"]
    )

    delta = out["close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain
        .rolling(14)
        .mean()
    )

    avg_loss = (
        loss
        .rolling(14)
        .mean()
    )

    rs = (
        avg_gain
        / avg_loss.replace(
            0,
            math.nan
        )
    )

    out["rsi"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    out["atr"] = calculate_atr(
        out,
        14
    )

    return out
    # =========================================================
# FORMAT
# =========================================================

def fmt_price(value):

    if value is None:
        return "-"

    try:
        value = float(value)
    except Exception:
        return "-"

    if value >= 1000:
        return f"{value:,.2f}"

    if value >= 1:
        return f"{value:,.4f}"

    if value >= 0.01:
        return f"{value:,.6f}"

    return f"{value:.8f}"


def fmt_pct(value):

    if value is None:
        return "-"

    try:
        return f"{float(value):.2f}%"
    except Exception:
        return "-"


# =========================================================
# MARKET ANALYSIS
# =========================================================

def analyze_market(
    inst_id,
    pair,
    timeframe
):

    bar = TIMEFRAMES.get(
        timeframe,
        "15m"
    )

    df = get_candles(
        inst_id,
        bar,
        120
    )

    if df.empty or len(df) < 60:
        return None

    df = calculate_indicators(df)

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    price = float(
        latest["close"]
    )

    ema20 = float(
        latest["ema20"]
    )

    ema50 = float(
        latest["ema50"]
    )

    rsi = latest["rsi"]
    atr = latest["atr"]

    if pd.isna(rsi) or pd.isna(atr):
        return None

    rsi = float(rsi)
    atr = float(atr)

    if price <= 0:
        return None

    atr_pct = (
        atr / price
    ) * 100

    ema_distance = (
        (ema20 - ema50)
        / price
    ) * 100

    previous_close = float(
        previous["close"]
    )

    momentum = (
        (price - previous_close)
        / previous_close
    ) * 100

    # =====================================================
    # SCORE
    # =====================================================

    long_score = 0
    short_score = 0

    if ema20 > ema50:
        long_score += 2
    elif ema20 < ema50:
        short_score += 2

    if price > ema20:
        long_score += 1
    else:
        short_score += 1

    if 50 <= rsi <= 70:
        long_score += 2

    elif 30 <= rsi < 50:
        short_score += 1

    elif rsi > 70:
        short_score += 1

    elif rsi < 30:
        long_score += 1

    if momentum > 0:
        long_score += 1

    elif momentum < 0:
        short_score += 1

    if ema_distance > 0.15:
        long_score += 1

    elif ema_distance < -0.15:
        short_score += 1

    # =====================================================
    # OUTLOOK
    # =====================================================

    if long_score >= short_score:

        outlook = "LONG"
        score = long_score

    else:

        outlook = "SHORT"
        score = short_score

    confidence = min(
        95,
        max(
            50,
            50 + score * 6
        )
    )

    # =====================================================
    # TP / SL
    # =====================================================

    risk_distance = max(
        atr * 1.2,
        price * 0.003
    )

    reward_distance = (
        risk_distance * 1.8
    )

    if outlook == "LONG":

        entry_low = (
            price - atr * 0.25
        )

        entry_high = (
            price + atr * 0.15
        )

        stop_loss = (
            price - risk_distance
        )

        take_profit = (
            price + reward_distance
        )

    else:

        entry_low = (
            price - atr * 0.15
        )

        entry_high = (
            price + atr * 0.25
        )

        stop_loss = (
            price + risk_distance
        )

        take_profit = (
            price - reward_distance
        )

    return {
        "pair": pair,
        "inst_id": inst_id,
        "timeframe": timeframe,
        "outlook": outlook,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "current_price": price,
        "movement": momentum,
        "volatility": atr_pct,
        "confidence": confidence,
        "rsi": rsi,
        "ema20": ema20,
        "ema50": ema50
    }


# =========================================================
# TOP MOVERS
# =========================================================

def select_top_movers(
    ticker_df,
    count=15
):

    if ticker_df.empty:
        return pd.DataFrame()

    df = ticker_df.copy()

    df["activity_score"] = (
        df["change24h"].abs()
        * 0.65
        +
        df["range24h"]
        * 0.35
    )

    return (
        df.sort_values(
            "activity_score",
            ascending=False
        )
        .head(count)
        .reset_index(drop=True)
    )


# =========================================================
# SAVE SIGNAL
# =========================================================

def save_signal(result):

    conn = get_db()
    cur = conn.cursor()

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    cur.execute(
        """
        INSERT INTO screening_history (
            timestamp,
            pair,
            timeframe,
            outlook,
            entry_low,
            entry_high,
            take_profit,
            stop_loss,
            current_price,
            movement,
            volatility,
            confidence,
            status,
            pnl_percent
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            result["pair"],
            result["timeframe"],
            result["outlook"],
            result["entry_low"],
            result["entry_high"],
            result["take_profit"],
            result["stop_loss"],
            result["current_price"],
            result["movement"],
            result["volatility"],
            result["confidence"],
            "OPEN",
            0
        )
    )

    conn.commit()
    conn.close()


def get_history():

    conn = get_db()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM screening_history
        ORDER BY id DESC
        """,
        conn
    )

    conn.close()

    return df


# =========================================================
# PERFORMANCE
# =========================================================

def update_performance():

    conn = get_db()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM screening_history
        WHERE status = 'OPEN'
        """,
        conn
    )

    if df.empty:

        conn.close()
        return

    cur = conn.cursor()

    for _, row in df.iterrows():

        try:

            created = datetime.fromisoformat(
                row["timestamp"]
            )

            if created.tzinfo is None:

                created = created.replace(
                    tzinfo=timezone.utc
                )

            now = datetime.now(
                timezone.utc
            )

            age = now - created

            inst_id = (
                str(row["pair"])
                .replace(
                    "-USDT",
                    "-USDT-SWAP"
                )
            )

            bar = TIMEFRAMES.get(
                row["timeframe"],
                "15m"
            )

            candles = get_candles(
                inst_id,
                bar,
                100
            )

            if candles.empty:
                continue

            signal_price = float(
                row["current_price"]
            )

            tp = float(
                row["take_profit"]
            )

            sl = float(
                row["stop_loss"]
            )

            outlook = row["outlook"]

            status = "OPEN"
            pnl = 0

            signal_ts = (
                created.timestamp()
                * 1000
            )

            candles = candles[
                candles["timestamp"]
                >= signal_ts
            ]

            for _, candle in candles.iterrows():

                high = float(
                    candle["high"]
                )

                low = float(
                    candle["low"]
                )

                if outlook == "LONG":

                    if low <= sl:

                        status = "LOSS"

                        pnl = (
                            (sl - signal_price)
                            / signal_price
                        ) * 100

                        break

                    if high >= tp:

                        status = "SUCCESS"

                        pnl = (
                            (tp - signal_price)
                            / signal_price
                        ) * 100

                        break

                else:

                    if high >= sl:

                        status = "LOSS"

                        pnl = (
                            (signal_price - sl)
                            / signal_price
                        ) * 100

                        break

                    if low <= tp:

                        status = "SUCCESS"

                        pnl = (
                            (signal_price - tp)
                            / signal_price
                        ) * 100

                        break

            if (
                status == "OPEN"
                and age >= timedelta(hours=24)
            ):

                last_price = (
                    float(
                        candles.iloc[-1]["close"]
                    )
                    if not candles.empty
                    else signal_price
                )

                if outlook == "LONG":

                    pnl = (
                        (last_price - signal_price)
                        / signal_price
                    ) * 100

                else:

                    pnl = (
                        (signal_price - last_price)
                        / signal_price
                    ) * 100

                status = (
                    "SUCCESS"
                    if pnl > 0
                    else "LOSS"
                )

            cur.execute(
                """
                UPDATE screening_history
                SET status = ?, pnl_percent = ?
                WHERE id = ?
                """,
                (
                    status,
                    pnl,
                    int(row["id"])
                )
            )

        except Exception:
            continue

    conn.commit()
    conn.close()


# =========================================================
# LBANK SIGNATURE
# =========================================================

def lbank_signature(
    params,
    secret_key
):

    clean = {
        k: v
        for k, v in params.items()
        if k != "sign"
    }

    sorted_params = sorted(
        clean.items(),
        key=lambda x: x[0]
    )

    query_string = "&".join(
        f"{k}={v}"
        for k, v in sorted_params
    )

    md5_hash = hashlib.md5(
        query_string.encode()
    ).hexdigest().upper()

    signature = hmac.new(
        secret_key.encode(),
        md5_hash.encode(),
        hashlib.sha256
    ).hexdigest()

    return signature
    # =========================================================
# LBANK SERVER TIME
# =========================================================

def lbank_get_timestamp():

    try:

        r = session.get(
            f"{LBANK_BASE}/cfd/openApi/v1/pub/getTime",
            timeout=10
        )

        result = {
            "http_status": r.status_code,
            "content_type": r.headers.get(
                "content-type"
            ),
            "server": r.headers.get(
                "server"
            )
        }

        try:

            data = r.json()

            result["response"] = data

        except Exception:

            result["response"] = (
                r.text[:2000]
            )

        if r.status_code != 200:

            return None, result

        try:

            data = r.json()

            timestamp = (
                data.get("data", {})
                .get("timestamp")
                or
                data.get("data", {})
                .get("ts")
                or
                data.get("data", {})
                .get("time")
                or
                data.get("timestamp")
                or
                data.get("ts")
            )

            if timestamp:

                return str(timestamp), result

        except Exception:
            pass

        return (
            str(
                int(
                    datetime.now()
                    .timestamp()
                    * 1000
                )
            ),
            result
        )

    except Exception as e:

        return None, {
            "error": str(e)
        }


# =========================================================
# LBANK PRIVATE CONNECTION
# =========================================================

def lbank_test_connection():

    try:

        api_key = st.secrets[
            "LBANK_API_KEY"
        ]

        secret_key = st.secrets[
            "LBANK_SECRET_KEY"
        ]

    except Exception:

        return {
            "success": False,
            "stage": "Streamlit Secrets",
            "error": (
                "LBANK_API_KEY atau "
                "LBANK_SECRET_KEY "
                "tidak ditemukan."
            )
        }

    timestamp, time_debug = (
        lbank_get_timestamp()
    )

    if not timestamp:

        return {
            "success": False,
            "stage": "LBank public time API",
            "debug": time_debug
        }

    echostr = secrets.token_hex(20)

    params = {
        "api_key": api_key,
        "asset": "USDT",
        "productGroup": "SwapU",
        "signature_method": "HmacSHA256",
        "timestamp": timestamp,
        "echostr": echostr
    }

    sign = lbank_signature(
        params,
        secret_key
    )

    params["sign"] = sign

    headers = {
        "Content-Type": "application/json",
        "timestamp": timestamp,
        "signature_method": "HmacSHA256",
        "echostr": echostr
    }

    try:

        r = session.post(
            f"{LBANK_BASE}/cfd/openApi/v1/prv/account",
            json=params,
            headers=headers,
            timeout=15
        )

    except Exception as e:

        return {
            "success": False,
            "stage": "LBank account API",
            "error": str(e)
        }

    try:

        data = r.json()

        if r.status_code == 200:

            return {
                "success": True,
                "stage": "LBank account API",
                "http_status": r.status_code,
                "response": data
            }

        return {
            "success": False,
            "stage": "LBank account API",
            "http_status": r.status_code,
            "response": data
        }

    except Exception:

        return {
            "success": False,
            "stage": "LBank account API",
            "http_status": r.status_code,
            "content_type": r.headers.get(
                "content-type"
            ),
            "server": r.headers.get(
                "server"
            ),
            "response": r.text[:3000]
        }


# =========================================================
# CHECK SERVER IP
# =========================================================

def get_server_ip():

    try:

        r = requests.get(
            "https://api.ipify.org?format=json",
            timeout=10
        )

        result = {
            "http_status": r.status_code
        }

        try:

            result["response"] = r.json()

        except Exception:

            result["response"] = r.text

        return result

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }


# =========================================================
# TEST LBANK PUBLIC
# =========================================================

def test_lbank_public():

    urls = [
        (
            "LBank Contract API",
            "https://lbkperp.lbank.com/"
            "cfd/openApi/v1/pub/getTime"
        ),
        (
            "LBank Website",
            "https://www.lbank.com"
        )
    ]

    results = []

    for label, url in urls:

        try:

            r = requests.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/131.0.0.0 "
                        "Safari/537.36"
                    ),
                    "Accept": (
                        "application/json,"
                        "text/plain,*/*"
                    ),
                    "Accept-Language": (
                        "en-US,en;q=0.9"
                    )
                },
                timeout=15
            )

            results.append({
                "test": label,
                "url": url,
                "http_status": r.status_code,
                "content_type": (
                    r.headers.get(
                        "content-type"
                    )
                ),
                "server": (
                    r.headers.get(
                        "server"
                    )
                ),
                "response_preview": (
                    r.text[:1000]
                )
            })

        except Exception as e:

            results.append({
                "test": label,
                "url": url,
                "error": str(e)
            })

    return results


# =========================================================
# TRADINGVIEW
# =========================================================

def show_tradingview(pair):

    if not pair:
        return

    symbol = pair.replace(
        "-USDT",
        "USDT"
    )

    html = f"""
    <div style="
        width:100%;
        height:600px;
        border-radius:12px;
        overflow:hidden;
    ">

        <div
            class="tradingview-widget-container"
            style="height:100%;width:100%"
        >

            <div
                id="tradingview_chart"
                style="height:100%;width:100%"
            ></div>

            <script
                type="text/javascript"
                src="https://s3.tradingview.com/tv.js">
            </script>

            <script type="text/javascript">

            new TradingView.widget({{
                "autosize": true,
                "symbol": "OKX:{symbol}.P",
                "interval": "15",
                "timezone": "Asia/Jakarta",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "allow_symbol_change": true,
                "container_id": "tradingview_chart"
            }});

            </script>

        </div>
    </div>
    """

    components.html(
        html,
        height=620
    )


# =========================================================
# HEADER
# =========================================================

st.title(
    "⚡ 0xmwY Kraken"
)

st.caption(
    "pengembang : Lutfi Andreyansah"
)

st.caption(
    '"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"'
)

st.divider()


# =========================================================
# LBANK CONNECTION
# =========================================================

st.subheader(
    "LBank Connection"
)

col1, col2, col3 = st.columns(3)


with col1:

    if st.button(
        "🌐 CHECK SERVER IP",
        use_container_width=True
    ):

        st.json(
            get_server_ip()
        )


with col2:

    if st.button(
        "🔎 TEST LBANK PUBLIC",
        use_container_width=True
    ):

        public_result = (
            test_lbank_public()
        )

        st.json(
            public_result
        )


with col3:

    if st.button(
        "🔗 TEST LBANK CONNECTION",
        use_container_width=True
    ):

        with st.spinner(
            "Testing LBank connection..."
        ):

            result = (
                lbank_test_connection()
            )

        if result.get("success"):

            st.success(
                "✅ LBank connection successful."
            )

        else:

            st.error(
                "❌ LBank connection failed."
            )

        st.json(result)


st.divider()


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header(
        "Scanner Settings"
    )

    selected_timeframe = st.selectbox(
        "Timeframe",
        ["15M", "30M", "1H"],
        index=0
    )

    number_of_candidates = st.slider(
        "Top candidates",
        min_value=5,
        max_value=25,
        value=12
    )

    run_scan = st.button(
        "🚀 RUN SCANNER",
        use_container_width=True
    )

    st.caption(
        "Scanner hanya membaca market data."
    )

    st.caption(
        "Auto trading belum diaktifkan."
        )
    # =========================================================
# UPDATE PERFORMANCE
# =========================================================

try:

    update_performance()

except Exception:

    pass


# =========================================================
# MARKET SCANNER
# =========================================================

st.subheader(
    "Market Scanner"
)

if run_scan:

    with st.spinner(
        "Scanning market..."
    ):

        tickers = get_tickers()

        if tickers.empty:

            st.error(
                "Gagal mengambil market data."
            )

        else:

            candidates = (
                select_top_movers(
                    tickers,
                    number_of_candidates
                )
            )

            results = []

            progress = st.progress(0)

            total = len(candidates)

            for index, row in (
                candidates.iterrows()
            ):

                result = analyze_market(
                    row["instId"],
                    row["pair"],
                    selected_timeframe
                )

                if result:

                    results.append(
                        result
                    )

                progress.progress(
                    int(
                        (
                            (index + 1)
                            / total
                        )
                        * 100
                    )
                )

            progress.empty()

            if not results:

                st.warning(
                    "Tidak ada setup yang "
                    "memenuhi kondisi."
                )

            else:

                results = sorted(
                    results,
                    key=lambda x: x[
                        "confidence"
                    ],
                    reverse=True
                )

                st.session_state[
                    "scan_results"
                ] = results

                for result in results[:10]:

                    save_signal(
                        result
                    )

                st.success(
                    f"Scanner selesai — "
                    f"{len(results)} setup ditemukan."
                )


# =========================================================
# CURRENT OUTLOOK
# =========================================================

scan_results = (
    st.session_state.get(
        "scan_results",
        []
    )
)


if scan_results:

    st.subheader(
        "Current Outlook"
    )

    for result in scan_results:

        outlook = result[
            "outlook"
        ]

        if outlook == "LONG":

            icon = "🟢"

        else:

            icon = "🔴"

        st.markdown(
            f"### {icon} "
            f"{result['pair']} — "
            f"OUTLOOK {outlook}"
        )

        col1, col2, col3 = st.columns(3)

        with col1:

            st.metric(
                "Current Price",
                fmt_price(
                    result[
                        "current_price"
                    ]
                )
            )

            st.metric(
                "Movement",
                fmt_pct(
                    result[
                        "movement"
                    ]
                )
            )

        with col2:

            st.write(
                "**Entry Range**"
            )

            st.write(
                f"{fmt_price(result['entry_low'])}"
                f" — "
                f"{fmt_price(result['entry_high'])}"
            )

            st.write(
                "**Take Profit**"
            )

            st.write(
                fmt_price(
                    result[
                        "take_profit"
                    ]
                )
            )

        with col3:

            st.write(
                "**Stop Loss**"
            )

            st.write(
                fmt_price(
                    result[
                        "stop_loss"
                    ]
                )
            )

            st.write(
                "Volatility: "
                f"{fmt_pct(result['volatility'])}"
            )

            st.write(
                "Confidence: "
                f"{result['confidence']:.0f}%"
            )

        chart_key = (
            "chart_"
            + result["pair"]
            + "_"
            + result["timeframe"]
        )

        if st.button(
            f"📈 Open Chart — "
            f"{result['pair']}",
            key=chart_key,
            use_container_width=True
        ):

            st.session_state[
                "selected_pair"
            ] = result["pair"]

            st.rerun()

        st.divider()


# =========================================================
# SELECTED CHART
# =========================================================

selected_pair = (
    st.session_state.get(
        "selected_pair"
    )
)


if selected_pair:

    st.subheader(
        f"Chart — {selected_pair}"
    )

    show_tradingview(
        selected_pair
    )

    if st.button(
        "✖ Close Chart",
        use_container_width=True
    ):

        st.session_state[
            "selected_pair"
        ] = None

        st.rerun()


# =========================================================
# 24H PERFORMANCE
# =========================================================

st.subheader(
    "24H Screening Performance"
)

history = get_history()

if history.empty:

    st.info(
        "Belum ada screening history."
    )

else:

    total = len(history)

    success = len(
        history[
            history["status"]
            == "SUCCESS"
        ]
    )

    loss = len(
        history[
            history["status"]
            == "LOSS"
        ]
    )

    opened = len(
        history[
            history["status"]
            == "OPEN"
        ]
    )

    closed = (
        success
        + loss
    )

    if closed > 0:

        winrate = (
            success
            / closed
        ) * 100

    else:

        winrate = 0

    avg_pnl = (
        history[
            "pnl_percent"
        ].mean()
    )

    c1, c2, c3, c4, c5 = (
        st.columns(5)
    )

    with c1:

        st.metric(
            "Total",
            total
        )

    with c2:

        st.metric(
            "Success",
            success
        )

    with c3:

        st.metric(
            "Loss",
            loss
        )

    with c4:

        st.metric(
            "Win Rate",
            f"{winrate:.2f}%"
        )

    with c5:

        st.metric(
            "Avg P/L",
            f"{avg_pnl:.2f}%"
        )

    display_history = (
        history.copy()
    )

    display_history[
        "timestamp"
    ] = pd.to_datetime(
        display_history[
            "timestamp"
        ],
        errors="coerce"
    )

    display_history = (
        display_history[
            [
                "timestamp",
                "pair",
                "timeframe",
                "outlook",
                "entry_low",
                "entry_high",
                "take_profit",
                "stop_loss",
                "current_price",
                "movement",
                "volatility",
                "confidence",
                "status",
                "pnl_percent"
            ]
        ]
        .head(50)
    )

    display_history.columns = [
        "Time",
        "Pair",
        "TF",
        "Outlook",
        "Entry Low",
        "Entry High",
        "Take Profit",
        "Stop Loss",
        "Price",
        "Movement %",
        "Volatility %",
        "Confidence",
        "Status",
        "P/L %"
    ]

    st.dataframe(
        display_history,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "0xmwY Kraken • "
    "Market scanner & simulated performance"
)

st.caption(
    "⚠️ Signal bukan financial advice. "
    "DYOR sebelum mengambil keputusan trading."
)
