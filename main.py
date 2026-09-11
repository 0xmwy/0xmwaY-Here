import streamlit as st
import streamlit.components.v1 as components
import requests
from urllib.parse import urlencode


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
    opacity: .7;
}

.pair-button {
    margin-top: 10px;
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
# OKX API
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

        pairs = []

        for item in data.get("data", []):

            inst_id = item.get("instId", "")

            # Hanya perpetual USDT
            if not inst_id.endswith("-USDT-SWAP"):
                continue

            # Hanya instrumen aktif
            if item.get("state") != "live":
                continue

            # BTC-USDT-SWAP -> BTC-USDT
            pair = inst_id.replace(
                "-SWAP",
                ""
            )

            pairs.append(pair)

        return sorted(
            list(set(pairs))
        )

    except Exception:

        return []


# =========================================================
# LOAD PAIRS
# =========================================================

pairs = get_okx_pairs()


if not pairs:

    st.error(
        "Gagal mengambil market OKX."
    )

    st.stop()


# =========================================================
# QUERY PARAM
# =========================================================

selected_pair = st.query_params.get(
    "pair",
    ""
)

selected_tf = st.query_params.get(
    "tf",
    "15"
)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header("Monitor")

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

    st.divider()

    st.write(
        f"**OKX USDT Perpetual:** {len(pairs)} pair"
    )


# =========================================================
# IF PAIR IS OPENED
# =========================================================

if selected_pair:

    selected_pair = selected_pair.upper()

    if selected_pair not in pairs:

        st.error(
            f"{selected_pair} tidak ditemukan di market OKX."
        )

        st.stop()

    st.subheader(
        f"Live Chart • {selected_pair}"
    )

    st.caption(
        f"Timeframe: {timeframe}"
    )

    symbol = (
        "OKX:"
        + selected_pair.replace("-", "")
        + ".P"
    )

    chart_id = (
        "tv_"
        + selected_pair.replace("-", "_")
    )

    html = f"""
    <div
        id="{chart_id}"
        style="
            width:100%;
            height:720px;
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

        "container_id": "{chart_id}"

    }});

    </script>
    """

    components.html(
        html,
        height=740
    )

    st.divider()

    st.caption(
        "Gunakan tombol Back atau buka pair lain dari halaman utama."
    )

    st.stop()


# =========================================================
# MAIN MONITOR
# =========================================================

st.subheader(
    "OKX Market Monitor"
)

st.caption(
    "Pilih pair yang ingin kamu pantau. Setiap pair dapat dibuka sebagai browser tab."
)


# =========================================================
# SEARCH
# =========================================================

search = st.text_input(
    "🔎 Search Pair",
    placeholder="Contoh: BTC, ETH, SOL..."
)

if search:

    filtered_pairs = [
        p for p in pairs
        if search.upper() in p
    ]

else:

    filtered_pairs = pairs


st.write(
    f"Menampilkan **{len(filtered_pairs)}** pair"
)


# =========================================================
# SELECT PAIRS
# =========================================================

selected = st.multiselect(
    "Pilih pair untuk dipantau",
    filtered_pairs,
    placeholder="Pilih BTC-USDT, ETH-USDT, SOL-USDT..."
)


# =========================================================
# OPEN SELECTED TABS
# =========================================================

if selected:

    st.divider()

    st.subheader(
        f"Selected • {len(selected)} pair"
    )

    # URL aplikasi saat ini
    current_url = st.context.url

    # Hilangkan query lama
    base_url = current_url.split("?")[0]

    urls = []

    for pair in selected:

        params = urlencode({
            "pair": pair,
            "tf": interval
        })

        urls.append(
            f"{base_url}?{params}"
        )


    # -----------------------------------------------------
    # OPEN ALL
    # -----------------------------------------------------

    js_urls = "[" + ",".join(
        '"' + url.replace('"', '\\"') + '"'
        for url in urls
    ) + "]"

    open_all_html = f"""

    <button
        onclick='openTabs()'
        style="
            width:100%;
            padding:14px;
            border:none;
            border-radius:10px;
            background:#4f7cff;
            color:white;
            font-size:16px;
            font-weight:700;
            cursor:pointer;
        ">
        ⚡ OPEN ALL SELECTED TABS
    </button>

    <script>

    const urls = {js_urls};

    function openTabs() {{

        urls.forEach(function(url) {{

            window.open(
                url,
                "_blank"
            );

        }});

    }}

    </script>

    """

    components.html(
        open_all_html,
        height=65
    )


    # =====================================================
    # INDIVIDUAL TAB LINKS
    # =====================================================

    st.write(
        "**Atau buka satu per satu:**"
    )

    for pair, url in zip(
        selected,
        urls
    ):

        st.markdown(
            f"""
            <a
                href="{url}"
                target="_blank"
                style="
                    display:block;
                    padding:12px 16px;
                    margin:7px 0;
                    border:1px solid rgba(128,128,128,.35);
                    border-radius:10px;
                    text-decoration:none;
                    font-weight:600;
                ">
                📊 {pair} → Open New Tab
            </a>
            """,
            unsafe_allow_html=True
        )


# =========================================================
# MARKET LIST
# =========================================================

st.divider()

st.subheader(
    "All OKX USDT Perpetual"
)

# tampilkan semua pair dalam beberapa kolom
cols = st.columns(4)

for i, pair in enumerate(filtered_pairs):

    col = cols[i % 4]

    params = urlencode({
        "pair": pair,
        "tf": interval
    })

    url = (
        f"{base_url if 'base_url' in locals() else ''}"
        f"?{params}"
    )

    with col:

        st.markdown(
            f"""
            <a
                href="{url}"
                target="_blank"
                style="
                    display:block;
                    padding:8px 10px;
                    margin:3px 0;
                    border:1px solid rgba(128,128,128,.25);
                    border-radius:7px;
                    text-decoration:none;
                    font-size:13px;
                ">
                {pair}
            </a>
            """,
            unsafe_allow_html=True
        )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "OKX market data • TradingView chart • DYOR"
)
