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

API_KEY = "937c265e51c344c79b71cd715bb928ba"

BASE_URL = "https://api.twelvedata.com"

EMA_TREND = 200
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14


# =========================================================
# HEADER
# =========================================================

st.markdown(
    """
    <h1>👋 Haiii 0xmwY</h1>
    <p>Multi-Timeframe Scalping Screener</p>
    """,
    unsafe_allow_html=True
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
def get_crypto_symbols():

    data = api_get(
        "/cryptocurrencies"
    )

    if isinstance(data, dict):
        data = data.get("data", [])

    symbols = []

    for coin in data:

        symbol = coin.get("symbol")

        if symbol:
            symbols.append(symbol)

    # Fokus pasangan USD
    symbols = [
        s for s in symbols
        if s.endswith("/USD")
    ]

    return sorted(
        list(set(symbols))
    )


# =========================================================
# GET CANDLES
# =========================================================

@st.cache_data(ttl=60)
def get_candles(symbol, interval):

    data = api_get(
        "/time_series",
        {
            "symbol": symbol,
            "interval": interval,
            "outputsize": 250
        }
    )

    values = data.get("values")

    if not values:
        return None

    df = pd.DataFrame(values)

    required_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]

    for column in required_columns:

        if column not in df.columns:
            return None

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(
        subset=required_columns
    )

    if len(df) < 220:
        return None

    # Lama -> terbaru
    df = df.iloc[::-1].reset_index(
        drop=True
    )

    return df


# =========================================================
# INDICATORS
# =========================================================

def add_indicators(df):

    df = df.copy()

    # EMA 200
    df["ema200"] = (
        df["close"]
        .ewm(
            span=EMA_TREND,
            adjust=False
        )
        .mean()
    )

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
        .rolling(RSI_PERIOD)
        .mean()
    )

    avg_loss = (
        loss
        .rolling(RSI_PERIOD)
        .mean()
    )

    rs = avg_gain / avg_loss.replace(
        0,
        pd.NA
    )

    df["rsi"] = (
        100 -
        (
            100 /
            (1 + rs)
        )
    )

    # Rata-rata volume 20 candle
    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


# =========================================================
# ANALYZE COIN
# =========================================================

