#!/usr/bin/env python3
"""
Daily news digest: AI, Tech, Finance, International, Tech Leaders
Runs at 07:30 via cron, sends HTML email via Gmail SMTP + Clash proxy.

Links fix: DeepSeek returns JSON; Python builds <a> tags — no link formatting left to the model.
Leaders fix: Google News RSS search per leader — not a scan of already-fetched articles.
"""

import os, json, hashlib, calendar, ssl, requests, smtplib, logging, sys
import feedparser
import socks, socket
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from openai import OpenAI
import re

# ── Logging ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "news_digest.log")),
    ],
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
EMAIL_FROM       = os.environ["EMAIL_FROM"]
EMAIL_TO         = os.environ["EMAIL_TO"]
EMAIL_PASSWORD   = os.environ["EMAIL_PASSWORD"]
SMTP_HOST        = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT        = int(os.environ.get("SMTP_PORT", "465"))
PROXY_HOST       = os.environ.get("PROXY_HOST", "")
PROXY_PORT       = int(os.environ.get("PROXY_PORT", "7890"))
SEEN_FILE        = os.path.join(BASE_DIR, "seen_articles.json")

MAX_PER_CATEGORY = 10   # max articles per news category
MAX_PER_LEADER   = 4    # max articles per tech leader
LOOKBACK_HOURS   = 36

# ── AI keyword filter (for non-dedicated feeds) ───────────────────────────────
AI_KEYWORDS = [
    "AI", "artificial intelligence", "machine learning", "deep learning", "LLM",
    "GPT", "Claude", "Gemini", "ChatGPT", "neural", "OpenAI", "Anthropic",
    "DeepSeek", "Mistral", "transformer", "language model", "robot", "automation",
    "autonomous", "nvidia", "chip", "semiconductor", "AGI", "generative",
]

# ── RSS Sources (4 news categories) ──────────────────────────────────────────
# (display_name, rss_url, keyword_filter_or_None)
RSS_SOURCES = {
    "AI动态": [
        ("VentureBeat AI",        "https://venturebeat.com/category/ai/feed/",     None),
        ("MIT Technology Review", "https://www.technologyreview.com/feed/",        None),
        ("The Verge",             "https://www.theverge.com/rss/index.xml",        AI_KEYWORDS),
        ("Wired",                 "https://www.wired.com/feed/rss",                AI_KEYWORDS),
    ],
    "科技新闻": [
        ("TechCrunch",   "https://techcrunch.com/feed/",                    None),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", None),
    ],
    "财经": [
        ("CNBC",          "https://www.cnbc.com/id/100003114/device/rss/rss.html",          None),
        ("MarketWatch",   "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines", None),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex",                         None),
    ],
    "国际新闻": [
        ("BBC World",      "http://feeds.bbci.co.uk/news/world/rss.xml",   None),
        ("Al Jazeera",     "https://www.aljazeera.com/xml/rss/all.xml",    None),
        ("Guardian World", "https://www.theguardian.com/world/rss",        None),
    ],
}

CATEGORY_ICONS = {
    "AI动态":  "🤖",
    "科技新闻": "💻",
    "财经":    "💰",
    "国际新闻": "🌍",
    "大佬动态": "👤",
}

