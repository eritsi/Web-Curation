# youtube-curation

横浜エリアの情報をまとめた静的サイト。`index.html` をそのまま GitHub Pages で公開する。

## 構成

| ファイル | 役割 |
|---|---|
| `generate_html.py` | `index.html` を生成（両タブ共通） |
| `video/yt_yobinori.py` `video/yt_yuutera.py` | YouTube チャンネルの動画一覧を取得 |
| `video/*_grouped.txt` | 動画一覧のキャッシュ（自動生成） |
| `news/scraper.py` | 各サイトの変更を検知 |
| `news/sites.yaml` | 監視サイトの設定（ユーザーが編集） |
| `news/news.json` | スクレイプ結果（自動生成） |
| `news/snapshots/` | 前回実行との差分検知用（自動生成） |

---

## 動画タブに何かを追加・変更したいとき

編集ファイル: `video/yt_yobinori.py` または `video/yt_yuutera.py`

スクリプト内の `categories` 辞書やチャンネル ID を変更し、ローカルで確認：

```bash
cd video
python yt_yobinori.py > yobinori_grouped.txt
python yt_yuutera.py > yuutera_grouped.txt
cd ..
python generate_html.py
```

---

## ニュースタブにサイトを追加・変更したいとき

編集ファイル: `news/sites.yaml`

`sites:` リストにエントリを追加するだけ。主なパラメータ：

```yaml
- name: "表示名"
  url: "https://example.com/news/"
  extract: "show_schedule"   # show_schedule / venue_news / announcements / links
  description: "説明文"
  # --- 主なオプション ---
  item_selector: ".list-item"          # 1件を表す CSS セレクタ
  artist_selector: ".title"            # アーティスト/タイトル
  date_selector: ".date"               # 日付
  keep_latest: 5                       # 保持件数の上限
  filter_past: true                    # 過去日付を除外
  exclude_artist_pattern: "^Private$"  # タイトル除外パターン（正規表現）
```

変更後にローカルで確認：

```bash
cd news
python scraper.py   # news.json と snapshots/ を更新
cd ..
python generate_html.py
```

---

## GitHub Actions

### `update_videolist.yml` — 毎月1日 自動実行

YouTube API で動画一覧を取得し `index.html` を再生成してコミット。
チャンネルの動画が増えたときに自動で反映される。

### `weekly_news.yml` — 毎週木曜 08:00 JST 自動実行

`news/sites.yaml` に登録した各サイトをスクレイプし、前回との差分を検知して `index.html` を再生成してコミット。
手動実行は GitHub Actions の「Run workflow」ボタンからも可能。
