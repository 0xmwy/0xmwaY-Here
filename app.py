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

BINANCE_URLS = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com",
]

TIMEFRAMES = {
    "5M": "5m",
    "15M": "15m",
    "30M": "30m"
}

BB_PERIOD = 20
BB_STD = 2


# =========================================================
# HEADER
# =========================================================

st.title("👋 Haiii 0xmwY")
st.caption("Binance Futures • Bollinger Bands Scanner")

st.divider()


# =========================================================
# BINANCE REQUEST
# =========================================================

def binance_get(endpoint, params=None):

    if params is None:
        params = {}

    last_error = None

    for base_url in BINANCE_URLS:

        try:

            response = requests.get(
                base_url + endpoint,
                params=params,
                timeout=15
            )

            if response.status_code == 200:
                return response.json()

            last_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

        except Exception as e:

            last_error = str(e)

    raise Exception(
        f"Binance API gagal: {last_error}"
    )


# =========================================================
# GET ALL USDT PERPETUAL
# =========================================================

@st.cache_data(ttl=1800)
def get_symbols():

    data = binance_get(
        "/fapi/v1/exchangeInfo"
    )

    symbols = []

    for item in data.get(
        "symbols",
        []
    ):

        if item.get(
            "status"
        ) != "TRADING":

            continue

        if item.get(
            "quoteAsset"
        ) != "USDT":

            continue

        if item.get(
            "contractType"
        ) != "PERPETUAL":

            continue

        symbol = item.get(
            "symbol"
        )

        if symbol:

            symbols.append(
                symbol
            )

    if not symbols:

        raise Exception(
            "Tidak ada USDT perpetual ditemukan."
        )

    return sorted(
        symbols
    )


# =========================================================
# GET KLINES
# =========================================================

@st.cache_data(ttl=30)
def get_klines(
    symbol,
    interval
):

    data = binance_get(
        "/fapi/v1/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": 100
        }
    )

    if not data:

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

    df = pd.DataFrame(
        data,
        columns=columns
    )

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

    if len(df) < BB_PERIOD + 5:

        return None

    return df


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
        .std()
    )

    df["upper"] = (
        df["middle"]
        +
        BB_STD * df["std"]
    )

    df["lower"] = (
        df["middle"]
        -
        BB_STD * df["std"]
    )

    df["band_width"] = (
        df["upper"]
        -
        df["lower"]
    )

    return df


# =========================================================
# ANALYZE TIMEFRAME
# =========================================================

def analyze_timeframe(df):

    df = calculate_bb(
        df
    )

    # Candle yang sudah close
    current = df.iloc[-2]
    previous = df.iloc[-3]

    close = float(
        current["close"]
    )

    upper = float(
        current["upper"]
    )

    lower = float(
        current["lower"]
    )

    middle = float(
        current["middle"]
    )

    previous_close = float(
        previous["close"]
    )

    previous_lower = float(
        previous["lower"]
    )

    previous_upper = float(
        previous["upper"]
    )

    # =====================================================
    # LONG
    # =====================================================

    long_signal = False

    # Harga sebelumnya di bawah/menyentuh lower
    # kemudian candle sekarang kembali ke atas lower
    if (
        previous_close <= previous_lower
        and
        close > lower
    ):

        long_signal = True

    # Rebound dari lower band
    elif (
        close <= lower * 1.003
        and
        close > previous_close
    ):

        long_signal = True

    # =====================================================
    # SHORT
    # =====================================================

    short_signal = False

    # Harga sebelumnya di atas/menyentuh upper
    # kemudian kembali masuk ke bawah upper
    if (
        previous_close >= previous_upper
        and
        close < upper
    ):

        short_signal = True

    # Rejection dari upper band
    elif (
        close >= upper * 0.997
        and
        close < previous_close
    ):

        short_signal = True

    # =====================================================
    # DISTANCE TO BANDS
    # =====================================================

    lower_distance = abs(
        close - lower
    )

    upper_distance = abs(
        upper - close
    )

    # =====================================================
    # RESULT
    # =====================================================

    return {
        "long": long_signal,
        "short": short_signal,
        "close": close,
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "lower_distance": lower_distance,
        "upper_distance": upper_distance
    }


# =========================================================
# ANALYZE COIN
# =========================================================

