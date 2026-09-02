import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="0xmwY Kraken — Maintenance",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Hide Streamlit default UI
st.markdown("""
<style>
    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    header {
        visibility: hidden;
    }

    .stApp {
        background: #0b0d12;
    }

    .block-container {
        padding-top: 8vh;
        max-width: 760px;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
# MAINTENANCE PAGE
# =========================================================

st.markdown("""
<div style="
    text-align:center;
    padding:40px 20px 20px 20px;
">

    <div style="
        font-size:52px;
        margin-bottom:18px;
    ">
        ⚡
    </div>

    <h1 style="
        color:white;
        font-size:38px;
        margin-bottom:8px;
        font-weight:700;
    ">
        0xmwY Kraken
    </h1>

    <p style="
        color:#8f96a3;
        font-size:15px;
        margin-bottom:35px;
    ">
        pengembang : Lutfi Andreyansah
    </p>

    <div style="
        background:#151922;
        border:1px solid #252b38;
        border-radius:18px;
        padding:35px 25px;
        box-shadow:0 10px 35px rgba(0,0,0,.25);
    ">

        <div style="
            display:inline-block;
            background:#332b13;
            color:#e6c85c;
            padding:8px 16px;
            border-radius:30px;
            font-size:13px;
            font-weight:600;
            margin-bottom:22px;
        ">
            ● SERVER MAINTENANCE
        </div>

        <h2 style="
            color:white;
            font-size:25px;
            margin:5px 0 12px 0;
        ">
            Sedang dalam maintenance
        </h2>

        <p style="
            color:#9da4b2;
            font-size:14px;
            line-height:1.7;
            margin:0 auto 28px auto;
            max-width:520px;
        ">
            0xmwY Kraken sedang melakukan pembaruan server
            dan sistem scanner. Tools akan kembali tersedia
            setelah maintenance selesai.
        </p>

        <p style="
            color:#707887;
            font-size:12px;
            margin-bottom:10px;
        ">
            ESTIMASI SELESAI
        </p>

        <div id="countdown" style="
            color:white;
            font-size:48px;
            font-weight:700;
            letter-spacing:3px;
            font-family:monospace;
            margin-bottom:8px;
        ">
            02:28:00
        </div>

        <p style="
            color:#707887;
            font-size:12px;
            margin:0;
        ">
            12:00 WIB
        </p>

    </div>

    <p style="
        color:#555c69;
        font-size:12px;
        margin-top:30px;
    ">
        "Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"
    </p>

</div>
""", unsafe_allow_html=True)


# =========================================================
# LIVE COUNTDOWN
# Target: 12:00 WIB
# =========================================================

components.html("""
<script>

(function() {

    const targetHour = 12;
    const targetMinute = 0;
    const targetSecond = 0;

    function updateCountdown() {

        const now = new Date();

        let target = new Date(now);

        target.setHours(
            targetHour,
            targetMinute,
            targetSecond,
            0
        );

        // Kalau sudah lewat jam 12,
        // target dianggap besok jam 12.
        if (now >= target) {
            target.setDate(
                target.getDate() + 1
            );
        }

        const distance =
            target.getTime() - now.getTime();

        const hours = Math.floor(
            distance / (1000 * 60 * 60)
        );

        const minutes = Math.floor(
            (distance % (1000 * 60 * 60))
            / (1000 * 60)
        );

        const seconds = Math.floor(
            (distance % (1000 * 60))
            / 1000
        );

        const h = String(hours).padStart(2, "0");
        const m = String(minutes).padStart(2, "0");
        const s = String(seconds).padStart(2, "0");

        const el =
            window.parent.document
            .getElementById("countdown");

        if (el) {
            el.innerText =
                h + ":" + m + ":" + s;
        }
    }

    updateCountdown();

    setInterval(
        updateCountdown,
        1000
    );

})();

</script>
""", height=1)