def analyze_coin(symbol):

    try:

        # -------------------------------------------------
        # GET ALL TIMEFRAMES
        # -------------------------------------------------

        df_1h = get_candles(
            symbol,
            "1h"
        )

        df_30m = get_candles(
            symbol,
            "30min"
        )

        df_15m = get_candles(
            symbol,
            "15min"
        )

        df_5m = get_candles(
            symbol,
            "5min"
        )

        if any(
            df is None
            for df in [
                df_1h,
                df_30m,
                df_15m,
                df_5m
            ]
        ):
            return None

        # -------------------------------------------------
        # ADD INDICATORS
        # -------------------------------------------------

        df_1h = add_indicators(df_1h)
        df_30m = add_indicators(df_30m)
        df_15m = add_indicators(df_15m)
        df_5m = add_indicators(df_5m)

        # Candle terakhir yang SUDAH CLOSE
        h1 = df_1h.iloc[-2]
        m30 = df_30m.iloc[-2]
        m15 = df_15m.iloc[-2]
        m5 = df_5m.iloc[-2]

        # =================================================
        # LONG SCORE
        # =================================================

        long_score = 0

        # 1H bullish
        if h1["close"] > h1["ema200"]:
            long_score += 1

        # 30M bullish
        if (
            m30["close"] > m30["ema200"]
            and
            m30["ema9"] > m30["ema21"]
        ):
            long_score += 1

        # 15M bullish momentum
        if m15["ema9"] > m15["ema21"]:
            long_score += 1

        # 5M bullish momentum
        if (
            m5["ema9"] > m5["ema21"]
            and
            m5["close"] > m5["ema9"]
        ):
            long_score += 1

        # RSI + volume
        if (
            45 <= m5["rsi"] <= 70
            and
            m5["volume"] > m5["volume_avg"]
        ):
            long_score += 1

        # =================================================
        # SHORT SCORE
        # =================================================

        short_score = 0

        # 1H bearish
        if h1["close"] < h1["ema200"]:
            short_score += 1

        # 30M bearish
        if (
            m30["close"] < m30["ema200"]
            and
            m30["ema9"] < m30["ema21"]
        ):
            short_score += 1

        # 15M bearish momentum
        if m15["ema9"] < m15["ema21"]:
            short_score += 1

        # 5M bearish momentum
        if (
            m5["ema9"] < m5["ema21"]
            and
            m5["close"] < m5["ema9"]
        ):
            short_score += 1

        # RSI + volume
        if (
            30 <= m5["rsi"] <= 55
            and
            m5["volume"] > m5["volume_avg"]
        ):
            short_score += 1

        # =================================================
        # SELECT SIGNAL
        # =================================================

        if long_score > short_score:

            signal = "LONG"
            score = long_score

        elif short_score > long_score:

            signal = "SHORT"
            score = short_score

        else:

            signal = "NEUTRAL"
            score = long_score

        # Hanya tampilkan score >= 3
        if score < 3:
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
            "Coin": symbol,
            "Signal": signal,
            "Score": score,
            "Strength": strength,
            "Price": float(m5["close"]),
            "RSI": round(
                float(m5["rsi"]),
                2
            ),
            "EMA200 1H": round(
                float(h1["ema200"]),
                6
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

max_coins = st.sidebar.selectbox(
    "Jumlah coin",
    [10, 25, 50, 100],
    index=1
)

minimum_score = st.sidebar.selectbox(
    "Minimum Score",
    [3, 4, 5],
    index=0
)


# =========================================================
# SCAN
# =========================================================

if st.button(
    "🔎 SCAN MARKET",
    use_container_width=True
):

    try:

        # -------------------------------------------------
        # GET COINS
        # -------------------------------------------------

        with st.spinner(
            "Mengambil daftar cryptocurrency..."
        ):

            symbols = get_crypto_symbols()

        if not symbols:

            st.error(
                "Daftar coin kosong."
            )

            st.stop()

        symbols = symbols[:max_coins]

        # -------------------------------------------------
        # SCANNING
        # -------------------------------------------------

        results = []

        progress = st.progress(0)

        status = st.empty()

        total = len(symbols)

        for index, symbol in enumerate(
            symbols
        ):

            status.write(
                f"Scanning {symbol} "
                f"({index + 1}/{total})"
            )

            result = analyze_coin(
                symbol
            )

            if result:

                if (
                    result["Score"]
                    >= minimum_score
                ):

                    results.append(
                        result
                    )

            progress.progress(
                (index + 1) / total
            )

            time.sleep(0.1)

        progress.empty()
        status.empty()

        # -------------------------------------------------
        # NO SIGNAL
        # -------------------------------------------------

        if not results:

            st.warning(
                "Belum ada setup yang memenuhi "
                "kriteria."
            )

            st.info(
                "Coba gunakan Minimum Score = 3."
            )

            st.stop()

        # -------------------------------------------------
        # DATA
        # -------------------------------------------------

        df = pd.DataFrame(
            results
        )

        df = df.sort_values(
            by="Score",
            ascending=False
        )

        long_df = df[
            df["Signal"] == "LONG"
        ]

        short_df = df[
            df["Signal"] == "SHORT"
        ]

        # =================================================
        # SUMMARY
        # =================================================

        st.divider()

        col1, col2 = st.columns(2)

        with col1:

            st.metric(
                "🟢 LONG",
                len(long_df)
            )

        with col2:

            st.metric(
                "🔴 SHORT",
                len(short_df)
            )

        # =================================================
        # LONG
        # =================================================

        st.subheader(
            "🟢 LONG SETUPS"
        )

        if long_df.empty:

            st.info(
                "Belum ada LONG setup."
            )

        else:

            st.dataframe(
                long_df,
                use_container_width=True,
                hide_index=True
            )

        # =================================================
        # SHORT
        # =================================================

        st.subheader(
            "🔴 SHORT SETUPS"
        )

        if short_df.empty:

            st.info(
                "Belum ada SHORT setup."
            )

        else:

            st.dataframe(
                short_df,
                use_container_width=True,
                hide_index=True
            )

        # =================================================
        # BEST SETUP
        # =================================================

        st.divider()

        st.subheader(
            "⭐ Best Setup"
        )

        best = df.iloc[0]

        if best["Signal"] == "LONG":

            st.success(
                f"🟢 {best['Coin']} — "
                f"LONG — "
                f"Score {best['Score']}/5"
            )

        elif best["Signal"] == "SHORT":

            st.error(
                f"🔴 {best['Coin']} — "
                f"SHORT — "
                f"Score {best['Score']}/5"
            )

        st.caption(
            "Signal menggunakan candle yang sudah "
            "close. Ini adalah screener, bukan jaminan profit."
        )

    except Exception as e:

        st.error(
            f"ERROR: {e}"
        )