def analyze_coin(symbol):

    try:

        results = {}

        for label, interval in TIMEFRAMES.items():

            df = get_klines(
                symbol,
                interval
            )

            if df is None:

                continue

            results[label] = (
                analyze_timeframe(
                    df
                )
            )

        # Minimal 1 timeframe sudah cukup
        if not results:

            return None

        # =================================================
        # SIGNAL COUNT
        # =================================================

        long_count = sum(
            1
            for x in results.values()
            if x["long"]
        )

        short_count = sum(
            1
            for x in results.values()
            if x["short"]
        )

        # =================================================
        # PRICE
        # =================================================

        if "5M" in results:

            price = results[
                "5M"
            ]["close"]

            lower = results[
                "5M"
            ]["lower"]

            upper = results[
                "5M"
            ]["upper"]

            middle = results[
                "5M"
            ]["middle"]

            band_width = (
                upper - lower
            )

        else:

            first = next(
                iter(results.values())
            )

            price = first["close"]
            lower = first["lower"]
            upper = first["upper"]
            middle = first["middle"]

            band_width = (
                upper - lower
            )

        # =================================================
        # ENTRY RANGE LONG
        # =================================================

        long_entry_low = min(
            price,
            lower
        )

        long_entry_high = max(
            price,
            lower
        )

        # =================================================
        # ENTRY RANGE SHORT
        # =================================================

        short_entry_low = min(
            price,
            upper
        )

        short_entry_high = max(
            price,
            upper
        )

        # =================================================
        # TAKE PROFIT
        # =================================================

        # LONG TP menuju middle band
        long_tp = middle

        # SHORT TP menuju middle band
        short_tp = middle

        # Jika middle terlalu dekat,
        # gunakan target berdasarkan band width
        if long_tp <= price:

            long_tp = (
                price
                +
                band_width * 0.50
            )

        if short_tp >= price:

            short_tp = (
                price
                -
                band_width * 0.50
            )

        # =================================================
        # STRENGTH
        # =================================================

        if long_count > short_count:

            direction = "LONG"

        elif short_count > long_count:

            direction = "SHORT"

        else:

            direction = "NEUTRAL"

        return {

            "Coin": symbol,

            "Direction":
                direction,

            "Long TF":
                long_count,

            "Short TF":
                short_count,

            "Price":
                price,

            "Long Entry Low":
                long_entry_low,

            "Long Entry High":
                long_entry_high,

            "Long TP":
                long_tp,

            "Short Entry Low":
                short_entry_low,

            "Short Entry High":
                short_entry_high,

            "Short TP":
                short_tp,

            "5M":
                (
                    "LONG"
                    if "5M" in results
                    and results["5M"]["long"]
                    else
                    "SHORT"
                    if "5M" in results
                    and results["5M"]["short"]
                    else
                    "-"
                ),

            "15M":
                (
                    "LONG"
                    if "15M" in results
                    and results["15M"]["long"]
                    else
                    "SHORT"
                    if "15M" in results
                    and results["15M"]["short"]
                    else
                    "-"
                ),

            "30M":
                (
                    "LONG"
                    if "30M" in results
                    and results["30M"]["long"]
                    else
                    "SHORT"
                    if "30M" in results
                    and results["30M"]["short"]
                    else
                    "-"
                )
        }

    except Exception:

        return None


# =========================================================
# FORMAT PRICE
# =========================================================

def format_price(value):

    value = float(
        value
    )

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

scan_limit = st.sidebar.selectbox(
    "Jumlah coin",
    [
        20,
        50,
        100,
        200,
        500
    ],
    index=2
)

st.sidebar.caption(
    "Data: Binance Futures Public API"
)

st.sidebar.caption(
    "Timeframe: 5M • 15M • 30M"
)


# =========================================================
# MARKET INFO
# =========================================================

try:

    symbols = get_symbols()

    st.info(
        f"Binance Futures menemukan "
        f"**{len(symbols)} USDT perpetual**."
    )

