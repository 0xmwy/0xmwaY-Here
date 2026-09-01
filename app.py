import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Haiii 0xmwY",
    page_icon="👋",
    layout="wide"
)

API_URL = "https://api.bybit.com"

EMA_TREND = 200
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14

MAX_WORKERS = 10


# =========================================================
# HEADER
# =========================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }

    .title {
        font-size: 34px;
        font-weight: 700;
    }

    .subtitle {
        color: #8b949e;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    '<div class="title">👋 Haiii 0xmwY</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">Live Public Market Screener</div>',
    unsafe_allow_html=True
)

st.divider()


# =========================================================
# CONTROLS
# =========================================================

col1, col2, col3 = st.columns(3)

with col1:
    direction = st.selectbox(
        "Signal",
        ["ALL", "LONG", "SHORT"]
    )

with col2:
    minimum_score = st.selectbox(
        "Minimum Score",
        [3, 4, 5],
        index=0
    )

with col3:
    refresh_seconds = st.selectbox(
        "Auto Refresh",
        [30, 60, 120],
        index=1
    )


st.caption(
    "1H + 15m = trend • 5m = momentum"
)


# =========================================================
# REQUEST SESSION
# =========================================================

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0"
})


# =========================================================
# GET ALL BYBIT USDT PERPETUALS
# =========================================================

