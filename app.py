import streamlit as st
import requests
import pandas as pd
import time
import math

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Haiii 0xmwY",
    page_icon="👋",
    layout="wide"
)

# =========================================================
# API KEY — SUDAH DIISI
# =========================================================

API_KEY = "937c265e51c344c79b71cd715bb928ba"

BASE_URL = "https://api.twelvedata.com"

# =========================================================
# SETTINGS
# =========================================================

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
ATR_PERIOD = 14


# =========================================================
# HEADER
# =========================================================

st.title("👋 Haiii 0xmwY")
st.caption(
    "Multi-Timeframe Crypto Scalping Scanner"
)

st.divider()


# =========================================================
# API REQUEST
# =========================================================

def api_get(endpoint, params=None):

    if params is None:
        params = {}

    params["apikey"] = API_KEY

    try:

        response = requests.get(
            BASE_URL + endpoint,
            params=params,
            timeout=20
        )

    except requests.exceptions.RequestException as e:

        raise Exception(
            f"Koneksi API gagal: {e}"
        )

    if response.status_code != 200:

        raise Exception(
            f"HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    try:

        data = response.json()

    except Exception:

        raise Exception(
            "Server API tidak mengembalikan JSON."
        )

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
            "outputsize": 10
        }
    )

    if not isinstance(data, dict):

        raise Exception(
            "Format response API tidak valid."
        )

    if not data.get("values"):

        raise Exception(
            "BTC/USD tidak mengembalikan candle."
        )

    return True


# =========================================================
# CRYPTO LIST
# =========================================================

@st.cache_data(ttl=3600)
def get_crypto_list():

    data = api_get(
        "/cryptocurrencies"
    )

    if isinstance(data, dict):

        coins = data.get(
            "data",
            []
        )

    elif isinstance(data, list):

        coins = data

    else:

        coins = []

    symbols = []

    for coin in coins:

        if isinstance(coin, dict):

            symbol = coin.get(
                "symbol"
            )

        else:

            symbol = str(coin)

        if not symbol:
            continue

        symbol = str(
            symbol
        ).upper()

        # Hanya crypto yang punya pasangan USD
        if "/" in symbol:

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
            "Daftar cryptocurrency kosong."
        )

    return symbols


# =========================================================
# GET CANDLES
# =========================================================

