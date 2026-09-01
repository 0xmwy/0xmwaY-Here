import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Haiii 0xmwY",
    page_icon="📊",
    layout="wide"
)

# API KEY
API_KEY = "937c265e51c344c79b71cd715bb928ba"

BASE_URL = "https://api.twelvedata.com"

EMA_PERIOD = 200

TIMEFRAMES = {
    "5 Menit": "5min",
    "15 Menit": "15min",
    "30 Menit": "30min",
    "1 Jam": "1h"
}


# =========================================================
# STYLE
# =========================================================

st.markdown("""
<style>

.main-title {
    font-size: 42px;
    font-weight: 800;
}

.subtitle {
    font-size: 18px;
    color: #8b949e;
}

.long-box {
    background: #123d22;
    padding: 18px;
    border-radius: 12px;
}

.short-box {
    background: #4a1717;
    padding: 18px;
    border-radius: 12px;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="main-title">📊 Haiii 0xmwY</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">Crypto Market Screener</div>',
    unsafe_allow_html=True
)

st.divider()


# =========================================================
# API REQUEST HELPER
# =========================================================

def api_get(endpoint, params):

    params["apikey"] = API_KEY

    response = requests.get(
        f"{BASE_URL}{endpoint}",
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
        "/cryptocurrencies",
        {}
    )

    if not isinstance(data, list):

        if isinstance(data, dict):
            data = data.get("data", [])

    symbols = []

    for item in data:

        symbol = item.get("symbol")

        if symbol:
            symbols.append(symbol)

    # Hanya pasangan USD
    usd_symbols = [
        x for x in symbols
        if x.endswith("/USD")
    ]

    return sorted(
        list(set(usd_symbols))
    )


# =========================================================
# GET CANDLE
# =========================================================

@st.cache_data(ttl=30)
def get_candles(symbol, interval):

    data = api_get(
        "/time_series",
        {
            "symbol": symbol,
            "interval": interval,
            "outputsize": 220
        }
    )

    values = data.get("values")

    if not values:
        return None

    df = pd.DataFrame(values)

    if "close" not in df.columns:
        return None

    df["close"] = pd.to_numeric(
        df["close"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["close"]
    )

    if len(df) < EMA_PERIOD:
        return None

    # API biasanya mengirim terbaru -> terlama
    # Kita balik menjadi terlama -> terbaru
    df = df.iloc[::-1].reset_index(
        drop=True
    )

    # EMA 200
    df["ema200"] = (
        df["close"]
        .ewm(
            span=EMA_PERIOD,
            adjust=False
        )
        .mean()
    )

    return df


# =========================================================
# ANALYZE
# =========================================================

def analyze(symbol, interval):

    df = get_candles(
        symbol,
        interval
    )

    if df is None:
        return None

    if len(df) < 3:
        return None

    current = df.iloc[-1]
    previous = df.iloc[-2]

    price = float(
        current["close"]
    )

    ema = float(
        current["ema200"]
    )

    previous_price = float(
        previous["close"]
    )

    previous_ema = float(
        previous["ema200"]
    )

    signal = "NEUTRAL"

    # =====================================================
    # LONG
    # =====================================================

    if (
        price > ema
        and previous_price <= previous_ema
    ):
        signal = "LONG"

    # =====================================================
    # SHORT
    # =====================================================

    elif (
        price < ema
        and previous_price >= previous_ema
    ):
        signal = "SHORT"

    distance = (
        (price - ema)
        / ema
        * 100
    )

    return {
        "Symbol": symbol,
        "Price": price,
        "EMA200": ema,
        "Distance %": distance,
        "Signal": signal
    }


# =========================================================
# CONTROLS
# =========================================================

col1, col2 = st.columns(2)

with col1:

    timeframe_name = st.selectbox(
        "Timeframe",
        list(TIMEFRAMES.keys())
    )

with col2:

    max_coins = st.selectbox(
        "Jumlah coin yang discan",
        [10, 25, 50, 100],
        index=0
    )


interval = TIMEFRAMES[
    timeframe_name
]


# =========================================================
# SCAN BUTTON
# =========================================================

if st.button(
    "🔄 SCAN MARKET",
    use_container_width=True
):

    # -----------------------------------------------------
    # GET SYMBOLS
    # -----------------------------------------------------

    with st.spinner(
        "Mengambil daftar cryptocurrency..."
    ):

        try:

            symbols = get_crypto_list()

        except Exception as e:

            st.error(
                f"Gagal mengambil daftar coin: {e}"
            )

            st.stop()

    if not symbols:

        st.error(
            "Tidak ada cryptocurrency yang ditemukan."
        )

        st.stop()

    # -----------------------------------------------------
    # LIMIT SCAN
    # -----------------------------------------------------

    symbols = symbols[:max_coins]

    results = []

    progress = st.progress(0)

    status = st.empty()

    total = len(symbols)

    # -----------------------------------------------------
    # SCAN
    # -----------------------------------------------------

    for index, symbol in enumerate(symbols):

        status.write(
            f"Scanning {symbol} "
            f"({index + 1}/{total})"
        )

        try:

            result = analyze(
                symbol,
                interval
            )

            if result is not None:
                results.append(result)

        except Exception:
            pass

        progress.progress(
            (index + 1) / total
        )

    progress.empty()
    status.empty()

    # -----------------------------------------------------
    # NO DATA
    # -----------------------------------------------------

    if not results:

        st.warning(
            "Tidak ada data yang berhasil diambil."
        )

        st.stop()

    # -----------------------------------------------------
    # DATAFRAME
    # -----------------------------------------------------

    df = pd.DataFrame(results)

    df["Price"] = df["Price"].round(8)
    df["EMA200"] = df["EMA200"].round(8)
    df["Distance %"] = df["Distance %"].round(3)

    # -----------------------------------------------------
    # SIGNALS
    # -----------------------------------------------------

    long_df = df[
        df["Signal"] == "LONG"
    ].copy()

    short_df = df[
        df["Signal"] == "SHORT"
    ].copy()

    # =====================================================
    # SUMMARY
    # =====================================================

    st.divider()

    st.subheader(
        f"Market Scan — {timeframe_name}"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.markdown(
            f"""
            <div class="long-box">
                <h2>🟢 LONG</h2>
                <h3>{len(long_df)} signal</h3>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:

        st.markdown(
            f"""
            <div class="short-box">
                <h2>🔴 SHORT</h2>
                <h3>{len(short_df)} signal</h3>
            </div>
            """,
            unsafe_allow_html=True
        )

    # =====================================================
    # LONG
    # =====================================================

    st.subheader("🟢 LONG")

    if long_df.empty:

        st.info(
            "Tidak ada LONG signal."
        )

    else:

        st.dataframe(
            long_df[
                [
                    "Symbol",
                    "Price",
                    "EMA200",
                    "Distance %",
                    "Signal"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    # =====================================================
    # SHORT
    # =====================================================

    st.subheader("🔴 SHORT")

    if short_df.empty:

        st.info(
            "Tidak ada SHORT signal."
        )

    else:

        st.dataframe(
            short_df[
                [
                    "Symbol",
                    "Price",
                    "EMA200",
                    "Distance %",
                    "Signal"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    # =====================================================
    # ALL RESULTS
    # =====================================================

    with st.expander(
        "📋 Lihat semua hasil scan"
    ):

        st.dataframe(
            df[
                [
                    "Symbol",
                    "Price",
                    "EMA200",
                    "Distance %",
                    "Signal"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    # =====================================================
    # TIME
    # =====================================================

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    st.caption(
        f"Scanner run: {now}"
            )