@st.cache_data(ttl=900)
def get_symbols():

    url = (
        f"{API_URL}/v5/market/instruments-info"
        "?category=linear"
        "&limit=1000"
    )

    try:

        response = session.get(
            url,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        if data.get("retCode") != 0:
            return []

        symbols = []

        for item in data["result"]["list"]:

            if (
                item.get("status") == "Trading"
                and item.get("quoteCoin") == "USDT"
                and item.get("contractType")
                == "LinearPerpetual"
            ):

                symbols.append(
                    item["symbol"]
                )

        return sorted(
            list(set(symbols))
        )

    except Exception:

        return []


# =========================================================
# GET KLINES
# =========================================================

def get_klines(
    symbol,
    interval,
    limit=250
):

    url = (
        f"{API_URL}/v5/market/kline"
    )

    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:

        response = session.get(
            url,
            params=params,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        if data.get("retCode") != 0:
            return None

        rows = data[
            "result"
        ]["list"]

        if not rows:
            return None

        df = pd.DataFrame(
            rows,
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover"
            ]
        )

        for column in [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        df["time"] = pd.to_datetime(
            pd.to_numeric(
                df["time"]
            ),
            unit="ms"
        )

        df = df.sort_values(
            "time"
        ).reset_index(
            drop=True
        )

        return df

    except Exception:

        return None


# =========================================================
# INDICATORS
# =========================================================

def calculate_indicators(df):

    df = df.copy()

    # Trend
    df["ema200"] = (
        df["close"]
        .ewm(
            span=EMA_TREND,
            adjust=False
        )
        .mean()
    )

    # Momentum
    df["ema9"] = (
        df["close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    df["ema21"] = (
        df["close"]
        .ewm(
            span=EMA_SLOW,
            adjust=False
        )
        .mean()
    )

    # RSI
    delta = df["close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain
        .rolling(RSI_PERIOD)
        .mean()
    )

    avg_loss = (
        loss
        .rolling(RSI_PERIOD)
        .mean()
    )

    rs = (
        avg_gain /
        avg_loss.replace(
            0,
            pd.NA
        )
    )

    df["rsi"] = (
        100 -
        (
            100 /
            (1 + rs)
        )
    )

    # Volume average
    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


# =========================================================
# ANALYZE COIN
# =========================================================

def analyze_symbol(symbol):

    try:

        # 1H
        data_1h = get_klines(
            symbol,
            "60",
            250
        )

        # 15M
        data_15m = get_klines(
            symbol,
            "15",
            250
        )

        # 5M
        data_5m = get_klines(
            symbol,
            "5",
            250
        )

        if (
            data_1h is None
            or data_15m is None
            or data_5m is None
        ):
            return None

        if (
            len(data_1h) < 220
            or len(data_15m) < 220
            or len(data_5m) < 220
        ):
            return None

        data_1h = calculate_indicators(
            data_1h
        )

        data_15m = calculate_indicators(
            data_15m
        )

        data_5m = calculate_indicators(
            data_5m
        )

        h1 = data_1h.iloc[-2]
        m15 = data_15m.iloc[-2]
        m5 = data_5m.iloc[-2]

        # =================================================
        # SHORT
        # =================================================

        short_score = 0

        if h1["close"] < h1["ema200"]:
            short_score += 1

        if m15["close"] < m15["ema200"]:
            short_score += 1

        if m5["ema9"] < m5["ema21"]:
            short_score += 1

        if m5["rsi"] < 50:
            short_score += 1

        if m5["volume"] > m5["volume_avg"]:
            short_score += 1


        # =================================================
        # LONG
        # =================================================

        long_score = 0

        if h1["close"] > h1["ema200"]:
            long_score += 1

        if m15["close"] > m15["ema200"]:
            long_score += 1

        if m5["ema9"] > m5["ema21"]:
            long_score += 1

        if m5["rsi"] > 50:
            long_score += 1

        if m5["volume"] > m5["volume_avg"]:
            long_score += 1


        # =================================================
        # SELECT
        # =================================================

        if (
            direction in ["ALL", "SHORT"]
            and short_score >= minimum_score
        ):

            signal = "SHORT"
            score = short_score

        elif (
            direction in ["ALL", "LONG"]
            and long_score >= minimum_score
        ):

            signal = "LONG"
            score = long_score

        else:

            return None


        # =================================================
        # STRENGTH
        # =================================================

        if score == 5:
            strength = "STRONG"

        elif score == 4:
            strength = "GOOD"

        else:
            strength = "WATCH"


        return {
            "Symbol": symbol,
            "Signal": signal,
            "Score": f"{score}/5",
            "Strength": strength,
            "Price": round(
                float(m5["close"]),
                8
            ),
            "RSI": round(
                float(m5["rsi"]),
                2
            )
        }

    except Exception:

        return None


# =========================================================
# SCAN ALL
# =========================================================

def scan_market(symbols):

    results = []

    progress = st.progress(0)

    status = st.empty()

    total = len(symbols)

    completed = 0

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                analyze_symbol,
                symbol
            )
            for symbol in symbols
        ]

        for future in as_completed(
            futures
        ):

            try:

                result = future.result()

                if result is not None:
                    results.append(
                        result
                    )

            except Exception:
                pass

            completed += 1

            progress.progress(
                completed / total
            )

            status.write(
                f"Scanning "
                f"{completed}/{total}..."
            )

    progress.empty()
    status.empty()

    return results


# =========================================================
# MAIN BUTTON
# =========================================================

if st.button(
    "🔴 START LIVE SCANNER",
    use_container_width=True
):

    st.session_state[
        "running"
    ] = True


if st.button(
    "⏹ STOP SCANNER",
    use_container_width=True
):

    st.session_state[
        "running"
    ] = False


# =========================================================
# INITIAL STATE
# =========================================================

if "running" not in st.session_state:

    st.session_state[
        "running"
    ] = False


# =========================================================
# RUN
# =========================================================

if st.session_state["running"]:

    symbols = get_symbols()

    if not symbols:

        st.error(
            "Gagal mengambil daftar coin "
            "dari public market data."
        )

    else:

        st.info(
            f"📡 Monitoring "
            f"{len(symbols)} USDT perpetual"
        )

        results = scan_market(
            symbols
        )

        st.session_state[
            "results"
        ] = results

        st.session_state[
            "last_update"
        ] = time.time()


# =========================================================
# RESULTS
# =========================================================

if "results" in st.session_state:

    results = st.session_state[
        "results"
    ]

    st.divider()

    if not results:

        st.warning(
            "Belum ada setup yang memenuhi filter."
        )

    else:

        df = pd.DataFrame(
            results
        )

        df["_score"] = (
            df["Score"]
            .str.extract(
                r"(\d+)"
            )[0]
            .astype(int)
        )

        df = df.sort_values(
            "_score",
            ascending=False
        )

        df = df.drop(
            columns=["_score"]
        )

        st.subheader(
            f"📊 {len(df)} Setup"
        )

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# AUTO REFRESH
# =========================================================

if st.session_state.get(
    "running",
    False
):

    time.sleep(
        refresh_seconds
    )

    st.rerun()
