import re
import json
import os
import hashlib
from datetime import date


# ── Video helpers ──────────────────────────────────────────────────────

def parse_txt(filepath):
    categories = {}
    current_cat = None
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            m = re.match(r"^## (.+?) \((\d+)本\)$", line)
            if m:
                current_cat = m.group(1)
                categories[current_cat] = []
            elif line.startswith("- ") and current_cat:
                m2 = re.match(r"^- (.+?) - (https://.+)$", line)
                if m2:
                    categories[current_cat].append((m2.group(1), m2.group(2)))
    return categories


def build_video_section(title, categories):
    html = f'<h2 class="channel-title">{title}</h2>\n'
    for cat, videos in categories.items():
        if not videos:
            continue
        html += f'<details>\n<summary>{cat}（{len(videos)}本）</summary>\n<ul>\n'
        for vtitle, url in videos:
            html += f'  <li><a href="{url}" target="_blank">{vtitle}</a></li>\n'
        html += '</ul>\n</details>\n'
    return html


# ── News helpers ───────────────────────────────────────────────────────

def load_news():
    if not os.path.exists("news/news.json"):
        return None
    with open("news/news.json", encoding="utf-8") as f:
        return json.load(f)


def nid(text):
    return "n" + hashlib.md5(text.encode()).hexdigest()[:10]


def build_news_tab(news):
    if not news:
        return '<p class="no-items" style="margin-top:40px">ニュースデータがありません（スクレイパー未実行）</p>'

    g = news.get("generated_at", "")
    date_str = g[:10].replace("-", "/") + " " + g[11:16] if g else ""
    html = f'<div class="news-meta"><span class="news-updated">最終チェック: {date_str}</span>'
    html += '<button class="reset-all-btn" onclick="resetAll()">既読をリセット</button></div>\n'

    for site in news.get("sites", []):
        html += build_site_block(site)

    return html


def build_site_block(site):
    name = site["name"]
    url = site["url"]
    desc = site.get("description", "")
    status = site["status"]
    extract = site.get("extract", "sections")

    if status == "changed":
        badge = '<span class="badge-updated">更新あり</span>'
    elif status == "error":
        badge = '<span class="badge-error">エラー</span>'
    else:
        badge = ''

    html = '<div class="news-site">\n'
    html += f'<div class="news-site-header">'
    html += f'<a href="{url}" target="_blank" class="news-site-name">{name}</a>{badge}'
    if desc:
        html += f'<span class="news-site-desc">{desc}</span>'
    html += '</div>\n'

    if status == "error":
        html += f'<p class="error-msg">{site.get("error", "取得に失敗しました")}</p>\n'
    elif extract in ("show_schedule", "wp_schedule_api"):
        html += build_show_schedule_block(site)
    elif extract == "venue_news":
        html += build_venue_news_block(site)
    elif extract == "links":
        html += build_links_block(site)
    elif extract == "announcements":
        html += build_announcements_block(site)
    elif extract == "text":
        html += build_text_block(site)
    elif extract == "js_pending":
        html += build_js_pending_block(site)
    else:
        html += build_sections_block(site)

    html += '</div>\n'
    return html


def build_js_pending_block(site):
    url = site.get("url", "#")
    return (
        f'<p class="js-pending-msg">⚠ このサイトのカレンダーはJavaScript必須のため自動取得できません。'
        f'<a href="{url}" target="_blank" rel="noopener">公式サイトで確認</a></p>\n'
    )


