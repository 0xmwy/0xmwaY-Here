import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timezone


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Binance BB Screener",
    page_icon="📊",
    layout="wide"
)

BINANCE_URLS = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com",
]

BB_PERIOD = 20
BB_STD = 2
REQUIRED_CANDLES = 3
INTERVAL = "5m"


# =========================================================
# CUSTOM CSS
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

    .signal-long {
        color: #00c853;
        font-weight: bold;
    }

    .signal-short {
        color: #ff1744;
        font-weight: bold;
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
    "Signal = 3 candle 5m berturut-turut close di luar Bollinger Bands."
)


# =========================================================
# HTTP SESSION
# =========================================================

session = requests.Session()

session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
)


# =========================================================
# REQUEST BINANCE DENGAN FALLBACK
# =========================================================

def binance_get(endpoint, params=None):
    """
    Mencoba beberapa endpoint Binance Futures.
    Kalau satu terkena error / gagal koneksi,
    otomatis mencoba endpoint berikutnya.
    """

    last_error = None

    for base_url in BINANCE_URLS:

        url = f"{base_url}{endpoint}"

        try:
            response = session.get(
                url,
                params=params,
                timeout=15
            )

            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as e:

            status = response.status_code

            last_error = (
                f"HTTP {status} dari {base_url}"
            )

            continue

        except requests.exceptions.RequestException as e:

            last_error = str(e)

            continue

        except ValueError as e:

            last_error = str(e)

            continue

    raise RuntimeError(
        "Semua endpoint Binance gagal. "
        f"Error terakhir: {last_error}"
    )


# =========================================================
# GET BINANCE SYMBOLS
# =========================================================

@st.cache_data(ttl=300)
def get_symbols():

    data = binance_get(
        "/fapi/v1/exchangeInfo"
    )

    symbols = []

    for s in data.get("symbols", []):

        if (
            s.get("quoteAsset") == "USDT"
            and s.get("contractType") == "PERPETUAL"
            and s.get("status") == "TRADING"
        ):
            symbols.append(
                s.get("symbol")
            )

    return symbols


# =========================================================
# GET KLINES
# =========================================================

def get_klines(symbol):

    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": 50,
    }

    data = binance_get(
        "/fapi/v1/klines",
        params=params
    )

    if not isinstance(data, list):
        return None

    if len(data) < BB_PERIOD + REQUIRED_CANDLES:
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
        "ignore",
    ]

    df = pd.DataFrame(
        data,
        columns=columns
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    return df


# =========================================================
# CALCULATE BOLLINGER BANDS
# =========================================================

def calculate_bb(df):

    df = df.copy()

    df["bb_middle"] = (
        df["close"]
        .rolling(BB_PERIOD)
        .mean()
    )

    df["bb_std"] = (
        df["close"]
        .rolling(BB_PERIOD)
        .std(ddof=0)
    )

    df["bb_upper"] = (
        df["bb_middle"]
        + BB_STD * df["bb_std"]
    )

    df["bb_lower"] = (
        df["bb_middle"]
        - BB_STD * df["bb_std"]
    )

    return df


# =========================================================
# DETECT SIGNAL
# =========================================================

def detect_signal(df):

    if df is None or df.empty:
        return None

    df = calculate_bb(df)

    recent = df.iloc[-REQUIRED_CANDLES:]

    if recent[
        ["bb_upper", "bb_lower"]
    ].isna().any().any():
        return None

    closes = recent["close"]
    upper = recent["bb_upper"]
    lower = recent["bb_lower"]

    # LONG:
    # 3 candle terakhir close di bawah lower BB

    long_condition = (
        closes < lower
    ).all()

    # SHORT:
    # 3 candle terakhir close di atas upper BB

    short_condition = (
        closes > upper
    ).all()

    last_close = float(
        df.iloc[-1]["close"]
    )

    last_upper = float(
        df.iloc[-1]["bb_upper"]
    )

    last_lower = float(
        df.iloc[-1]["bb_lower"]
    )

    if long_condition:

        return {
            "symbol": None,
            "signal": "LONG",
            "close": last_close,
            "upper": last_upper,
            "lower": last_lower,
        }

    if short_condition:

        return {
            "symbol": None,
            "signal": "SHORT",
            "close": last_close,
            "upper": last_upper,
            "lower": last_lower,
        }

    return None


# =========================================================
# SCAN ONE SYMBOL
# =========================================================

def scan_symbol(symbol):

    try:

        df = get_klines(symbol)

        result = detect_signal(df)

        if result is not None:

            result["symbol"] = symbol

            return result

    except Exception:
        return None

    return None


# =========================================================
# SCAN MARKET
# =========================================================

def scan_market():

    symbols = get_symbols()

    results = []

    progress = st.progress(0)

    total = len(symbols)

    for i, symbol in enumerate(symbols):

        result = scan_symbol(symbol)

        if result is not None:
            results.append(result)

        progress.progress(
            int(((i + 1) / total) * 100)
        )

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
        "Scanning Binance Futures..."
    ):

        try:

            results = scan_market()

            scan_time = datetime.now(
                timezone.utc
            )

            st.session_state[
                "results"
            ] = results

            st.session_state[
                "scan_time"
            ] = scan_time

        except Exception as e:

            st.error(
                f"Binance connection error: {e}"
            )


# =========================================================
# DISPLAY RESULTS
# =========================================================

if "results" in st.session_state:

    results = st.session_state["results"]

    long_results = [
        r for r in results
        if r["signal"] == "LONG"
    ]

    short_results = [
        r for r in results
        if r["signal"] == "SHORT"
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

            long_df = pd.DataFrame(
                long_results
            )

            long_df = long_df[
                [
                    "symbol",
                    "close",
                    "lower",
                    "upper",
                ]
            ]

            long_df.columns = [
                "Symbol",
                "Price",
                "Lower BB",
                "Upper BB",
            ]

            st.dataframe(
                long_df,
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

            short_df = pd.DataFrame(
                short_results
            )

            short_df = short_df[
                [
                    "symbol",
                    "close",
                    "lower",
                    "upper",
                ]
            ]

            short_df.columns = [
                "Symbol",
                "Price",
                "Lower BB",
                "Upper BB",
            ]

            st.dataframe(
                short_df,
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
        "Last scan: "
        + scan_time.strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )
