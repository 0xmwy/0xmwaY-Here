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

BASE = "https://www.okx.com"


# =========================================================
# STYLE
# =========================================================

st.markdown("""
<style>

.block-container {
    padding-top: 1.3rem;
    padding-bottom: 2rem;
}

.title {
    font-size: 38px;
    font-weight: 800;
}

.sub {
    opacity: .65;
    margin-bottom: 4px;
}

.small-text {
    font-size: 13px;
    opacity: .65;
}

.market-price {
    font-size: 22px;
    font-weight: 700;
}

.outlook-long {
    font-size: 20px;
    font-weight: 800;
}

.outlook-short {
    font-size: 20px;
    font-weight: 800;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="title">0xmwY Kraken</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub">pengembang : Lutfi Andreyansah</div>',
    unsafe_allow_html=True
)

st.caption(
    '"Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"'
)


# =========================================================
# API
# =========================================================

def api(path, params=None):

    try:

        r = requests.get(
            BASE + path,
            params=params or {},
            timeout=15
        )

        r.raise_for_status()

        data = r.json()

        if data.get("code") != "0":
            return None

        return data.get("data")

    except Exception:

        return None


# =========================================================
# GET ALL OKX USDT PERPETUAL
# =========================================================

@st.cache_data(ttl=60)
def get_instruments():

    data = api(
        "/api/v5/public/instruments",
        {
            "instType": "SWAP"
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for x in data:

        inst = x.get(
            "instId",
            ""
        )

        if not inst.endswith(
            "-USDT-SWAP"
        ):
            continue

        if x.get("state") != "live":
            continue

        pair = inst.replace(
            "-SWAP",
            ""
        )

        rows.append({
            "inst": inst,
            "pair": pair
        })

    return pd.DataFrame(rows)


# =========================================================
# GET TICKERS
# =========================================================

@st.cache_data(ttl=10)
def get_tickers():

    data = api(
        "/api/v5/market/tickers",
        {
            "instType": "SWAP"
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for x in data:

        inst = x.get(
            "instId",
            ""
        )

        if not inst.endswith(
            "-USDT-SWAP"
        ):
            continue

        try:

            last = float(
                x.get("last", 0)
            )

            open24 = float(
                x.get("open24h", 0)
            )

            high = float(
                x.get("high24h", 0)
            )

            low = float(
                x.get("low24h", 0)
            )

            vol_ccy = float(
                x.get("volCcy24h", 0)
            )

            if last <= 0:
                continue

            if open24 > 0:

                change = (
                    (last - open24)
                    / open24
                ) * 100

            else:

                change = 0

            # OKX volCcy24h untuk SWAP
            # dapat digunakan sebagai
            # volume quote currency.
            volume_usdt = (
                vol_ccy * last
                if vol_ccy > 0
                else 0
            )

            rows.append({

                "inst": inst,

                "pair": inst.replace(
                    "-SWAP",
                    ""
                ),

                "price": last,

                "change": change,

                "high": high,

                "low": low,

                "volume": volume_usdt

            })

        except Exception:

            continue

    return pd.DataFrame(rows)


# =========================================================
# GET CANDLES
# =========================================================

@st.cache_data(ttl=20)
def get_candles(
    inst,
    bar,
    limit=60
):

    data = api(
        "/api/v5/market/candles",
        {
            "instId": inst,
            "bar": bar,
            "limit": str(limit)
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for c in data:

        try:

            rows.append({

                "timestamp": int(c[0]),

                "open": float(c[1]),

                "high": float(c[2]),

                "low": float(c[3]),

                "close": float(c[4]),

                "volume": float(c[5])

            })

        except Exception:

            continue

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .iloc[::-1]
        .reset_index(drop=True)
    )


# =========================================================
# FORMAT PRICE
# =========================================================

def format_price(price):

    if price >= 1000:

        return f"{price:,.2f}"

    if price >= 1:

        return f"{price:,.4f}"

    if price >= 0.01:

        return f"{price:,.5f}"

    return f"{price:.8f}"


# =========================================================
# FORMAT VOLUME
# =========================================================

def format_volume(value):

    if value >= 1_000_000_000:

        return (
            f"${value / 1_000_000_000:.2f}B"
        )

    if value >= 1_000_000:

        return (
            f"${value / 1_000_000:.2f}M"
        )

    if value >= 1_000:

        return (
            f"${value / 1_000:.2f}K"
        )

    return f"${value:,.0f}"


# =========================================================
# OUTLOOK ANALYSIS
# =========================================================

def analyze_outlook(
    df,
    bars
):

    if df.empty or len(df) < 25:
        return None

    close = df["close"]

    ema9 = close.ewm(
        span=9,
        adjust=False
    ).mean()

    ema21 = close.ewm(
        span=21,
        adjust=False
    ).mean()

    # Momentum beberapa candle
    momentum = (
        (
            close.iloc[-1]
            - close.iloc[-6]
        )
        / close.iloc[-6]
    ) * 100

    score = 0

    # Trend
    if ema9.iloc[-1] > ema21.iloc[-1]:
        score += 1
    else:
        score -= 1

    # Momentum
    if momentum > 0:
        score += 1
    else:
        score -= 1

    # Candle terakhir
    if close.iloc[-1] > close.iloc[-2]:
        score += 1
    else:
        score -= 1

    if score > 0:

        side = "LONG"

    else:

        side = "SHORT"

    return {
        "side": side,
        "score": score,
        "momentum": momentum
    }


# =========================================================
# GET COIN OUTLOOK
# =========================================================

def get_coin_outlook(inst):

    timeframes = {
        "5M": "5m",
        "15M": "15m",
        "30M": "30m"
    }

    result = {}

    for name, bar in timeframes.items():

        candles = get_candles(
            inst,
            bar
        )

        analysis = analyze_outlook(
            candles,
            bar
        )

        if analysis:

            result[name] = analysis["side"]

    if not result:
        return None

    long_count = sum(
        x == "LONG"
        for x in result.values()
    )

    short_count = sum(
        x == "SHORT"
        for x in result.values()
    )

    if long_count >= 2:

        overall = "LONG"

    elif short_count >= 2:

        overall = "SHORT"

    else:

        overall = "NEUTRAL"

    return {
        "5M": result.get(
            "5M",
            "-"
        ),

        "15M": result.get(
            "15M",
            "-"
        ),

        "30M": result.get(
            "30M",
            "-"
        ),

        "overall": overall
    }


# =========================================================
# TRADINGVIEW CHART
# =========================================================

def tradingview_chart(
    pair,
    interval,
    height=420
):

    symbol = (
        "OKX:"
        + pair.replace("-", "")
        + ".P"
    )

    chart_id = (
        "tv_"
        + pair.replace("-", "_")
        + "_"
        + str(time.time()).replace(
            ".",
            ""
        )
    )

    html = f"""
    <div
        id="{chart_id}"
        style="
            width:100%;
            height:{height}px;
        ">
    </div>

    <script
        src="https://s3.tradingview.com/tv.js">
    </script>

    <script>

    new TradingView.widget({{

        "autosize": true,

        "symbol": "{symbol}",

        "interval": "{interval}",

        "timezone": "Asia/Jakarta",

        "theme": "dark",

        "style": "1",

        "locale": "en",

        "enable_publishing": false,

        "hide_top_toolbar": false,

        "hide_legend": false,

        "save_image": false,

        "allow_symbol_change": false,

        "withdateranges": true,

        "hide_side_toolbar": false,

        "container_id": "{chart_id}"

    }});

    </script>
    """

    components.html(
        html,
        height=height + 20
    )


# =========================================================
# LOAD DATA
# =========================================================

instruments = get_instruments()

tickers = get_tickers()


if instruments.empty or tickers.empty:

    st.error(
        "Market OKX gagal dimuat."
    )

    st.stop()


market = instruments.merge(
    tickers,
    on=[
        "inst",
        "pair"
    ],
    how="left"
)


# =========================================================
# TABS
# =========================================================

tab_market, tab_chart, tab_outlook, tab_heatmap = st.tabs(
    [
        "Market",
        "Chart",
        "Outlook",
        "Heatmap"
    ]
)


# =========================================================
# TAB 1 — MARKET
# =========================================================

with tab_market:

    st.subheader(
        "Market"
    )

    search = st.text_input(
        "Search pair",
        placeholder="BTC, ETH, SOL..."
    )

    market_view = market.copy()

    if search:

        market_view = market_view[
            market_view["pair"].str.contains(
                search.upper(),
                na=False
            )
        ]

    sort_by = st.selectbox(
        "Sort",
        [
            "Volume",
            "24H Change",
            "Pair"
        ]
    )

    if sort_by == "Volume":

        market_view = market_view.sort_values(
            "volume",
            ascending=False
        )

    elif sort_by == "24H Change":

        market_view = market_view.sort_values(
            "change",
            ascending=False
        )

    else:

        market_view = market_view.sort_values(
            "pair"
        )


    st.caption(
        f"{len(market_view)} pair"
    )


    # -----------------------------------------------------
    # MARKET ROWS
    # -----------------------------------------------------

    for _, row in market_view.head(50).iterrows():

        pair = row["pair"]

        price = row["price"]

        change = row["change"]

        volume = row["volume"]


        left, middle, right = st.columns(
            [1.2, 1.2, 3]
        )


        with left:

            st.markdown(
                f"### {pair}"
            )

            st.caption(
                f"24H {change:+.2f}%"
            )


        with middle:

            st.markdown(
                f"**{format_price(price)}**"
            )

            st.caption(
                f"Volume {format_volume(volume)}"
            )


        with right:

            tradingview_chart(
                pair,
                "15",
                220
            )


        st.divider()


# =========================================================
# TAB 2 — CHART
# =========================================================

with tab_chart:

    st.subheader(
        "Multi Chart"
    )

    search_chart = st.text_input(
        "Search pair",
        key="chart_search",
        placeholder="BTC, ETH, SOL..."
    )

    chart_pairs = all_pairs = list(
        instruments["pair"]
    )

    if search_chart:

        chart_pairs = [
            x
            for x in chart_pairs
            if search_chart.upper() in x
        ]


    selected_pairs = st.multiselect(
        "Pilih maksimal 4 pair",
        chart_pairs,
        max_selections=4,
        default=[
            x
            for x in [
                "BTC-USDT",
                "ETH-USDT",
                "SOL-USDT",
                "XRP-USDT"
            ]
            if x in chart_pairs
        ],
        key="chart_pairs"
    )


    chart_tf = st.selectbox(
        "Timeframe",
        [
            "1M",
            "5M",
            "15M",
            "30M",
            "1H",
            "4H",
            "1D"
        ],
        index=2,
        key="chart_tf"
    )


    chart_interval = {
        "1M": "1",
        "5M": "5",
        "15M": "15",
        "30M": "30",
        "1H": "60",
        "4H": "240",
        "1D": "D"
    }[chart_tf]


    st.divider()


    if selected_pairs:

        # Row 1
        row1 = st.columns(2)

        for i in range(
            min(
                2,
                len(selected_pairs)
            )
        ):

            with row1[i]:

                pair = selected_pairs[i]

                st.markdown(
                    f"### {pair}"
                )

                tradingview_chart(
                    pair,
                    chart_interval,
                    430
                )


        # Row 2
        if len(selected_pairs) > 2:

            st.divider()

            row2 = st.columns(2)

            for i in range(2):

                index = i + 2

                if index >= len(
                    selected_pairs
                ):
                    break

                with row2[i]:

                    pair = selected_pairs[index]

                    st.markdown(
                        f"### {pair}"
                    )

                    tradingview_chart(
                        pair,
                        chart_interval,
                        430
                    )

    else:

        st.info(
            "Pilih pair untuk menampilkan chart."
        )


# =========================================================
# TAB 3 — OUTLOOK
# =========================================================

with tab_outlook:

    st.subheader(
        "Outlook"
    )

    st.caption(
        "Arah sederhana berdasarkan 5M, 15M dan 30M."
    )


    outlook_search = st.text_input(
        "Search pair",
        key="outlook_search",
        placeholder="BTC, ETH, SOL..."
    )


    outlook_pairs = list(
        instruments["pair"]
    )


    if outlook_search:

        outlook_pairs = [
            x
            for x in outlook_pairs
            if outlook_search.upper() in x
        ]


    selected_outlook = st.selectbox(
        "Pair",
        outlook_pairs,
        key="outlook_pair"
    )


    selected_inst = instruments.loc[
        instruments["pair"]
        == selected_outlook,
        "inst"
    ].iloc[0]


    with st.spinner(
        "Menganalisis..."
    ):

        outlook = get_coin_outlook(
            selected_inst
        )


    st.divider()


    if outlook:

        c1, c2, c3 = st.columns(3)


        with c1:

            st.caption("5M")

            st.markdown(
                f"## {outlook['5M']}"
            )


        with c2:

            st.caption("15M")

            st.markdown(
                f"## {outlook['15M']}"
            )


        with c3:

            st.caption("30M")

            st.markdown(
                f"## {outlook['30M']}"
            )


        st.divider()


        st.markdown(
            "### Overall"
        )


        if outlook["overall"] == "LONG":

            st.success(
                "OUTLOOK LONG"
            )

        elif outlook["overall"] == "SHORT":

            st.error(
                "OUTLOOK SHORT"
            )

        else:

            st.warning(
                "NEUTRAL"
            )


        st.caption(
            "Outlook adalah analisis indikatif, bukan jaminan arah harga."
        )

    else:

        st.warning(
            "Data candle belum tersedia."
        )


# =========================================================
# TAB 4 — HEATMAP
# =========================================================

with tab_heatmap:

    st.subheader(
        "Market Strength"
    )

    st.caption(
        "Ranking berdasarkan kombinasi perubahan 24H dan volume."
    )


    heat = market.copy()


    # -----------------------------------------------------
    # NORMALIZED SCORE
    # -----------------------------------------------------

    if not heat.empty:

        move_max = max(
            heat["change"].abs().max(),
            0.000001
        )

        vol_max = max(
            heat["volume"].max(),
            0.000001
        )


        heat["strength"] = (

            (
                heat["change"].abs()
                / move_max
            ) * 0.60

            +

            (
                heat["volume"]
                / vol_max
            ) * 0.40

        )


        heat["direction"] = heat[
            "change"
        ].apply(
            lambda x:
            "LONG"
            if x > 0
            else "SHORT"
        )


        heat = heat.sort_values(
            "strength",
            ascending=False
        )


        # -------------------------------------------------
        # TOP 20
        # -------------------------------------------------

        top = heat.head(20).copy()


        for rank, (_, row) in enumerate(
            top.iterrows(),
            start=1
        ):

            pair = row["pair"]

            change = row["change"]

            volume = row["volume"]

            direction = row[
                "direction"
            ]


            a, b, c, d = st.columns(
                [0.5, 2, 1.2, 1.5]
            )


            with a:

                st.write(
                    f"**{rank}**"
                )


            with b:

                st.write(
                    f"**{pair}**"
                )


            with c:

                if direction == "LONG":

                    st.write(
                        f"LONG {change:+.2f}%"
                    )

                else:

                    st.write(
                        f"SHORT {change:+.2f}%"
                    )


            with d:

                st.write(
                    format_volume(
                        volume
                    )
                )


            st.divider()


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "OKX Market Monitor • TradingView • DYOR"
                     )