def build_show_schedule_block(site):
    """新着公演（new_shows）をアーティスト・日付付きで表示する。
    変更なし時は直近公演を5件表示する。"""
    new_shows = site.get("new_shows", [])
    shows     = site.get("shows", [])

    html = ""
    if new_shows:
        html += '<p class="venue-label">新着公演</p>\n<ul class="news-list">\n'
        for s in new_shows:
            lid    = nid(s["url"])
            badge  = '<span class="badge-new">NEW</span>'
            artist = s.get("artist", "")
            date   = s.get("date", "")
            title  = s.get("title", "")
            url    = s["url"]
            html += f'  <li class="news-item ann-item" data-id="{lid}">\n'
            html += f'    <div class="ann-content">\n'
            html += f'      <div class="ann-store">{badge}<a href="{url}" target="_blank" class="venue-link">{artist}</a></div>\n'
            parts = []
            if date:  parts.append(date)
            if title: parts.append(title)
            if parts:
                html += f'      <div class="ann-date">{" ／ ".join(parts)}</div>\n'
            html += f'    </div>\n'
            html += f'    <button class="dismiss-btn" onclick="dismiss(\'{lid}\')">既読</button>\n'
            html += f'  </li>\n'
        html += '</ul>\n'
    elif shows:
        html += '<p class="no-items" style="font-size:0.78em">本日の変更なし（直近公演情報）</p>\n'
        html += '<ul class="news-list">\n'
        for s in shows[:5]:
            lid    = nid(s["url"])
            artist = s.get("artist", "")
            date   = s.get("date", "")
            url    = s["url"]
            html += f'  <li class="news-item ann-item" data-id="{lid}">\n'
            html += f'    <div class="ann-content">\n'
            html += f'      <div class="ann-store"><a href="{url}" target="_blank" class="venue-link">{artist}</a></div>\n'
            if date:
                html += f'      <div class="ann-date">{date}</div>\n'
            html += f'    </div>\n'
            html += f'    <button class="dismiss-btn" onclick="dismiss(\'{lid}\')">既読</button>\n'
            html += f'  </li>\n'
        html += '</ul>\n'
    else:
        html = '<p class="no-items">公演情報が取得できませんでした</p>\n'
    return html


def build_venue_news_block(site):
    """新着公演（new_events）とチケット更新（ticket_updates）を描画する。
    ticket_updates には data-artist-id を付けることで、親アーティストを既読にすると
    JS 側で連動して非表示になる。"""
    new_events     = site.get("new_events", [])
    ticket_updates = site.get("ticket_updates", [])
    all_items      = site.get("all_items", [])

    if not new_events and not ticket_updates and not all_items:
        return '<p class="no-items">変更はありませんでした</p>\n'

    html = ""

    def render_item(item, lid, extra_attrs="", badge="", is_link=False):
        content   = item.get("content", "")[:70]
        show_date = item.get("show_date", "")
        tag       = item.get("tag", "")
        url       = item.get("url", "#")
        h  = f'  <li class="news-item ann-item" data-id="{lid}"{extra_attrs}>\n'
        h += f'    <div class="ann-content">\n'
        h += f'      <div class="ann-store">{badge}<a href="{url}" target="_blank" class="venue-link">{content}</a></div>\n'
        parts = []
        if show_date: parts.append(f"公演日: {show_date}")
        if tag:       parts.append(tag)
        if parts:
            h += f'      <div class="ann-date">{" ／ ".join(parts)}</div>\n'
        h += f'    </div>\n'
        h += f'    <button class="dismiss-btn" onclick="dismiss(\'{lid}\')">既読</button>\n'
        h += f'  </li>\n'
        return h

    if new_events:
        html += '<p class="venue-label">新着公演</p>\n<ul class="news-list">\n'
        for item in new_events:
            eid = item.get("event_id") or item.get("item_id", "")
            lid = nid(eid)
            html += render_item(item, lid, badge='<span class="badge-new">NEW</span>')
        html += '</ul>\n'

    if ticket_updates:
        html += '<p class="venue-label ticket-label">チケット情報更新</p>\n<ul class="news-list">\n'
        for item in ticket_updates:
            eid = item.get("event_id") or item.get("item_id", "")
            lid = nid("ticket_" + eid)
            artist_lid = nid(eid)  # 親アーティストの dismiss ID と紐づけ
            html += render_item(
                item, lid,
                extra_attrs=f' data-artist-id="{artist_lid}"',
                badge='<span class="badge-ticket">TICKET</span>',
            )
        html += '</ul>\n'

    # 変更なし時：直近アイテムを表示
    if not new_events and not ticket_updates and all_items:
        html += '<p class="no-items" style="font-size:0.78em">本日の変更なし（直近公演情報）</p>\n'
        html += '<ul class="news-list">\n'
        for item in all_items[:5]:
            eid = item.get("event_id") or item.get("item_id", "")
            lid = nid(eid)
            html += render_item(item, lid)
        html += '</ul>\n'

    return html


