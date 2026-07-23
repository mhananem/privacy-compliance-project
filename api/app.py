"""
privacy_scorer REST API  -  Flask + MySQL

Two resources, four endpoints:

    GET /api/sites             list of sites   (paginated + filters)
    GET /api/sites/<domain>    one site        (its scan nested inside)
    GET /api/scans             list of scans   (paginated + filters)
    GET /api/scans/<scan_id>   one scan        (its site nested inside)

Run:  cd api  ->  python app.py  ->  http://127.0.0.1:5000
"""
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

engine = create_engine(
    f"mysql+pymysql://root:{quote_plus(os.getenv('SQL_PASSWORD'))}"
    f"@localhost/{os.getenv('DB_NAME')}"
)

app = Flask(__name__)


# --------------------------------------------------------------------------
# Helper: run a list-style query and return it with its pagination info
# --------------------------------------------------------------------------
def paginated(select_sql, count_sql, filters):
    """Both list endpoints do the same 3 things, so they share this."""
    limit = min(request.args.get("limit", 20, type=int), 100)
    offset = request.args.get("offset", 0, type=int)

    with engine.connect() as conn:
        total = conn.execute(text(count_sql), filters).scalar()
        rows = conn.execute(
            text(select_sql), {**filters, "limit": limit, "offset": offset}
        ).mappings()
        data = [dict(row) for row in rows]

    return jsonify({
        "total": total,        # rows matching the filters
        "count": len(data),    # rows in this response
        "limit": limit,
        "offset": offset,
        "filters": filters,
        "data": data,
    })


# --------------------------------------------------------------------------
# Home - lists what the API can do
# --------------------------------------------------------------------------
@app.route("/")
def home():
    return jsonify({
        "api": "privacy_scorer",
        "endpoints": ["/api/sites", "/api/sites/<domain>",
                      "/api/scans", "/api/scans/<scan_id>"],
        "examples": ["/api/sites?region=European&min_trackers=20&limit=5",
                     "/api/sites/bbc.co.uk",
                     "/api/scans?cmp_name=onetrust&limit=5",
                     "/api/scans/5"],
    })


# --------------------------------------------------------------------------
# SITES
# --------------------------------------------------------------------------
# Written once, used by both the list query and the COUNT query below.
# A filter left out of the URL arrives as None, and "NULL IS NULL" is true,
# so that line then matches every row -> one query handles every combination.
SITES_WHERE = """
    FROM sites s
    LEFT JOIN scans sc ON s.site_id = sc.site_id
    WHERE (:region       IS NULL OR s.region = :region)
      AND (:country      IS NULL OR s.country = :country)
      AND (:min_trackers IS NULL OR sc.tracker_count >= :min_trackers)
"""


@app.route("/api/sites")
def get_sites():
    filters = {
        "region": request.args.get("region"),                   # European / International
        "country": request.args.get("country"),                 # UK, FR, DE ...
        "min_trackers": request.args.get("min_trackers", type=int),
    }
    return paginated(
        f"""SELECT s.site_id, s.domain, s.country, s.region, sc.tracker_count,
                   sc.has_cookie_banner, sc.has_reject_button
            {SITES_WHERE}
            ORDER BY s.site_id
            LIMIT :limit OFFSET :offset""",
        f"SELECT COUNT(*) {SITES_WHERE}",
        filters,
    )


@app.route("/api/sites/<domain>")
def get_one_site(domain):
    with engine.connect() as conn:
        site = conn.execute(
            text("SELECT site_id, domain, country, region FROM sites WHERE domain = :domain"),
            {"domain": domain},
        ).mappings().first()

        if site is None:
            return jsonify({"error": f"no site with domain '{domain}'"}), 404

        scan = conn.execute(
            text("""SELECT sc.scan_id, sc.tracker_count, sc.ad_network_count,
                           sc.has_cookie_banner, sc.has_accept_button,
                           sc.has_reject_button, sc.has_privacy_policy,
                           sc.server_country, c.cmp_name
                    FROM scans sc
                    LEFT JOIN cmps c ON sc.cmp_id = c.cmp_id
                    WHERE sc.site_id = :site_id"""),
            {"site_id": site["site_id"]},
        ).mappings().first()

    site = dict(site)
    site["scan"] = dict(scan) if scan else None   # <- the nested part
    return jsonify(site)


# --------------------------------------------------------------------------
# SCANS
# --------------------------------------------------------------------------
SCANS_WHERE = """
    FROM scans sc
    LEFT JOIN sites s ON sc.site_id = s.site_id
    LEFT JOIN cmps  c ON sc.cmp_id = c.cmp_id
    WHERE (:cmp_name          IS NULL OR c.cmp_name = :cmp_name)
      AND (:has_reject_button IS NULL OR sc.has_reject_button = :has_reject_button)
      AND (:has_cookie_banner IS NULL OR sc.has_cookie_banner = :has_cookie_banner)
"""


@app.route("/api/scans")
def get_scans():
    filters = {
        "cmp_name": request.args.get("cmp_name"),                        # onetrust, didomi ...
        "has_reject_button": request.args.get("has_reject_button", type=int),   # 1 or 0
        "has_cookie_banner": request.args.get("has_cookie_banner", type=int),   # 1 or 0
    }
    return paginated(
        f"""SELECT sc.scan_id, sc.site_id, s.domain, sc.tracker_count,
                   sc.ad_network_count, sc.has_cookie_banner,
                   sc.has_reject_button, c.cmp_name
            {SCANS_WHERE}
            ORDER BY sc.scan_id
            LIMIT :limit OFFSET :offset""",
        f"SELECT COUNT(*) {SCANS_WHERE}",
        filters,
    )


@app.route("/api/scans/<int:scan_id>")
def get_one_scan(scan_id):
    with engine.connect() as conn:
        scan = conn.execute(
            text("""SELECT sc.scan_id, sc.site_id, s.domain,
                           s.country AS market_country, s.region AS market_region,
                           sc.tracker_count, sc.ad_network_count,
                           sc.has_cookie_banner, sc.has_accept_button,
                           sc.has_reject_button, sc.has_privacy_policy,
                           sc.is_hosting, sc.flagged_unsafe,
                           sc.server_country, sc.server_region, c.cmp_name
                    FROM scans sc
                    LEFT JOIN sites s ON sc.site_id = s.site_id
                    LEFT JOIN cmps  c ON sc.cmp_id = c.cmp_id
                    WHERE sc.scan_id = :scan_id"""),
            {"scan_id": scan_id},
        ).mappings().first()

    if scan is None:
        return jsonify({"error": f"no scan with id {scan_id}"}), 404
    return jsonify(dict(scan))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
