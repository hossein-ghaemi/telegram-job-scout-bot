"""
db.py — Thin JSON database layer.

Two files:
  data/users.json     — one record per Telegram user
  data/seen_jobs.json — set of job IDs already sent, per user
"""

import json
import os
from datetime import datetime

USERS_FILE    = os.path.join("data", "users.json")
SEEN_FILE     = os.path.join("data", "seen_jobs.json")

# ── Default search config applied to every new user ──────────────────────────
DEFAULT_CONFIG = {
    "site_name":                  ["linkedin", "indeed"],
    "search_term":                "AI Engineer",
    "google_search_term":         "Internship Software Developer jobs in Germany",
    "location":                   "Germany",
    "results_wanted":             50,
    "country_indeed":             "germany",
    "job_type":                   "fulltime",
    "linkedin_fetch_description": False,
}

# ── Internal helpers ──────────────────────────────────────────────────────────

def _load(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# ── User DB ───────────────────────────────────────────────────────────────────

def get_user(user_id: int) -> dict:
    """Return the user record, creating it if it doesn't exist."""
    db = _load(USERS_FILE)
    uid = str(user_id)
    if uid not in db:
        db[uid] = {
            "telegram_id":       user_id,
            "username":          None,
            "first_name":        None,
            "created_at":        datetime.utcnow().isoformat(),
            "last_active":       datetime.utcnow().isoformat(),
            "total_jobs_found":  0,
            "search_config":     DEFAULT_CONFIG.copy(),
        }
        _save(USERS_FILE, db)
    return db[uid]


def update_user(user_id: int, fields: dict) -> None:
    """Merge `fields` into the user record and touch last_active."""
    db = _load(USERS_FILE)
    uid = str(user_id)
    if uid not in db:
        get_user(user_id)           # creates the record
        db = _load(USERS_FILE)
    db[uid].update(fields)
    db[uid]["last_active"] = datetime.utcnow().isoformat()
    _save(USERS_FILE, db)


def set_search_param(user_id: int, key: str, value) -> None:
    """Update a single key inside the user's search_config."""
    db = _load(USERS_FILE)
    uid = str(user_id)
    if uid not in db:
        get_user(user_id)
        db = _load(USERS_FILE)
    db[uid]["search_config"][key] = value
    db[uid]["last_active"] = datetime.utcnow().isoformat()
    _save(USERS_FILE, db)


def get_search_config(user_id: int) -> dict:
    return get_user(user_id)["search_config"]


def increment_jobs_found(user_id: int, count: int) -> None:
    db = _load(USERS_FILE)
    uid = str(user_id)
    db[uid]["total_jobs_found"] = db[uid].get("total_jobs_found", 0) + count
    _save(USERS_FILE, db)


def all_users() -> dict:
    return _load(USERS_FILE)


# ── Seen-jobs DB ──────────────────────────────────────────────────────────────

def get_seen_ids(user_id: int) -> set:
    db = _load(SEEN_FILE)
    return set(db.get(str(user_id), []))


def mark_seen(user_id: int, job_ids: list) -> None:
    db = _load(SEEN_FILE)
    uid = str(user_id)
    existing = set(db.get(uid, []))
    existing.update(job_ids)
    db[uid] = list(existing)
    _save(SEEN_FILE, db)
