import streamlit as st
import requests
import pandas as pd
import streamlit.components.v1 as components
import time

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="0xmwY Kraken",
    page_icon="⚡",
    layout="wide"
)

OKX_BASE = "https://www.okx.com"

TIMEFRAMES = {
    "15M": "15m",
    "30M": "30m",
    "1H": "1H"
}

BB_PERIOD = 20
BB_STD = 2


# =========================================================
# ACCESS TOKEN
# =========================================================
# Ganti token dan limit sesuai kebutuhan.
#
# Contoh:
# "KRAKEN-001": 100
#
# Angka = jumlah scan yang boleh dilakukan.
# =========================================================

TOKENS = {
    "KRAKEN-001": 100,
    "KRAKEN-002": 50,
    "KRAKEN-003": 25,
}


# =========================================================
# SESSION STATE
# =========================================================

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "active_token" not in st.session_state:
    st.session_state.active_token = None

if "remaining_scans" not in st.session_state:
    st.session_state.remaining_scans = 0

if "scan_results" not in st.session_state:
    st.session_state.scan_results = []

if "scan_done" not in st.session_state:
    st.session_state.scan_done = False


# =========================================================
# TOKEN LOGIN
# =========================================================

if not st.session_state.authenticated:

    st.title("⚡ 0xmwY Kraken")

    st.caption("pengembang : Lutfi Andreyansah")

    st.markdown(
        '**"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"**'
    )

    st.divider()

    st.subheader("🔐 Access Token")

    token_input = st.text_input(
        "Masukkan token",
        type="password",
        placeholder="KRAKEN-XXXX-XXXX"
    )

    if st.button(
        "ACCESS",
        use_container_width=True
    ):

        token_input = token_input.strip()

        if token_input in TOKENS:

            limit = TOKENS[token_input]

            if limit <= 0:

                st.error(
                    "LIMIT REACHED — token ini sudah habis."
                )

            else:

                st.session_state.authenticated = True
                st.session_state.active_token = token_input
                st.session_state.remaining_scans = limit

                st.rerun()

        else:

            st.error(
                "Token tidak valid."
            )

    st.stop()


# =========================================================
# MAIN HEADER
# =========================================================

st.title("⚡ 0xmwY Kraken")

st.caption("pengembang : Lutfi Andreyansah")

st.markdown(
    '**"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"**'
)

st.divider()


# =========================================================
# TOKEN INFO
# =========================================================

col1, col2 = st.columns(2)

with col1:

    st.info(
        "Token: "
        + st.session_state.active_token
    )

with col2:

    remaining = st.session_state.remaining_scans

    if remaining > 10:

        st.success(
            "Sisa scan: "
            + str(remaining)
        )

    elif remaining > 0:

        st.warning(
            "Sisa scan: "
            + str(remaining)
        )

    else:

        st.error(
            "Sisa scan: 0"
        )


# =========================================================
# LOGOUT
# =========================================================

if st.sidebar.button(
    "Logout"
):

    st.session_state.authenticated = False
    st.session_state.active_token = None
    st.session_state.remaining_scans = 0
    st.session_state.scan_results = []
    st.session_state.scan_done = False

    st.rerun()


# =========================================================
# API GET
# =========================================================

