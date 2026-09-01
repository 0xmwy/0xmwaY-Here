import streamlit as st
import requests
import pandas as pd
import time

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Haiii 0xmwY",
    page_icon="👋",
    layout="wide"
)

# API KEY DIAMBIL DARI STREAMLIT SECRETS
API_KEY = "937c265e51c344c79b71cd715bb928ba"

BASE_URL = "https://api.twelvedata.com"

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 200
RSI_PERIOD = 14


# =========================================================
# HEADER
# =========================================================

st.title("👋 Haiii 0xmwY")
st.caption(
    "Multi-Timeframe Crypto Scalping Screener"
)

st.divider()


# =========================================================
# API REQUEST
# =========================================================

def api_get(endpoint, params=None):

    if params is None:
        params = {}

    params["apikey"] = API_KEY

    response = requests.get(
        BASE_URL + endpoint,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):

        if data.get("status") == "error":

            raise Exception(
                data.get(
                    "message",
                    "Twelve Data API error"
                )
            )

    return data


# =========================================================
# GET CRYPTO LIST
# =========================================================

@st.cache_data(ttl=3600)
def get_crypto_list():

    data = api_get(
        "/cryptocurrencies"
    )

    if isinstance(data, dict):

        data = data.get(
            "data",
            []
        )

    symbols = []

    for coin in data:

        symbol = coin.get(
            "symbol"
        )

        if symbol:

            symbols.append(
                symbol
            )

    symbols = [
        symbol
        for symbol in symbols
        if symbol.endswith("/USD")
    ]

    return sorted(
        list(set(symbols))
    )


# =========================================================
# GET CANDLES
# =========================================================

@st.cache_data(ttl=60)
def get_candles(
    symbol,
    interval
):

    data = api_get(
        "/time_series",
        {
            "symbol": symbol,
            "interval": interval,
            "outputsize": 220
        }
    )

    values = data.get(
        "values"
    )

    if not values:

        return None

    df = pd.DataFrame(
        values
    )

    required = [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]

    for column in required:

        if column not in df.columns:

            return None

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    )

    if len(df) < 205:

        return None

    # oldest -> newest
    df = df.iloc[::-1].reset_index(
        drop=True
    )

    return df


# =========================================================
# INDICATORS
# =========================================================

