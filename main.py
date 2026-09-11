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
    padding-top: 1.2rem;
    padding-bottom: 1.5rem;
}

.title {
    font-size: 38px;
    font-weight: 800;
}

.sub {
    opacity: 0.65;
    font-size: 13px;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    padding: 0.4rem;
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
# OKX MARKET
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

            if not inst_id.endswith(
                "-USDT-SWAP"
            ):
                continue

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


all_pairs = get_okx_pairs()


if not all_pairs:

    st.error(
        "Tidak bisa mengambil market OKX."
    )

    st.stop()


# =========================================================
# SETTINGS
# =========================================================

col1, col2 = st.columns(2)


with col1:

    search = st.text_input(
        "Search pair",
        placeholder="BTC / ETH / SOL..."
    )


with col2:

    timeframe = st.selectbox(
        "Default timeframe",
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
# FILTER
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
# SELECT PAIRS
# =========================================================

selected_pairs = st.multiselect(
    "Pilih maksimal 4 pair",
    options=filtered_pairs,
    max_selections=4,
    default=[
        pair
        for pair in [
            "BTC-USDT",
            "ETH-USDT",
            "DOGE-USDT",
            "SOL-USDT"
        ]
        if pair in all_pairs
    ]
)


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
# TRADINGVIEW
# =========================================================

def show_chart(
    pair,
    interval,
    height=430
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

        "allow_symbol_change": true,

        "withdateranges": true,

        "hide_side_toolbar": true,

        "details": false,

        "hotlist": false,

        "calendar": false,

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

if selected_pairs:

    st.divider()

    selected_pairs = selected_pairs[:4]

    # =====================================================
    # ROW 1
    # =====================================================

    row1 = st.columns(2)

    for i in range(
        min(2, len(selected_pairs))
    ):

        pair = selected_pairs[i]

        with row1[i]:

            show_chart(
                pair,
                interval,
                430
            )


    # =====================================================
    # ROW 2
    # =====================================================

    if len(selected_pairs) > 2:

        row2 = st.columns(2)

        for i in range(2):

            index = i + 2

            if index >= len(
                selected_pairs
            ):
                break

            pair = selected_pairs[index]

            with row2[i]:

                show_chart(
                    pair,
                    interval,
                    430
                )


else:

    st.info(
        "Pilih pair untuk mulai monitoring."
    )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    f"OKX Market • {len(all_pairs)} USDT Perpetual • TradingView"
)
