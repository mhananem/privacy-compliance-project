# privacy_scorer REST API

A small Flask API that serves the project's MySQL database over HTTP.
**Two resources, four endpoints.**

## Run it

The database must exist first (built by `notebooks/00_sql_database_setup.ipynb`).
Credentials are read from the `.env` at the project root.

```bash
cd api
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000/> — the home route lists every endpoint.

## Endpoints

| Endpoint | What it returns |
|---|---|
| `/` | List of all endpoints |
| `/api/sites` | List of sites — paginated, filterable |
| `/api/sites/<domain>` | One site, **with its scan nested inside** |
| `/api/scans` | List of scans — paginated, filterable |
| `/api/scans/<scan_id>` | One scan, with its site nested inside |

### Pagination

`?limit=10&offset=20` — `limit` defaults to 20 and is capped at 100.

### Filters

| Endpoint | Filters |
|---|---|
| `/api/sites` | `region`, `country`, `min_trackers` |
| `/api/scans` | `cmp_name`, `has_reject_button` (1/0), `has_cookie_banner` (1/0) |

Filters can be combined. Leaving one out means "don't filter on it".

## Examples

```bash
curl "http://127.0.0.1:5000/api/sites?region=European&min_trackers=20&limit=5"
curl "http://127.0.0.1:5000/api/sites/bbc.co.uk"
curl "http://127.0.0.1:5000/api/scans?cmp_name=onetrust&limit=5"
curl "http://127.0.0.1:5000/api/scans/5"
```

**A list response** — the pagination info sits next to the data:

```json
{
  "total": 440,
  "count": 2,
  "limit": 2,
  "offset": 0,
  "filters": { "region": "European", "country": null, "min_trackers": 20 },
  "data": [ { "domain": "bbc.co.uk", "tracker_count": 25.0, ... } ]
}
```

**A single site** — the scan and CMP name are *nested*, so one request is enough:

```json
{
  "site_id": 5,
  "domain": "bbc.co.uk",
  "country": "UK",
  "region": "European",
  "scan": {
    "scan_id": 3,
    "tracker_count": 25.0,
    "has_reject_button": 1,
    "server_country": "Canada",
    "cmp_name": "none"
  }
}
```

## Errors

Unknown domain or scan id returns **404** with a JSON message:

```json
{ "error": "no site with domain 'nope.com'" }
```

## How the filters work

Rather than building the SQL string differently for each combination of
filters, the query is written once and each filter is skipped when its value
is `None`:

```sql
WHERE (:region IS NULL OR s.region = :region)
```

If `region` isn't in the URL it arrives as `None`, `NULL IS NULL` is true, and
that line matches everything. One fixed query handles all filter combinations.

**Values are always passed separately from the SQL** (`:region` is a bound
parameter, never glued into the string). That is what makes SQL injection
impossible here — requesting `/api/sites/x';DROP TABLE sites;--` just looks up
a site with that silly name and returns 404.

## Files

| File | Purpose |
|---|---|
| `app.py` | The whole API — connection, routes, queries |
| `requirements.txt` | flask, sqlalchemy, pymysql, python-dotenv |