def calculate_indicators(df):

    df = df.copy()

    # EMA 9
    df["ema9"] = (
        df["close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    # EMA 21
    df["ema21"] = (
        df["close"]
        .ewm(
            span=EMA_SLOW,
            adjust=False
        )
        .mean()
    )

    # EMA 200
    df["ema200"] = (
        df["close"]
        .ewm(
            span=EMA_TREND,
            adjust=False
        )
        .mean()
    )

    # RSI 14
    delta = df["close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain
        .rolling(
            RSI_PERIOD
        )
        .mean()
    )

    avg_loss = (
        loss
        .rolling(
            RSI_PERIOD
        )
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

    # Average volume
    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


# =========================================================
# TIMEFRAME SCORE
# =========================================================

def score_timeframe(df):

    df = calculate_indicators(
        df
    )

    # gunakan candle yang sudah close
    current = df.iloc[-2]
    previous = df.iloc[-3]

    long_score = 0
    short_score = 0

    # -----------------------------------------------------
    # EMA 200
    # -----------------------------------------------------

    if current["close"] > current["ema200"]:

        long_score += 2

    else:

        short_score += 2

    # -----------------------------------------------------
    # EMA 9 / 21
    # -----------------------------------------------------

    if current["ema9"] > current["ema21"]:

        long_score += 2

    else:

        short_score += 2

    # -----------------------------------------------------
    # EMA 9 MOMENTUM
    # -----------------------------------------------------

    if current["ema9"] > previous["ema9"]:

        long_score += 1

    else:

        short_score += 1

    # -----------------------------------------------------
    # RSI
    # -----------------------------------------------------

    rsi = float(
        current["rsi"]
    )

    # bullish momentum
    if 45 <= rsi <= 70:

        long_score += 1

    # bearish momentum
    if 30 <= rsi <= 55:

        short_score += 1

    # -----------------------------------------------------
    # VOLUME
    # -----------------------------------------------------

    volume_high = (
        current["volume"]
        >
        current["volume_avg"]
    )

    if volume_high:

        if current["close"] > current["open"]:

            long_score += 1

        elif current["close"] < current["open"]:

            short_score += 1

    return {
        "long": long_score,
        "short": short_score,
        "price": float(
            current["close"]
        ),
        "rsi": rsi
    }


# =========================================================
# ANALYZE COIN
# =========================================================

def analyze_coin(symbol):

    try:

        data = {}

        # -------------------------------------------------
        # 1H
        # -------------------------------------------------

        candles = get_candles(
            symbol,
            "1h"
        )

        if candles is None:
            return None

        data["1H"] = score_timeframe(
            candles
        )

        # -------------------------------------------------
        # 30M
        # -------------------------------------------------

        candles = get_candles(
            symbol,
            "30min"
        )

        if candles is None:
            return None

        data["30M"] = score_timeframe(
            candles
        )

        # -------------------------------------------------
        # 15M
        # -------------------------------------------------

        candles = get_candles(
            symbol,
            "15min"
        )

        if candles is None:
            return None

        data["15M"] = score_timeframe(
            candles
        )

        # -------------------------------------------------
        # 5M
        # -------------------------------------------------

        candles = get_candles(
            symbol,
            "5min"
        )

        if candles is None:
            return None

        data["5M"] = score_timeframe(
            candles
        )

        # =================================================
        # TOTAL SCORE
        # =================================================

        long_score = (
            data["1H"]["long"]
            +
            data["30M"]["long"]
            +
            data["15M"]["long"]
            +
            data["5M"]["long"]
        )

        short_score = (
            data["1H"]["short"]
            +
            data["30M"]["short"]
            +
            data["15M"]["short"]
            +
            data["5M"]["short"]
        )

        # -------------------------------------------------
        # Normalize to 5
        # -------------------------------------------------

        long_score = round(
            long_score / 3
        )

        short_score = round(
            short_score / 3
        )

        # =================================================
        # PRICE / RSI
        # =================================================

        price = data["5M"]["price"]
        rsi = data["5M"]["rsi"]

        # =================================================
        # RETURN
        # =================================================

        return {
            "Coin": symbol,

            "LONG Score": long_score,

            "SHORT Score": short_score,

            "Price": price,

            "RSI 5M": round(
                rsi,
                2
            ),

            "1H": (
                "🟢"
                if data["1H"]["long"]
                >
                data["1H"]["short"]
                else "🔴"
            ),

            "30M": (
                "🟢"
                if data["30M"]["long"]
                >
                data["30M"]["short"]
                else "🔴"
            ),

            "15M": (
                "🟢"
                if data["15M"]["long"]
                >
                data["15M"]["short"]
                else "🔴"
            ),

            "5M": (
                "🟢"
                if data["5M"]["long"]
                >
                data["5M"]["short"]
                else "🔴"
            )
        }

    except Exception:

        return None


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header(
    "⚙️ Scanner"
)

coin_limit = st.sidebar.selectbox(
    "Jumlah coin",
    [10, 25, 50, 100],
    index=1
)

refresh = st.sidebar.button(
    "🔄 Refresh"
)


# =========================================================
# MAIN SCANNER
# =========================================================

if st.button(
    "🔎 SCAN MARKET",
    use_container_width=True
) or refresh:

    # -----------------------------------------------------
    # COIN LIST
    # -----------------------------------------------------

    try:

        with st.spinner(
            "Mengambil daftar coin..."
        ):

            coins = get_crypto_list()

    except Exception as e:

        st.error(
            f"Gagal mengambil daftar coin: {e}"
        )

        st.stop()

    if not coins:

        st.error(
            "Daftar coin kosong."
        )

        st.stop()

    # -----------------------------------------------------
    # LIMIT
    # -----------------------------------------------------

    coins = coins[
        :coin_limit
    ]

    results = []

    progress = st.progress(
        0
    )

    status = st.empty()

    total = len(coins)

    # -----------------------------------------------------
    # SCAN
    # -----------------------------------------------------

    for i, coin in enumerate(
        coins
    ):

        status.write(
            f"Scanning {coin} "
            f"({i + 1}/{total})"
        )

        result = analyze_coin(
            coin
        )

        if result:

            results.append(
                result
            )

        progress.progress(
            (i + 1) / total
        )

        # prevent excessive requests
        time.sleep(
            0.15
        )

    progress.empty()
    status.empty()

    # -----------------------------------------------------
    # CHECK
    # -----------------------------------------------------

    if not results:

        st.error(
            "Tidak ada data market yang berhasil diambil."
        )

        st.stop()

    df = pd.DataFrame(
        results
    )

    # =====================================================
    # TOP LONG
    # =====================================================

    long_df = df.sort_values(
        by="LONG Score",
        ascending=False
    ).head(5)

    # =====================================================
    # TOP SHORT
    # =====================================================

    short_df = df.sort_values(
        by="SHORT Score",
        ascending=False
    ).head(5)

    # =====================================================
    # SUMMARY
    # =====================================================

    st.divider()

    c1, c2 = st.columns(2)

    with c1:

        st.metric(
            "🟢 TOP LONG",
            len(long_df)
        )

    with c2:

        st.metric(
            "🔴 TOP SHORT",
            len(short_df)
        )

    # =====================================================
    # LONG
    # =====================================================

    st.subheader(
        "🟢 TOP LONG"
    )

    st.dataframe(
        long_df[
            [
                "Coin",
                "LONG Score",
                "Price",
                "RSI 5M",
                "1H",
                "30M",
                "15M",
                "5M"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

    # =====================================================
    # SHORT
    # =====================================================

    st.subheader(
        "🔴 TOP SHORT"
    )

    st.dataframe(
        short_df[
            [
                "Coin",
                "SHORT Score",
                "Price",
                "RSI 5M",
                "1H",
                "30M",
                "15M",
                "5M"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

    # =====================================================
    # BEST LONG
    # =====================================================

    best_long = long_df.iloc[0]

    st.success(
        f"🟢 BEST LONG: "
        f"{best_long['Coin']} "
        f"— Score "
        f"{best_long['LONG Score']}/5"
    )

    # =====================================================
    # BEST SHORT
    # =====================================================

    best_short = short_df.iloc[0]

    st.error(
        f"🔴 BEST SHORT: "
        f"{best_short['Coin']} "
        f"— Score "
        f"{best_short['SHORT Score']}/5"
    )

    st.caption(
        "TOP LONG/SHORT selalu ditampilkan berdasarkan "
        "ranking indikator. Signal bukan jaminan profit."
            )
