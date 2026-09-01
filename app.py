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
    page_title="Haiii 0xmwY",
    page_icon="👋",
    layout="wide"
)

BASE_URL = "https://data.binance.vision"

TIMEFRAMES = {
    "5 menit": "5m",
    "15 menit": "15m",
    "30 menit": "30m",
    "1 jam": "1h"
}

PERIOD = 200
REQUIRED_CANDLES = 3


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
    "1000PEPEUSDT"
]


# =========================================================
# STYLE
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
        font-size: 15px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="title">👋 Haiii 0xmwY</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Binance Futures Screener'
    '</div>',
    unsafe_allow_html=True
)

st.divider()


# =========================================================
# TIMEFRAME SELECTOR
# =========================================================

selected_name = st.selectbox(
    "Timeframe",
    list(TIMEFRAMES.keys())
)

selected_interval = TIMEFRAMES[
    selected_name
]


# =========================================================
# DOWNLOAD DATA
# =========================================================

@st.cache_data(ttl=1800)
def download_klines(symbol, interval, date):

    date_string = date.strftime(
        "%Y-%m-%d"
    )

    url = (
        f"{BASE_URL}/data/futures/um/daily/"
        f"klines/{symbol}/{interval}/"
        f"{symbol}-{interval}-{date_string}.zip"
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

        df = df.dropna(
            subset=["close"]
        )

        return df

    except Exception:

        return None


# =========================================================
# GET LATEST AVAILABLE DATA
# =========================================================

def get_latest_data(
    symbol,
    interval
):

    today = datetime.now(
        timezone.utc
    ).date()

    for days_back in [
        1,
        2,
        3,
        4,
        5
    ]:

        target_date = (
            today -
            timedelta(days=days_back)
        )

        df = download_klines(
            symbol,
            interval,
            target_date
        )

        if (
            df is not None
            and len(df) >= PERIOD + REQUIRED_CANDLES
        ):

            return df, target_date

    return None, None


# =========================================================
# CALCULATE INDICATOR
# =========================================================

def calculate_indicator(df):

    df = df.copy()

    df["indicator"] = (
        df["close"]
        .ewm(
            span=PERIOD,
            adjust=False
        )
        .mean()
    )

    return df


# =========================================================
# DETECT SIGNAL
# =========================================================

def detect_signal(df):

    if df is None:
        return None

    df = calculate_indicator(df)

    if len(df) < PERIOD + REQUIRED_CANDLES:
        return None

    recent = df.iloc[
        -REQUIRED_CANDLES:
    ]

    above = (
        recent["close"] >
        recent["indicator"]
    ).all()

    below = (
        recent["close"] <
        recent["indicator"]
    ).all()

    last = df.iloc[-1]

    if above:

        return {
            "signal": "LONG",
            "price": float(
                last["close"]
            )
        }

    if below:

        return {
            "signal": "SHORT",
            "price": float(
                last["close"]
            )
        }

    return None


# =========================================================
# SCAN MARKET
# =========================================================

def scan_market(interval):

    results = []

    progress = st.progress(0)

    status = st.empty()

    total = len(SYMBOLS)

    for i, symbol in enumerate(SYMBOLS):

        status.write(
            f"Scanning {symbol}..."
        )

        df, data_date = get_latest_data(
            symbol,
            interval
        )

        if df is not None:

            result = detect_signal(
                df
            )

            if result:

                result["symbol"] = symbol

                result["date"] = str(
                    data_date
                )

                results.append(
                    result
                )

        progress.progress(
            (i + 1) / total
        )

    progress.empty()

    status.empty()

    return results


# =========================================================
# SCAN BUTTON
# =========================================================

if st.button(
    "🔄 SCAN MARKET",
    use_container_width=True
):

    with st.spinner(
        "Scanning market..."
    ):

        results = scan_market(
            selected_interval
        )

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
                    "date"
                ]
            ]

            df_long.columns = [
                "Symbol",
                "Price",
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
                    "date"
                ]
            ]

            df_short.columns = [
                "Symbol",
                "Price",
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

    st.caption(
        "Last scan: "
        + st.session_state[
            "scan_time"
        ].strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )
