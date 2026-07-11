"""
Website Privacy Risk Scorer — Streamlit app
Page 1: Introduction & market research

Run from the app/ folder with:  streamlit run Home.py
Expects:
  ../clean_data/dataset_completed_clean.csv     (the scraped dataset)
  ../models/reject_effectiveness_rf.joblib (used by page 2)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "clean_data" / "dataset_completed_clean.csv"


st.set_page_config(
    page_title="Privacy Risk Scorer",
    page_icon="🛡️",
    layout="wide",
)

@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH)


df = load_data()

# ---------------------------------------------------------------- header
st.title("🛡️ Website Privacy Risk Scorer")
st.subheader("Does the “Reject” button on cookie banners actually do anything?")

st.markdown(
    """
GDPR and the CNIL require that refusing cookies be **as easy as accepting them** —
and that a refusal be **respected**. In practice, compliance is usually checked on
what's *visible*: is there a banner, is there a reject button. Almost nobody measures
what happens **after** you click reject.

This project measured exactly that, at scale: **5,000 URLs scraped**, a real reject
click performed wherever possible, and trackers re-counted afterwards. The result is a
dataset, a set of market insights, and a machine-learning model that can estimate the
honesty of any site's reject button from a quick pre-consent scan 
-> try it on the
**Compliance Checker** page (sidebar 👈).
"""
)

# ---------------------------------------------------------------- headline numbers
c1, c2, c3, c4 = st.columns(4)

n_sites = len(df)
n_reject_btn = (df["has_reject_button"] == True).mean() * 100
tested = df[df["reject_click_attempted"] == True]
works_pct = (tested["tracker_count_after_reject"] == 0).mean() * 100

c1.metric("Sites scanned(successfull)", f"{n_sites:,}")
c2.metric("Offer a reject button", f"{n_reject_btn:.0f}%")
c3.metric("Reject actually tested", f"{len(tested):,}")
c4.metric("Reject truly works", f"{works_pct:.0f}%", help="Trackers drop to zero after the reject click")

st.divider()

# ---------------------------------------------------------------- market research charts
st.header("📊 What the data says")
st.caption(
    "These insights come from the SQL layer of the project "
    "(MySQL, 5-table schema, recomputed here from the flat dataset."
)

tab1, tab2, tab3 = st.tabs(
    ["CMP market share", "Reject effectiveness by CMP", "Trackers by country"]
)

with tab1:
    st.markdown(
        "**Which consent platforms dominate the market?** "
        "`none` means a custom-built banner with no recognized CMP vendor."
    )
    cmp_share = df["cmp_detected"].value_counts().head(10).reset_index()
    cmp_share.columns = ["CMP vendor", "Sites"]
    fig = px.bar(
        cmp_share, x="Sites", y="CMP vendor", orientation="h",
        color_discrete_sequence=["#0E7C7B"],
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.markdown(
        "**The headline finding: your CMP vendor largely decides whether your reject "
        "button is honest.** % of tested sites where clicking reject dropped trackers "
        "to zero, for vendors with ≥50 tested sites."
    )
    eff = (
        tested.assign(works=tested["tracker_count_after_reject"] == 0)
        .groupby("cmp_detected")
        .agg(n=("works", "size"), pct=("works", "mean"))
        .query("n >= 50")
        .sort_values("pct")
        .reset_index()
    )
    eff["pct"] = eff["pct"] * 100
    fig = px.bar(
        eff, x="pct", y="cmp_detected", orientation="h",
        labels={"pct": "Reject actually works (%)", "cmp_detected": "CMP vendor"},
        color="pct", color_continuous_scale=["#C1443C", "#E8A33D", "#0E7C7B"],
        range_color=[0, 100],
    )
    fig.update_layout(height=420, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Strict definition: “works” = zero trackers after reject. Low scores can also "
        "reflect default configurations as deployed in the wild, not the vendor's tech itself."
    )

with tab3:
    st.markdown("**How many trackers load before any consent, by hosting country?**")
    top_countries = df["country"].value_counts().head(6).index
    by_country = (
        df[df["country"].isin(top_countries)]
        .groupby("country")["tracker_count"]
        .agg(["median", "mean", "count"])
        .sort_values("median", ascending=False)
        .reset_index()
    )
    fig = px.bar(
        by_country, x="country", y="median",
        labels={"median": "Median trackers before consent", "country": ""},
        color_discrete_sequence=["#13315C"],
        hover_data={"mean": ":.1f", "count": True},
    )
    fig.update_layout(height=420)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------- how it works
st.header("⚙️ How the scorer works")
left, right = st.columns(2)
with left:
    st.markdown(
        """
**1. Light pre-consent scan (~10s)** — the site is loaded once, without touching the
banner: trackers, ad networks, cookies, CMP vendor, hosting.

**2. Prediction** — a Random Forest, trained on the 1,583 sites where the real reject
test could run, estimates **P(reject actually works)** from those pre-consent signals
alone. Test ROC-AUC: **0.887**.
"""
    )
with right:
    st.markdown(
        """
**3. Verdict** — the probability is displayed with a color label
(🟢 likely compliant / 🔴 likely not).

**4. Verification (optional)** — a second button runs the *real* differential test:
click reject, reload, re-count trackers — and shows prediction vs. ground truth side
by side.
"""
    )

st.info(
    "**Why predict instead of always measuring?** The real test only completes on ~38% "
    "of sites (missing reject buttons, shadow-DOM banners, bot detection, timeouts) and "
    "takes 30–60s. The expensive measurement was done once, at scale, to build the "
    "training labels, the model then covers every site, in seconds.",
    icon="💡",
)
