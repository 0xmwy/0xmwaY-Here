import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timezone

# =========================
# CONFIG
# =========================

st.set_page_config(
    page_title="Haiii 0xmwY",
    page_icon="📊",
    layout="wide"
)

API_KEY = st.secrets["937c265e51c344c79b71cd715bb928ba"]
BASE_URL = "https://api.twelvedata.com"

TIMEFRAMES = {
    "5 Menit": "5min",
    "15 Menit": "15min",
    "30 Menit": "30min",
    "1 Jam": "1h",
}

EMA_PERIOD = 200


# =========================
# STYLE
# =========================

st.markdown("""
<style>

.title {
    font-size: 42px;
    font-weight: 800;
}

.subtitle {
    color: #8b949e;
    font-size: 18px;
}

.signal-long {
    background: #123d22;
    padding: 18px;
    border-radius: 12px;
    margin-bottom: 10px;
}

.signal-short {
    background: #4a1717;
    padding: 18px;
    border-radius: 12px;
    margin-bottom: 10px;
}

.signal-neutral {
    background: #22272e;
    padding: 18px;
    border-radius: 12px;
    margin-bottom: 10px;
}

</style>
""", unsafe_allow_html=True)


# =========================
# HEADER
# =========================

st.markdown(
    '<div class="title">📊 Haiii 0xmwY</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">Crypto Market Screener</div>',
    unsafe_allow_html=True
)

st.divider()


# =========================
# FUNCTIONS
# =========================

@st.cache_data(ttl=3600)
def get_crypto_list():

    url = f"{BASE_URL}/cryptocurrencies"

    params = {
        "apikey": API_KEY
    }

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict) and "data" in data:
        data = data["data"]

    if not isinstance(data, list):
        raise Exception("Format daftar crypto tidak dikenali.")

    symbols = []

    for item in data:

        symbol = item.get("symbol")

        if symbol:
            symbols.append(symbol)

    return sorted(list(set(symbols)))


@st.cache_data(ttl=30)
def get_candles(symbol, interval):

    url = f"{BASE_URL}/time_series"

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": 220,
        "apikey": API_KEY
    }

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    data = response.json()

    if isinstance(data, dict) and data.get("status") == "error":
        return None

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

    df = df.dropna(subset=["close"])

    if len(df) < EMA_PERIOD:
        return None

    # API mengembalikan candle terbaru di atas.
    # Balik supaya urutan waktunya lama -> baru.
    df = df.iloc[::-1].reset_index(drop=True)

    df["ema200"] = (
        df["close"]
        .ewm(
            span=EMA_PERIOD,
            adjust=False
        )
        .mean()
    )

    return df


def analyze(symbol, interval):

    df = get_candles(symbol, interval)

    if df is None or df.empty:
        return None

    last = df.iloc[-1]

    price = float(last["close"])
    ema = float(last["ema200"])

    previous = df.iloc[-2]

    previous_price = float(previous["close"])
    previous_ema = float(previous["ema200"])

    signal = "NEUTRAL"

    # =========================
    # LONG
    # =========================

    if (
        price > ema
        and previous_price <= previous_ema
    ):
        signal = "LONG"

    # =========================
    # SHORT
    # =========================

    elif (
        price < ema
        and previous_price >= previous_ema
    ):
        signal = "SHORT"

    distance = ((price - ema) / ema) * 100

    return {
        "Symbol": symbol,
        "Price": price,
        "EMA": ema,
        "Distance %": distance,
        "Signal": signal
    }


# =========================
# CONTROLS
# =========================

col1, col2 = st.columns(2)

with col1:

    timeframe_name = st.selectbox(
        "Timeframe",
        list(TIMEFRAMES.keys())
    )

with col2:

    max_coins = st.selectbox(
        "Jumlah coin",
        [10, 25, 50, 100],
        index=0
    )


interval = TIMEFRAMES[timeframe_name]


# =========================
# SCAN
# =========================

if st.button(
    "🔄 SCAN MARKET",
    use_container_width=True
):

    with st.spinner("Mengambil daftar crypto..."):

        try:

            symbols = get_crypto_list()

        except Exception as e:

            st.error(
                f"Gagal mengambil daftar coin: {e}"
            )

            st.stop()

    if not symbols:

        st.error("Daftar coin kosong.")
        st.stop()

    # Batasi dahulu supaya API tidak langsung
    # menghabiskan banyak credit.

    symbols = symbols[:max_coins]

    results = []

    progress = st.progress(0)

    status = st.empty()

    total = len(symbols)

    for i, symbol in enumerate(symbols):

        status.text(
            f"Scanning {symbol} "
            f"({i + 1}/{total})"
        )

        try:

            result = analyze(
                symbol,
                interval
            )

            if result:
                results.append(result)

        except Exception:
            pass

        progress.progress(
            (i + 1) / total
        )

        # Sedikit jeda agar tidak terlalu agresif
        time.sleep(0.15)

    progress.empty()
    status.empty()

    if not results:

        st.warning(
            "Tidak ada data yang berhasil diambil."
        )

        st.stop()

    df = pd.DataFrame(results)

    # =========================
    # SIGNAL FILTER
    # =========================

    long_df = df[
        df["Signal"] == "LONG"
    ].copy()

    short_df = df[
        df["Signal"] == "SHORT"
    ].copy()

    # Urut berdasarkan jarak dari EMA
    long_df["Distance %"] = (
        long_df["Distance %"].round(3)
    )

    short_df["Distance %"] = (
        short_df["Distance %"].round(3)
    )

    # =========================
    # RESULTS
    # =========================

    st.divider()

    st.subheader(
        f"Market Scan • {timeframe_name}"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.markdown(
            f"""
            <div class="signal-long">
            <h2>🟢 LONG</h2>
            <h3>{len(long_df)} signal</h3>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:

        st.markdown(
            f"""
            <div class="signal-short">
            <h2>🔴 SHORT</h2>
            <h3>{len(short_df)} signal</h3>
            </div>
            """,
            unsafe_allow_html=True
        )

    # =========================
    # LONG TABLE
    # =========================

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
                    "EMA",
                    "Distance %",
                    "Signal"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    # =========================
    # SHORT TABLE
    # =========================

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
                    "EMA",
                    "Distance %",
                    "Signal"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    # =========================
    # TIME
    # =========================

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    st.caption(
        f"Scanner run: {now}"
    )
