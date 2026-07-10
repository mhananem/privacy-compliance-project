-- ============================================================================
-- My 10 SQL insight queries
-- ============================================================================
-- These run against my privacy_scorer database (built in 00_sql_database_setup.ipynb).
-- I ended up with 5 tables: sites, scans, cmps, trackers, and bigquery_technologies.
--
-- I ordered these like I'd tell the story out loud: I start with the biggest,
-- simplest question about the whole dataset, then I go narrower and narrower
-- until I'm looking at individual sites by name, and I finish with the queries
-- that check whether I can actually trust my own numbers.
--
-- USE privacy_scorer;   -- uncomment this if Workbench isn't already pointed
--                        -- at the right schema
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Query 1 — how many sites show a cookie banner but give me no way to refuse?
-- This is basically my headline number. A banner that only lets you accept
-- isn't real consent, so I wanted this count first before anything else.
-- I save this one as: reject_button_compliance.csv
-- ----------------------------------------------------------------------------
SELECT
    has_cookie_banner,
    has_reject_button,
    COUNT(*) AS num_sites
FROM scans
WHERE has_cookie_banner = TRUE
GROUP BY has_cookie_banner, has_reject_button;


-- ----------------------------------------------------------------------------
-- Query 2 — which consent tools (CMPs) show up the most?
-- Just counting how many sites use each vendor, so I know who the big
-- players are before I ask any harder questions about them.
-- I save this one as: cmp_popularity.csv
-- ----------------------------------------------------------------------------
SELECT
    c.cmp_name,
    COUNT(*) AS num_sites
FROM scans sc
JOIN cmps c ON sc.cmp_id = c.cmp_id
GROUP BY c.cmp_name
ORDER BY num_sites DESC;


-- ----------------------------------------------------------------------------
-- Query 3 — do sites with a real CMP actually have fewer trackers?
-- I expected "yes". I compare the average tracker count for sites that use a
-- recognized CMP against sites that don't, and it's not what I expected --
-- more on that in my takeaways at the bottom.
-- I save this one as: cmp_vs_tracker_comparison.csv
-- ----------------------------------------------------------------------------
SELECT
    CASE
        WHEN c.cmp_name = 'none' OR c.cmp_name IS NULL THEN 'No recognized CMP'
        ELSE 'Has recognized CMP'
    END AS cmp_status,
    COUNT(*) AS num_sites,
    ROUND(AVG(sc.tracker_count), 1) AS avg_trackers,
    ROUND(AVG(sc.ad_network_count), 1) AS avg_ad_networks
FROM scans sc
LEFT JOIN cmps c ON sc.cmp_id = c.cmp_id
GROUP BY cmp_status;


