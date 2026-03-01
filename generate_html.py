import re
from datetime import date

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
                # "- タイトル - URL" の形式をパース
                m2 = re.match(r"^- (.+?) - (https://.+)$", line)
                if m2:
                    categories[current_cat].append((m2.group(1), m2.group(2)))
    return categories

def build_section(title, categories):
    html = f'<h2 class="channel-title">{title}</h2>\n'
    for cat, videos in categories.items():
        if not videos:
            continue
        html += f'<details>\n<summary>{cat}（{len(videos)}本）</summary>\n<ul>\n'
        for vtitle, url in videos:
            html += f'  <li><a href="{url}" target="_blank">{vtitle}</a></li>\n'
        html += '</ul>\n</details>\n'
    return html

ch1 = parse_txt("yuutera_grouped.txt")
ch2 = parse_txt("yobinori_grouped.txt")

updated = date.today().strftime("%Y年%m月%d日")

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
  header {{ margin-bottom: 48px; }}
  h1 {{
    font-size: 1.8em;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 0.03em;
    margin-bottom: 8px;
  }}
  .tagline {{
    color: #888;
    font-size: 0.95em;
    margin-bottom: 6px;
  }}
  .updated {{ color: #555; font-size: 0.85em; }}
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
  summary::after {{
    content: '▸';
    color: #555;
    transition: transform 0.2s;
  }}
  details[open] summary::after {{ transform: rotate(90deg); }}
  ul {{
    padding: 0 16px 12px 16px;
    list-style: none;
    border-top: 1px solid #2a2a3a;
  }}
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

{build_section("ユーテラ授業チャンネル", ch1)}
{build_section("予備校のノリで学ぶ「大学の数学・物理」", ch2)}

<div class="request-box">
  <p>追加してほしいチャンネルがあればリクエストどうぞ</p>
  <a href="https://github.com/eritsi/youtube-curation/issues/new?template=request.md" target="_blank">チャンネルをリクエストする</a>
</div>

</div>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("index.html を生成しました")