except Exception as e:

    st.error(
        "❌ Gagal mengambil daftar Binance."
    )

    st.code(
        str(e)
    )

    st.stop()


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

    # Ambil sebanyak yang dipilih
    scan_symbols = symbols[
        :scan_limit
    ]

    results = []

    progress = st.progress(
        0
    )

    status = st.empty()

    total = len(
        scan_symbols
    )

    # =====================================================
    # LOOP
    # =====================================================

    for i, symbol in enumerate(
        scan_symbols
    ):

        status.write(
            f"Scanning {symbol} "
            f"({i + 1}/{total})"
        )

        result = analyze_coin(
            symbol
        )

        if result:

            results.append(
                result
            )

        progress.progress(
            (i + 1) / total
        )

        time.sleep(
            0.08
        )

    progress.empty()
    status.empty()

    # =====================================================
    # NO RESULT
    # =====================================================

    if not results:

        st.warning(
            "Tidak ada data yang berhasil dianalisis."
        )

        st.stop()

    df = pd.DataFrame(
        results
    )

    # =====================================================
    # LONG CANDIDATES
    # =====================================================

    long_df = df[
        df["Long TF"] > 0
    ].copy()

    long_df = (
        long_df
        .sort_values(
            by=[
                "Long TF",
                "Long Entry Low"
            ],
            ascending=[
                False,
                True
            ]
        )
    )

    # =====================================================
    # SHORT CANDIDATES
    # =====================================================

    short_df = df[
        df["Short TF"] > 0
    ].copy()

    short_df = (
        short_df
        .sort_values(
            by=[
                "Short TF",
                "Short Entry High"
            ],
            ascending=[
                False,
                True
            ]
        )
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

    if len(long_df) > 0:

        best_long = (
            long_df.iloc[0]
        )

        st.success(
            f"""
🟢 **TARGET LONG**

### {best_long["Coin"]}

**Entry**

`{format_price(best_long["Long Entry Low"])}`
→
`{format_price(best_long["Long Entry High"])}`

**Take Profit**

`{format_price(best_long["Long TP"])}`

**Konfirmasi**

{int(best_long["Long TF"])}/3 timeframe
"""
        )

    else:

        st.info(
            "Belum ada setup LONG."
        )

    # =====================================================
    # SHORT
    # =====================================================

    if len(short_df) > 0:

        best_short = (
            short_df.iloc[0]
        )

        st.error(
            f"""
🔴 **TARGET SHORT**

### {best_short["Coin"]}

**Entry**

`{format_price(best_short["Short Entry Low"])}`
→
`{format_price(best_short["Short Entry High"])}`

**Take Profit**

`{format_price(best_short["Short TP"])}`

**Konfirmasi**

{int(best_short["Short TF"])}/3 timeframe
"""
        )

    else:

        st.info(
            "Belum ada setup SHORT."
        )

    # =====================================================
    # LONG LIST
    # =====================================================

    st.divider()

    st.subheader(
        "🟢 Long Candidates"
    )

    if len(long_df) > 0:

        long_display = pd.DataFrame({

            "Coin":
                long_df["Coin"],

            "Target Long":
                long_df.apply(
                    lambda row:
                    f"{format_price(row['Long Entry Low'])} "
                    f"→ "
                    f"{format_price(row['Long Entry High'])}",
                    axis=1
                ),

            "Take Profit":
                long_df[
                    "Long TP"
                ].apply(
                    format_price
                ),

            "Confirm":
                long_df[
                    "Long TF"
                ].astype(str)
                +
                "/3"
        })

        st.dataframe(
            long_display.head(15),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.write(
            "Tidak ada kandidat LONG."
        )

    # =====================================================
    # SHORT LIST
    # =====================================================

    st.subheader(
        "🔴 Short Candidates"
    )

    if len(short_df) > 0:

        short_display = pd.DataFrame({

            "Coin":
                short_df["Coin"],

            "Target Short":
                short_df.apply(
                    lambda row:
                    f"{format_price(row['Short Entry Low'])} "
                    f"→ "
                    f"{format_price(row['Short Entry High'])}",
                    axis=1
                ),

            "Take Profit":
                short_df[
                    "Short TP"
                ].apply(
                    format_price
                ),

            "Confirm":
                short_df[
                    "Short TF"
                ].astype(str)
                +
                "/3"
        })

        st.dataframe(
            short_display.head(15),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.write(
            "Tidak ada kandidat SHORT."
        )

    # =====================================================
    # TIMEFRAME DETAIL
    # =====================================================

    with st.expander(
        "📊 Detail timeframe"
    ):

        detail_columns = [
            "Coin",
            "Direction",
            "5M",
            "15M",
            "30M",
            "Long TF",
            "Short TF",
            "Price"
        ]

        st.dataframe(
            df[
                detail_columns
            ],
            use_container_width=True,
            hide_index=True
        )

    st.caption(
        "Signal menggunakan Bollinger Bands periode 20 "
        "dengan 2 standard deviation. Entry dan TP adalah "
        "target teknikal bukan jaminan profit."
    )
