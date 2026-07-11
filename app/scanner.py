"""
scanner.py — the scraping layer for the Streamlit app.

Two functions:
  light_scan(url)             -> pre-consent features only (fast, ~10s, works on any site)
  full_differential_test(url) -> the real test: click reject, reload, re-count (slow, can fail)

⚠️ IMPORTANT: these are simplified, self-contained versions using the same techniques
as the capstone scraper (Selenium headless Chrome, performance-log tracker counting,
multilingual reject-button matching). If your capstone scraper has richer logic
(shadow DOM traversal, better CMP signatures), import and call YOUR functions here
instead — the app only cares about the returned dict keys.
"""

import json
import time
from urllib.parse import urlparse
from selenium.webdriver.chrome.service import Service

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import os
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# ------------------------------------------------------------------ constants
# Known tracker / ad-network domains (short illustrative lists — replace with the
# full lists used in the capstone scraper for identical feature values).
TRACKER_DOMAINS = [
    "google-analytics.com", "googletagmanager.com", "doubleclick.net",
    "facebook.net", "facebook.com/tr", "hotjar.com", "mouseflow.com",
    "criteo.com", "criteo.net", "adnxs.com", "amazon-adsystem.com",
    "scorecardresearch.com", "quantserve.com", "outbrain.com", "taboola.com",
    "adsrvr.org", "rubiconproject.com", "pubmatic.com", "openx.net",
    "bing.com/bat", "clarity.ms", "yandex.ru/metrika", "matomo", "piwik",
    "segment.com", "segment.io", "mixpanel.com", "amplitude.com",
    "chartbeat.com", "newrelic.com", "krxd.net", "bluekai.com", "demdex.net",
    "omtrdc.net", "everesttech.net", "tiktok.com/i18n", "snapchat.com/tr",
]
AD_NETWORK_DOMAINS = [
    "doubleclick.net", "adnxs.com", "amazon-adsystem.com", "criteo.com",
    "criteo.net", "rubiconproject.com", "pubmatic.com", "openx.net",
    "adsrvr.org", "taboola.com", "outbrain.com", "smartadserver.com",
    "adform.net", "yieldlab.net", "improvedigital.com", "indexexchange.com",
    "casalemedia.com", "33across.com", "sharethrough.com", "teads.tv",
]

# CMP vendor signatures: substring to look for in page source / script srcs
CMP_SIGNATURES = {
    "onetrust": ["onetrust", "optanon"],
    "didomi": ["didomi"],
    "cookiebot": ["cookiebot"],
    "usercentrics": ["usercentrics"],
    "sourcepoint": ["sourcepoint", "sp-cc"],
    "trustarc": ["trustarc", "truste"],
    "iubenda": ["iubenda"],
    "cookieyes": ["cookieyes"],
    "cookie notice": ["cookie-notice", "cookie_notice"],
    "trustcommander": ["trustcommander", "tagcommander"],
    "quantcast": ["quantcast"],
    "axeptio": ["axeptio"],
}

# Multilingual reject-button keywords (same normalization idea as the capstone scraper)
REJECT_KEYWORDS = [
    "reject", "reject all", "decline", "refuse", "deny", "disagree",
    "tout refuser", "refuser", "continuer sans accepter",
    "alle ablehnen", "ablehnen",
    "rechazar", "rifiuta", "weigeren", "avvisa", "odmítnout",
]

MAJOR_CLOUD_CDN = ["amazon", "google", "fastly", "akamai", "cloudflare", "microsoft"]


# ------------------------------------------------------------------ browser setup



def _make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    if os.path.exists("/usr/bin/chromium"):
        # Streamlit Cloud: apt-installed chromium (from packages.txt)
        opts.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
    else:
        # Local machine: same webdriver-manager approach as your capstone notebooks
        service = Service(ChromeDriverManager().install())

    return webdriver.Chrome(service=service, options=opts)


