import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timezone

st.set_page_config(
    page_title="Binance BB Screener",
    page_icon="📊",
    layout="wide"
)

BINANCE_URL = "https://fapi.binance.com"
BB_PERIOD = 20
BB_STD = 2
REQUIRED_CANDLES = 3


st.markdown("""
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
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def get_symbols():

    url = f"{BINANCE_URL}/fapi/v1/exchangeInfo"

    response = requests.get(url, timeout=15)
    response.raise_for_status()

    data = response.json()

    return [
        s["symbol"]
        for s in data["symbols"]
        if s["quoteAsset"] == "USDT"
        and s["contractType"] == "PERPETUAL"
        and s["status"] == "TRADING"
    ]


def get_klines(symbol):

    url = f"{BINANCE_URL}/fapi/v1/klines"

    params = {
        "symbol": symbol,
        "interval": "5m",
        "limit": 50
    }

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
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

    df = pd.DataFrame(data, columns=columns)

    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    return df


def calculate_bb(df):

    df = df.copy()

    df["middle"] = (
        df["close"]
        .rolling(BB_PERIOD)
        .mean()
    )

    std = (
        df["close"]
        .rolling(BB_PERIOD)
        .std()
    )

    df["upper"] = (
        df["middle"] +
        BB_STD * std
    )

    df["lower"] = (
        df["middle"] -
        BB_STD * std
    )

    return df


def check_signal(df):

    df = calculate_bb(df)

    # Candle terakhir masih berjalan,
    # jadi tidak digunakan.
    df = df.iloc[:-1]

    last = df.tail(REQUIRED_CANDLES)

    if len(last) < REQUIRED_CANDLES:
        return None

    if last["close"].isna().any():
        return None

    long_signal = (
        last["close"] > last["upper"]
    ).all()

    short_signal = (
        last["close"] < last["lower"]
    ).all()

    if long_signal:
        return "LONG"

    if short_signal:
        return "SHORT"

    return None


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
    "Signal = 3 candle 5m berturut-turut "
    "close di luar Bollinger Bands."
)

if st.button(
    "🔄 SCAN MARKET",
    use_container_width=True
):

    results = []

    try:
        symbols = get_symbols()

        progress = st.progress(0)
        status = st.empty()

        total = len(symbols)

        for i, symbol in enumerate(symbols):

            status.text(
                f"Scanning {symbol} "
                f"({i + 1}/{total})"
            )

            try:

                df = get_klines(symbol)

                if df is not None:

                    signal = check_signal(df)

                    if signal:

                        candle = df.iloc[-2]

                        results.append({
                            "Symbol": symbol,
                            "Signal": signal,
                            "Price": candle["close"],
                            "Volume": candle["volume"]
                        })

            except Exception:
                pass

            progress.progress(
                (i + 1) / total
            )

        progress.empty()
        status.empty()

        st.session_state["results"] = results
        st.session_state["scan_time"] = datetime.now(
            timezone.utc
        )

    except Exception as e:

        st.error(
            f"Binance connection error: {e}"
        )


if "results" in st.session_state:

    results = st.session_state["results"]

    st.subheader("Signals")

    if not results:

        st.success(
            "Tidak ada signal saat ini."
        )

    else:

        result_df = pd.DataFrame(results)

        long_df = result_df[
            result_df["Signal"] == "LONG"
        ]

        short_df = result_df[
            result_df["Signal"] == "SHORT"
        ]

        col1, col2 = st.columns(2)

        with col1:

            st.markdown("### 🟢 LONG")

            if not long_df.empty:

                st.dataframe(
                    long_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.caption(
                    "Tidak ada LONG signal."
                )

        with col2:

            st.markdown("### 🔴 SHORT")

            if not short_df.empty:

                st.dataframe(
                    short_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.caption(
                    "Tidak ada SHORT signal."
                )

        st.caption(
            "Last scan: "
            + st.session_state["scan_time"].strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            )
