# Ticket Booking Notifier — Avengers: Doomsday, Chennai

Watches **District** (district.in) 24×7 for **English, 3D / premium (Infinity Vision, IMAX, 4DX), morning (before 12 PM)**
shows of *Avengers: Doomsday* in Chennai, 17–21 Dec 2026, and pings you on **Telegram** with a direct booking link when:

- 🎬 a theatre **opens bookings for the first time**,
- 🆕 a **new show** is added, or
- 💺 **seats free up** in a show that was full (30-min cooldown per show).

Priority theatres (Rakki, Phoenix Marketcity, INOX BigPix — see `config.json`) get a 🚨 alert that **repeats every
check until you reply anything** to the bot. Send `/status` to the bot any time for a snapshot.

> BookMyShow answers automated requests with a Cloudflare "verify you are human" page, so it is **not** monitored —
> the watcher does not try to get around bot checks. District serves its public show data normally.

## 1. Create the Telegram bot (2 minutes)

1. In Telegram, open **@BotFather** → `/newbot` → copy the **bot token**.
2. Open your new bot and send it any message (e.g. `hi`).
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `"chat":{"id": ... }` → that's your **chat id**.

## 2a. Run on GitHub Actions (cloud, free on public repos)

1. Repo → **Settings → Secrets and variables → Actions → New repository secret**:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
2. **Actions** tab → *Ticket watcher* → **Run workflow**.

Each run watches for ~5h40m and checks every 3 minutes; the 20-minute schedule keeps the next run queued so it takes
over immediately. State (what was already alerted) is carried between runs via the Actions cache.

## 2b. Run on a PC or old Android phone (Termux)

```bash
# Termux: pkg install python git   |  PC: install Python 3.10+
git clone https://github.com/naKarthikSurya/tickek-booking-notifier && cd tickek-booking-notifier
export TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...      # PowerShell: $env:TELEGRAM_BOT_TOKEN="..."
python -m notifier                                        # runs forever
```

On Android run `termux-wake-lock` first and keep the phone charging. **Disable the GitHub workflow** (Actions tab →
⋯ → Disable) when you switch, or you'll get double alerts.

No dependencies — standard library only.

## Options

| Command | What it does |
|---|---|
| `python -m notifier --dry-run --once` | One check, print alerts instead of sending (great for testing) |
| `python -m notifier --max-minutes 60` | Stop after an hour |
| `python -m unittest discover -s tests` | Run tests |

Edit `config.json` to change dates, the morning cut-off, format regex, priority theatres (regex on the District
cinema name), check interval, or repeat count.
