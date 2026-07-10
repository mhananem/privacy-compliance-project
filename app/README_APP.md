# Streamlit app — how to run

## Folder layout expected

```
project-root/
├── clean_data/
│   └── dataset_completed.csv
├── notebooks/
│   ├── reject_effectiveness_rf.joblib      <- created by the modeling notebook
│   └── model_feature_columns.joblib        <- created by the modeling notebook
└── app/
    ├── Home.py                             <- page 1 (intro + market research)
    ├── scanner.py                          <- Selenium scraping layer
    ├── requirements.txt
    └── pages/
        └── 2_🔍_Compliance_Checker.py      <- page 2 (the scorer)
```

If your folders are named differently, adjust the three paths at the top of
Home.py (`DATA_PATH`) and the checker page (`MODEL_PATH`, `COLUMNS_PATH`).

## Run it

```bash
cd app
pip install -r requirements.txt
streamlit run Home.py
```

Streamlit picks up the `pages/` folder automatically — the sidebar will show
both pages.

## Live scraping requirements (page 2 only)

The "Check compliance" and "Run full verification" buttons use Selenium with
headless Chrome. You need Chrome (or Chromium) installed; Selenium 4.6+
downloads the matching driver automatically.

**🎭 Demo mode:** toggle it on in the sidebar of the Compliance Checker to
present without any live scraping — it uses a canned ad-heavy example (42
trackers, OneTrust) so the demo can never be broken by venue wifi or a
capricious website. Highly recommended as a backup during the jury demo.

## Plugging in your capstone scraper

`scanner.py` contains simplified, self-contained versions of the scans (short
tracker lists, basic CMP signatures, no shadow-DOM traversal, no ip-api
enrichment). For feature values identical to your training data, replace the
bodies of `light_scan()` and `full_differential_test()` with calls to your
capstone scraper functions — the app only depends on the returned dict keys.

Two features are currently defaulted to False in `light_scan()` because they
need the ip-api.com / org enrichment from your pipeline: `is_hosting` and
`uses_major_cloud_cdn`. Wire in your enrichment for full fidelity (their
feature importance is low, so predictions are reasonable even without).