def build_links_block(site):
    links = site.get("links", [])
    new_hrefs = {l["href"] for l in site.get("new_links", [])}
    if not links:
        return '<p class="no-items">リンクが見つかりませんでした</p>\n'

    html = '<ul class="news-list">\n'
    for link in links:
        lid = nid(link["href"])
        badge = '<span class="badge-new">NEW</span>' if link["href"] in new_hrefs else ''
        html += f'  <li class="news-item" data-id="{lid}">'
        html += f'{badge}<a href="{link["href"]}" target="_blank" class="news-link">{link["text"]}</a>'
        html += f'<button class="dismiss-btn" onclick="dismiss(\'{lid}\')">既読</button>'
        html += '</li>\n'
    html += '</ul>\n'
    return html


def build_text_block(site):
    items = site.get("items", [])
    new_set = set(site.get("new_items", []))
    if not items:
        return '<p class="no-items">変更はありませんでした</p>\n'

    html = '<ul class="news-list">\n'
    for item in items:
        lid = nid(item)
        badge = '<span class="badge-new">NEW</span>' if item in new_set else ''
        html += f'  <li class="news-item" data-id="{lid}">'
        html += f'{badge}<span class="news-text">{item}</span>'
        html += f'<button class="dismiss-btn" onclick="dismiss(\'{lid}\')">既読</button>'
        html += '</li>\n'
    html += '</ul>\n'
    return html


def build_announcements_block(site):
    """h2=月・h3=案内単位で個別既読ボタン付きリストを生成する"""
    months = site.get("months", [])
    new_keys = set(site.get("new_keys", []))

    if not months:
        return '<p class="no-items">変更はありませんでした</p>\n'

    html = ''
    for month in months:
        month_title = month["title"]
        announcements = month.get("announcements", [])
        if not announcements:
            continue

        html += f'<p class="month-label">{month_title}</p>\n'
        html += '<ul class="news-list">\n'
        for ann in announcements:
            store = ann["store"]
            details = ann.get("details", [])
            key = f"{month_title}::{store}"
            lid = nid(key)
            is_new = key in new_keys
            badge = '<span class="badge-new">NEW</span>' if is_new else ''

            # 日時情報：最初の3つのdetailsを使用（販売日時が含まれる）
            date_info = "　".join(details[:3]) if details else ""

            html += f'  <li class="news-item ann-item" data-id="{lid}">\n'
            ann_links = ann.get("links", [])
            html += f'    <div class="ann-content">\n'
            html += f'      <div class="ann-store">{badge}{store}</div>\n'
            if date_info:
                html += f'      <div class="ann-date">{date_info}</div>\n'
            if ann_links:
                html += '      <div class="ann-links">'
                for lnk in ann_links:
                    html += f'<a href="{lnk["href"]}" target="_blank" class="ann-link">{lnk["text"]}</a>'
                html += '</div>\n'
            html += f'    </div>\n'
            html += f'    <button class="dismiss-btn" onclick="dismiss(\'{lid}\')">既読</button>\n'
            html += f'  </li>\n'
        html += '</ul>\n'

    return html


