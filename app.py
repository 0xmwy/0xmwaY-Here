import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="0xmwY Kraken — Maintenance",
    page_icon="⚡",
    layout="centered"
)

st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

.stApp {
    background: #0b0d12;
}

.block-container {
    padding-top: 7vh;
    max-width: 760px;
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# MAINTENANCE + LIVE COUNTDOWN
# =========================================================

components.html("""

<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<style>

html, body {
    margin: 0;
    padding: 0;
    width: 100%;
    background: #0b0d12;
    font-family: Arial, sans-serif;
}

.container {
    text-align: center;
    padding: 35px 20px;
}

.logo {
    font-size: 48px;
    margin-bottom: 15px;
}

.title {
    color: #ffffff;
    font-size: 38px;
    font-weight: 700;
    margin-bottom: 8px;
}

.developer {
    color: #8f96a3;
    font-size: 14px;
    margin-bottom: 35px;
}

.card {
    background: #151922;
    border: 1px solid #252b38;
    border-radius: 18px;
    padding: 38px 25px;
    box-shadow: 0 12px 35px rgba(0,0,0,.25);
}

.status {
    display: inline-block;
    background: #332b13;
    color: #e6c85c;
    padding: 9px 17px;
    border-radius: 30px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .5px;
    margin-bottom: 22px;
}

.heading {
    color: #ffffff;
    font-size: 25px;
    font-weight: 600;
    margin-bottom: 12px;
}

.description {
    color: #9da4b2;
    font-size: 14px;
    line-height: 1.7;
    max-width: 520px;
    margin: 0 auto 30px auto;
}

.label {
    color: #707887;
    font-size: 11px;
    letter-spacing: 1.5px;
    margin-bottom: 10px;
}

.countdown {
    color: #ffffff;
    font-size: 52px;
    font-weight: 700;
    letter-spacing: 3px;
    font-family: monospace;
    margin-bottom: 8px;
}

.target {
    color: #707887;
    font-size: 12px;
}

.quote {
    color: #555c69;
    font-size: 12px;
    margin-top: 30px;
}

.finished {
    color: #65d99a;
}

</style>

</head>


<body>


<div class="container">

    <div class="logo">
        ⚡
    </div>

    <div class="title">
        0xmwY Kraken
    </div>

    <div class="developer">
        pengembang : Lutfi Andreyansah
    </div>


    <div class="card">

        <div class="status">
            ● SERVER MAINTENANCE
        </div>

        <div class="heading">
            Sedang dalam maintenance
        </div>

        <div class="description">
            0xmwY Kraken sedang melakukan pembaruan
            server dan sistem scanner. Tools akan kembali
            tersedia setelah maintenance selesai.
        </div>

        <div class="label">
            ESTIMASI SELESAI
        </div>

        <div
            id="countdown"
            class="countdown"
        >
            --:--:--
        </div>

        <div class="target">
            12:00 WIB
        </div>

    </div>


    <div class="quote">
        "Ai tak akan mampu gantikan jiwa jiwa manusia #dyor"
    </div>

</div>


<script>

function updateCountdown() {

    const now = new Date();

    /*
       Target maintenance:
       Hari ini pukul 12:00 waktu lokal browser
    */

    let target = new Date();

    target.setHours(12);
    target.setMinutes(0);
    target.setSeconds(0);
    target.setMilliseconds(0);


    let difference =
        target.getTime() - now.getTime();


    const countdown =
        document.getElementById("countdown");


    /*
       Kalau sudah lewat jam 12,
       countdown menjadi 00:00:00
       dan tidak pindah ke besok.
    */

    if (difference <= 0) {

        countdown.innerText = "00:00:00";

        countdown.classList.add("finished");

        return;
    }


    const totalSeconds =
        Math.floor(
            difference / 1000
        );


    const hours =
        Math.floor(
            totalSeconds / 3600
        );


    const minutes =
        Math.floor(
            (totalSeconds % 3600) / 60
        );


    const seconds =
        totalSeconds % 60;


    const h =
        String(hours).padStart(2, "0");

    const m =
        String(minutes).padStart(2, "0");

    const s =
        String(seconds).padStart(2, "0");


    countdown.innerText =
        h + ":" + m + ":" + s;
}


/* Jalankan langsung */

updateCountdown();


/* Update setiap 1 detik */

setInterval(
    updateCountdown,
    1000
);

</script>


</body>

</html>

""", height=650, scrolling=False)
