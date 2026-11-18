# Ticket Booking Notifier — Avengers: Doomsday, Chennai

Watches **District** (district.in) 24×7 for **English, 3D / premium (Infinity Vision, IMAX, 4DX), morning (before 12 PM)**
shows of *Avengers: Doomsday* in Chennai, 17–18 Dec 2026, and pings you on **Telegram** with a direct booking link when:

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

## 2a. Run on an old Android phone (Termux — recommended for 24×7)

District blocks most cloud/data-centre IPs (`HTTP 403`), so running on an old phone over home Wi-Fi works reliably.

1. Install **Termux from F-Droid** (`f-droid.org/packages/com.termux/`) — avoid the outdated Google Play Store build, whose package repos are broken.
2. In Android **Settings → Apps → Termux → Battery**, set it to **Unrestricted** (disable battery optimisation) so Android doesn't kill it overnight, and keep the phone plugged in on home Wi-Fi.
3. Open Termux and run:

```bash
termux-wake-lock
pkg update -y && pkg install -y python git
git clone https://github.com/naKarthikSurya/tickek-booking-notifier.git
cd tickek-booking-notifier
export TELEGRAM_BOT_TOKEN="<YOUR_BOT_TOKEN>"
export TELEGRAM_CHAT_ID="<YOUR_CHAT_ID>"
python -m notifier
```

If you were running it on your PC first, press `Ctrl+C` there once you see `🟢 Ticket watcher started` from the phone, and keep the GitHub Actions workflow disabled so you don't get double alerts.

## 2b. Run on a Windows PC

Requires Python 3.10+ (no external packages — standard library only).

```powershell
git clone https://github.com/naKarthikSurya/tickek-booking-notifier.git
cd tickek-booking-notifier
$env:TELEGRAM_BOT_TOKEN="<YOUR_BOT_TOKEN>"
$env:TELEGRAM_CHAT_ID="<YOUR_CHAT_ID>"
python -m notifier
```

Keep the PowerShell window open and prevent the PC from sleeping.

## 2c. Run on GitHub Actions (cloud — may be blocked by District)

> Note: In testing, District returned `HTTP 403` to GitHub Actions' cloud runners. Keep this disabled unless you've verified it can reach District.

1. Repo → **Settings → Secrets and variables → Actions → New repository secret**:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
2. **Actions** tab → *Ticket watcher* → **Run workflow** (or `⋯` → **Disable workflow** when running locally).

Each run watches for ~5h40m and checks every 3 minutes; the 20-minute schedule keeps the next run queued so it takes
over immediately. State (what was already alerted) is carried between runs via the Actions cache.

## Options

| Command | What it does |
|---|---|
| `python -m notifier --dry-run --once` | One check, print alerts instead of sending (great for testing) |
| `python -m notifier --max-minutes 60` | Stop after an hour |
| `python -m unittest discover -s tests` | Run tests |

Edit `config.json` to change dates, the morning cut-off, format regex, priority theatres (regex on the District
cinema name), check interval, or repeat count.
