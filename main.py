import streamlit as st
import streamlit.components.v1 as components
import requests


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
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}

.title {
    font-size: 40px;
    font-weight: 800;
}

.sub {
    opacity: 0.7;
}

.chart-title {
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 5px;
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
# GET ALL OKX USDT PERPETUAL
# =========================================================

@st.cache_data(ttl=60)
def get_okx_pairs():

    try:

        response = requests.get(
            BASE + "/api/v5/public/instruments",
            params={
                "instType": "SWAP"
            },
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        if data.get("code") != "0":
            return []

        result = []

        for item in data.get("data", []):

            inst_id = item.get(
                "instId",
                ""
            )

            state = item.get(
                "state",
                ""
            )

            # Hanya USDT perpetual
            if not inst_id.endswith(
                "-USDT-SWAP"
            ):
                continue

            # Hanya market aktif
            if state != "live":
                continue

            pair = inst_id.replace(
                "-SWAP",
                ""
            )

            result.append(pair)

        return sorted(
            list(set(result))
        )

    except Exception:

        return []


# =========================================================
# LOAD MARKET
# =========================================================

all_pairs = get_okx_pairs()


if not all_pairs:

    st.error(
        "Tidak bisa mengambil market OKX."
    )

    st.stop()


# =========================================================
# SETTINGS
# =========================================================

st.subheader(
    "Multi Pair Monitor"
)

st.caption(
    f"Market OKX tersedia: {len(all_pairs)} USDT perpetual"
)


col1, col2 = st.columns(2)


# =========================================================
# TIMEFRAME
# =========================================================

with col1:

    timeframe = st.selectbox(
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
        index=2
    )


# =========================================================
# SEARCH
# =========================================================

with col2:

    search = st.text_input(
        "Search pair",
        placeholder="Contoh: BTC / ETH / SOL"
    )


# =========================================================
# FILTER MARKET
# =========================================================

if search:

    filtered_pairs = [
        pair
        for pair in all_pairs
        if search.upper() in pair
    ]

else:

    filtered_pairs = all_pairs


# =========================================================
# SELECT 4 PAIRS
# =========================================================

selected_pairs = st.multiselect(
    "Pilih maksimal 4 pair",
    options=filtered_pairs,
    max_selections=4,
    placeholder="Pilih BTC-USDT, ETH-USDT, SOL-USDT, XRP-USDT..."
)


# =========================================================
# DEFAULT 4 PAIRS
# =========================================================

if not selected_pairs:

    default_pairs = [
        "BTC-USDT",
        "ETH-USDT",
        "SOL-USDT",
        "XRP-USDT"
    ]

    selected_pairs = [
        pair
        for pair in default_pairs
        if pair in all_pairs
    ]


# =========================================================
# TIMEFRAME MAP
# =========================================================

interval_map = {

    "1M": "1",

    "5M": "5",

    "15M": "15",

    "30M": "30",

    "1H": "60",

    "4H": "240",

    "1D": "D"
}

interval = interval_map[timeframe]


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
        type="text/javascript"
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
# CHART GRID
# =========================================================

st.divider()

if selected_pairs:

    st.subheader(
        f"Live Monitor • {timeframe}"
    )

    # Pastikan maksimal 4
    selected_pairs = selected_pairs[:4]

    # -----------------------------------------------------
    # BARIS 1
    # -----------------------------------------------------

    row1 = st.columns(2)

    for i in range(
        min(2, len(selected_pairs))
    ):

        pair = selected_pairs[i]

        with row1[i]:

            st.markdown(
                f"### {pair}"
            )

            tradingview_chart(
                pair,
                interval,
                430
            )


    # -----------------------------------------------------
    # BARIS 2
    # -----------------------------------------------------

    if len(selected_pairs) > 2:

        st.divider()

        row2 = st.columns(2)

        for i in range(2):

            index = i + 2

            if index >= len(
                selected_pairs
            ):
                break

            pair = selected_pairs[index]

            with row2[i]:

                st.markdown(
                    f"### {pair}"
                )

                tradingview_chart(
                    pair,
                    interval,
                    430
                )


else:

    st.info(
        "Tidak ada pair yang tersedia."
    )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Multi Pair Monitor • OKX Market • TradingView • DYOR"
)