@st.cache_data(ttl=30)
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

    if not isinstance(data, dict):
        return None

    values = data.get(
        "values"
    )

    if not values:
        return None

    df = pd.DataFrame(
        values
    )

    required_columns = [
        "datetime",
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required_columns:

        if column not in df.columns:

            return None

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
    # Kita balik menjadi lama -> terbaru

    df = (
        df.iloc[::-1]
        .reset_index(drop=True)
    )

    return df


# =========================================================
# INDICATORS
# =========================================================

def calculate_indicators(df):

    df = df.copy()

    # -----------------------------------------------------
    # EMA 9
    # -----------------------------------------------------

    df["ema9"] = (
        df["close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    # -----------------------------------------------------
    # EMA 21
    # -----------------------------------------------------

    df["ema21"] = (
        df["close"]
        .ewm(
            span=EMA_SLOW,
            adjust=False
        )
        .mean()
    )

    # -----------------------------------------------------
    # EMA 200
    # -----------------------------------------------------

    df["ema200"] = (
        df["close"]
        .ewm(
            span=EMA_TREND,
            adjust=False
        )
        .mean()
    )

    # -----------------------------------------------------
    # RSI
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # ATR
    # -----------------------------------------------------

    high_low = (
        df["high"] -
        df["low"]
    )

    high_close = (
        df["high"] -
        df["close"].shift(1)
    ).abs()

    low_close = (
        df["low"] -
        df["close"].shift(1)
    ).abs()

    true_range = pd.concat(
        [
            high_low,
            high_close,
            low_close
        ],
        axis=1
    ).max(
        axis=1
    )

    df["atr"] = (
        true_range
        .rolling(
            ATR_PERIOD
        )
        .mean()
    )

    # -----------------------------------------------------
    # Average Volume
    # -----------------------------------------------------

    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


# =========================================================
# ANALYZE ONE TIMEFRAME
# =========================================================

def analyze_timeframe(df):

    df = calculate_indicators(
        df
    )

    # Gunakan candle yang sudah close
    current = df.iloc[-2]
    previous = df.iloc[-3]

    long_score = 0
    short_score = 0

    # =====================================================
    # TREND
    # =====================================================

    if current["close"] > current["ema200"]:

        long_score += 2

    else:

        short_score += 2

    # =====================================================
    # EMA MOMENTUM
    # =====================================================

    if current["ema9"] > current["ema21"]:

        long_score += 2

    else:

        short_score += 2

    # =====================================================
    # EMA DIRECTION
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

    # Tidak terlalu ketat
    if rsi >= 45:

        long_score += 1

    if rsi <= 55:

        short_score += 1

    # =====================================================
    # CANDLE
    # =====================================================

    if current["close"] > current["open"]:

        long_score += 1

    elif current["close"] < current["open"]:

        short_score += 1

    # =====================================================
    # VOLUME
    # =====================================================

    volume = float(
        current["volume"]
    )

    volume_avg = float(
        current["volume_avg"]
    )

    if (
        volume_avg > 0
        and
        volume > volume_avg
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
        "rsi": rsi,
        "atr": float(
            current["atr"]
        )
    }


# =========================================================
# ANALYZE COIN
# =========================================================

def analyze_coin(symbol):

    try:

        results = {}

        # =================================================
        # ALL TIMEFRAMES
        # =================================================

        for label, interval in TIMEFRAMES.items():

            df = get_candles(
                symbol,
                interval
            )

            if df is None:

                return None

            results[label] = (
                analyze_timeframe(
                    df
                )
            )

        # =================================================
        # TOTAL SCORE
        # =================================================

        long_score = sum(
            results[x]["long"]
            for x in results
        )

        short_score = sum(
            results[x]["short"]
            for x in results
        )

        # =================================================
        # TIMEFRAME DIRECTION
        # =================================================

        long_tf = sum(
            1
            for x in results.values()
            if x["long"] > x["short"]
        )

        short_tf = sum(
            1
            for x in results.values()
            if x["short"] > x["long"]
        )

        # =================================================
        # 5M PRICE
        # =================================================

        price = results[
            "5M"
        ]["price"]

        atr = results[
            "5M"
        ]["atr"]

        # =================================================
        # FALLBACK ATR
        # =================================================

        if (
            not math.isfinite(atr)
            or
            atr <= 0
        ):

            atr = price * 0.01

        # =================================================
        # LONG ENTRY
        # =================================================

        long_entry_low = (
            price -
            atr * 0.25
        )

        long_entry_high = (
            price +
            atr * 0.05
        )

        # =================================================
        # SHORT ENTRY
        # =================================================

        short_entry_low = (
            price -
            atr * 0.05
        )

        short_entry_high = (
            price +
            atr * 0.25
        )

        # =================================================
        # TAKE PROFIT
        # =================================================

        long_tp = (
            price +
            atr * 1.50
        )

        short_tp = (
            price -
            atr * 1.50
        )

        return {

            "Coin":
                symbol,

            "LONG SCORE":
                long_score,

            "SHORT SCORE":
                short_score,

            "LONG TF":
                long_tf,

            "SHORT TF":
                short_tf,

            "PRICE":
                price,

            "ATR":
                atr,

            "LONG ENTRY LOW":
                long_entry_low,

            "LONG ENTRY HIGH":
                long_entry_high,

            "LONG TP":
                long_tp,

            "SHORT ENTRY LOW":
                short_entry_low,

            "SHORT ENTRY HIGH":
                short_entry_high,

            "SHORT TP":
                short_tp,

            "RSI":
                results[
                    "5M"
                ]["rsi"]
        }

    except Exception:

        return None


# =========================================================
# FORMAT PRICE
# =========================================================

def format_price(value):

    try:

        value = float(
            value
        )

    except Exception:

        return "-"

    if value >= 1000:

        return f"{value:,.2f}"

    if value >= 1:

        return f"{value:.4f}"

    if value >= 0.01:

        return f"{value:.6f}"

    if value >= 0.000001:

        return f"{value:.8f}"

    return f"{value:.10g}"


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header(
    "⚙️ Scanner"
)

coin_limit = st.sidebar.selectbox(
    "Jumlah coin",
    [
        10,
        20,
        30,
        50
    ],
    index=1
)

st.sidebar.caption(
    "5M • 15M • 30M • 1H"
)


# =========================================================
# API TEST
# =========================================================

with st.expander(
    "🔧 API Status"
):

    if st.button(
        "Test API",
        use_container_width=True
    ):

        try:

            test_api()

            st.success(
                "✅ Twelve Data API aktif."
            )

        except Exception as e:

            st.error(
                "❌ API gagal."
            )

            st.code(
                str(e)
            )


# =========================================================
# SCAN MARKET
# =========================================================

if st.button(
    "🔎 SCAN MARKET",
    use_container_width=True
):

    # =====================================================
    # GET COINS
    # =====================================================

    try:

        with st.spinner(
            "Mengambil daftar market..."
        ):

            coins = get_crypto_list()

    except Exception as e:

        st.error(
            "❌ Data market gagal diambil."
        )

        st.code(
            str(e)
        )

        st.stop()

    # =====================================================
    # LIMIT
    # =====================================================

    scan_coins = coins[
        :coin_limit
    ]

    st.info(
        f"Scanning {len(scan_coins)} coin..."
    )

    # =====================================================
    # SCANNING
    # =====================================================

    results = []

    progress = st.progress(
        0
    )

    status = st.empty()

    total = len(
        scan_coins
    )

    for i, symbol in enumerate(
        scan_coins
    ):

        status.write(
            f"🔎 {symbol} "
            f"({i + 1}/{total})"
        )

        result = analyze_coin(
            symbol
        )

        if result is not None:

            results.append(
                result
            )

        progress.progress(
            int(
                (
                    (i + 1)
                    /
                    total
                ) * 100
            )
        )

        # Hindari request terlalu cepat
        time.sleep(
            0.15
        )

    progress.empty()
    status.empty()

    # =====================================================
    # NO RESULT
    # =====================================================

    if not results:

        st.error(
            "❌ Tidak ada coin yang berhasil dianalisis."
        )

        st.stop()

    df = pd.DataFrame(
        results
    )

    # =====================================================
    # BEST LONG
    # =====================================================

    best_long = (
        df
        .sort_values(
            by=[
                "LONG TF",
                "LONG SCORE"
            ],
            ascending=False
        )
        .iloc[0]
    )

    # =====================================================
    # BEST SHORT
    # =====================================================

    best_short = (
        df
        .sort_values(
            by=[
                "SHORT TF",
                "SHORT SCORE"
            ],
            ascending=False
        )
        .iloc[0]
    )

    # =====================================================
    # TRADE SETUPS
    # =====================================================

    st.divider()

    st.header(
        "🎯 Trade Setup"
    )

    # =====================================================
    # LONG
    # =====================================================

    st.success(
        f"""
🟢 **LONG**

### {best_long["Coin"]}

**Target Entry**

`{format_price(best_long["LONG ENTRY LOW"])}`
→
`{format_price(best_long["LONG ENTRY HIGH"])}`

**Take Profit**

`{format_price(best_long["LONG TP"])}`

**Konfirmasi**

{int(best_long["LONG TF"])}/4 timeframe

**Arah**

LONG
"""
    )

    # =====================================================
    # SHORT
    # =====================================================

    st.error(
        f"""
🔴 **SHORT**

### {best_short["Coin"]}

**Target Entry**

`{format_price(best_short["SHORT ENTRY LOW"])}`
→
`{format_price(best_short["SHORT ENTRY HIGH"])}`

**Take Profit**

`{format_price(best_short["SHORT TP"])}`

**Konfirmasi**

{int(best_short["SHORT TF"])}/4 timeframe

**Arah**

SHORT
"""
    )

    # =====================================================
    # ALL CANDIDATES
    # =====================================================

    st.divider()

    st.subheader(
        "📊 Semua Kandidat"
    )

    # =====================================================
    # LONG CANDIDATES
    # =====================================================

    st.markdown(
        "### 🟢 LONG"
    )

    long_df = (
        df
        .sort_values(
            by=[
                "LONG TF",
                "LONG SCORE"
            ],
            ascending=False
        )
        .head(10)
        .copy()
    )

    long_display = pd.DataFrame({

        "Coin":
            long_df["Coin"],

        "Target Entry":
            long_df.apply(
                lambda row:
                f"{format_price(row['LONG ENTRY LOW'])} "
                f"→ "
             