-- ----------------------------------------------------------------------------
-- Query 4 — do European sites bother with a privacy policy more than others?
-- I split my sites into European vs International and check what % of each
-- group actually has a privacy policy I could detect.
-- I save this one as: privacy_policy_by_region.csv
-- ----------------------------------------------------------------------------
SELECT
    s.region,
    COUNT(*) AS num_sites,
    SUM(CASE WHEN sc.has_privacy_policy = TRUE THEN 1 ELSE 0 END) AS sites_with_policy,
    ROUND(100.0 * SUM(CASE WHEN sc.has_privacy_policy = TRUE THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_with_policy
FROM sites s
JOIN scans sc ON s.site_id = sc.site_id
GROUP BY s.region;


-- ----------------------------------------------------------------------------
-- Query 5 — which countries load the most trackers on average?
-- Only using rows where I actually know the country (I dropped 'Unknown' --
-- that's mostly .com/.org/.net sites where I can't guess a country from the
-- domain name, see my notes on that if I need a reminder).
-- I save this one as: tracker_count_by_country.csv
-- ----------------------------------------------------------------------------
SELECT
    s.country,
    COUNT(*) AS num_sites,
    ROUND(AVG(sc.tracker_count), 1) AS avg_trackers
FROM sites s
JOIN scans sc ON s.site_id = sc.site_id
WHERE s.country != 'Unknown'
GROUP BY s.country
ORDER BY avg_trackers DESC;


-- ----------------------------------------------------------------------------
-- Query 6 — does WHERE a site is hosted change how many trackers it runs?
-- is_hosting tells me if the site's server sits on a big cloud/hosting
-- provider instead of the company's own infrastructure. I also throw in a
-- quick safety check here: did Google Safe Browsing flag anything as unsafe?
-- I save this one as: hosting_vs_trackers.csv
-- ----------------------------------------------------------------------------
SELECT
    is_hosting,
    COUNT(*) AS num_sites,
    ROUND(AVG(tracker_count), 1) AS avg_trackers,
    SUM(CASE WHEN flagged_unsafe THEN 1 ELSE 0 END) AS num_flagged_unsafe
FROM scans
GROUP BY is_hosting;


-- ----------------------------------------------------------------------------
-- Query 7 — who are my worst 10 offenders, by name?
-- This is where I stop looking at averages and actually point at specific
-- sites. I use hosting_country here (from the geolocation API) instead of my
-- market-guess country, because it's a real measurement, not a guess from
-- the domain extension. Just remember: hosting_country tells me where the
-- SERVER sits, not necessarily where the company is actually based.
-- I save this one as: top10_highest_tracker_sites.csv
-- ----------------------------------------------------------------------------
SELECT
    s.domain AS domain_name,
    sc.server_country AS hosting_country,
    sc.tracker_count,
    sc.ad_network_count,
    c.cmp_name
FROM sites s
JOIN scans sc ON s.site_id = sc.site_id
LEFT JOIN cmps c ON sc.cmp_id = c.cmp_id
ORDER BY sc.tracker_count DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Query 8 — how big is the tracker "catalog" I'm even working with?
-- This one's a bit different from the rest -- I'm not looking at my scanned
-- sites at all here, just counting how many known trackers exist in each
-- category inside the Disconnect.me list I'm using as my reference. It's
-- context for how big the tracking ecosystem is, not a finding about my data.
-- I save this one as: tracker_categories_overview.csv
-- ----------------------------------------------------------------------------
SELECT
    category,
    COUNT(*) AS num_known_trackers
FROM trackers
GROUP BY category
ORDER BY num_known_trackers DESC;


-- ----------------------------------------------------------------------------
-- Query 9 — can I trust my own CMP detection? (part 1, my own scraper)
-- I want to check my scraper's CMP detection rate against BigQuery's,
-- since they're two completely independent ways of measuring the same
-- thing. The BigQuery side isn't loaded as a table I can join here (it's a
-- separate ML-training source), so I just note the number I already know:
-- BigQuery came out to 5000 scans, 1437 with a CMP detected, so 28.74%.
-- I compare that by hand against whatever my own scraper says below.
-- I save this one as: scraper_cmp_detection_rate.csv
-- ----------------------------------------------------------------------------
SELECT
    COUNT(*) AS total_scans,
    SUM(CASE WHEN c.cmp_name != 'none' THEN 1 ELSE 0 END) AS scans_with_cmp,
    ROUND(100.0 * SUM(CASE WHEN c.cmp_name != 'none' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_with_cmp
FROM scans sc
JOIN cmps c ON sc.cmp_id = c.cmp_id;


-- ----------------------------------------------------------------------------
-- Query 10 — can I trust my own CMP detection? (part 2, checking Query 3 again)
-- Same basic question as Query 3 -- does having a CMP actually mean less
-- tracking? -- but this time I run it against BigQuery's own tech-detection
-- columns instead of my scraper's numbers. If I get the same answer from a
-- totally different source, that tells me it's a real pattern and not just
-- something weird about how my own scraper counts trackers.
-- I save this one as: cmp_vs_tech_bigquery.csv
-- ----------------------------------------------------------------------------
SELECT
    CASE WHEN has_cmp = 1 THEN 'Has CMP' ELSE 'No CMP' END AS cmp_status,
    COUNT(*) AS num_sites,
    ROUND(100.0 * SUM(has_advertising) / COUNT(*), 1) AS pct_with_advertising,
    ROUND(100.0 * SUM(has_analytics) / COUNT(*), 1) AS pct_with_analytics,
    ROUND(AVG(tech_count), 1) AS avg_tech_count
FROM bigquery_technologies
GROUP BY cmp_status;


-- ============================================================================
-- What I actually took away from all this
-- ============================================================================
-- - Most sites still don't use a real CMP. Only around 40% of my own
--   scraped sites do, and BigQuery says about 29% -- close enough that I
--   trust both numbers.
-- - Having a CMP does NOT mean fewer trackers -- it's actually the
--   opposite (Query 3). My best guess: a CMP shows up on sites that already
--   run enough third-party tools to need one in the first place. It's a
--   "these two things happen together" signal, not "CMPs cause less tracking".
-- - The biggest compliance gap I found is sites with a cookie banner but no
--   real reject option (Query 1). That's exactly what
--   05_model_reject_effectiveness.ipynb is trying to predict.
-- - Sites hosted on big cloud/hosting providers run more trackers on
--   average than self-hosted sites (Query 6) -- probably because the
--   bigger, more commercial sites are the ones using cloud hosting anyway.
-- - Not a single site got flagged as unsafe by Google Safe Browsing
--   (Query 6). Makes sense, not a red flag -- my whole sample comes from
--   Tranco's list of already-popular, legit sites.
-- - The "CMP doesn't reduce tracking" pattern shows up again in a totally
--   different dataset (Query 10): 85.2% of BigQuery sites with a CMP run
--   advertising tech, vs. only 34.5% of sites without one. Same story,
--   completely independent source -- that's what makes me trust it.
-- ============================================================================
