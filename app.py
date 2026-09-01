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

# API KEY
API_KEY = "937c265e51c344c79b71cd715bb928ba"

BASE_URL = "https://api.twelvedata.com"

TIMEFRAMES = {
    "5M": "5min",
    "15M": "15min",
    "30M": "30min",
    "1H": "1h"
}

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 200
RSI_PERIOD = 14


# =========================================================
# HEADER
# =========================================================

st.title("👋 Haiii 0xmwY")
st.caption(
    "Crypto Scalping Scanner • EMA 9/21/200 • RSI • Volume"
)

st.divider()


# =========================================================
# API FUNCTION
# =========================================================

def api_get(endpoint, params=None):

    if params is None:
        params = {}

    params["apikey"] = API_KEY

    url = BASE_URL + endpoint

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    # HTTP error
    if response.status_code != 200:
        raise Exception(
            f"HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    try:
        data = response.json()
    except Exception:
        raise Exception(
            "Response API bukan JSON: "
            + response.text[:300]
        )

    # Twelve Data API error
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
# TEST API
# =========================================================

def test_api():

    data = api_get(
        "/time_series",
        {
            "symbol": "BTC/USD",
            "interval": "5min",
            "outputsize": 5
        }
    )

    if not data.get("values"):
        raise Exception(
            "BTC/USD tidak mengembalikan candle."
        )

    return True


# =========================================================
# GET CRYPTO LIST
# =========================================================

@st.cache_data(ttl=3600)
def get_crypto_list():

    data = api_get(
        "/cryptocurrencies"
    )

    # Bentuk response normal:
    # {"data":[...]}

    if isinstance(data, dict):

        coins = data.get(
            "data",
            []
        )

    else:

        coins = data

    symbols = []

    for coin in coins:

        if isinstance(coin, dict):

            symbol = coin.get(
                "symbol"
            )

        else:

            symbol = str(coin)

        if symbol:

            symbol = str(
                symbol
            ).upper()

            # Pastikan pair crypto/USD
            if symbol.endswith("/USD"):

                symbols.append(
                    symbol
                )

    symbols = sorted(
        list(
            set(symbols)
        )
    )

    if not symbols:

        raise Exception(
            "Twelve Data tidak mengembalikan "
            "daftar cryptocurrency/USD."
        )

    return symbols


# =========================================================
# GET CANDLES
# =========================================================

@st.cache_data(ttl=45)
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
        "datetime",
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required:

        if column not in df.columns:

            return None

    # volume tidak selalu tersedia
    if "volume" not in df.columns:

        df["volume"] = 0

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(
        subset=[
            "open",
            "high",
            "low",
            "close"
        ]
    )

    if len(df) < 205:

        return None

    # API mengembalikan terbaru -> lama
    # Kita ubah menjadi lama -> terbaru
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

    # Volume average
    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


# =========================================================
# SCORE
# =========================================================

def calculate_score(df):

    df = calculate_indicators(
        df
    )

    # Candle terakhir yang SUDAH CLOSE
    current = df.iloc[-2]
    previous = df.iloc[-3]

    long_score = 0
    short_score = 0

    # =====================================================
    # EMA 200 TREND
    # =====================================================

    if current["close"] > current["ema200"]:

        long_score += 2

    else:

        short_score += 2

    # =====================================================
    # EMA 9 / 21
    # =====================================================

    if current["ema9"] > current["ema21"]:

        long_score += 2

    else:

        short_score += 2

    # =====================================================
    # MOMENTUM EMA 9
    # =====================================================

    if current["ema9"] > previous["ema9"]:

        long_score += 1

    else:

        short_score += 1

    # =====================================================
    # RSI
    # =====================================================

    rsi = float(
        current["rsi"]
    )

    if 45 <= rsi <= 70:

        long_score += 1

    if 30 <= rsi <= 55:

        short_score += 1

    # =====================================================
    # CANDLE MOMENTUM
    # =====================================================

    if current["close"] > current["open"]:

        long_score += 1

    elif current["close"] < current["open"]:

        short_score += 1

    # =====================================================
    # VOLUME
    # =====================================================

    if (
        current["volume"]
        > current["volume_avg"]
    ):

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
# ANALYZE ONE COIN
# =========================================================

def analyze_coin(symbol):

    result = {
        "Coin": symbol
    }

    total_long = 0
    total_short = 0

    try:

        for label, interval in TIMEFRAMES.items():

            candles = get_candles(
                symbol,
                interval
            )

            if candles is None:

                return None

            score = calculate_score(
                candles
            )

            total_long += score["long"]
            total_short += score["short"]

            result[
                f"{label} LONG"
            ] = score["long"]

            result[
                f"{label} SHORT"
            ] = score["short"]

            result[
                f"{label} RSI"
            ] = round(
                score["rsi"],
                1
            )

            result[
                f"{label} DIR"
            ] = (
                "LONG"
                if score["long"]
                > score["short"]
                else "SHORT"
            )

            result[
                f"{label} PRICE"
            ] = score["price"]

        # =================================================
        # TOTAL
        # =================================================

        result[
            "LONG SCORE"
        ] = total_long

        result[
            "SHORT SCORE"
        ] = total_short

        result["PRICE"] = result[
            "5M PRICE"
        ]

        # =================================================
        # FINAL SIGNAL
        # =================================================

        if total_long > total_short:

            result[
                "SIGNAL"
            ] = "🟢 LONG"

        elif total_short > total_long:

            result[
                "SIGNAL"
            ] = "🔴 SHORT"

        else:

            result[
                "SIGNAL"
            ] = "⚪ NEUTRAL"

        return result

    except Exception:

        return None


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header(
    "⚙️ Scanner"
)

coin_limit = st.sidebar.selectbox(
    "Jumlah coin yang discan",
    [
        10,
        20,
        30,
        50
    ],
    index=1
)

st.sidebar.info(
    "Scanner mengambil kandidat terbaik "
    "berdasarkan 5M + 15M + 30M + 1H."
)


# =========================================================
# API TEST
# =========================================================

with st.expander(
    "🔧 API Status"
):

    if st.button(
        "Test API"
    ):

        try:

            test_api()

            st.success(
                "API Twelve Data berhasil."
            )

        except Exception as e:

            st.error(
                f"API gagal: {e}"
            )


# =========================================================
# SCAN BUTTON
# =========================================================

scan = st.button(
    "🔎 SCAN MARKET",
    use_container_width=True
)


# =========================================================
# SCANNER
# =========================================================

if scan:

    # -----------------------------------------------------
    # GET COINS
    # -----------------------------------------------------

    try:

        with st.spinner(
            "Mengambil daftar cryptocurrency..."
        ):

            coins = get_crypto_list()

    except Exception as e:

        st.error(
            "❌ Gagal mengambil daftar market."
        )

        st.code(
            str(e)
        )

        st.info(
            "Kalau pesan di atas mengatakan "
            "invalid API key / credits / access denied, "
            "masalahnya ada pada API Twelve Data."
        )

        st.stop()

    # -----------------------------------------------------
    # SHOW AVAILABLE
    # -----------------------------------------------------

    st.success(
        f"Berhasil menemukan "
        f"{len(coins)} pair crypto/USD."
    )

    # -----------------------------------------------------
    # LIMIT
    # -----------------------------------------------------

    scan_coins = coins[
        :coin_limit
    ]

    results = []

    progress = st.progress(
        0
    )

    status = st.empty()

    total = len(
        scan_coins
    )

    # -----------------------------------------------------
    # SCAN
    # -----------------------------------------------------

    for index, symbol in enumerate(
        scan_coins
    ):

        status.write(
            f"Scanning {symbol} "
            f"({index + 1}/{total})"
        )

        result = analyze_coin(
            symbol
        )

        if result is not None:

            results.append(
                result
            )

        progress.progress(
            (index + 1) / total
        )

        # sedikit jeda
        time.sleep(
            0.15
        )

    progress.empty()
    status.empty()

    # -----------------------------------------------------
    # NO RESULT
    # -----------------------------------------------------

    if not results:

        st.error(
            "Tidak ada candle market yang berhasil "
            "diperoleh."
        )

        st.stop()

    # -----------------------------------------------------
    # DATAFRAME
    # -----------------------------------------------------

    df = pd.DataFrame(
        results
    )

    # =====================================================
    # TOP LONG
    # =====================================================

    top_long = (
        df
        .sort_values(
            "LONG SCORE",
            ascending=False
        )
        .head(5)
    )

    # =====================================================
    # TOP SHORT
    # =====================================================

    top_short = (
        df
        .sort_values(
            "SHORT SCORE",
            ascending=False
        )
        .head(5)
    )

    # =====================================================
    # BEST LONG
    # =====================================================

    st.divider()

    st.subheader(
        "🟢 TOP LONG"
    )

    long_columns = [
        "Coin",
        "LONG SCORE",
        "SHORT SCORE",
        "5M DIR",
        "15M DIR",
        "30M DIR",
        "1H DIR",
        "5M RSI",
        "PRICE"
    ]

    st.dataframe(
        top_long[
            long_columns
        ],
        use_container_width=True,
        hide_index=True
    )

    # =====================================================
    # BEST SHORT
    # =====================================================

    st.subheader(
        "🔴 TOP SHORT"
    )

    short_columns = [
        "Coin",
        "SHORT SCORE",
        "LONG SCORE",
        "5M DIR",
        "15M DIR",
        "30M DIR",
        "1H DIR",
        "5M RSI",
        "PRICE"
    ]

    st.dataframe(
        top_short[
            short_columns
        ],
        use_container_width=True,
        hide_index=True
    )

    # =====================================================
    # STRONGEST SIGNAL
    # =====================================================

    best_long = top_long.iloc[0]

    best_short = top_short.iloc[0]

    st.divider()

    col1, col2 = st.columns(2)

    with col1:

        st.success(
            f"🟢 BEST LONG\n\n"
            f"**{best_long['Coin']}**\n\n"
            f"Long score: "
            f"{best_long['LONG SCORE']}\n\n"
            f"Price: "
            f"{best_long['PRICE']}\n\n"
            f"RSI 5M: "
            f"{best_long['5M RSI']}"
        )

    with col2:

        st.error(
            f"🔴 BEST SHORT\n\n"
            f"**{best_short['Coin']}**\n\n"
            f"Short score: "
            f"{best_short['SHORT SCORE']}\n\n"
            f"Price: "
            f"{best_short['PRICE']}\n\n"
            f"RSI 5M: "
            f"{best_short['5M RSI']}"
        )

    # =====================================================
    # ALL RESULTS
    # =====================================================

    with st.expander(
        "📊 Semua hasil scan"
    ):

        all_columns = [
            "Coin",
            "SIGNAL",
            "LONG SCORE",
            "SHORT SCORE",
            "5M DIR",
            "15M DIR",
            "30M DIR",
            "1H DIR",
            "5M RSI",
            "PRICE"
        ]

        st.dataframe(
            df.sort_values(
                "LONG SCORE",
                ascending=False
            )[
                all_columns
            ],
            use_container_width=True,
            hide_index=True
        )

    st.caption(
        "Signal ini adalah ranking teknikal, "
        "bukan jaminan harga akan naik/turun."
        )
