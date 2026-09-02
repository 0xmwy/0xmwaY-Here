import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import sqlite3
import re
import xml.etree.ElementTree as ET
from html import unescape
from datetime import datetime, timedelta, timezone

st.set_page_config(
    page_title="0xmwY Kraken",
    page_icon="⚡",
    layout="wide"
)

BASE = "https://www.okx.com"
DB = "screening_history.db"

TIMEFRAMES = {
    "15M": "15m",
    "30M": "30m",
    "1H": "1H"
}

MAX_MOVER = 12


# =========================================================
# FED CONFIG
# =========================================================

FED_NEWS_URL = (
    "https://www.federalreserve.gov/newsevents.htm"
)

FED_SPEECHES_URL = (
    "https://www.federalreserve.gov/"
    "newsevents/speech/2026-speeches.htm"
)

FED_CALENDAR_URL = (
    "https://www.federalreserve.gov/"
    "newsevents/calendar.htm"
)

FED_FOMC_URL = (
    "https://www.federalreserve.gov/"
    "monetarypolicy/fomccalendars.htm"
)

FED_RSS_URLS = [
    "https://www.federalreserve.gov/"
    "feeds/speeches.xml",

    "https://www.federalreserve.gov/"
    "feeds/testimony.xml"
]


# =========================================================
# HEADER
# =========================================================

st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
}

.title {
    font-size: 40px;
    font-weight: 800;
}

.sub {
    opacity: .7;
}

.macro-card {
    padding: 18px;
    border-radius: 14px;
    border: 1px solid rgba(128,128,128,.25);
    margin-bottom: 12px;
}

.macro-title {
    font-size: 20px;
    font-weight: 700;
}

.macro-small {
    opacity: .7;
    font-size: 13px;
}

.sentiment-bar {
    width: 100%;
    height: 28px;
    border-radius: 999px;
    overflow: hidden;
    display: flex;
    margin-top: 10px;
    margin-bottom: 8px;
    background: #333;
}

.sentiment-bull {
    background: #19c37d;
    height: 100%;
}

.sentiment-bear {
    background: #ef4444;
    height: 100%;
}

.news-item {
    padding: 12px 0;
    border-bottom: 1px solid rgba(128,128,128,.18);
}

.news-date {
    font-size: 12px;
    opacity: .6;
}