def build_sections_block(site):
    sections = site.get("sections", [])
    new_titles = set(site.get("new_titles", []))
    if not sections:
        return '<p class="no-items">変更はありませんでした</p>\n'

    html = ''
    for sec in sections:
        title = sec["title"]
        body = sec.get("body", [])
        lid = nid(title)
        badge = '<span class="badge-new">NEW</span>' if title in new_titles else ''
        html += f'<details class="news-card" data-id="{lid}">\n'
        html += f'  <summary>{badge}{title}'
        html += f'  <button class="dismiss-btn" onclick="event.stopPropagation(); dismiss(\'{lid}\')">既読</button>'
        html += '</summary>\n'
        if body:
            html += '  <div class="news-card-body">\n'
            for line in body[:12]:
                html += f'    <p>{line}</p>\n'
            html += '  </div>\n'
        html += '</details>\n'
    return html


# ── Build ──────────────────────────────────────────────────────────────

ch1 = parse_txt("video/yuutera_grouped.txt")
ch2 = parse_txt("video/yobinori_grouped.txt")
news = load_news()

updated = date.today().strftime("%Y年%m月%d日")
video_html = build_video_section("ユーテラ授業チャンネル", ch1) + build_video_section("予備校のノリで学ぶ「大学の数学・物理」", ch2)
news_html = build_news_tab(news)