def api_get(endpoint, params=None):

    response = requests.get(
        OKX_BASE + endpoint,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if data.get("code") != "0":

        raise Exception(
            data.get(
                "msg",
                "API error"
            )
        )

    return data.get(
        "data",
        []
    )


# =========================================================
# GET USDT SWAP PAIRS
# =========================================================

@st.cache_data(ttl=1800)
def get_symbols():

    data = api_get(
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

            symbols.append(
                inst_id
            )

    return sorted(symbols)


# =========================================================
# GET CANDLES
# =========================================================

@st.cache_data(ttl=15)
def get_candles(
    inst_id,
    bar
):

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

    df = df.reset_index(
        drop=True
    )

    return df


# =========================================================
# BOLLINGER CALCULATION
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
        + (
            BB_STD
            * df["std"]
        )
    )

    df["lower"] = (
        df["middle"]
        - (
            BB_STD
            * df["std"]
        )
    )

    return df


# =========================================================
# ANALYZE TIMEFRAME
# =========================================================

def analyze_timeframe(df):

    df = calculate_bollinger(df)

    current = df.iloc[-2]

    previous = df.iloc[-3]

    close = float(
        current["close"]
    )

    upper = float(
        current["upper"]
    )

    middle = float(
        current["middle"]
    )

    lower = float(
        current["lower"]
    )

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

    # -----------------------------------------------------
    # LONG
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # SHORT
    # -----------------------------------------------------

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
# ANALYZE PAIR
# =========================================================

def analyze_pair(inst_id):

    try:

        timeframe_results = {}

        for name, bar in TIMEFRAMES.items():

            df = get_candles(
                inst_id,
                bar
            )

            if df is None:
                continue

            timeframe_results[name] = (
                analyze_timeframe(df)
            )

        if not timeframe_results:

            return None

        long_count = 0

        short_count = 0

        for result in timeframe_results.values():

            if result["long"]:

                long_count += 1

            if result["short"]:

                short_count += 1

        base = timeframe_results.get(
            "15M"
        )

        if base is None:

            base = list(
                timeframe_results.values()
            )[0]

        price = base["close"]

        upper = base["upper"]

        middle = base["middle"]

        lower = base["lower"]

        band_width = (
            upper - lower
        )

        if band_width <= 0:

            return None

        # -------------------------------------------------
        # LONG
        # -------------------------------------------------

        long_entry_low = lower

        long_entry_high = price

        long_tp = middle

        if long_tp <= price:

            long_tp = (
                price
                + band_width * 0.5
            )

        # -------------------------------------------------
        # SHORT
        # -------------------------------------------------

        short_entry_low = price

        short_entry_high = upper

        short_tp = middle

        if short_tp >= price:

            short_tp = (
                price
                - band_width * 0.5
            )

        display_pair = (
            inst_id
            .replace(
                "-SWAP",
                ""
            )
        )

        result = {

            "pair":
                display_pair,

            "inst_id":
                inst_id,

            "long_count":
                long_count,

            "short_count":
                short_count,

            "price":
                price,

            "long_low":
                long_entry_low,

            "long_high":
                long_entry_high,

            "long_tp":
                long_tp,

            "short_low":
                short_entry_low,

            "short_high":
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

            if tf_name not in timeframe_results:
                continue

            tf = timeframe_results[
                tf_name
            ]

            if tf["long"]:

                result[tf_name] = "LONG"

            elif tf["short"]:

                result[tf_name] = "SHORT"

        return result

    except Exception:

        return None


# =========================================================
# PRICE FORMAT
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

    pair = (
        inst_id
        .replace(
            "-SWAP",
            ""
        )
        .replace(
            "-",
            ""
        )
    )

    return (
        "OKX:"
        + pair
        + ".P"
    )


# =========================================================
# TRADINGVIEW CHART
# =========================================================

def show_tradingview(
    inst_id,
    timeframe
):

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

    html, body {{
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        background: #131722;
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
# SIDEBAR
# =========================================================

st.sidebar.header(
    "Scanner"
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
    "15M • 30M • 1H"
)


# =========================================================
# MARKET
# =========================================================

try:

    symbols = get_symbols()

except Exception as e:

    st.error(
        "Data market gagal diambil."
    )

    st.code(
        str(e)
    )

    st.stop()


# =========================================================
# SCAN
# =========================================================

scan_button = st.button(
    "SCAN MARKET",
    use_container_width=True
)


if scan_button:

    # -----------------------------------------------------
    # CHECK LIMIT
    # -----------------------------------------------------

    if (
        st.session_state.remaining_scans
        <= 0
    ):

        st.error(
            "LIMIT REACHED"
        )

        st.stop()

    # -----------------------------------------------------
    # CONSUME ONE SCAN
    # -----------------------------------------------------

    st.session_state.remaining_scans -= 1

    selected_symbols = (
        symbols[:scan_limit]
    )

    results = []

    progress = st.progress(
        0
    )

    status = st.empty()

    total = len(
        selected_symbols
    )

    for index, symbol in enumerate(
        selected_symbols
    ):

        status.write(
            "Scanning "
            + symbol.replace(
                "-SWAP",
                ""
            )
            + "  "
            + str(index + 1)
            + "/"
            + str(total)
        )

        result = analyze_pair(
            symbol
        )

        if result is not None:

            if (
                result["long_count"] > 0
                or
                result["short_count"] > 0
            ):

                results.append(
                    result
                )

        progress.progress(
            (index + 1)
            / total
        )

        time.sleep(
            0.02
        )

    progress.empty()

    status.empty()

    st.session_state.scan_results = results

    st.session_state.scan_done = True

    st.rerun()


# =========================================================
# RESULTS
# =========================================================

if st.session_state.scan_done:

    results = (
        st.session_state.scan_results
    )

    if not results:

        st.warning(
            "Tidak ditemukan signal."
        )

        st.stop()

    df = pd.DataFrame(
        results
    )


    # =====================================================
    # LONG
    # =====================================================

    long_df = df[
        df["long_count"] > 0
    ].copy()

    long_df = long_df.sort_values(
        "long_count",
        ascending=False
    )


    # =====================================================
    # SHORT
    # =====================================================

    short_df = df[
        df["short_count"] > 0
    ].copy()

    short_df = short_df.sort_values(
        "short_count",
        ascending=False
    )


    # =====================================================
    # MATCH OPTIONS
    # =====================================================

    match_options = []

    match_data = {}

    for _, row in long_df.iterrows():

        label = (
            "LONG • "
            + row["pair"]
            + " • "
            + str(
                int(
                    row["long_count"]
                )
            )
            + "/3"
        )

        match_options.append(
            label
        )

        match_data[label] = (
            "LONG",
            row
        )


    for _, row in short_df.iterrows():

        label = (
            "SHORT • "
            + row["pair"]
            + " • "
            + str(
                int(
                    row["short_count"]
                )
            )
            + "/3"
        )

        match_options.append(
            label
        )

        match_data[label] = (
            "SHORT",
            row
        )


    # =====================================================
    # MATCH CHART
    # =====================================================

    st.divider()

    st.header(
        "Match Chart"
    )

    selected_option = st.selectbox(
        "Pilih hasil scanner",
        match_options
    )

    signal, row = match_data[
        selected_option
    ]


    # =====================================================
    # TIMEFRAME
    # =====================================================

    chart_timeframe = st.selectbox(
        "Timeframe",
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
### OUTLOOK LONG

**{row["pair"]}**

Outlook Long

`{format_price(row["long_low"])} - {format_price(row["long_high"])}`

Take Profit

`{format_price(row["long_tp"])}`

Konfirmasi: **{int(row["long_count"])}/3**
"""
        )

    else:

        st.error(
            f"""
### OUTLOOK SHORT

**{row["pair"]}**

Outlook Short

`{format_price(row["short_low"])} - {format_price(row["short_high"])}`

Take Profit

`{format_price(row["short_tp"])}`

Konfirmasi: **{int(row["short_count"])}/3**
"""
        )


    # =====================================================
    # TRADINGVIEW
    # =====================================================

    st.divider()

    s