def _requested_urls(driver):
    """All network request URLs seen so far, from the Chrome performance log."""
    urls = []
    for entry in driver.get_log("performance"):
        try:
            msg = json.loads(entry["message"])["message"]
            if msg.get("method") == "Network.requestWillBeSent":
                urls.append(msg["params"]["request"]["url"])
        except (KeyError, json.JSONDecodeError):
            continue
    return urls


def _count_trackers(urls):
    trackers = {d for d in TRACKER_DOMAINS for u in urls if d in u}
    ad_networks = {d for d in AD_NETWORK_DOMAINS for u in urls if d in u}
    return len(trackers), len(ad_networks)


def _detect_cmp(page_source):
    src = page_source.lower()
    for vendor, sigs in CMP_SIGNATURES.items():
        if any(s in src for s in sigs):
            return vendor
    return "none"


def _cookie_stats(driver):
    cookies = driver.get_cookies()
    total = len(cookies)
    now = time.time()
    long_lived = sum(
        1 for c in cookies if c.get("expiry") and c["expiry"] - now > 180 * 24 * 3600
    )
    # heuristic: cookies from third-party/tracking-looking names count as non-essential.
    # The capstone scraper has a proper classification — plug it in here for parity.
    essential_hints = ("session", "csrf", "xsrf", "auth", "consent", "cookie")
    non_essential = sum(
        1 for c in cookies if not any(h in c.get("name", "").lower() for h in essential_hints)
    )
    return total, non_essential, long_lived


def _find_reject_button(driver):
    """Look for a visible element whose text matches a reject keyword."""
    candidates = driver.find_elements(By.XPATH, "//button | //a | //*[@role='button']")
    for el in candidates:
        try:
            text = (el.text or "").strip().lower()
            if not text or not el.is_displayed():
                continue
            if any(k in text for k in REJECT_KEYWORDS):
                return el
        except Exception:
            continue
    return None


# ------------------------------------------------------------------ public API
def light_scan(url: str) -> dict:
    """Pre-consent scan only. Returns the exact features the model needs."""
    if not url.startswith("http"):
        url = "https://" + url

    driver = _make_driver()
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(5)  # let trackers fire

        urls = _requested_urls(driver)
        tracker_count, ad_network_count = _count_trackers(urls)
        total_cookies, non_essential, long_lived = _cookie_stats(driver)
        cmp_vendor = _detect_cmp(driver.page_source)
        has_privacy_policy = any(
            k in driver.page_source.lower()
            for k in ["privacy policy", "politique de confidentialit", "datenschutz"]
        )
        reject_btn = _find_reject_button(driver)

        return {
            "url": url,
            "tracker_count": tracker_count,
            "ad_network_count": ad_network_count,
            "non_essential_cookies_before_interaction": non_essential,
            "long_lived_cookies_count": long_lived,
            "cmp_detected": cmp_vendor,
            "has_privacy_policy": has_privacy_policy,
            "is_hosting": False,          # requires an org/ASN lookup — see note below
            "uses_major_cloud_cdn": False, # idem; plug in the ip-api.com enrichment from the capstone
            "has_reject_button": reject_btn is not None,
        }
    finally:
        driver.quit()


def full_differential_test(url: str) -> dict:
    """The real test: measure, click reject, reload, re-measure."""
    if not url.startswith("http"):
        url = "https://" + url

    driver = _make_driver()
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(5)

        before_urls = _requested_urls(driver)
        trackers_before, _ = _count_trackers(before_urls)

        reject_btn = _find_reject_button(driver)
        if reject_btn is None:
            return {"status": "no_reject_button", "trackers_before": trackers_before}

        try:
            reject_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", reject_btn)
        time.sleep(2)

        # reload and re-count with the refusal stored
        driver.get_log("performance")  # flush the log
        driver.get(url)
        time.sleep(5)
        after_urls = _requested_urls(driver)
        trackers_after, _ = _count_trackers(after_urls)

        return {
            "status": "ok",
            "trackers_before": trackers_before,
            "trackers_after": trackers_after,
            "reject_works": trackers_after == 0,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        driver.quit()