# ── Tech Leaders — Google News search per person ──────────────────────────────
# (display_name, search_query, hl, gl, ceid)
# hl/gl/ceid: Google News locale params
LEADER_SEARCH = [
    # Global
    ("Jensen Huang (黄仁勋)",  "Jensen Huang",           "en-US", "US", "US:en"),
    ("Elon Musk (马斯克)",     "Elon Musk",              "en-US", "US", "US:en"),
    ("Sam Altman",             "Sam Altman",             "en-US", "US", "US:en"),
    ("Mark Zuckerberg",        "Mark Zuckerberg",        "en-US", "US", "US:en"),
    ("Satya Nadella",          "Satya Nadella",          "en-US", "US", "US:en"),
    ("Demis Hassabis",         "Demis Hassabis",         "en-US", "US", "US:en"),
    ("Yann LeCun",             "Yann LeCun",             "en-US", "US", "US:en"),
    ("Andrew Ng (吴恩达)",     "Andrew Ng AI",           "en-US", "US", "US:en"),
    ("Fei-Fei Li (李飞飞)",   "Fei-Fei Li",             "en-US", "US", "US:en"),
    # China — search in Chinese Google News for better coverage
    ("雷军 (小米)",            "雷军",                   "zh-CN", "CN", "CN:zh-Hans"),
    ("任正非 (华为)",          "任正非",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("余承东 (华为)",          "余承东",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("张一鸣 (字节跳动)",      "张一鸣",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("梁汝波 (字节跳动)",      "梁汝波",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("马化腾 (腾讯)",          "马化腾",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("刘强东 (京东)",          "刘强东",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("黄峥 (拼多多)",          "黄峥 拼多多",            "zh-CN", "CN", "CN:zh-Hans"),
    ("李彦宏 (百度)",          "李彦宏",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("王兴 (美团)",            "王兴 美团",              "zh-CN", "CN", "CN:zh-Hans"),
    ("周鸿祎 (360)",           "周鸿祎",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("丁磊 (网易)",            "丁磊 网易",              "zh-CN", "CN", "CN:zh-Hans"),
    ("吴泳铭 (阿里巴巴)",      "吴泳铭",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("梁文锋 (DeepSeek)",      "梁文锋 DeepSeek",        "zh-CN", "CN", "CN:zh-Hans"),
    ("何小鹏 (小鹏汽车)",      "何小鹏",                 "zh-CN", "CN", "CN:zh-Hans"),
    ("李想 (理想汽车)",        "李想 理想",              "zh-CN", "CN", "CN:zh-Hans"),
    ("李斌 (蔚来)",            "李斌 蔚来",              "zh-CN", "CN", "CN:zh-Hans"),
    ("王传福 (比亚迪)",        "王传福",                 "zh-CN", "CN", "CN:zh-Hans"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_seen():
    if not os.path.exists(SEEN_FILE):
        return {}
    with open(SEEN_FILE) as f:
        return json.load(f)

def save_seen(seen):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=2)

def article_id(entry):
    key = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.md5(key.encode()).hexdigest()

def get_proxies():
    if PROXY_HOST:
        return {
            "http":  f"socks5h://{PROXY_HOST}:{PROXY_PORT}",
            "https": f"socks5h://{PROXY_HOST}:{PROXY_PORT}",
        }
    return None

def fetch_feed(url):
    try:
        resp = requests.get(
            url,
            proxies=get_proxies(),
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RockyNewsDigest/1.0)"},
        )
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception as e:
        log.warning(f"  Failed to fetch {url}: {e}")
        return None

def is_recent(entry):
    pub = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pub:
        return True
    pub_dt = datetime.fromtimestamp(calendar.timegm(pub), tz=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    return pub_dt >= cutoff

def matches_keywords(entry, keywords):
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    return any(kw.lower() in text for kw in keywords)

def clean_summary(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:600]

def entry_to_dict(entry, source_name):
    return {
        "title":   entry.get("title", "No Title").strip(),
        "link":    entry.get("link", ""),
        "summary": clean_summary(entry.get("summary", "")),
        "source":  source_name,
    }


# ── Fetch: news categories ────────────────────────────────────────────────────

def fetch_category(category, sources, seen):
    articles = []
    seen_in_run = set()
    for name, url, keywords in sources:
        log.info(f"  [{category}] {name}...")
        feed = fetch_feed(url)
        if not feed:
            continue
        for entry in feed.entries:
            aid = article_id(entry)
            if aid in seen or aid in seen_in_run:
                continue
            if not is_recent(entry):
                continue
            if keywords and not matches_keywords(entry, keywords):
                continue
            seen_in_run.add(aid)
            articles.append((aid, entry_to_dict(entry, name)))
            if len(articles) >= MAX_PER_CATEGORY:
                break
        if len(articles) >= MAX_PER_CATEGORY:
            break
    return articles


# ── Fetch: tech leaders via Google News RSS ───────────────────────────────────

def fetch_leader_news(name, query, hl, gl, ceid):
    """Fetch Google News RSS for one tech leader. Returns list of article dicts."""
    url = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    )
    feed = fetch_feed(url)
    if not feed:
        return []
    arts = []
    seen_titles = set()
    for entry in feed.entries:
        if not is_recent(entry):
            continue
        title = entry.get("title", "").strip()
        if title in seen_titles:
            continue
        seen_titles.add(title)
        # Google News wraps source name in title as "Title - Source"
        source = "Google News"
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            title = parts[0].strip()
            source = parts[1].strip()
        arts.append({
            "title":   title,
            "link":    entry.get("link", ""),
            "summary": clean_summary(entry.get("summary", "")),
            "source":  source,
        })
        if len(arts) >= MAX_PER_LEADER:
            break
    return arts


# ── Summarize: news categories (returns JSON list) ────────────────────────────

def summarize_category(articles, category, client):
    """Ask DeepSeek to return structured JSON; Python builds HTML with real links."""
    if not articles:
        return []

    def clean(s):
        return s.replace('"', "'").replace("\\", "")

    article_text = "\n\n".join(
        f"[{i+1}] 标题：{clean(a['title'])}\n摘要：{clean(a['summary'])}"
        for i, a in enumerate(articles)
    )

    prompt = (
        f"将以下 {len(articles)} 条「{category}」新闻翻译标题并写中文摘要。\n\n"
        "严格只返回JSON数组，格式：\n"
        '[{"i":1,"t":"中文标题","s":"2-3句摘要，重点：核心事件+为什么重要"},...]\n'
        "不要输出任何其他内容，不要markdown代码块。\n\n"
        f"新闻：\n{article_text}"
    )

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        return json.loads(content)
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse error [{category}], retrying with stricter prompt: {e}")
        try:
            # Retry: ask for simpler format to reduce JSON errors
            simple_prompt = (
                f"为以下{len(articles)}条新闻分别写一句中文摘要（20字以内），"
                "只返回JSON数组格式：\n"
                '[{"i":1,"t":"中文标题","s":"一句摘要"},...]\n'
                "不含任何其他文字。\n\n"
                f"{article_text}"
            )
            resp2 = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": simple_prompt}],
                max_tokens=1500,
            )
            c2 = re.sub(r"^```(?:json)?\s*", "", resp2.choices[0].message.content.strip())
            c2 = re.sub(r"\s*```$", "", c2)
            return json.loads(c2)
        except Exception as e2:
            log.error(f"DeepSeek retry failed [{category}]: {e2}")
            return []
    except Exception as e:
        log.error(f"DeepSeek error [{category}]: {e}")
        return []


# ── Summarize: single tech leader ─────────────────────────────────────────────

def summarize_leader(leader_name, articles, client):
    """Summarize one leader's recent news into a short Chinese paragraph."""
    article_text = "\n".join(
        f"- [{a['source']}] {a['title']}：{a['summary'][:300]}"
        for a in articles
    )
    prompt = (
        f"以下是关于{leader_name}的最新新闻，请用中文写一段3-5句话的动态摘要。\n"
        "重点：他做了什么、说了什么、决定了什么，为什么值得关注。\n"
        "语言直接，不废话，直接陈述事实，不用【根据以上新闻】之类的开头。\n\n"
        f"{article_text}"
    )
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"DeepSeek error [leader {leader_name}]: {e}")
        return ""


# ── HTML builders ─────────────────────────────────────────────────────────────

def render_category_html(summaries, articles):
    """Build HTML for one news category. Links built in Python, not by model."""
    if not articles:
        return ""
    parts = []
    # If summaries is shorter than articles (JSON failed), fall back to original title
    for i, a in enumerate(articles):
        s = summaries[i] if i < len(summaries) else {}
        title_zh = s.get("t", a["title"])
        summary  = s.get("s", "")
        parts.append(
            f'<div style="margin-bottom:18px;">'
            f'<p style="margin:0 0 4px 0;"><strong>{title_zh}</strong></p>'
            f'<p style="margin:0 0 6px 0;color:#444;">{summary}</p>'
            f'<p style="margin:0;font-size:13px;color:#888;">'
            f'来源：{a["source"]} ｜ '
            f'<a href="{a["link"]}" style="color:#4a90d9;">原文链接</a>'
            f'</p>'
            f'</div>'
            f'<hr style="border:none;border-top:1px solid #f0f0f0;margin:0 0 18px 0;">'
        )
    return "\n".join(parts)

def render_leader_html(leader_name, summary, articles):
    """Build HTML for one tech leader block."""
    links = " · ".join(
        f'<a href="{a["link"]}" style="color:#4a90d9;">{a["source"]}</a>'
        for a in articles
    )
    return (
        f'<div style="margin-bottom:22px;">'
        f'<p style="margin:0 0 4px 0;"><strong>{leader_name}</strong></p>'
        f'<p style="margin:0 0 6px 0;color:#444;">{summary}</p>'
        f'<p style="margin:0;font-size:13px;color:#888;">来源：{links}</p>'
        f'</div>'
        f'<hr style="border:none;border-top:1px solid #f0f0f0;margin:0 0 18px 0;">'
    )

def build_email(section_html_blocks, date_str):
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;max-width:720px;margin:0 auto;padding:24px;color:#222;line-height:1.75;">

<h1 style="font-size:22px;border-bottom:2px solid #222;padding-bottom:10px;margin-bottom:4px;">
  科技 · 财经 · 国际 日报
</h1>
<p style="color:#888;margin-top:4px;font-size:14px;">{date_str}</p>
"""
    for section_name, html_content in section_html_blocks.items():
        if not html_content:
            continue
        icon = CATEGORY_ICONS.get(section_name, "📌")
        html += (
            f'\n<h2 style="font-size:17px;margin-top:36px;padding-left:12px;'
            f'border-left:4px solid #4a90d9;">{icon} {section_name}</h2>\n'
            f'<div style="margin-left:4px;">\n{html_content}\n</div>\n'
        )

    html += (
        '\n<hr style="margin-top:48px;border:none;border-top:1px solid #eee;">'
        '\n<p style="color:#bbb;font-size:12px;">Rocky News Digest · 每日 07:30 自动生成</p>'
        "\n</body>\n</html>"
    )
    return html


# ── Send ──────────────────────────────────────────────────────────────────────

def send_email(html_body, date_str):
    subject = f"日报 {date_str} ｜ 科技 · 财经 · 国际 · 大佬动态"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if PROXY_HOST:
        socks.set_default_proxy(socks.SOCKS5, PROXY_HOST, PROXY_PORT)
        socket.socket = socks.socksocket

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
    log.info(f"Email sent: {subject}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Rocky News Digest starting ===")
    seen = load_seen()
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    # ── 1. Fetch news categories ──
    category_articles = {}
    new_seen = {}

    for category, sources in RSS_SOURCES.items():
        items = fetch_category(category, sources, seen)
        arts = []
        for aid, art in items:
            arts.append(art)
            new_seen[aid] = datetime.now(timezone.utc).isoformat()
        category_articles[category] = arts
        log.info(f"  [{category}] {len(arts)} new articles")

    seen.update(new_seen)
    save_seen(seen)

    # ── 2. Fetch tech leaders via Google News ──
    leader_results = {}
    log.info("  [大佬动态] Searching Google News per leader...")
    for leader_name, query, hl, gl, ceid in LEADER_SEARCH:
        arts = fetch_leader_news(leader_name, query, hl, gl, ceid)
        if arts:
            leader_results[leader_name] = arts
            log.info(f"    {leader_name}: {len(arts)} articles")

    if not any(category_articles.values()) and not leader_results:
        log.info("No new content. Skipping email.")
        return

    # ── 3. Summarize + build HTML per section ──
    section_html = {}

    for category, arts in category_articles.items():
        if not arts:
            continue
        log.info(f"Summarizing [{category}]...")
        summaries = summarize_category(arts, category, client)
        section_html[category] = render_category_html(summaries, arts)

    if leader_results:
        log.info(f"Summarizing [{len(leader_results)} leaders]...")
        leader_blocks = []
        for leader_name, arts in leader_results.items():
            summary = summarize_leader(leader_name, arts, client)
            if summary:
                leader_blocks.append(render_leader_html(leader_name, summary, arts))
        section_html["大佬动态"] = "\n".join(leader_blocks)

    # ── 4. Build + send email ──
    date_str = datetime.now().strftime("%Y年%m月%d日")
    html = build_email(section_html, date_str)
    send_email(html, datetime.now().strftime("%Y-%m-%d"))
    log.info("=== Done ===")


if __name__ == "__main__":
    main()
