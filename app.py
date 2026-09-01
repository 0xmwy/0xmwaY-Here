import streamlit as st
import pandas as pd
import requests
import zipfile
import io
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Haiii 0xmwY",
    page_icon="👋",
    layout="wide"
)

DATA_URL = "https://data.binance.vision"

EMA_TREND = 200
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14

TIMEFRAMES = {
    "5m": "5m",
    "15m": "15m",
    "1H": "1h"
}

MAX_WORKERS = 8


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
    '<div class="subtitle">Scalping Market Screener</div>',
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
    min_score = st.selectbox(
        "Minimum Score",
        [3, 4, 5],
        index=0
    )

with col3:
    max_results = st.selectbox(
        "Tampilkan",
        [20, 50, 100, 200],
        index=1
    )

st.caption(
    "Semua USDT-M perpetual • 1H + 15m trend • 5m momentum"
)


# =========================================================
# HTTP SESSION
# =========================================================

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})


# =========================================================
# GET ALL SYMBOLS
# =========================================================

@st.cache_data(ttl=3600)
def get_all_symbols():

    # Kita coba beberapa endpoint metadata Binance.
    # Ini hanya untuk mendapatkan daftar pair.
    urls = [
        "https://fapi.binance.com/fapi/v1/exchangeInfo",
        "https://fapi1.binance.com/fapi/v1/exchangeInfo",
        "https://fapi2.binance.com/fapi/v1/exchangeInfo",
        "https://fapi3.binance.com/fapi/v1/exchangeInfo",
        "https://fapi4.binance.com/fapi/v1/exchangeInfo"
    ]

    for url in urls:

        try:

            response = session.get(
                url,
                timeout=15
            )

            if response.status_code != 200:
                continue

            data = response.json()

            symbols = []

            for item in data.get(
                "symbols",
                []
            ):

                if (
                    item.get("status") == "TRADING"
                    and item.get("contractType")
                    == "PERPETUAL"
                    and item.get("quoteAsset")
                    == "USDT"
                ):

                    symbols.append(
                        item["symbol"]
                    )

            if symbols:
                return sorted(
                    list(set(symbols))
                )

        except Exception:
            continue

    return []


# =========================================================
# DOWNLOAD HISTORICAL KLINES
# =========================================================

@st.cache_data(ttl=1800)
def download_klines(
    symbol,
    interval,
    date
):

    date_string = date.strftime(
        "%Y-%m-%d"
    )

    url = (
        f"{DATA_URL}/data/futures/um/daily/"
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

        df = df.dropna(
            subset=[
                "close",
                "volume"
            ]
        )

        return df

    except Exception:

        return None


# =========================================================
# GET LATEST AVAILABLE DATA
# =========================================================

def get_data(
    symbol,
    interval
):

    today = datetime.now(
        timezone.utc
    ).date()

    for days_back in range(1, 8):

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
            and len(df)
            >= EMA_TREND + 30
        ):

            return df

    return None


# =========================================================
# INDICATORS
# =========================================================

def add_indicators(df):

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

    # Volume
    df["volume_avg"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    return df


# =========================================================
# ANALYZE SYMBOL
# =========================================================

def analyze_symbol(symbol):

    try:

        data_1h = get_data(
            symbol,
            "1h"
        )

        data_15m = get_data(
            symbol,
            "15m"
        )

        data_5m = get_data(
            symbol,
            "5m"
        )

        if (
            data_1h is None
            or data_15m is None
            or data_5m is None
        ):
            return None

        data_1h = add_indicators(
            data_1h
        )

        data_15m = add_indicators(
            data_15m
        )

        data_5m = add_indicators(
            data_5m
        )

        h1 = data_1h.iloc[-1]
        m15 = data_15m.iloc[-1]
        m5 = data_5m.iloc[-1]

        # =================================================
        # SHORT SCORE
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
        # LONG SCORE
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
        # SIGNAL
        # =================================================

        if (
            direction in ["ALL", "SHORT"]
            and short_score >= min_score
        ):

            signal = "SHORT"
            score = short_score

        elif (
            direction in ["ALL", "LONG"]
            and long_score >= min_score
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
            "Price": float(
                m5["close"]
            ),
            "RSI": round(
                float(m5["rsi"]),
                2
            )
        }

    except Exception:

        return None


# =========================================================
# SCAN ALL MARKET
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

        futures = {
            executor.submit(
                analyze_symbol,
                symbol
            ): symbol
            for symbol in symbols
        }

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
                f"{completed}/{total} coins..."
            )

    progress.empty()
    status.empty()

    return results


# =========================================================
# BUTTON
# =========================================================

if st.button(
    "🔄 SCAN ALL BINANCE",
    use_container_width=True
):

    with st.spinner(
        "Mengambil semua pair Binance Futures..."
    ):

        symbols = get_all_symbols()

        if not symbols:

            st.error(
                "Tidak bisa mendapatkan daftar "
                "coin Binance Futures."
            )

        else:

            st.info(
                f"{len(symbols)} pair ditemukan. "
                "Memulai scanning..."
            )

            results = scan_market(
                symbols
            )

            st.session_state[
                "results"
            ] = results

            st.session_state[
                "scan_time"
            ] = datetime.now(
                timezone.utc
            )

            st.session_state[
                "symbol_count"
            ] = len(symbols)


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
            "Tidak ada setup yang memenuhi filter."
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

        df = df.head(
            max_results
        )

        st.subheader(
            f"📊 Top {len(df)} Setup"
        )

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# INFO
# =========================================================

if "symbol_count" in st.session_state:

    st.caption(
        "Pair scanned: "
        + str(
            st.session_state[
                "symbol_count"
            ]
        )
    )


if "scan_time" in st.session_state:

    st.caption(
        "Last scan: "
        +
        st.session_state[
            "scan_time"
        ].strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )
