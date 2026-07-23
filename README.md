# 🛡️ Website Privacy Compliance Scorer

**One testable measure of cookie-consent compliance: does the reject button actually work?**

This project scores a website against one concrete, measurable proxy for
cookie-consent compliance — whether clicking "reject" actually stops the
tracking — starting from nothing but its URL. That focus is deliberate:
compliance is broad and partly a legal judgment, so the project scopes to the
one dimension it can test objectively and at scale. It combines a web-scraping
pipeline, a MySQL analytics layer, a machine-learning model, a Flask REST API
and a Streamlit app into one end-to-end data product built around GDPR / CNIL
cookie-consent rules.

---

## 📄 Project deliverables

| | |
|---|---|
| 📘 **Full project report (PDF)** | [RNCP_report_privacy_compliance_scorer_Hanane_Mamalik_FV.pdf](docs/RNCP_report_privacy_compliance_scorer_Hanane_Mamalik_FV.pdf) |
| 🎤 **Presentation deck** | [Google Slides](https://docs.google.com/presentation/d/12QFdIPtCiMVJkGl1e7hrauxltaf_sJBR7f-BRo6vK1o/edit?usp=sharing) |

The report covers the full pipeline in 12 sections — use case, planning, the
five data sources, data dictionary, cleaning, EDA, the relational database and
ERD, SQL insights, the REST API, the machine-learning model, and the
conclusions including the GDPR note.

---

## The question

Under GDPR and European Data Regulators guidelines, **refusing cookies must be as easy as
accepting them**. In practice, many sites show a slick "Accept" button and
either hide the reject option or make clicking it do nothing at all.

The core ML question of this project:
> When a site *does* show a reject button, does clicking it actually stop the
> trackers — or is the button just there for show?

---

## Key findings

From the SQL analytics layer (10 insight queries over ~4,100 scanned sites):

- **1 in 3 cookie banners has no reject button at all** — 815 of 2,398 sites
  with a banner (34%) give you no way to refuse.
- **Having a consent platform (CMP) correlates with *more* tracking, not less**
  — sites with a recognized CMP average **17.3 trackers** vs **9.7** without one.
  A CMP shows up on sites already big enough to need one.
- **This pattern holds on a completely independent dataset** — in the BigQuery
  sample, **85%** of sites with a CMP run advertising tech vs **35%** without.
- **Region matters** — 85.6% of European sites have a detectable privacy policy
  vs 68.3% of international ones.
- **Cross-source validation** — the scraper's CMP-detection rate (40%) lands in
  the same ballpark as BigQuery's independent measurement (29%).

---

## The machine-learning model

**Goal:** predict whether clicking "reject" actually drops trackers to zero,
using only signals available *before* any consent interaction.

- **Why a model instead of just measuring?** The real differential test (click
  reject → reload → recount) only completes on ~38% of sites (missing buttons,
  shadow-DOM banners, bot detection, timeouts) and takes 30–60s each. The
  expensive test was run once at scale to build labels; the model then covers
  any site in seconds.
- **No leakage:** the model only sees pre-consent features — tracker counts,
  cookies before consent, CMP vendor — never anything measured after the click.
- **Models compared:** Logistic Regression, Decision Tree, Random Forest,
  XGBoost — each default + GridSearchCV-tuned.
- **Winner: Random Forest (tuned)** — **80.1% accuracy, 0.872 ROC-AUC**, against
  a 56.8% majority-class baseline. Chosen over the slightly-higher-accuracy
  single Decision Tree because the app shows a *probability* (so ranking quality
  / ROC-AUC matters) and a lone tree overfits.
- **Top predictive signals:** ad-network count, total tracker count,
  non-essential cookies before consent, OneTrust as the CMP, long-lived cookies.

---

## Architecture

```
 3 data sources        SQL analytics         ML pipeline           product
┌───────────────┐    ┌──────────────┐    ┌────────────────┐    ┌─────────────┐
│ Tranco (flat) │    │ MySQL        │    │ clean + EDA    │    │ Streamlit   │
│ Selenium scrape│──▶ │ privacy_scorer│──▶ │ feature select │──▶ │ app:        │
│ BigQuery + 2  │    │ 5 tables     │    │ 4 models → RF  │    │ URL → score │
│ APIs          │    │ 10 queries   │    │ (reject model) │    │             │
└───────────────┘    └──────────────┘    └────────────────┘    └─────────────┘
```

---

## Data sources

| Source | Type | Volume | Role |
|---|---|---|---|
| Tranco top-sites list | Flat file | 5,000 URLs | Scrape targets (`urls.csv`) |
| Selenium web scraper | Web scraping | 4,100 sites | Trackers, cookies, banners, consent tests |
| IP geolocation (ip-api) | API | 4,100 | Hosting country / infrastructure |
| Google Safe Browsing | API | 5,000 | Malware / phishing safety check |
| BigQuery / HTTPArchive | Big data | 5,000 sites | Independent cross-validation |
| Disconnect.me | Reference list | 4,443 domains | Known-tracker catalog |

---

## SQL layer

MySQL database `privacy_scorer`, 5 tables:

| Table | Rows | What it holds |
|---|---|---|
| `sites` | 5,000 | One row per site (domain, market country/region) |
| `scans` | 4,100 | One scan result per site (trackers, banner, hosting) |
| `cmps` | 37 | Consent-platform lookup |
| `trackers` | 4,443 | Disconnect.me tracker catalog |
| `bigquery_technologies` | 5,000 | Independent BigQuery tech-detection source |

The 10 insight queries live in [`notebooks/06_sql_insight_queries.sql`](notebooks/06_sql_insight_queries.sql)
(run directly in Workbench) and in the equivalent notebook. Query results are
exported to `clean_data/sql_query_exports/`.

---

## Repository structure

```
├── notebooks/
│   ├── 00_sql_database_setup.ipynb          build the 5-table MySQL database
│   ├── 00a_tracker_list_setup.ipynb         download the Disconnect.me tracker list
│   ├── 00b_tranco_data_cleaning.ipynb       clean the flat file → urls.csv
│   ├── 01_scraper_single_url_prototype.ipynb  single-URL scraper prototype
│   ├── 02_scraper_batch_full_audit.ipynb    the Selenium scraper (batch)
│   ├── 03_api_safe_browsing_enrichment.ipynb  Google Safe Browsing API
│   ├── 03a_api_geolocation_enrichment.ipynb   IP geolocation API
│   ├── 03b_data_cleaning.ipynb              clean the enriched dataset
│   ├── 04_eda_reject_effectiveness.ipynb    EDA + all report figures
│   ├── 05_model_reject_effectiveness.ipynb  train + compare 4 models
│   └── 06_sql_insight_queries.sql           the 10 insight queries (Workbench)
├── api/                                     Flask REST API (see api/README.md)
├── app/                                     Streamlit app (see app/README_APP.md)
├── docs/                                    report PDF + generated figures
├── models/                                  trained model + feature columns
├── clean_data/                              cleaned datasets + query exports
└── raw_data/                                raw scrape + API + reference data
```

---

## How to run

**1. Set up credentials** — create a `.env` file:
```
SQL_PASSWORD=your_mysql_password
DB_NAME=privacy_scorer
SAFE_BROWSING_KEY=your_google_api_key
```

**2. Run the notebooks in order** — `00` → `06`. `00_sql_database_setup.ipynb`
builds the database; re-run it after any new scrape to refresh all tables.

**3. Launch the app:**
```bash
cd app
pip install -r requirements.txt
streamlit run Home.py
```

The app has a **demo mode** (sidebar toggle) that uses a canned example, so a
live demo never depends on venue wifi or on a site behaving as expected.

**4. Launch the REST API** (optional — needs the MySQL database from step 2):
```bash
cd api
pip install -r requirements.txt
python app.py
```
Then open <http://127.0.0.1:5000/>. See [`api/README.md`](api/README.md) for the
endpoints, filters and example responses.

---

## Future work

- **Broaden the scrape** — more small / long-tail / non-EU sites so the model
  generalizes beyond Tranco-ranked popular domains.
- **Add the "reject as visible as accept" signal** — CNIL's actual legal
  standard is about *visual parity*, not just whether a reject button exists.
- **Deploy the app** publicly and wire the full capstone scraper into
  `scanner.py` for production-fidelity feature values.

## External Resources & References

This project was developed using the following external resources, documentation, and open-source references:

### Web Measurement & HTTP Archive

- HTTP Archive documentation and FAQ:  
  https://httparchive.org/faq

### Web Scraping & Selenium Automation

- WebDriver Manager (Selenium driver management):  
  https://github.com/SergeyPirogov/webdriver_manager

- Automating Web Scraping with Selenium and ChromeDriver using GitHub Actions:  
  https://vasantharan.medium.com/automating-web-scraping-with-selenium-and-chromedriver-using-github-actions-5e4a24559dc1

- Selenium + ChromeDriver setup on Ubuntu/Debian:  
  https://github.com/password123456/setup-selenium-with-chrome-driver-on-ubuntu_debian

### Tracker & Advertising Network Identification

- Disconnect tracking protection lists (used for ad/tracker network identification):  
  https://github.com/disconnectme/disconnect

- Tracker services database (`services.json`):  
  https://github.com/disconnectme/disconnect-tracking-protection/blob/master/services.json

### Machine Learning Model Deployment

- Deploying a Machine Learning model using Streamlit:  
  https://medium.com/@adeniyi221/how-to-deploy-your-machine-learning-model-using-streamlit-455b67a69e31

### Python Development

- Python `dataclasses` documentation:  
  https://docs.python.org/3/library/dataclasses.html

- Real Python guide on Data Classes:  
  https://realpython.com/python-data-classes/

### Security & Website Reputation

- Google Safe Browsing API documentation:  
  https://developers.google.com/safe-browsing/reference

---

*Built as a data-analytics capstone. Stack: Python, Selenium, pandas,
scikit-learn, XGBoost, MySQL, Streamlit.*
