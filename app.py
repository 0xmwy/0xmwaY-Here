import streamlit as st
import requests
import pandas as pd
import time

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="0xmwY Kraken",
    page_icon="⚡",
    layout="wide"
)

OKX_BASE_URL = "https://www.okx.com"

# TIMEFRAME SCREENER
TIMEFRAMES = {
    "15M": "15m",
    "30M": "30m",
    "1H": "1H"
}

# BOLLINGER BANDS
BB_PERIOD = 20
BB_STD = 2


# =========================================================
# HEADER
# =========================================================

st.title("⚡ 0xmwY Kraken")

st.caption(
    "pengembang : Lutfi Andreyansah"
)

st.markdown(
    """
    > **"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"**
    """
)

st.divider()


# =========================================================
# OKX PUBLIC API
# =========================================================

def okx_get(endpoint, params=None):

    if params is None:
        params = {}

    response = requests.get(
        OKX_BASE_URL + endpoint,
        params=params,
        timeout=20
    )

    if response.status_code != 200:
        raise Exception(
            f"HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    data = response.json()

    if data.get("code") != "0":
        raise Exception(
            data.get(
                "msg",
                "OKX API error"
            )
        )

    return data.get("data", [])


# =========================================================
# GET ALL USDT PERPETUAL
# =========================================================

@st.cache_data(ttl=1800)
def get_symbols():

    data = okx_get(
        "/api/v5/public/instruments",
        {
            "instType": "SWAP"
        }
    )

    symbols = []

    for item in data:

        if item.get("state") != "live":
            continue

        if item.get("settleCcy") != "USDT":
            continue

        inst_id = item.get("instId")

        if inst_id:
            symbols.append(inst_id)

    if not symbols:
        raise Exception(
            "Tidak ada USDT perpetual OKX ditemukan."
        )

    return sorted(symbols)


# =========================================================
# GET CANDLES
# =========================================================

@st.cache_data(ttl=30)
def get_candles(
    inst_id,
    bar
):

    data = okx_get(
        "/api/v5/market/candles",
        {
            "instId": inst_id,
            "bar": bar,
            "limit": "100"
        }
    )

    if not data:
        return None

    rows = []

    for candle in data:

        if len(candle) < 6:
            continue

        rows.append({
            "ts": candle[0],
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": float(candle[5])
        })

    if len(rows) < BB_PERIOD + 5:
        return None

    # OKX mengirim candle terbaru lebih dulu
    df = (
        pd.DataFrame(rows)
        .iloc[::-1]
        .reset_index(drop=True)
    )

    return df


# =========================================================
# BOLLINGER BANDS
# =========================================================

def calculate_bollinger(df):

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

    return df


# =========================================================
# ANALYZE TIMEFRAME
# =========================================================

def analyze_timeframe(df):

    df = calculate_bollinger(df)

    # Gunakan candle yang sudah close
    current = df.iloc[-2]
    previous = df.iloc[-3]

    close = float(current["close"])

    upper = float(current["upper"])
    middle = float(current["middle"])
    lower = float(current["lower"])

    previous_close = float(
        previous["close"]
    )

    previous_upper = float(
        previous["upper"]
    )

    previous_lower = float(
        previous["lower"]
    )

    long_signal = False
    short_signal = False

    # =====================================================
    # LONG
    # =====================================================

    # Rebound dari lower Bollinger Band
    if (
        previous_close <= previous_lower
        and
        close > lower
    ):

        long_signal = True

    elif (
        close <= lower * 1.003
        and
        close > previous_close
    ):

        long_signal = True

    # =====================================================
    # SHORT
    # =====================================================

    # Rejection dari upper Bollinger Band
    if (
        previous_close >= previous_upper
        and
        close < upper
    ):

        short_signal = True

    elif (
        close >= upper * 0.997
        and
        close < previous_close
    ):

        short_signal = True

    return {
        "long": long_signal,
        "short": short_signal,
        "close": close,
        "upper": upper,
        "middle": middle,
        "lower": lower
    }


# =========================================================
# ANALYZE COIN
# =========================================================

def analyze_coin(inst_id):

    try:

        results = {}

        for label, bar in TIMEFRAMES.items():

            df = get_candles(
                inst_id,
                bar
            )

            if df is None:
                continue

            results[label] = (
                analyze_timeframe(df)
            )

        if not results:
            return None

        # =================================================
        # SIGNAL COUNT
        # =================================================

        long_tf = sum(
            1
            for result in results.values()
            if result["long"]
        )

        short_tf = sum(
            1
            for result in results.values()
            if result["short"]
        )

        # =================================================
        # PRICE BASE
        # =================================================

        # Prioritaskan 15M sebagai timeframe utama
        base = results.get(
            "15M",
            next(iter(results.values()))
        )

        price = base["close"]
        upper = base["upper"]
        middle = base["middle"]
        lower = base["lower"]

        band_width = (
            upper - lower
        )

        if band_width <= 0:
            return None

        # =================================================
        # LONG ENTRY
        # =================================================

        long_entry_low = lower

        long_entry_high = price

        # =================================================
        # SHORT ENTRY
        # =================================================

        short_entry_low = price

        short_entry_high = upper

        # =================================================
        # TAKE PROFIT
        # =================================================

        long_tp = middle

        short_tp = middle

        # Jika middle sudah berada
        # di sisi yang salah, gunakan
        # target berdasarkan lebar BB.

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
        # DIRECTION
        # =================================================

        if long_tf > short_tf:

            direction = "LONG"

        elif short_tf > long_tf:

            direction = "SHORT"

        else:

            direction = "NEUTRAL"

        return {

            "Coin": inst_id,

            "Direction": direction,

            "Long TF": long_tf,

            "Short TF": short_tf,

            "Price": price,

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

            "15M":
                (
                    "LONG"
                    if results.get(
                        "15M",
                        {}
                    ).get(
                        "long",
                        False
                    )

                    else

                    "SHORT"
                    if results.get(
                        "15M",
                        {}
                    ).get(
                        "short",
                        False
                    )

                    else "-"
                ),

            "30M":
                (
                    "LONG"
                    if results.get(
                        "30M",
                        {}
                    ).get(
                        "long",
                        False
                    )

                    else

                    "SHORT"
                    if results.get(
                        "30M",
                        {}
                    ).get(
                        "short",
                        False
                    )

                    else "-"
                ),

            "1H":
                (
                    "LONG"
                    if results.get(
                        "1H",
                        {}
                    ).get(
                        "long",
                        False
                    )

                    else

                    "SHORT"
                    if results.get(
                        "1H",
                        {}
                    ).get(
                        "short",
                        False
                    )

                    else "-"
                )
        }

    except Exception:

        return None


# =========================================================
# FORMAT PRICE
# =========================================================

def format_price(value):

    value = float(value)

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
    "Jumlah pair",
    [
        20,
        50,
        100,
        200,
        300,
        400
    ],
    index=2
)

