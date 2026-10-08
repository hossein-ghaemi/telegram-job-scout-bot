# Telegram Job Scout Bot

Scrapes LinkedIn & Indeed and sends only **new** jobs to your Telegram.

## Use the bot

The bot is live on Telegram: **[@jam_job_finder_bot](https://t.me/jam_job_finder_bot)**

1. Open [t.me/jam_job_finder_bot](https://t.me/jam_job_finder_bot) (or search `@jam_job_finder_bot` in Telegram)
2. Press **Start** (or send `/start`)
3. Tap **⚙️ Configure Search** to set your job title, location, job type, etc.
4. Tap **▶️ Run Now** (or send `/run`) — you'll receive every job posted in the last 24 hours that you haven't seen yet

No installation needed. The sections below are only for running your own copy.

## Project Structure

```
telegram-job-scout-bot/
├── bot.py          # Main bot — commands, conversation handlers, button router
├── scraper.py      # jobspy wrapper + duplicate filter + message formatter
├── db.py           # JSON database layer (users + seen jobs)
├── requirements.txt
├── .env.example    # Copy to .env and fill in your token
├── job_bot.service # systemd unit for server deployment
├── data/
│   ├── users.json      # User records & per-user search configs
│   └── seen_jobs.json  # Job IDs already sent per user
└── logs/
    └── bot.log
```

## Setup

### 1. Get a Bot Token
- Open Telegram → search **@BotFather**
- Send `/newbot`, follow prompts, copy the token

### 2. Install dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
nano .env          # paste your TELEGRAM_BOT_TOKEN
```

### 4. Run locally
```bash
python bot.py
```

### 5. Run as a systemd service (server)
```bash
# Edit job_bot.service — replace YOUR_LINUX_USER and paths
sudo cp job_bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable job_bot
sudo systemctl start job_bot
sudo systemctl status job_bot

# View logs
sudo journalctl -u job_bot -f
```

## Bot Commands

| Command    | Description                          |
|------------|--------------------------------------|
| `/start`   | Welcome screen + main menu buttons   |
| `/config`  | Configure search parameters wizard   |
| `/run`     | Scrape now and receive new jobs      |
| `/status`  | Show your config and stats           |
| `/help`    | Usage guide                          |

## Search Parameters

| Parameter                  | Type    | Example                                      |
|----------------------------|---------|----------------------------------------------|
| `site_name`                | list    | `linkedin, indeed`                           |
| `search_term`              | string  | `AI Engineer`                                |
| `google_search_term`       | string  | `Internship Data Science jobs Germany`       |
| `location`                 | string  | `Berlin` or `Germany`                        |
| `results_wanted`           | number  | `50` (total, split across sites)                                       |
| `country_indeed`           | string  | `germany`                                    |
| `job_type`                 | string  | `fulltime` / `parttime` / `internship`       |
| `linkedin_fetch_description` | bool  | `yes` / `no`                                 |

## Auto-scheduling (cron alternative)

Add to crontab to run every 6 hours:
```
0 */6 * * * cd /path/to/telegram-job-scout-bot && /path/to/venv/bin/python -c "
import asyncio
from telegram import Bot
from dotenv import load_dotenv
import os, db, scraper

load_dotenv()
bot = Bot(os.getenv('TELEGRAM_BOT_TOKEN'))

async def run():
    for uid, user in db.all_users().items():
        jobs = scraper.fetch_new_jobs(int(uid))
        for job in jobs:
            await bot.send_message(chat_id=int(uid), text=scraper.format_job(job), parse_mode='HTML', disable_web_page_preview=True)
            db.mark_seen(int(uid), [scraper.job_key(job)])

asyncio.run(run())
"
```
