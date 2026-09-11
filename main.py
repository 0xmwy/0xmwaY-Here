import streamlit as st
import streamlit.components.v1 as components


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="0xmwY Kraken",
    page_icon="⚡",
    layout="wide"
)


# =========================================================
# HEADER
# =========================================================

st.markdown("""
<style>
.block-container {
    padding-top: 1.5rem;
}

.title {
    font-size: 40px;
    font-weight: 800;
}

.sub {
    opacity: 0.7;
}

div[data-baseweb="tab-list"] {
    gap: 6px;
}

div[data-baseweb="tab"] {
    padding-left: 18px;
    padding-right: 18px;
}
</style>
""", unsafe_allow_html=True)


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
# PAIR SETTINGS
# =========================================================

DEFAULT_PAIRS = [
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "XRP-USDT",
    "DOGE-USDT",
    "SUI-USDT"
]


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header("Monitor Settings")

    pair_text = st.text_area(
        "Pair",
        value="\n".join(DEFAULT_PAIRS),
        height=180,
        help="Satu pair per baris"
    )

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

    chart_height = st.slider(
        "Chart Height",
        min_value=450,
        max_value=900,
        value=650,
        step=50
    )


# =========================================================
# CLEAN PAIRS
# =========================================================

pairs = []

for line in pair_text.splitlines():

    pair = line.strip().upper()

    if not pair:
        continue

    pair = pair.replace("/", "-")

    if "-USDT" not in pair:
        continue

    if pair not in pairs:
        pairs.append(pair)


# =========================================================
# CHECK PAIRS
# =========================================================

if not pairs:

    st.warning(
        "Masukkan minimal 1 pair."
    )

    st.stop()


# =========================================================
# TRADINGVIEW CHART
# =========================================================

def show_chart(pair, timeframe, height):

    symbol = (
        "OKX:"
        + pair.replace("-", "")
        + ".P"
    )

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

    chart_id = (
        "tradingview_"
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

        "allow_symbol_change": false,

        "container_id": "{chart_id}"

    }});

    </script>
    """

    components.html(
        html,
        height=height + 20
    )


# =========================================================
# MULTI TABS
# =========================================================

st.subheader("Multi Pair Monitor")

tabs = st.tabs(pairs)


for tab, pair in zip(tabs, pairs):

    with tab:

        st.markdown(
            f"### {pair}"
        )

        show_chart(
            pair,
            timeframe,
            chart_height
        )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "TradingView monitor — DYOR."
)
