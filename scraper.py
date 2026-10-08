"""
scraper.py — Wraps python-jobspy and filters out already-seen jobs.
"""

import html
import logging
import math
from jobspy import scrape_jobs
import db

logger = logging.getLogger(__name__)


def _clean(value):
    """pandas fills missing cells with NaN (truthy!) — normalise to None."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def job_key(job: dict) -> str:
    """Stable ID used for duplicate filtering (falls back to the job URL)."""
    return str(_clean(job.get("id")) or _clean(job.get("job_url")) or "")


def fetch_new_jobs(user_id: int) -> list[dict]:
    """
    Scrape jobs using the user's stored config.
    Returns only jobs NOT previously sent to this user.
    Does NOT mark them as seen — call db.mark_seen() after each job is delivered.
    Raises on scrape failure so callers can tell errors apart from "no new jobs".
    """
    config = db.get_search_config(user_id)
    logger.info("Scraping for user %s | config: %s", user_id, config)

    sites = config.get("site_name", ["linkedin", "indeed"])
    # jobspy applies results_wanted per site — split the total across sites
    total = int(config.get("results_wanted", 50))
    per_site = max(1, math.ceil(total / max(1, len(sites))))

    df = scrape_jobs(
        site_name=sites,
        search_term=config.get("search_term", "Software Engineer"),
        google_search_term=config.get("google_search_term") or None,
        location=config.get("location", "Germany"),
        results_wanted=per_site,
        hours_old=24,
        country_indeed=config.get("country_indeed", "germany"),
        job_type=config.get("job_type") or None,
        linkedin_fetch_description=bool(config.get("linkedin_fetch_description", False)),
        verbose=0,
    )

    if df is None or df.empty:
        logger.info("No jobs returned from scraper.")
        return []

    # ── Deduplicate against already-seen job IDs (and within this batch) ──────
    seen = db.get_seen_ids(user_id)
    new_jobs = []
    for job in df.to_dict(orient="records"):
        key = job_key(job)
        if key and key not in seen:
            seen.add(key)
            new_jobs.append(job)

    logger.info("Returning %d new jobs for user %s.", len(new_jobs), user_id)
    return new_jobs


def format_job(job: dict) -> str:
    """Build a clean Telegram HTML message for one job."""
    def text(key, default="N/A"):
        return html.escape(str(_clean(job.get(key)) or default))

    title    = text("title")
    company  = text("company")
    location = text("location")
    date     = text("date_posted")[:10]
    jtype    = text("job_type", "").capitalize() or "N/A"
    site     = text("site", "").capitalize()
    url      = _clean(job.get("job_url_direct")) or _clean(job.get("job_url")) or ""
    remote   = _clean(job.get("is_remote"))
    level    = text("job_level", "")

    badges = "  ".join(filter(None, [
        "🌐 Remote" if remote else "",
        f"📊 {level}" if level else "",
    ]))

    lines = [
        f"💼 <b>{title}</b>",
        f"🏢 {company}",
        f"📍 {location}",
        f"🗓 {date}  •  🕐 {jtype}",
    ]
    if badges:
        lines.append(badges)
    if site:
        lines.append(f"🔍 via {site}")
    if url:
        lines.append(f'🔗 <a href="{html.escape(str(url))}">Apply here</a>')

    return "\n".join(lines)