.news-title {
    font-weight: 600;
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
# DATABASE
# =========================================================

def connect_db():
    return sqlite3.connect(DB)


def init_db():

    con = connect_db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            pair TEXT,
            outlook TEXT,
            movement REAL,
            volatility REAL,
            entry_low REAL,
            entry_high REAL,
            tp REAL,
            sl REAL,
            confidence REAL,
            status TEXT DEFAULT 'OPEN',
            pnl_pct REAL DEFAULT 0,
            resolved_at TEXT
        )
    """)

    con.commit()
    con.close()


def migrate_db():

    con = connect_db()

    cols = [
        x[1]
        for x in con.execute(
            "PRAGMA table_info(history)"
        ).fetchall()
    ]

    additions = {
        "sl": "REAL",
        "status": "TEXT DEFAULT 'OPEN'",
        "pnl_pct": "REAL DEFAULT 0",
        "resolved_at": "TEXT"
    }

    for name, typ in additions.items():

        if name not in cols:

            con.execute(
                f"ALTER TABLE history ADD COLUMN {name} {typ}"
            )

    con.commit()
    con.close()


def clean_db():

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=24)
    ).isoformat()

    con = connect_db()

    con.execute(
        "DELETE FROM history WHERE timestamp < ?",
        (cutoff,)
    )

    con.commit()
    con.close()


def save_results(results):

    if not results:
        return

    con = connect_db()

    for x in results:

        con.execute("""
            INSERT INTO history (
                timestamp,
                pair,
                outlook,
                movement,
                volatility,
                entry_low,
                entry_high,
                tp,
                sl,
                confidence,
                status,
                pnl_pct
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, 'OPEN', 0
            )
        """, (
            x["timestamp"],
            x["pair"],
            x["outlook"],
            x["movement"],
            x["volatility"],
            x["entry_low"],
            x["entry_high"],
            x["tp"],
            x["sl"],
            x["confidence"]
        ))

    con.commit()
    con.close()


def get_history():

    con = connect_db()

    df = pd.read_sql_query(
        "SELECT * FROM history ORDER BY timestamp DESC",
        con
    )

    con.close()

    return df


init_db()
migrate_db()
clean_db()


# =========================================================
# API
# =========================================================

def api(path, params):

    try:

        r = requests.get(
            BASE + path,
            params=params,
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
# TICKERS
# =========================================================

@st.cache_data(ttl=30)
def get_tickers():

    data = api(
        "/api/v5/market/tickers",
        {"instType": "SWAP"}
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for x in data:

        inst = x.get("instId", "")

        if not inst.endswith("-USDT-SWAP"):
            continue

        try:

            price = float(x["last"])
            op = float(x["open24h"])
            high = float(x["high24h"])
            low = float(x["low24h"])

        except Exception:

            continue

        if price <= 0 or op <= 0:
            continue

        movement = (
            (price - op)
            / op
        ) * 100

        volatility = (
            (high - low)
            / op
        ) * 100

        rows.append({
            "inst": inst,
            "pair": inst.replace("-SWAP", ""),
            "price": price,
            "movement": movement,
            "abs_move": abs(movement),
            "volatility": volatility
        })

    return pd.DataFrame(rows)
    # =========================================================
# FED NEWS
# =========================================================

def clean_html(text):

    if not text:
        return ""

    text = unescape(text)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


@st.cache_data(ttl=120)
def get_fed_news():

    news = []

    # -----------------------------------------------------
    # OFFICIAL FED NEWS PAGE
    # -----------------------------------------------------

    try:

        r = requests.get(
            FED_NEWS_URL,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        r.raise_for_status()

        html = r.text

        pattern = re.compile(
            r'href="([^"]+)"[^>]*>'
            r'\s*([^<]{10,250})'
            r'</a>',
            re.IGNORECASE
        )

        matches = pattern.findall(html)

        for href, title in matches:

            title = clean_html(title)

            if len(title) < 10:
                continue

            if href.startswith("/"):
                link = (
                    "https://www.federalreserve.gov"
                    + href
                )
            else:
                link = href

            if "speech" in link.lower():
                category = "SPEECH"

            elif "testimony" in link.lower():
                category = "TESTIMONY"

            elif "press" in link.lower():
                category = "PRESS"

            else:
                category = "FED"

            news.append({
                "title": title,
                "link": link,
                "category": category,
                "date": ""
            })

    except Exception:
        pass


    # -----------------------------------------------------
    # OFFICIAL FED RSS
    # -----------------------------------------------------

    for rss_url in FED_RSS_URLS:

        try:

            r = requests.get(
                rss_url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            r.raise_for_status()

            root = ET.fromstring(r.content)

            for item in root.iter("item"):

                title = item.findtext(
                    "title",
                    default=""
                )

                link = item.findtext(
                    "link",
                    default=""
                )

                pub = item.findtext(
                    "pubDate",
                    default=""
                )

                description = item.findtext(
                    "description",
                    default=""
                )

                title = clean_html(title)
                description = clean_html(
                    description
                )

                if not title:
                    continue

                news.append({
                    "title": title,
                    "link": link,
                    "category": "FED RSS",
                    "date": pub,
                    "description": description
                })

        except Exception:
            continue


    # -----------------------------------------------------
    # REMOVE DUPLICATES
    # -----------------------------------------------------

    unique = {}

    for item in news:

        key = (
            item.get("title", "")
            .strip()
            .lower()
        )

        if key and key not in unique:
            unique[key] = item

    return list(unique.values())[:30]


# =========================================================
# FED SENTIMENT
# =========================================================

BULLISH_TERMS = [
    "rate cut",
    "rate cuts",
    "lower rates",
    "lowering rates",
    "easing",
    "dovish",
    "accommodative",
    "support growth",
    "economic growth",
    "strong growth",
    "soft landing",
    "inflation cooling",
    "inflation eased",
    "inflation moderating",
    "labor market weakening",
    "labor market cooling",
    "room to ease",
    "policy easing",
    "cut rates"
]

BEARISH_TERMS = [
    "rate hike",
    "rate hikes",
    "higher rates",
    "raising rates",
    "tightening",
    "hawkish",
    "restrictive",
    "persistent inflation",
    "inflation remains elevated",
    "inflation remains high",
    "inflation pressures",
    "overheating",
    "strong inflation",
    "labor market remains strong",
    "upside inflation",
    "policy tightening",
    "keep rates high",
    "higher for longer"
]


def fed_sentiment_score(news):

    bullish = 0
    bearish = 0

    for item in news:

        text = (
            item.get("title", "")
            + " "
            + item.get("description", "")
        ).lower()

        for term in BULLISH_TERMS:

            if term in text:
                bullish += 1

        for term in BEARISH_TERMS:

            if term in text:
                bearish += 1

    total = bullish + bearish

    if total == 0:

        return {
            "bullish": 50,
            "bearish": 50,
            "winner": "NEUTRAL",
            "score": 0
        }

    bullish_pct = (
        bullish
        / total
        * 100
    )

    bearish_pct = (
        bearish
        / total
        * 100
    )

    if bullish_pct > bearish_pct:
        winner = "BULLISH"

    elif bearish_pct > bullish_pct:
        winner = "BEARISH"

    else:
        winner = "NEUTRAL"

    score = (
        bullish_pct
        - bearish_pct
    )

    return {
        "bullish": bullish_pct,
        "bearish": bearish_pct,
        "winner": winner,
        "score": score
    }


def fed_macro_ratio():

    news = get_fed_news()

    sentiment = fed_sentiment_score(
        news
    )

    return {
        "news": news,
        "bullish": sentiment["bullish"],
        "bearish": sentiment["bearish"],
        "winner": sentiment["winner"],
        "score": sentiment["score"]
    }


# =========================================================
# FED H-1 EVENT
# =========================================================

def get_month_calendar_url(year, month):

    month_name = datetime(
        year,
        month,
        1
    ).strftime("%B").lower()

    return (
        "https://www.federalreserve.gov/"
        f"newsevents/{year}-{month_name}.htm"
    )


@st.cache_data(ttl=300)
def get_fed_calendar():

    events = []

    now = datetime.now(
        timezone.utc
    )

    urls = [
        FED_CALENDAR_URL,
        get_month_calendar_url(
            now.year,
            now.month
        )
    ]

    if now.month == 12:

        next_year = now.year + 1
        next_month = 1

    else:

        next_year = now.year
        next_month = now.month + 1

    urls.append(
        get_month_calendar_url(
            next_year,
            next_month
        )
    )

    seen = set()

    for url in urls:

        try:

            r = requests.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            r.raise_for_status()

            html = r.text

            text = clean_html(html)

            # -------------------------------------------------
            # FOMC
            # -------------------------------------------------

            if "FOMC" in text:

                key = "FOMC"

                if key not in seen:

                    events.append({
                        "name": "FOMC",
                        "date_text": "",
                        "type": "FOMC",
                        "source": FED_FOMC_URL
                    })

                    seen.add(key)

            # -------------------------------------------------
            # SPEECH
            # -------------------------------------------------

            speech_matches = re.findall(
                r"Speech[^<]{0,150}",
                html,
                re.IGNORECASE
            )

            for speech in speech_matches[:10]:

                speech = clean_html(
                    speech
                )

                if len(speech) < 10:
                    continue

                events.append({
                    "name": speech,
                    "date_text": "",
                    "type": "SPEECH",
                    "source": FED_CALENDAR_URL
                })

        except Exception:
            continue

    return events


def h1_fed_alert():

    events = get_fed_calendar()

    # The official calendar structure changes,
    # so only display a safe informational alert
    # when an upcoming Fed/FOMC event is detected.

    if not events:
        return []

    unique = {}

    for event in events:

        key = (
            event["type"],
            event["name"]
        )

        unique[key] = event

    return list(unique.values())[:10]


# =========================================================
# FED MACRO UI
# =========================================================

def show_fed_macro():

    macro = fed_macro_ratio()

    bullish = macro["bullish"]
    bearish = macro["bearish"]
    winner = macro["winner"]

    st.divider()

    st.subheader(
        "🏦 Fed Macro Market Impact"
    )

    if winner == "BULLISH":

        st.success(
            f"Dominan: BULLISH • "
            f"{bullish:.0f}% Bullish"
        )

    elif winner == "BEARISH":

        st.error(
            f"Dominan: BEARISH • "
            f"{bearish:.0f}% Bearish"
        )

    else:

        st.info(
            "Dominan: NEUTRAL"
        )

    # -----------------------------------------------------
    # ONE SPLIT BAR
    # -----------------------------------------------------

    st.markdown(
        f"""
        <div class="sentiment-bar">
            <div
                class="sentiment-bull"
                style="width:{bullish:.2f}%">
            </div>

            <div
                class="sentiment-bear"
                style="width:{bearish:.2f}%">
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    left, right = st.columns(2)

    with left:

        st.metric(
            "🟢 Bullish",
            f"{bullish:.0f}%"
        )

    with right:

        st.metric(
            "🔴 Bearish",
            f"{bearish:.0f}%"
        )

    # -----------------------------------------------------
    # FED NEWS
    # -----------------------------------------------------

    st.markdown(
        "### 📰 Latest Fed Updates"
    )

    news = macro["news"]

    if not news:

        st.info(
            "Belum ada update Fed yang berhasil diambil."
        )

    else:

        for item in news[:8]:

            title = item.get(
                "title",
                "Fed Update"
            )

            category = item.get(
                "category",
                "FED"
            )

            date = item.get(
                "date",
                ""
            )

            link = item.get(
                "link",
                ""
            )

            st.markdown(
                f"""
                <div class="news-item">
                    <div class="news-title">
                        {title}
                    </div>
                    <div class="news-date">
                        {category} {date}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            if link:

                st.markdown(
                    f"[Open official Fed source]({link})"
                )

    # -----------------------------------------------------
    # H-1 ALERT
    # -----------------------------------------------------

    alerts = h1_fed_alert()

    if alerts:

        st.markdown(
            "### 🚨 Upcoming Fed Alert"
        )

        st.warning(
            "Ada agenda Federal Reserve "
            "yang perlu diperhatikan. "
            "Cek kalender resmi sebelum trading."
        )

        for event in alerts[:5]:

            st.caption(
                f"• {event['type']}: "
                f"{event['name']}"
            )

    # -----------------------------------------------------
    # REFRESH
    # -----------------------------------------------------

    if st.button(
        "🔄 Refresh Fed Data",
        use_container_width=True
    ):

        st.cache_data.clear()

        st.rerun()


# =========================================================
# TOP MOVER
# =========================================================

def top_movers(df):

    if df.empty:
        return df

    df = df.copy()

    move_max = max(
        df["abs_move"].max(),
        0.000001
    )

    vol_max = max(
        df["volatility"].max(),
        0.000001
    )

    df["score"] = (
        df["abs_move"]
        / move_max
        * 0.60
        +
        df["volatility"]
        / vol_max
        * 0.40
    )

    return (
        df.sort_values(
            "score",
            ascending=False
        )
        .head(MAX_MOVER)
        .reset_index(drop=True)
    )


# =========================================================
# CANDLES
# =========================================================

@st.cache_data(ttl=30)
def get_candles(inst, bar):

    data = api(
        "/api/v5/market/candles",
        {
            "instId": inst,
            "bar": bar,
            "limit": "80"
        }
    )

    if not data:
        return pd.DataFrame()

    rows = []

    for c in data:

        try:

            rows.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5])
            })

        except Exception:

            pass

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .iloc[::-1]
        .reset_index(drop=True)
    )


# =========================================================
# TIMEFRAME ANALYSIS
# =========================================================

def analyze_tf(df):

    if len(df) < 30:
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

    momentum = (
        (
            close.iloc[-1]
            - close.iloc[-6]
        )
        / close.iloc[-6]
    ) * 100

    bull = 0
    bear = 0

    if ema9.iloc[-1] > ema21.iloc[-1]:
        bull += 1
    else:
        bear += 1

    if momentum > 0:
        bull += 1
    else:
        bear += 1

    if close.iloc[-1] > close.iloc[-2]:
        bull += 1
    else:
        bear += 1

    if bull > bear:

        side = "LONG"
        confidence = bull / 3 * 100

    else:

        side = "SHORT"
        confidence = bear / 3 * 100

    high = close.tail(20).max()
    low = close.tail(20).min()

    volatility = (
        (high - low)
        / close.iloc[-1]
    ) * 100

    return {
        "side": side,
        "confidence": confidence,
        "price": close.iloc[-1],
        "volatility": volatility
            }
    # =========================================================
# COIN ANALYSIS
# =========================================================

def analyze_coin(inst):

    tf = {}

    for name, bar in TIMEFRAMES.items():

        df = get_candles(
            inst,
            bar
        )

        result = analyze_tf(df)

        if result:
            tf[name] = result

    if len(tf) < 2:
        return None

    longs = sum(
        x["side"] == "LONG"
        for x in tf.values()
    )

    shorts = sum(
        x["side"] == "SHORT"
        for x in tf.values()
    )

    if longs >= 2:

        side = "LONG"

    elif shorts >= 2:

        side = "SHORT"

    else:

        return None

    price = list(
        tf.values()
    )[-1]["price"]

    vol = sum(
        x["volatility"]
        for x in tf.values()
    ) / len(tf)

    distance = max(
        price * (vol / 100) * 0.20,
        price * 0.001
    )

    if side == "LONG":

        entry_low = price - distance
        entry_high = price
        tp = price + distance * 2
        sl = price - distance

    else:

        entry_low = price
        entry_high = price + distance
        tp = price - distance * 2
        sl = price + distance

    confidence = (
        max(longs, shorts)
        / len(tf)
        * 100
    )

    return {
        "outlook": side,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "tp": tp,
        "sl": sl,
        "confidence": confidence
    }


# =========================================================
# SCREENING
# =========================================================

def screening():

    tickers = get_tickers()

    if tickers.empty:
        return []

    movers = top_movers(tickers)

    results = []

    for _, mover in movers.iterrows():

        result = analyze_coin(
            mover["inst"]
        )

        if not result:
            continue

        now = datetime.now(timezone.utc)

        results.append({
            "timestamp": now.isoformat(),
            "pair": mover["pair"],
            "outlook": result["outlook"],
            "movement": mover["movement"],
            "volatility": mover["volatility"],
            "entry_low": result["entry_low"],
            "entry_high": result["entry_high"],
            "tp": result["tp"],
            "sl": result["sl"],
            "confidence": result["confidence"]
        })

    return sorted(
        results,
        key=lambda x: (
            x["confidence"],
            abs(x["movement"])
        ),
        reverse=True
    )


# =========================================================
# CHECK PROFIT / LOSS
# =========================================================

def resolve_history():

    con = connect_db()

    rows = con.execute("""
        SELECT
            id,
            pair,
            outlook,
            entry_low,
            entry_high,
            tp,
            sl
        FROM history
        WHERE status = 'OPEN'
    """).fetchall()

    for row in rows:

        trade_id = row[0]
        pair = row[1]
        side = row[2]
        entry_low = row[3]
        entry_high = row[4]
        tp = row[5]
        sl = row[6]

        if sl is None:
            continue

        df = get_candles(
            pair + "-SWAP",
            "15m"
        )

        if df.empty:
            continue

        current = float(
            df["close"].iloc[-1]
        )

        status = None
        pnl = 0

        if side == "LONG":

            if current >= tp:

                status = "SUCCESS"

                pnl = (
                    (tp - entry_high)
                    / entry_high
                ) * 100

            elif current <= sl:

                status = "LOSS"

                pnl = (
                    (sl - entry_high)
                    / entry_high
                ) * 100

        else:

            if current <= tp:

                status = "SUCCESS"

                pnl = (
                    (entry_low - tp)
                    / entry_low
                ) * 100

            elif current >= sl:

                status = "LOSS"

                pnl = (
                    (entry_low - sl)
                    / entry_low
                ) * 100

        if status:

            con.execute("""
                UPDATE history
                SET
                    status = ?,
                    pnl_pct = ?,
                    resolved_at = ?
                WHERE id = ?
            """, (
                status,
                pnl,
                datetime.now(
                    timezone.utc
                ).isoformat(),
                trade_id
            ))

    con.commit()
    con.close()


# =========================================================
# SESSION
# =========================================================

if "results" not in st.session_state:
    st.session_state.results = []

if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = None

if "last_scan" not in st.session_state:
    st.session_state.last_scan = "-"


# =========================================================
# SCREEN NOW
# =========================================================

if st.button(
    "⚡ SCREEN NOW",
    use_container_width=True
):

    with st.spinner(
        "Mencari coin volatile..."
    ):

        results = screening()

    st.session_state.results = results

    st.session_state.last_scan = (
        datetime.now().strftime(
            "%H:%M:%S"
        )
    )

    save_results(results)

    clean_db()

    st.rerun()


st.caption(
    f"Last screening: "
    f"{st.session_state.last_scan}"
)


# =========================================================
# UPDATE PROFIT / LOSS
# =========================================================

resolve_history()


# =========================================================
# FED MACRO
# =========================================================

show_fed_macro()


# =========================================================
# CURRENT OUTLOOK
# =========================================================

st.divider()

st.subheader(
    "Current Outlook"
)

results = st.session_state.results

longs = [
    x for x in results
    if x["outlook"] == "LONG"
]

shorts = [
    x for x in results
    if x["outlook"] == "SHORT"
]

col1, col2 = st.columns(2)


# =========================================================
# CARD
# =========================================================

def show_card(x, key, icon):

    with st.container(border=True):

        st.subheader(
            x["pair"]
        )

        st.write(
            f"**Entry:** "
            f"{x['entry_low']:.8g}"
            f" → "
            f"{x['entry_high']:.8g}"
        )

        st.write(
            f"**Take Profit:** "
            f"{x['tp']:.8g}"
        )

        st.write(
            f"**Stop Loss:** "
            f"{x['sl']:.8g}"
        )

        st.caption(
            f"Movement: "
            f"{x['movement']:.2f}%"
        )

        st.caption(
            f"Volatility: "
            f"{x['volatility']:.2f}%"
        )

        st.caption(
            f"Confidence: "
            f"{x['confidence']:.0f}%"
        )

        if st.button(
            f"{icon} Open Chart • {x['pair']}",
            key=key,
            use_container_width=True
        ):

            st.session_state.selected_pair = (
                x["pair"]
            )

            st.rerun()


# =========================================================
# LONG
# =========================================================

with col1:

    st.markdown(
        "### 🟢 OUTLOOK LONG"
    )

    if not longs:

        st.info(
            "Belum ada setup LONG."
        )

    for i, x in enumerate(longs):

        show_card(
            x,
            f"long_{i}_{x['pair']}",
            "📈"
        )


# =========================================================
# SHORT
# =========================================================

with col2:

    st.markdown(
        "### 🔴 OUTLOOK SHORT"
    )

    if not shorts:

        st.info(
            "Belum ada setup SHORT."
        )

    for i, x in enumerate(shorts):

        show_card(
            x,
            f"short_{i}_{x['pair']}",
            "📉"
        )


# =========================================================
# TRADINGVIEW LIVE CHART
# =========================================================

if st.session_state.selected_pair:

    pair = st.session_state.selected_pair

    st.divider()

    st.subheader(
        f"Live Chart • {pair}"
    )

    symbol = (
        "OKX:"
        + pair.replace("-", "")
        + ".P"
    )

    html = f"""
    <div
        id="tradingview_chart"
        style="height:650px;width:100%;">
    </div>

    <script
        src="https://s3.tradingview.com/tv.js">
    </script>

    <script>
    new TradingView.widget({{
        "autosize": true,
        "symbol": "{symbol}",
        "interval": "15",
        "timezone": "Asia/Jakarta",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "hide_legend": false,
        "save_image": false,
        "container_id": "tradingview_chart"
    }});
    </script>
    """

    components.html(
        html,
        height=670
    )


# =========================================================
# HISTORY 24 HOURS
# =========================================================

st.divider()

st.subheader(
    "Screening History — 24 Hours"
)

clean_db()

history = get_history()

if history.empty:

    st.info(
        "Belum ada history screening."
    )

else:

    display = history.copy()

    display["timestamp"] = (
        pd.to_datetime(
            display["timestamp"],
            utc=True
        )
        .dt.tz_convert(
            "Asia/Jakarta"
        )
        .dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    display = display.rename(
        columns={
            "timestamp": "Time",
            "pair": "Pair",
            "outlook": "Outlook",
            "movement": "Movement %",
            "volatility": "Volatility %",
            "entry_low": "Entry Low",
            "entry_high": "Entry High",
            "tp": "Take Profit",
            "sl": "Stop Loss",
            "confidence": "Confidence %",
            "status": "Status",
            "pnl_pct": "P/L %"
        }
    )

    display["Movement %"] = (
        display["Movement %"].round(2)
    )

    display["Volatility %"] = (
        display["Volatility %"].round(2)
    )

    display["Confidence %"] = (
        display["Confidence %"].round(0)
    )

    display["P/L %"] = (
        display["P/L %"].round(2)
    )

    st.dataframe(
        display[
            [
                "Time",
                "Pair",
                "Outlook",
                "Movement %",
                "Volatility %",
                "Entry Low",
                "Entry High",
                "Take Profit",
                "Stop Loss",
                "Confidence %",
                "Status",
                "P/L %"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )
    # =========================================================
# 24H PERFORMANCE
# =========================================================

st.divider()

st.subheader(
    "24H Performance"
)

perf = get_history()

if perf.empty:

    st.info(
        "Belum ada data performance 24 jam."
    )

else:

    success = perf[
        perf["status"] == "SUCCESS"
    ]

    losses = perf[
        perf["status"] == "LOSS"
    ]

    opened = perf[
        perf["status"] == "OPEN"
    ]

    closed = (
        len(success)
        + len(losses)
    )

    winrate = (
        len(success)
        / closed
        * 100
        if closed
        else 0
    )

    total_profit = (
        success["pnl_pct"].sum()
    )

    total_loss = (
        losses["pnl_pct"].sum()
    )

    net_pnl = (
        total_profit
        + total_loss
    )

    a, b, c, d, e = st.columns(5)

    with a:

        st.metric(
            "SUCCESS",
            len(success)
        )

    with b:

        st.metric(
            "LOSS",
            len(losses)
        )

    with c:

        st.metric(
            "WIN RATE",
            f"{winrate:.2f}%"
        )

    with d:

        st.metric(
            "PROFIT",
            f"+{total_profit:.2f}%"
        )

    with e:

        st.metric(
            "NET P/L",
            f"{net_pnl:+.2f}%"
        )

    st.caption(
        f"Open trades: {len(opened)}"
    )


    # =====================================================
    # SUCCESS PAIRS
    # =====================================================

    st.markdown(
        "### ✅ Pair Sukses"
    )

    if success.empty:

        st.info(
            "Belum ada pair yang mencapai TP."
        )

    else:

        s = success[
            [
                "pair",
                "outlook",
                "pnl_pct",
                "resolved_at"
            ]
        ].copy()

        s.columns = [
            "Pair",
            "Outlook",
            "Profit %",
            "Resolved"
        ]

        s["Profit %"] = (
            s["Profit %"].round(2)
        )

        s["Resolved"] = (
            pd.to_datetime(
                s["Resolved"],
                utc=True
            )
            .dt.tz_convert(
                "Asia/Jakarta"
            )
            .dt.strftime(
                "%H:%M:%S"
            )
        )

        st.dataframe(
            s,
            use_container_width=True,
            hide_index=True
        )


    # =====================================================
    # LOSS PAIRS
    # =====================================================

    st.markdown(
        "### ❌ Pair Loss"
    )

    if losses.empty:

        st.info(
            "Belum ada pair yang terkena SL."
        )

    else:

        l = losses[
            [
                "pair",
                "outlook",
                "pnl_pct",
                "resolved_at"
            ]
        ].copy()

        l.columns = [
            "Pair",
            "Outlook",
            "Loss %",
            "Resolved"
        ]

        l["Loss %"] = (
            l["Loss %"].round(2)
        )

        l["Resolved"] = (
            pd.to_datetime(
                l["Resolved"],
                utc=True
            )
            .dt.tz_convert(
                "Asia/Jakarta"
            )
            .dt.strftime(
                "%H:%M:%S"
            )
        )

        st.dataframe(
            l,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Informational scanner — DYOR."
)
