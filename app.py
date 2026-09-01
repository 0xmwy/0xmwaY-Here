import streamlit as st
import streamlit.components.v1 as components
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

BASE_URL = "https://www.okx.com"

TIMEFRAMES = {
    "15M": "15m",
    "30M": "30m",
    "1H": "1H"
}

BB_PERIOD = 20
BB_STD = 2


# =========================================================
# HEADER
# =========================================================

st.title("⚡ 0xmwY Kraken")
st.caption("pengembang : Lutfi Andreyansah")

st.markdown(
    '**"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"**'
)

st.divider()


# =========================================================
# API
# =========================================================

def api_get(endpoint, params=None):

    if params is None:
        params = {}

    response = requests.get(
        BASE_URL + endpoint,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if data.get("code") != "0":
        raise Exception(
            data.get("msg", "API error")
        )

    return data.get("data", [])


# =========================================================
# GET PAIRS
# =========================================================

@st.cache_data(ttl=1800)
def get_symbols():

    data = api_get(
        "/api/v5/public/instruments",
        {"instType": "SWAP"}
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

    return sorted(symbols)


# =========================================================
# GET CANDLES
# =========================================================

@st.cache_data(ttl=20)
def get_candles(inst_id, bar):

    data = api_get(
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

    df = pd.DataFrame(rows)

    df = df.iloc[::-1]

    df = df.reset_index(drop=True)

    return df


# =========================================================
# BOLLINGER BANDS
# =========================================================

def calculate_bands(df):

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
        + BB_STD * df["std"]
    )

    df["lower"] = (
        df["middle"]
        - BB_STD * df["std"]
    )

    return df


# =========================================================
# ANALYZE TIMEFRAME
# =========================================================

def analyze_timeframe(df):

    df = calculate_bands(df)

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

    # LONG

    if (
        previous_close <= previous_lower
        and close > lower
    ):
        long_signal = True

    elif (
        close <= lower * 1.003
        and close > previous_close
    ):
        long_signal = True

    # SHORT

    if (
        previous_close >= previous_upper
        and close < upper
    ):
        short_signal = True

    elif (
        close >= upper * 0.997
        and close < previous_close
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
# ANALYZE PAIR
# =========================================================

def analyze_pair(inst_id):

    try:

        tf_results = {}

        for tf_name, bar in TIMEFRAMES.items():

            df = get_candles(
                inst_id,
                bar
            )

            if df is None:
                continue

            tf_results[tf_name] = analyze_timeframe(
                df
            )

        if not tf_results:
            return None

        long_count = 0
        short_count = 0

        for result in tf_results.values():

            if result["long"]:
                long_count += 1

            if result["short"]:
                short_count += 1

        base = tf_results.get(
            "15M",
            list(tf_results.values())[0]
        )

        price = base["close"]
        upper = base["upper"]
        middle = base["middle"]
        lower = base["lower"]

        band_width = upper - lower

        if band_width <= 0:
            return None

        # LONG

        long_entry_low = lower
        long_entry_high = price

        long_tp = middle

        if long_tp <= price:
            long_tp = (
                price
                + band_width * 0.50
            )

        # SHORT

        short_entry_low = price
        short_entry_high = upper

        short_tp = middle

        if short_tp >= price:
            short_tp = (
                price
                - band_width * 0.50
            )

        # Display pair tanpa SWAP

        display_pair = inst_id.replace(
            "-SWAP",
            ""
        )

        result = {
            "pair": display_pair,
            "inst_id": inst_id,

            "long_count": long_count,
            "short_count": short_count,

            "price": price,

            "long_entry_low":
                long_entry_low,

            "long_entry_high":
                long_entry_high,

            "long_tp":
                long_tp,

            "short_entry_low":
                short_entry_low,

            "short_entry_high":
                short_entry_high,

            "short_tp":
                short_tp,

            "15M":
                "-",

            "30M":
                "-",

            "1H":
                "-"
        }

        for tf_name in TIMEFRAMES:

            if tf_name not in tf_results:
                continue

            tf = tf_results[tf_name]

            if tf["long"]:
                result[tf_name] = "LONG"

            elif tf["short"]:
                result[tf_name] = "SHORT"

        return result

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
# TRADINGVIEW SYMBOL
# =========================================================

def tradingview_symbol(inst_id):

    pair = inst_id.replace(
        "-SWAP",
        ""
    )

    pair = pair.replace(
        "-",
        ""
    )

    return "OKX:" + pair + ".P"


# =========================================================
# TRADINGVIEW
# =========================================================

def show_chart(inst_id, timeframe):

    symbol = tradingview_symbol(
        inst_id
    )

    interval = {
        "15M": "15",
        "30M": "30",
        "1H": "60"
    }.get(
        timeframe,
        "15"
    )

    html = f"""
    <html>

    <head>

        <style>

            html,
            body {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                background: #131722;
                overflow: hidden;
            }}

            .tradingview-widget-container {{
                width: 100%;
                height: 100%;
            }}

            .tradingview-widget-container__widget {{
                width: 100%;
                height: 100%;
            }}

        </style>

    </head>

    <body>

        <div
            class="tradingview-widget-container"
        >

            <div
                class="tradingview-widget-container__widget"
            ></div>

            <script
                type="text/javascript"
                src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
                async
            >
            {{
                "autosize": true,
                "symbol": "{symbol}",
                "interval": "{interval}",
                "timezone": "Asia/Jakarta",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "allow_symbol_change": false,
                "hide_top_toolbar": false,
                "hide_legend": false,
                "save_image": false,
                "calendar": false,
                "support_host": "https://www.tradingview.com"
            }}
            </script>

        </div>

    </body>

    </html>
    """

    components.html(
        html,
        height=600,
        scrolling=False
    )


# =========================================================
# SESSION STATE
# =========================================================

if "results" not in st.session_state:
    st.session_state.results = []

if "scanned" not in st.session_state:
    st.session_state.scanned = False


# =========================================================
# MARKET
# =========================================================

try:

    symbols = get_symbols()

except Exception as e:

    st.error(
        "Data market gagal diambil."
    )

    st.code(str(e))

    st.stop()


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("Scanner")

scan_limit = st.sidebar.selectbox(
    "Jumlah pair",
    [20, 50, 100, 200, 300, 400],
    index=2
)

st.sidebar.caption(
    "Timeframe: 15M • 30M • 1H"
)


# =========================================================
# SCAN BUTTON
# =========================================================

if st.button(
    "SCAN MARKET",
    use_container_width=True
):

    results = []

    progress = st.progress(0)

    status = st.empty()

    selected_symbols = symbols[:scan_limit]

    total = len(selected_symbols)

    for index, symbol in enumerate(
        selected_symbols
    ):

        status.write(
            "Scanning "
            + symbol.replace("-SWAP", "")
            + " "
            + str(index + 1)
            + "/"
            + str(total)
        )

        result = analyze_pair(
            symbol
        )

        if result is not None:

            # Hanya simpan pair yang
            # mempunyai signal

            if (
                result["long_count"] > 0
                or
                result["short_count"] > 0
            ):

                results.append(result)

        progress.progress(
            (index + 1) / total
        )

        time.sleep(0.03)

    progress.empty()
    status.empty()

    st.session_state.results = results

    st.session_state.scanned = True


# =========================================================
# DISPLAY RESULTS
# =========================================================

if st.session_state.scanned:

    results = st.session_state.results

    if not results:

        st.warning(
            "Tidak ditemukan signal."
        )

        st.stop()

    df = pd.DataFrame(results)


    # =====================================================
    # BUILD MATCH OPTIONS
    # =====================================================

    match_options = []

    match_data = {}

    # LONG OPTIONS

    long_results = df[
        df["long_count"] > 0
    ].copy()

    long_results = long_results.sort_values(
        by="long_count",
        ascending=False
    )

    for _, row in long_results.iterrows():

        label = (
            "🟢 LONG • "
            + row["pair"]
            + " • "
            + str(int(row["long_count"]))
            + "/3"
        )

        match_options.append(label)

        match_data[label] = {
            "signal": "LONG",
            "row": row
        }


    # SHORT OPTIONS

    short_results = df[
        df["short_count"] > 0
    ].copy()

    short_results = short_results.sort_values(
        by="short_count",
        ascending=False
    )

    for _, row in short_results.iterrows():

        label = (
            "🔴 SHORT • "
            + row["pair"]
            + " • "
            + str(int(row["short_count"]))
            + "/3"
        )

        match_options.append(label)

        match_data[label] = {
            "signal": "SHORT",
            "row": row
        }


    # =====================================================
    # MATCH CHART
    # =====================================================

    st.divider()

    st.header("🎯 Match Chart")

    selected_match = st.selectbox(
        "Pilih hasil scanner",
        match_options
    )

    selected = match_data[
        selected_match
    ]

    signal = selected["signal"]

    row = selected["row"]


    # =====================================================
    # TIMEFRAME
    # =====================================================

    chart_timeframe = st.selectbox(
        "Timeframe TradingView",
        [
            "15M",
            "30M",
            "1H"
        ]
    )


    # =====================================================
    # SETUP
    # =====================================================

    st.divider()


    if signal == "LONG":

        st.success(
            f"""
🟢 **OUTLOOK LONG**

### {row["pair"]}

**Outlook Long**

`{format_price(row["long_entry_low"])} - {format_price(row["long_entry_high"])}`

**Take Profit**

`{format_price(row["long_tp"])}`

**Konfirmasi**

{int(row["long_count"])}/3 timeframe
"""
        )

    else:

        st.error(
            f"""
🔴 **OUTLOOK SHORT**

### {row["pair"]}

**Outlook Short**

`{format_price(row["short_entry_low"])} - {format_price(row["short_entry_high"])}`

**Take Profit**

`{format_price(row["short_tp"])}`

**Konfirmasi**

{int(row["short_count"])}/3 timeframe
"""
        )


    # =====================================================
    # MATCHED TRADINGVIEW
    # =====================================================

    st.divider()

    st.header("📈 Live Chart")

    st.caption(
        row["pair"]
        + " • "
        + signal
        + " • "
        + chart_timeframe
    )

    show_chart(
        row["inst_id"],
        chart_timeframe
    )


    # =====================================================
    # ALL LONG
    # =====================================================

    st.divider()

    st.subheader(
        "🟢 Semua Outlook Long"
    )

    if len(long_results) > 0:

        long_display = []

        for _, item in long_results.iterrows():

            long_display.append({
                "Pair":
                    item["pair"],

                "Outlook":
                    (
                        format_price(
                            item["long_entry_low"]
                        )
                        + " - "
                        + format_price(
                            item["long_entry_high"]
                        )
                    ),

                "Take Profit":
                    format_price(
                        item["long_tp"]
                    ),

                "Confirm":
                    str(
                        int(
                            item["long_count"]
                        )
                    )
                    + "/3"
            })

        st.dataframe(
            pd.DataFrame(long_display),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.write(
            "Tidak ada Outlook Long."
        )


    # =====================================================
    # ALL SHORT
    # =====================================================

    st.subheader(
        "🔴 Semua Outlook Short"
    )

    if len(short_results) > 0:

        short_display = []

        for _, item in short_results.iterrows():

            short_display.append({
                "Pair":
                    item["pair"],

                "Outlook":
                    (
                        format_price(
                            item["short_entry_low"]
                        )
                        + " - "
                        + format_price(
                            item["short_entry_high"]
                        )
                    ),

                "Take Profit":
                    format_price(
                        item["short_tp"]
                    ),

                "Confirm":
                    str(
                        int(
                            item["short_count"]
                        )
                    )
                    + "/3"
            })

        st.dataframe(
            pd.DataFrame(short_display),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.write(
            "Tidak ada Outlook Short."
        )


    # =====================================================
    # DETAIL
    # =====================================================

    with st.expander(
        "📊 Detail scanner"
    ):

        detail = []

        for _, item in df.iterrows():

            detail.append({
                "Pair":
                    item["pair"],

                "15M":
                    item["15M"],

                "30M":
                    item["30M"],

                "1H":
                    item["1H"],

                "Long":
                    str(
                        int(
                            item["long_count"]
                        )
                    )
                    + "/3",

                "Short":
                    str(
                        int(
                            item["short_count"]
                        )
                    )
                    + "/3",

                "Price":
                    format_price(
                        item["price"]
                    )
            })

        st.dataframe(
            pd.DataFrame(detail),
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Signal bersifat teknikal dan bukan jaminan profit. DYOR."
    )
