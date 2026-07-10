"""
Page 2: Compliance Checker
Enter a URL -> light pre-consent scan -> model predicts P(reject works) -> verdict.
Then an optional "Verify" button runs the real differential test to compare.
"""

import joblib
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Compliance Checker", page_icon="🔍", layout="centered")

MODEL_PATH = "../models/reject_effectiveness_rf.joblib"
COLUMNS_PATH = "../models/model_feature_columns.joblib"

# Demo mode lets you present without live scraping (no Chrome needed, no network risk).
DEMO_MODE = st.sidebar.toggle(
    "🎭 Demo mode (no live scraping)",
    value=False,
    help="Uses a canned example scan instead of Selenium. Perfect for the jury demo "
         "if the venue wifi is unreliable.",
)


@st.cache_resource
def load_model():
    model = joblib.load(MODEL_PATH)
    columns = joblib.load(COLUMNS_PATH)
    return model, columns


def scan_to_feature_row(scan: dict, columns: list) -> pd.DataFrame:
    """Turn a light_scan() result into a one-row DataFrame with EXACTLY the
    training columns, in the training order. Missing dummies default to 0."""
    row = {
        "tracker_count": scan["tracker_count"],
        "ad_network_count": scan["ad_network_count"],
        "non_essential_cookies_before_interaction": scan["non_essential_cookies_before_interaction"],
        "long_lived_cookies_count": scan["long_lived_cookies_count"],
        "has_privacy_policy": int(scan["has_privacy_policy"]),
        "is_hosting": int(scan["is_hosting"]),
        "uses_major_cloud_cdn": int(scan["uses_major_cloud_cdn"]),
    }
    # one-hot the CMP the same way training did (rare vendors were grouped as 'other')
    cmp_col = f"cmp_{scan['cmp_detected']}"
    known_cmp_cols = [c for c in columns if c.startswith("cmp_")]
    row[cmp_col if cmp_col in known_cmp_cols else "cmp_other"] = 1

    X_new = pd.DataFrame([row]).reindex(columns=columns, fill_value=0)
    return X_new


DEMO_SCAN = {
    "url": "https://example-news-site.com",
    "tracker_count": 42,
    "ad_network_count": 12,
    "non_essential_cookies_before_interaction": 31,
    "long_lived_cookies_count": 9,
    "cmp_detected": "onetrust",
    "has_privacy_policy": True,
    "is_hosting": False,
    "uses_major_cloud_cdn": True,
    "has_reject_button": True,
}
DEMO_VERIFY = {"status": "ok", "trackers_before": 42, "trackers_after": 17, "reject_works": False}


# ------------------------------------------------------------------ UI
st.title("🔍 Compliance Checker")
st.markdown(
    "Enter a website URL. The app performs a **light pre-consent scan** (no interaction "
    "with the banner) and the model estimates the probability that the site's reject "
    "button actually stops tracking."
)

url = st.text_input("Website URL", placeholder="https://example.com")
check = st.button("✅ Check compliance", type="primary", disabled=not url)

if check:
    with st.spinner("Scanning the site (pre-consent pass, ~10s)..."):
        if DEMO_MODE:
            scan = dict(DEMO_SCAN, url=url or DEMO_SCAN["url"])
        else:
            from scanner import light_scan
            try:
                scan = light_scan(url)
            except Exception as e:
                st.error(f"Scan failed: {e}")
                st.stop()
    st.session_state["scan"] = scan
    st.session_state.pop("verify", None)  # reset any previous verification

if "scan" in st.session_state:
    scan = st.session_state["scan"]
    model, columns = load_model()
    X_new = scan_to_feature_row(scan, columns)
    proba = float(model.predict_proba(X_new)[0, 1])  # P(reject actually works)

    st.divider()
    st.subheader("Scan results")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trackers (pre-consent)", scan["tracker_count"])
    c2.metric("Ad networks", scan["ad_network_count"])
    c3.metric("Non-essential cookies", scan["non_essential_cookies_before_interaction"])
    c4.metric("CMP detected", scan["cmp_detected"])

    st.subheader("Model verdict")
    st.progress(proba, text=f"P(reject button actually works) = {proba:.0%}")

    # color label — thresholds are a product choice, stated openly
    if proba >= 0.60:
        st.success(f"🟢 **LIKELY COMPLIANT** — sites with this profile honor the reject "
                   f"click about {proba:.0%} of the time.")
    elif proba >= 0.40:
        st.warning(f"🟡 **UNCERTAIN** — {proba:.0%} estimated chance the reject click is "
                   f"honored. Verification recommended.")
    else:
        st.error(f"🔴 **LIKELY NOT COMPLIANT** — sites with this profile honor the reject "
                 f"click only about {proba:.0%} of the time.")

    if not scan.get("has_reject_button", True):
        st.error("⚠️ No reject button was even detected on the banner — that alone is a "
                 "GDPR/CNIL red flag (refusing must be as easy as accepting).")

    # ------------------------------------------------------------- verification
    st.divider()
    st.subheader("Verify with the real test")
    st.caption(
        "This runs the actual differential test: click the reject button, reload, and "
        "re-count trackers. Slower (~30–60s) and it can fail on complex banners — which "
        "is exactly why the model exists."
    )

    if st.button("🔬 Run full verification"):
        with st.spinner("Running the differential test (this takes a while)..."):
            if DEMO_MODE:
                result = DEMO_VERIFY
            else:
                from scanner import full_differential_test
                result = full_differential_test(scan["url"])
        st.session_state["verify"] = result

    if "verify" in st.session_state:
        result = st.session_state["verify"]
        if result["status"] == "ok":
            v1, v2 = st.columns(2)
            v1.metric("Trackers BEFORE reject", result["trackers_before"])
            v2.metric(
                "Trackers AFTER reject",
                result["trackers_after"],
                delta=result["trackers_after"] - result["trackers_before"],
                delta_color="inverse",
            )
            truth = result["reject_works"]
            predicted_works = proba >= 0.5

            if truth:
                st.success("✅ **Ground truth: the reject click stopped all trackers.**")
            else:
                st.error("❌ **Ground truth: trackers are still firing after reject.**")

            if truth == predicted_works:
                st.info(f"🎯 The model's prediction ({proba:.0%}) **agrees** with the real test.")
            else:
                st.warning(
                    f"🤔 The model predicted {proba:.0%} but the real test says otherwise — "
                    "this happens; the model is right ~82% of the time, not 100%."
                )
        elif result["status"] == "no_reject_button":
            st.error("The verification couldn't run: no clickable reject button was found. "
                     "(This is the case for ~61% of sites — the exact gap the model fills.)")
        else:
            st.error(f"Verification failed: {result.get('error', 'unknown error')} — "
                     "complex banners (shadow DOM, bot detection) often resist automation.")

st.sidebar.divider()
st.sidebar.caption(
    "Model: tuned Random Forest · test ROC-AUC 0.887 · trained on 1,583 sites with "
    "ground-truth differential tests. Predictions use pre-consent features only."
)