html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>勉強系YouTube キュレーション</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    background: #0f0f13;
    color: #e0e0e0;
    padding: 40px 20px;
  }}
  .container {{ max-width: 860px; margin: 0 auto; }}
  header {{ margin-bottom: 32px; }}
  h1 {{
    font-size: 1.8em;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 0.03em;
    margin-bottom: 8px;
  }}
  .tagline {{ color: #888; font-size: 0.95em; margin-bottom: 6px; }}
  .updated {{ color: #555; font-size: 0.85em; }}

  /* ── Tabs ── */
  .tab-bar {{
    display: flex;
    gap: 0;
    border-bottom: 2px solid #2a2a3a;
    margin-bottom: 32px;
  }}
  .tab-btn {{
    background: none;
    border: none;
    color: #666;
    font-size: 0.95em;
    font-weight: 600;
    padding: 10px 22px;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: color 0.2s;
    letter-spacing: 0.03em;
  }}
  .tab-btn.active {{ color: #f59e0b; border-bottom-color: #f59e0b; }}
  .tab-btn:hover:not(.active) {{ color: #aaa; }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  /* ── Video tab ── */
  h2.channel-title {{
    font-size: 1.2em;
    font-weight: 600;
    color: #f59e0b;
    margin: 48px 0 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid #2a2a3a;
    letter-spacing: 0.05em;
  }}
  details {{
    margin: 6px 0;
    background: #16161e;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    overflow: hidden;
    transition: border-color 0.2s;
  }}
  details:hover {{ border-color: #f59e0b44; }}
  details[open] {{ border-color: #f59e0b66; }}
  summary {{
    cursor: pointer;
    font-weight: 600;
    font-size: 0.95em;
    padding: 12px 16px;
    color: #fcd34d;
    list-style: none;
    display: flex;
    justify-content: space-between;
    align-items: center;
    user-select: none;
  }}
  summary::after {{ content: '▸'; color: #555; transition: transform 0.2s; }}
  details[open] summary::after {{ transform: rotate(90deg); }}
  ul {{ padding: 0 16px 12px 16px; list-style: none; border-top: 1px solid #2a2a3a; }}
  li {{ margin: 0; }}
  li a {{
    display: block;
    padding: 7px 4px;
    color: #94a3b8;
    text-decoration: none;
    font-size: 0.9em;
    border-bottom: 1px solid #1e1e28;
    transition: color 0.15s;
  }}
  li:last-child a {{ border-bottom: none; }}
  li a:hover {{ color: #e2e8f0; }}

  /* ── News tab ── */
  .news-meta {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 28px;
  }}
  .news-updated {{ color: #555; font-size: 0.82em; }}
  .reset-all-btn {{
    background: none;
    border: 1px solid #333;
    color: #555;
    font-size: 0.78em;
    padding: 4px 10px;
    border-radius: 4px;
    cursor: pointer;
  }}
  .reset-all-btn:hover {{ border-color: #555; color: #888; }}
  .news-site {{
    margin-bottom: 36px;
  }}
  .news-site-header {{
    margin-bottom: 10px;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 8px;
  }}
  .news-site-name {{
    font-size: 1.1em;
    font-weight: 600;
    color: #f59e0b;
    text-decoration: none;
  }}
  .news-site-name:hover {{ color: #fcd34d; }}
  .news-site-desc {{
    color: #555;
    font-size: 0.82em;
    width: 100%;
  }}
  .badge-updated {{
    display: inline-block;
    background: #f59e0b22;
    color: #f59e0b;
    border: 1px solid #f59e0b55;
    border-radius: 4px;
    font-size: 0.72em;
    padding: 2px 7px;
    font-weight: 600;
  }}
  .badge-error {{
    display: inline-block;
    background: #ef444422;
    color: #ef4444;
    border: 1px solid #ef444455;
    border-radius: 4px;
    font-size: 0.72em;
    padding: 2px 7px;
  }}
  .badge-new {{
    display: inline-block;
    background: #3b82f622;
    color: #60a5fa;
    border: 1px solid #3b82f655;
    border-radius: 3px;
    font-size: 0.68em;
    padding: 1px 5px;
    margin-right: 6px;
    font-weight: 700;
    vertical-align: middle;
  }}
  .news-list {{
    list-style: none;
    padding: 0;
    margin: 0;
    background: #16161e;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    overflow: hidden;
  }}
  .news-item {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    border-bottom: 1px solid #1e1e28;
    gap: 10px;
  }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-link {{
    color: #94a3b8;
    text-decoration: none;
    font-size: 0.9em;
    flex: 1;
  }}
  .news-link:hover {{ color: #e2e8f0; }}
  .news-text {{
    color: #94a3b8;
    font-size: 0.88em;
    flex: 1;
  }}
  .dismiss-btn {{
    background: none;
    border: 1px solid #2a2a3a;
    color: #444;
    font-size: 0.72em;
    padding: 3px 8px;
    border-radius: 4px;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0;
    transition: border-color 0.15s, color 0.15s;
  }}
  .dismiss-btn:hover {{ border-color: #555; color: #888; }}
  .news-card {{
    margin: 6px 0;
    background: #16161e;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    overflow: hidden;
  }}
  .news-card summary {{
    padding: 11px 16px;
    font-size: 0.92em;
    color: #c4b5fd;
  }}
  .news-card summary::after {{ color: #555; }}
  .news-card-body {{
    padding: 10px 16px 12px;
    border-top: 1px solid #2a2a3a;
  }}
  .news-card-body p {{
    color: #64748b;
    font-size: 0.85em;
    padding: 3px 0;
    border-bottom: 1px solid #1e1e28;
  }}
  .news-card-body p:last-child {{ border-bottom: none; }}
  .no-items {{ color: #444; font-size: 0.85em; padding: 8px 0; }}
  .error-msg {{ color: #ef4444; font-size: 0.82em; padding: 6px 0; }}
  .month-label {{
    font-size: 0.8em;
    color: #555;
    font-weight: 600;
    letter-spacing: 0.05em;
    margin: 16px 0 6px;
    padding-left: 2px;
  }}
  .ann-item {{ align-items: flex-start; padding: 10px 14px; }}
  .ann-content {{ flex: 1; min-width: 0; }}
  .ann-store {{ color: #94a3b8; font-size: 0.9em; margin-bottom: 3px; }}
  .ann-date {{ color: #4b5563; font-size: 0.8em; line-height: 1.5; margin-bottom: 4px; }}
  .ann-links {{ margin-top: 4px; }}
  .ann-link {{
    display: inline-block;
    color: #60a5fa;
    font-size: 0.78em;
    text-decoration: none;
    margin-right: 10px;
    padding: 1px 0;
  }}
  .ann-link::before {{ content: '📄 '; }}
  .ann-link:hover {{ color: #93c5fd; text-decoration: underline; }}
  .venue-label {{
    font-size: 0.8em;
    color: #555;
    font-weight: 600;
    letter-spacing: 0.05em;
    margin: 16px 0 6px;
    padding-left: 2px;
  }}
  .ticket-label {{ color: #60a5fa !important; }}
  .badge-ticket {{
    display: inline-block;
    background: #3b82f622;
    color: #60a5fa;
    border: 1px solid #3b82f655;
    border-radius: 3px;
    font-size: 0.68em;
    padding: 1px 6px;
    margin-right: 6px;
    font-weight: 700;
    vertical-align: middle;
  }}
  .venue-link {{
    color: #94a3b8;
    text-decoration: none;
  }}
  .venue-link:hover {{ color: #e2e8f0; }}

  /* ── Request box ── */
  .request-box {{
    margin-top: 60px;
    padding: 20px 24px;
    background: #16161e;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    text-align: center;
  }}
  .request-box p {{ color: #888; font-size: 0.9em; margin-bottom: 12px; }}
  .request-box a {{
    display: inline-block;
    padding: 10px 24px;
    background: #f59e0b22;
    color: #f59e0b;
    border: 1px solid #f59e0b66;
    border-radius: 6px;
    text-decoration: none;
    font-size: 0.9em;
    font-weight: 600;
    transition: background 0.2s;
  }}
  .request-box a:hover {{ background: #f59e0b33; }}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>勉強系YouTube キュレーション</h1>
  <p class="tagline">社会人でも勉強が楽しくなるおすすめYouTubeチャンネル</p>
  <p class="updated">最終更新: {updated}</p>
</header>

<div class="tab-bar">
  <button class="tab-btn" data-tab="videos">動画キュレーション</button>
  <button class="tab-btn" data-tab="news">ニュース・お知らせ</button>
</div>

<div id="tab-videos" class="tab-content">
{video_html}
<div class="request-box">
  <p>追加してほしいチャンネルがあればリクエストどうぞ</p>
  <a href="https://github.com/eritsi/youtube-curation/issues/new?template=request.md" target="_blank">チャンネルをリクエストする</a>
</div>
</div>

<div id="tab-news" class="tab-content">
{news_html}
</div>

</div>

<script>
(function() {{
  // ── Tab switching ──
  function switchTab(name) {{
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const content = document.getElementById('tab-' + name);
    const btn = document.querySelector('[data-tab="' + name + '"]');
    if (content) content.classList.add('active');
    if (btn) btn.classList.add('active');
    localStorage.setItem('activeTab', name);
  }}

  document.querySelectorAll('.tab-btn').forEach(btn => {{
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  }});

  // ── Dismiss (既読) ──
  function getDismissed() {{
    return JSON.parse(localStorage.getItem('dismissed') || '[]');
  }}

  window.dismiss = function(id) {{
    const list = getDismissed();
    if (!list.includes(id)) list.push(id);
    localStorage.setItem('dismissed', JSON.stringify(list));
    document.querySelectorAll('[data-id="' + id + '"]').forEach(el => el.style.display = 'none');
  }};

  window.resetAll = function() {{
    localStorage.removeItem('dismissed');
    document.querySelectorAll('[data-id]').forEach(el => el.style.display = '');
  }};

  function applyDismissed() {{
    getDismissed().forEach(id => {{
      document.querySelectorAll('[data-id="' + id + '"]').forEach(el => el.style.display = 'none');
      // 同アーティストのチケット更新通知も連動で非表示
      document.querySelectorAll('[data-artist-id="' + id + '"]').forEach(el => el.style.display = 'none');
    }});
  }}

  // ── Init ──
  const lastTab = localStorage.getItem('activeTab') || 'videos';
  switchTab(lastTab);
  applyDismissed();
}})();
</script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("index.html を生成しました")