st.sidebar.caption(
    "OKX USDT Perpetual"
)

st.sidebar.caption(
    "15M • 30M • 1H"
)

st.sidebar.caption(
    "Bollinger Bands 20 / 2"
)


# =========================================================
# MARKET
# =========================================================

try:

    symbols = get_symbols()

    st.info(
        f"OKX menemukan "
        f"**{len(symbols)} USDT perpetual**."
    )

except Exception as e:

    st.error(
        "❌ Gagal mengambil market OKX."
    )

    st.code(
        str(e)
    )

    st.stop()


# =========================================================
# SCAN BUTTON
# =========================================================

if st.button(
    "🔎 SCAN MARKET",
    use_container_width=True
):

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
    # SCAN LOOP
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
    # CHECK RESULT
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
            by="Long TF",
            ascending=False
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
            by="Short TF",
            ascending=False
        )
    )

    # =====================================================
    # TRADE SETUP
    # =====================================================

    st.divider()

    st.header(
        "🎯 Trade Setup"
    )

    # =====================================================
    # BEST LONG
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
            "Belum ada signal LONG."
        )

    # =====================================================
    # BEST SHORT
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
            "Belum ada signal SHORT."
        )

    # =====================================================
    # LONG LIST
    # =====================================================

    st.divider()

    st.subheader(
        "🟢 LONG CANDIDATES"
    )

    if len(long_df) > 0:

        display_long = pd.DataFrame({

            "Pair":
                long_df["Coin"],

            "Target Long":
                long_df.apply(
                    lambda row:
                    (
                        f"{format_price(row['Long Entry Low'])}"
                        f" → "
                        f"{format_price(row['Long Entry High'])}"
                    ),
                    axis=1
                ),

            "Take Profit":
                long_df[
                    "Long TP"
                ].apply(
                    format_price
                ),

            "Confirm":
                (
                    long_df[
                        "Long TF"
                    ].astype(str)
                    +
                    "/3"
                )
        })

        st.dataframe(
            display_long.head(20),
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
        "🔴 SHORT CANDIDATES"
    )

    if len(short_df) > 0:

        display_short = pd.DataFrame({

            "Pair":
                short_df["Coin"],

            "Target Short":
                short_df.apply(
                    lambda row:
                    (
                        f"{format_price(row['Short Entry Low'])}"
                        f" → "
                        f"{format_price(row['Short Entry High'])}"
                    ),
                    axis=1
                ),

            "Take Profit":
                short_df[
                    "Short TP"
                ].apply(
                    format_price
                ),

            "Confirm":
                (
                    short_df[
                        "Short TF"
                    ].astype(str)
                    +
                    "/3"
                )
        })

        st.dataframe(
            display_short.head(20),
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

        detail = df[
            [
                "Coin",
                "Direction",
                "15M",
                "30M",
                "1H",
                "Long TF",
                "Short TF",
                "Price"
            ]
        ].copy()

        detail["Price"] = (
            detail["Price"]
            .apply(format_price)
        )

        st.dataframe(
            detail,
            use_container_width=True,
            hide_index=True
        )

    # =====================================================
    # FOOTER
    # =====================================================

    st.divider()

    st.caption(
        "Bollinger Bands: period 20 • standard deviation 2"
    )

    st.caption(
        "Signal bersifat teknikal dan bukan jaminan profit. DYOR."
        )
