# Web-Curation

横浜エリアの情報をまとめた静的サイト。`index.html` をそのまま GitHub Pages で公開する。  
3タブ構成：**動画キュレーション / ニュース・お知らせ / 不動産情報**

## 構成

| ファイル | 役割 |
|---|---|
| `generate_html.py` | `index.html` を生成（全タブ共通。直接 index.html は編集しない） |
| `video/yt_yobinori.py` `video/yt_yuutera.py` | YouTube チャンネルの動画一覧を取得 |
| `video/*_grouped.txt` | 動画一覧のキャッシュ（自動生成） |
| `news/scraper.py` | 各サイトの変更を検知 |
| `news/sites.yaml` | 監視サイトの設定（ユーザーが編集） |
| `news/news.json` | スクレイプ結果（自動生成） |
| `news/snapshots/` | 前回実行との差分検知用（自動生成） |
| `realestate/scraper.py` | 不動産サイトの物件一覧を取得・差分検知 |
| `realestate/sites.yaml` | 監視する不動産サイトの設定（ユーザーが編集） |
| `realestate/realestate.json` | スクレイプ結果（自動生成） |
| `realestate/snapshots/` | 前回実行との差分検知用（自動生成） |

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

## 不動産タブにサイトを追加・変更したいとき

編集ファイル: `realestate/sites.yaml`

`sites:` リストにエントリを追加する。`extract` の値でスクレイパーの処理が切り替わる：

| extract 値 | 対象サイト |
|---|---|
| `globalbase` | Global Base (Renocolle) |
| `meiwa` | 明和地所 tukurite |
| `cowcamo` | cowcamo |
| `rte` | 東京R不動産 |
| `suumo` | SUUMO（駅フィルタあり） |

主なパラメータ：

```yaml
- name: "表示名"
  url: "https://example.com/list/"
  extract: "suumo"
  max_price_man: 9000      # 上限価格（万円）
  min_area_m2: 50          # 下限面積（㎡）
  allowed_prefs:           # 都道府県フィルタ（cowcamo用）
    - "東京都"
    - "神奈川県"
  allowed_stations:        # 駅名フィルタ（suumo用）
    - "みなとみらい"
  max_walk_min: 5          # 徒歩分数上限（suumo用）
  description: "説明文"
```

変更後にローカルで確認：

```bash
cd realestate
python scraper.py   # realestate.json と snapshots/ を更新
cd ..
python generate_html.py
```

新しいサイトを追加する場合は `realestate/scraper.py` に対応する `extract_xxx()` 関数も追加する。

---

## 音楽プレイヤー（yt-history/）

`yt-history/index.html` は YouTube 視聴履歴の閲覧・再生ページ。GitHub Pages では `/yt-history/` で独立したページとして公開される。

| ファイル | 役割 |
|---|---|
| `yt-history/index.html` | 視聴履歴ビューアー（完全クライアントサイド） |
| `yt-history/youtube_history.csv` | 視聴履歴データ（手動で更新） |

**CSVのフォーマット：**

```
視聴日時,タイトル,チャンネル,URL,視聴回数,カテゴリ
2026/05/19 20:24:32 JST,タイトル,チャンネル名,https://...,3,レシピ
```

カテゴリは `レシピ`・`音楽`・空欄（その他）の3種類。空欄の行は「その他」タブに表示される。

履歴を更新するときは `youtube_history.csv` を差し替えて `git push` するだけ。ビルドスクリプト不要。

---

## GitHub Actions

### `update_videolist.yml` — 毎月1日 自動実行

YouTube API で動画一覧を取得し `index.html` を再生成してコミット。

### `weekly_news.yml` — 毎週木曜 08:00 JST 自動実行

`news/sites.yaml` に登録した各サイトをスクレイプし、前回との差分を検知して `index.html` を再生成してコミット。

### `daily_realestate.yml` — 毎日 09:00 JST 自動実行

`realestate/sites.yaml` に登録した不動産サイトの物件一覧を取得し、前回との差分（新着物件）を検知して `index.html` を再生成してコミット。  
手動実行は GitHub Actions の「Run workflow」ボタンからも可能。
