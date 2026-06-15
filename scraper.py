"""
scraper.py — Wraps python-jobspy and filters out already-seen jobs.
"""

import logging
from jobspy import scrape_jobs
import db

logger = logging.getLogger(__name__)


def fetch_new_jobs(user_id: int) -> list[dict]:
    """
    Scrape jobs using the user's stored config.
    Returns only jobs NOT previously sent to this user.
    """
    config = db.get_search_config(user_id)
    logger.info("Scraping for user %s | config: %s", user_id, config)

    try:
        df = scrape_jobs(
            site_name=config.get("site_name", ["linkedin", "indeed"]),
            search_term=config.get("search_term", "Software Engineer"),
            google_search_term=config.get("google_search_term") or None,
            location=config.get("location", "Germany"),
            results_wanted=int(config.get("results_wanted", 50)),
            hours_old=24,
            country_indeed=config.get("country_indeed", "germany"),
            job_type=config.get("job_type") or None,
            linkedin_fetch_description=bool(config.get("linkedin_fetch_description", False)),
            verbose=0,
        )
    except Exception as e:
        logger.error("jobspy scrape failed: %s", e)
        return []

    if df is None or df.empty:
        logger.info("No jobs returned from scraper.")
        return []

    # ── Deduplicate against already-seen job IDs ──────────────────────────────
    seen = db.get_seen_ids(user_id)
    jobs = df.to_dict(orient="records")
    new_jobs = [j for j in jobs if str(j.get("id", "")) not in seen]

    if not new_jobs:
        logger.info("All %d jobs already seen by user %s.", len(jobs), user_id)
        return []

    new_ids = [str(j.get("id", "")) for j in new_jobs]
    db.mark_seen(user_id, new_ids)
    db.increment_jobs_found(user_id, len(new_jobs))

    logger.info("Returning %d new jobs for user %s.", len(new_jobs), user_id)
    return new_jobs


def format_job(job: dict) -> str:
    """Build a clean Telegram HTML message for one job."""
    title    = job.get("title")    or "N/A"
    company  = job.get("company")  or "N/A"
    location = job.get("location") or "N/A"
    date     = str(job.get("date_posted") or "N/A")[:10]
    jtype    = str(job.get("job_type")  or "N/A").capitalize()
    site     = str(job.get("site")     or "").capitalize()
    url      = job.get("job_url_direct") or job.get("job_url") or ""
    remote   = job.get("is_remote")
    level    = job.get("job_level") or ""

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
        lines.append(f'🔗 Apply here:'+url)

    return "\n".join(lines)