import streamlit as st
import pandas as pd
import requests
import zipfile
import io
from datetime import datetime, timedelta, timezone


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Binance BB Screener",
    page_icon="📊",
    layout="wide"
)

BB_PERIOD = 20
BB_STD = 2
REQUIRED_CANDLES = 3
INTERVAL = "5m"


# =========================================================
# SYMBOLS
# =========================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "TRXUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "DOTUSDT",
    "UNIUSDT",
    "NEARUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "1000PEPEUSDT",
]


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
    <style>

    .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }

    .title {
        font-size: 32px;
        font-weight: 700;
    }

    .subtitle {
        color: #8b949e;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="title">📊 Binance BB Screener</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Binance Futures • 5m • Bollinger Bands 20/2'
    '</div>',
    unsafe_allow_html=True
)

st.divider()

st.info(
    "Signal = 3 candle 5m berturut-turut close "
    "di luar Bollinger Bands."
)

st.warning(
    "Mode historical: data diambil dari Binance Data Vision, "
    "bukan Binance Futures API live."
)


# =========================================================
# DOWNLOAD HISTORICAL KLINES
# =========================================================

@st.cache_data(ttl=1800)
def download_klines(symbol, date):

    date_string = date.strftime("%Y-%m-%d")

    url = (
        "https://data.binance.vision/"
        "data/futures/um/daily/klines/"
        f"{symbol}/{INTERVAL}/"
        f"{symbol}-{INTERVAL}-{date_string}.zip"
    )

    try:

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        if response.status_code != 200:
            return None

        if not response.content:
            return None

        with zipfile.ZipFile(
            io.BytesIO(response.content)
        ) as z:

            names = z.namelist()

            if not names:
                return None

            with z.open(names[0]) as f:

                df = pd.read_csv(
                    f,
                    header=None
                )

        if df.empty:
            return None

        columns = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore"
        ]

        df = df.iloc[:, :12]
        df.columns = columns

        df["close"] = pd.to_numeric(
            df["close"],
            errors="coerce"
        )

        df["open"] = pd.to_numeric(
            df["open"],
            errors="coerce"
        )

        df["high"] = pd.to_numeric(
            df["high"],
            errors="coerce"
        )

        df["low"] = pd.to_numeric(
            df["low"],
            errors="coerce"
        )

        df = df.dropna(
            subset=["close"]
        )

        return df

    except Exception:
        return None


# =========================================================
# GET LATEST AVAILABLE DATA
# =========================================================

def get_latest_data(symbol):

    today = datetime.now(
        timezone.utc
    ).date()

    # Coba beberapa hari terakhir.
    # Ini menghindari error kalau file hari terbaru
    # belum tersedia.

    for days_back in [1, 2, 3]:

        target_date = (
            today - timedelta(days=days_back)
        )

        df = download_klines(
            symbol,
            target_date
        )

        if df is not None and len(df) >= 30:
            return df, target_date

    return None, None


# =========================================================
# BOLLINGER BANDS
# =========================================================

def calculate_bb(df):

    df = df.copy()

    df["middle"] = (
        df["close"]
        .rolling(BB_PERIOD)
        .mean()
    )

    df["std"] = (
        df["close"]
        .rolling(BB_PERIOD)
        .std(ddof=0)
    )

    df["upper"] = (
        df["middle"]
        + BB_STD * df["std"]
    )

    df["lower"] = (
        df["middle"]
        - BB_STD * df["std"]
    )

    return df


# =========================================================
# SIGNAL
# =========================================================

def detect_signal(df):

    df = calculate_bb(df)

    if len(df) < BB_PERIOD + REQUIRED_CANDLES:
        return None

    recent = df.iloc[
        -REQUIRED_CANDLES:
    ]

    # LONG
    long_signal = (
        recent["close"] <
        recent["lower"]
    ).all()

    # SHORT
    short_signal = (
        recent["close"] >
        recent["upper"]
    ).all()

    last = df.iloc[-1]

    if long_signal:

        return {
            "signal": "LONG",
            "price": float(last["close"]),
            "lower": float(last["lower"]),
            "upper": float(last["upper"])
        }

    if short_signal:

        return {
            "signal": "SHORT",
            "price": float(last["close"]),
            "lower": float(last["lower"]),
            "upper": float(last["upper"])
        }

    return None


# =========================================================
# SCAN
# =========================================================

def scan_market():

    results = []

    progress = st.progress(0)

    status = st.empty()

    total = len(SYMBOLS)

    for i, symbol in enumerate(SYMBOLS):

        status.write(
            f"Scanning {symbol}..."
        )

        df, data_date = get_latest_data(
            symbol
        )

        if df is not None:

            signal = detect_signal(df)

            if signal:

                signal["symbol"] = symbol
                signal["date"] = str(
                    data_date
                )

                results.append(signal)

        progress.progress(
            (i + 1) / total
        )

    status.empty()
    progress.empty()

    return results


# =========================================================
# BUTTON
# =========================================================

if st.button(
    "🔄 SCAN MARKET",
    use_container_width=True
):

    with st.spinner(
        "Scanning Binance historical data..."
    ):

        results = scan_market()

        st.session_state[
            "results"
        ] = results

        st.session_state[
            "scan_time"
        ] = datetime.now(
            timezone.utc
        )


# =========================================================
# RESULTS
# =========================================================

if "results" in st.session_state:

    results = st.session_state[
        "results"
    ]

    long_results = [
        x for x in results
        if x["signal"] == "LONG"
    ]

    short_results = [
        x for x in results
        if x["signal"] == "SHORT"
    ]

    col1, col2 = st.columns(2)


    # =====================================================
    # LONG
    # =====================================================

    with col1:

        st.markdown(
            "### 🟢 LONG"
        )

        if long_results:

            df_long = pd.DataFrame(
                long_results
            )

            df_long = df_long[
                [
                    "symbol",
                    "price",
                    "lower",
                    "upper",
                    "date"
                ]
            ]

            df_long.columns = [
                "Symbol",
                "Price",
                "Lower BB",
                "Upper BB",
                "Date"
            ]

            st.dataframe(
                df_long,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.caption(
                "Tidak ada LONG signal."
            )


    # =====================================================
    # SHORT
    # =====================================================

    with col2:

        st.markdown(
            "### 🔴 SHORT"
        )

        if short_results:

            df_short = pd.DataFrame(
                short_results
            )

            df_short = df_short[
                [
                    "symbol",
                    "price",
                    "lower",
                    "upper",
                    "date"
                ]
            ]

            df_short.columns = [
                "Symbol",
                "Price",
                "Lower BB",
                "Upper BB",
                "Date"
            ]

            st.dataframe(
                df_short,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.caption(
                "Tidak ada SHORT signal."
            )


# =========================================================
# LAST SCAN
# =========================================================

if "scan_time" in st.session_state:

    scan_time = st.session_state[
        "scan_time"
    ]

    st.caption(
        "Scanner run: "
        + scan_time.strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )
