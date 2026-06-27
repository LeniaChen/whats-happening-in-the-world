# Rocky News Digest

A daily email digest that automatically aggregates and summarizes news across four categories — AI, Tech, Finance, and World News — plus a dedicated section tracking the latest moves from tech leaders worldwide.

Runs every morning at 07:30 via cron. Fetches RSS feeds, summarizes with DeepSeek V3, and sends a clean HTML email via Gmail.

---

## What's in the email

| Section | Sources |
|---------|---------|
| 🤖 AI News | MIT Technology Review, The Verge (AI-filtered), Wired (AI-filtered), VentureBeat AI |
| 💻 Tech News | TechCrunch, Ars Technica |
| 💰 Finance | CNBC, MarketWatch, Yahoo Finance |
| 🌍 World News | BBC World, Al Jazeera, The Guardian |
| 👤 Tech Leaders | Google News RSS search per person — 27 leaders tracked |

**Tech leaders tracked:**

*Global:* Jensen Huang, Elon Musk, Sam Altman, Mark Zuckerberg, Satya Nadella, Demis Hassabis, Yann LeCun, Andrew Ng, Fei-Fei Li

*China:* 雷军 (Xiaomi), 任正非 / 余承东 (Huawei), 张一鸣 / 梁汝波 (ByteDance), 马化腾 (Tencent), 刘强东 (JD.com), 黄峥 (Pinduoduo), 李彦宏 (Baidu), 王兴 (Meituan), 周鸿祎 (360), 丁磊 (NetEase), 吴泳铭 (Alibaba), 梁文锋 (DeepSeek), 何小鹏 (Xpeng), 李想 (Li Auto), 李斌 (NIO), 王传福 (BYD)

Only leaders with news published in the last 36 hours appear in the email.

---

## Requirements

- Python 3.9+
- A Gmail account with an [App Password](https://support.google.com/accounts/answer/185833) enabled
- A [DeepSeek API key](https://platform.deepseek.com)
- macOS (for the cron setup described below; Linux works the same way)
- If you're in mainland China: a SOCKS5 proxy running locally (e.g. Clash on port 7890)

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/LeniaChen/rocky-news-digest.git
cd rocky-news-digest
```

### 2. Install dependencies

```bash
pip install feedparser requests openai PySocks
```

### 3. Configure credentials

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and set:

| Variable | What it is |
|----------|-----------|
| `DEEPSEEK_API_KEY` | From [platform.deepseek.com](https://platform.deepseek.com) → API Keys |
| `EMAIL_FROM` | Your Gmail address |
| `EMAIL_TO` | Recipient address (can be the same) |
| `EMAIL_PASSWORD` | Gmail **App Password** (16 chars, no spaces) — see below |
| `SMTP_HOST` | `smtp.gmail.com` (leave as-is) |
| `SMTP_PORT` | `465` (leave as-is) |
| `PROXY_HOST` | Your SOCKS5 proxy host, e.g. `127.0.0.1` — leave blank if not needed |
| `PROXY_PORT` | Your SOCKS5 proxy port, e.g. `7890` — leave blank if not needed |

**How to get a Gmail App Password:**
1. Go to your Google Account → Security → 2-Step Verification (must be enabled)
2. Search for "App passwords" at the bottom of that page
3. Create one, copy the 16-character password into `.env`

### 4. Test it manually

```bash
set -a && source .env && set +a
python3 news_digest.py
```

Check your inbox. The first run fetches up to 10 articles per category and up to 4 articles per tech leader. Subsequent runs skip already-seen articles (tracked in `seen_articles.json`).

### 5. Schedule with cron (daily at 07:30)

```bash
chmod +x run.sh
crontab -e
```

Add this line (adjust the path to match your clone location and your Python binary):

```
30 7 * * * /path/to/rocky-news-digest/run.sh
```

The script auto-sources `.env` before running, so no environment setup is needed in cron.

**Finding your Python binary:**

```bash
which python3
```

Open `run.sh` and update the Python path on the last line if needed.

---

## Files

```
rocky-news-digest/
├── news_digest.py      # Main script
├── run.sh              # Cron launcher (sources .env, calls python)
├── .env                # Your credentials — never commit this
├── .env.example        # Template
├── .gitignore
└── README.md
```

Auto-generated at runtime (not committed):

```
seen_articles.json      # Deduplication log — articles seen in the last 14 days
news_digest.log         # Run log
```

---

## Customization

### Change the schedule

Edit the crontab line. Format is `minute hour * * *`:

```
0 8 * * *    # 08:00 every day
30 6 * * 1-5 # 06:30 on weekdays only
```

### Add or remove news sources

Edit `RSS_SOURCES` in `news_digest.py`. Each entry is a tuple:

```python
("Display Name", "https://example.com/feed.rss", keyword_filter_or_None)
```

Set the third element to `None` to include all articles, or pass a list of strings to only include articles whose title or summary contains at least one of those strings.

### Add or remove tech leaders

Edit `LEADER_SEARCH` in `news_digest.py`. Each entry:

```python
("Display Name", "search query for Google News", "hl", "gl", "ceid")
```

For English-language search: `"en-US", "US", "US:en"`
For Chinese-language search: `"zh-CN", "CN", "CN:zh-Hans"`

Add specifics to the query to reduce noise (e.g. `"李想 理想"` instead of just `"李想"`).

### Change the AI model

In `news_digest.py`, update the `model` parameter in both `summarize_category` and `summarize_leader`:

```python
model="deepseek-chat"   # DeepSeek V3 (default)
```

Any OpenAI-compatible API works — update `base_url` in `OpenAI(...)` accordingly.

### Force a full re-send

Delete `seen_articles.json` and re-run. All articles from the past 36 hours will be re-fetched and re-sent.

---

## Troubleshooting

**No email received:**
- Check `news_digest.log` for errors
- Verify Clash / proxy is running if you're in mainland China
- Make sure you're using an App Password, not your Google account password

**`ModuleNotFoundError`:**
- cron uses the system Python, which may differ from your shell Python
- Open `run.sh` and update the Python path to match `which python3` output in your terminal

**Empty tech leader section:**
- Normal — only leaders with news in the last 36 hours appear
- If consistently empty, check that your proxy can reach `news.google.com`

**JSON parse error in log:**
- Non-critical — the script retries automatically with a simpler prompt
- If it happens every run for the same category, the article summaries may contain unusual characters; the fallback still renders the article with its original title

---

## License

MIT
