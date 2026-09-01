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
# API REQUEST
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

    return (
        pd.DataFrame(rows)
        .iloc[::-1]
        .reset_index(drop=True)
    )


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

    # -----------------------------------------------------
    # LONG
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # SHORT
    # -----------------------------------------------------

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

        results = {}

        for label, bar in TIMEFRAMES.items():

            df = get_candles(
                inst_id,
                bar
            )

            if df is None:
                continue

            results[label] = analyze_timeframe(df)

        if not results:
            return None

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

        base = results.get(
            "15M",
            next(iter(results.values()))
        )

        price = base["close"]
        upper = base["upper"]
        middle = base["middle"]
        lower = base["lower"]

        band_width = upper - lower

        if band_width <= 0:
            return None

        # -------------------------------------------------
        # LONG OUTLOOK
        # -------------------------------------------------

        long_entry_low = lower
        long_entry_high = price

        long_tp = middle

        if long_tp <= price:
            long_tp = (
                price
                + band_width * 0.50
            )

        # -------------------------------------------------
        # SHORT OUTLOOK
        # -------------------------------------------------

        short_entry_low = price
        short_entry_high = upper

        short_tp = middle

        if short_tp >= price:
            short_tp = (
                price
                - band_width * 0.50
            )

        # -------------------------------------------------
        # DIRECTION
        # -------------------------------------------------

        if long_tf > short_tf:
            direction = "LONG"

        elif short_tf > long_tf:
            direction = "SHORT"

        else:
            direction = "NEUTRAL"

        display_pair = inst_id.replace(
            "-SWAP",
            ""
        )

        return {
            "Coin": display_pair,
            "InstID": inst_id,
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
# TRADINGVIEW SYMBOL
# =========================================================

def get_tradingview_symbol(inst_id):

    pair = inst_id.replace(
        "-SWAP",
        ""
    )

    pair = pair.replace(
        "-",
        ""
    )

    return f"OKX:{pair}.P"


# =========================================================
# TRADINGVIEW OFFICIAL CHART
# =========================================================

def show_tradingview_chart(
    inst_id,
    timeframe
):

    tv_symbol = get_tradingview_symbol(
        inst_id
    )

    tv_interval = {
        "15M": "15",
        "30M": "30",
        "1H": "60"
    }.get(
        timeframe,
        "15"
    )

    chart_html = f"""
    <!DOCTYPE html>

    <html>

    <head>

        <meta charset="UTF-8">

        <style>

            html,
            body {{
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
                "symbol": "{tv_symbol}",
                "interval": "{tv_interval}",
                "timezone": "Asia/Jakarta",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "hide_legend": false,
                "allow_symbol_change": false,
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
        chart_html,
        height=600,
        scrolling=False
    )


# =========================================================
# SESSION STATE
# =========================================================

if "scan_results" not in st.session_state:
    st.session_state.scan_results = []

if "scan_done" not in st.session_state:
    st.session_state.scan_done = False


# =========================================================
# LOAD MARKET
# =========================================================

try:

    symbols = get_symbols()

except Exception as e:

    st.error(
        "❌ Gagal mengambil data market."
    )

    st.code(str(e))

    st.stop()


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("⚙️ Scanner")

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
    f"{len(symbols)} pair USDT tersedia"
)

st.sidebar.caption(
    "15M • 30M • 1H"
)


# =========================================================
# SCAN
# =========================================================

if st.button(
    "🔎 SCAN MARKET",
    use_container_width=True
):

    scan_symbols = symbols[:scan_limit]

    results = []

    progress = st.progress(0)

    status = st.empty()

    total = len(scan_symbols)

    for i, symbol in enumerate(
        scan_symbols
    ):

        status.write(
            f"Scanning "
            f"{symbol.replace('-SWAP', '')} "
            f"({i + 1}/{total})"
        )

        result = analyze_pair(
            symbol
        )

        if result:
            results.append(result)

        progress.progress(
            (i + 1) / total
        )

        time.sleep(0.05)

    progress.empty()
    status.empty()

    st.session_state.scan_results = results
    st.session_state.scan_done = True


# =========================================================
# MATCHING SYSTEM
# =========================================================

if st.session_state.scan_done:

    results = st.session_state.scan_results

    if not results:

        st.warning(
            "Tidak ada data market yang berhasil dianalisis."
        )

        st.stop()

    df = pd.DataFrame(results)


    # =====================================================
    # SEPARATE LONG / SHORT
    # =====================================================

    long_df = df[
        df["Long TF"] > 0
    ].copy()

    short_df = df[
        df["Short TF"] > 0
    ].copy()


    long_df = long_df.sort_values(
        by="Long TF",
        ascending=False
    )

    short_df = short_df.sort_values(
        by="Short TF",
        ascending=False
    )


    # =====================================================
    # MATCHING SELECTOR
    # =====================================================

    st.divider()

    st.header(
        "🎯 Trade Setup"
    )

    signal_options = []

    if len(long_df) > 0:
        signal_options.append(
            "LONG"
        )

    if len(short_df) > 0:
        signal_options.append(
            "SHORT"
        )

    if not signal_options:

        st.info(
            "Belum ada signal LONG atau SHORT."
        )

        st.stop()


    selected_signal = st.radio(
        "Pilih signal",
        signal_options,
        horizontal=True
    )


    # =====================================================
    # SELECT DATASET
    # =====================================================

    if selected_signal == "LONG":

        selected_df = long_df

    else:

        selected_df = short_df


    # =====================================================
    # PAIR OPTIONS
    # =====================================================

    pair_options = (
        selected_df["Coin"]
        .tolist()
    )


    selected_pair = st.selectbox(
        f"Pilih pair {selected_signal}",
        pair_options
    )


    # =====================================================
    # GET SELECTED RESULT
    # =====================================================

    selected_row = selected_df[
        selected_df["Coin"]
        == selected_pair
    ].iloc[0]


    # =====================================================
    # TIMEFRAME CHART
    # =====================================================

    chart_tf = st.selectbox(
        "Timeframe TradingView",
        [
            "15M",
            "30M",
            "1H"
        ]
    )


    # =====================================================
    # SELECTED SETUP
    # =====================================================

    st.divider()


    if selected_signal == "LONG":

        st.success(
            f"""
🟢 **OUTLOOK LONG**

### {selected_row["Coin"]}

**Outlook Long**

`{format_price(selected_row["Long Entry Low"])} - {format_price(selected_row["Long Entry High"])}`

**Take Profit**

`{format_price(selected_row["Long TP"])}`

**Konfirmasi**

{int(selected_row["Long TF"])}/3 timeframe
"""
        )

    else:

        st.error(
            f"""
🔴 **OUTLOOK SHORT**

### {selected_row["Coin"]}

**Outlook Short**

`{format_price(selected_row["Short Entry Low"])} - {format_price(selected_row["Short Entry High"])}`

**Take Profit**

`{format_price(selected_row["Short TP"])}`

**Konfirmasi**

{int(selected_row["Short TF"])}/3 timeframe
"""
        )


    # =====================================================
    # MATCHED TRADINGVIEW
    # =====================================================

    st.divider()

    st.header(
        "📈 TradingView"
    )

    st.caption(
        f"{selected_pair} • {selected_signal} • {chart_tf}"
    )

    selected_inst_id = selected_row[
        "InstID"
    ]

    show_tradingview_chart(
        selected_inst_id,
        chart_tf
    )


    # =====================================================
    # LONG CANDIDATES
    # =====================================================

    st.divider()

    st.subheader(
        "🟢 LONG CANDIDATES"
    )

    if len(long_df) > 0:

        display_long = pd.DataFrame({

            "Pair":
                long_df["Coin"],

            "Outlook Long":
                long_df.apply(
                    lambda row:
                    (
                        f"{format_price(row['Long Entry Low'])}"
                        f" - "
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
                    ]
                    .astype(str)
                    + "/3"
                )
        })

        st.dataframe(
            display_long.head(30),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.write(
            "Tidak ada kandidat LONG."
        )


    # =====================================================
    # SHORT CANDIDATES
    # =====================================================

    st.subheader(
        "🔴 SHORT CANDIDATES"
    )

    if len(short_df) > 0:

        display_short = pd.DataFrame({

            "Pair":
                short_df["Coin"],

            "Outlook Short":
                short_df.apply(
                    lambda row:
                    (
                        f"{format_price(row['Short Entry Low'])}"
                        f" - "
                        f"{format_price(row['Short Entry High'])}"
)
