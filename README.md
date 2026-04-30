# mercariauto

メルカリで出品中の全商品を **3日に1回 100円ずつ自動値下げ** するツール(macOS用)。下限は元値の70%(設定で変更可)。

## 仕組み

- **GitHub Actions** が3日ごとに「値下げの時間です」リマインダーメールを Gmail に送信
- メールが届いたら **Mac を開いて手動でスクリプトを実行**(`python -m mercari_auto.main`)
- スクリプトは Playwright でメルカリのマイページにアクセスし、各商品の最終値下げ日を確認して必要なものだけ100円下げる
- 実行結果のサマリーが Gmail に届く

> ⚠️ メルカリの利用規約上、自動化ツールはBANリスクがあります。利用は自己責任で。

## セットアップ (macOS)

### 1. 依存インストール

```bash
brew install python@3.11
git clone <this-repo>
cd mercariauto
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

### 2. 設定ファイル

```bash
cp config.example.yaml config.yaml
```

`config.yaml` を編集して以下を埋める:

- `notify.gmail_user` / `notify.gmail_app_password` — Gmail のアプリパスワード(2段階認証必須、[発行ページ](https://myaccount.google.com/apppasswords))
- `notify.to` — 通知先メールアドレス(通常は同じGmail)
- `pricing.floor_ratio` — 下限比率(デフォルト 0.70 = 70%)

### 3. メルカリにログイン(初回のみ)

```bash
python scripts/login.py
```

ブラウザが開くので、メルカリにログインする(SMS認証/CAPTCHAも完了させる)。マイページに遷移すると `storage_state.json` が保存され、以降は自動で再ログイン不要。

> セッションが切れたら同じコマンドを再実行。

### 4. 動作確認(dry-run)

```bash
python -m mercari_auto.main --dry-run
```

実際の値下げは行わず、何をどう変える計画かをログ出力する。`logs/run-YYYY-MM-DD.log` に記録される。

### 5. 本番実行

```bash
python -m mercari_auto.main
```

実行後、Gmail に「値下げ X件 / スキップ Y件」のサマリーが届く。

## GitHub Actions リマインダー設定

3日ごとにリマインダーメールを送る設定:

1. このリポジトリを GitHub に push
2. リポジトリの **Settings → Secrets and variables → Actions** で以下を登録:
   - `GMAIL_USER` — 送信元 Gmail
   - `GMAIL_APP_PASSWORD` — Gmail アプリパスワード
   - `GMAIL_TO` — 通知先メール(通常 `GMAIL_USER` と同じ)
3. `.github/workflows/reminder.yml` の cron(`0 1 */3 * *` = UTC 01:00 / JST 10:00、3日ごと)を必要なら調整
4. **Actions タブ → Price-down reminder → Run workflow** で手動テスト

## ファイル構成

```
src/mercari_auto/
  config.py     - config.yaml ローダ
  state.py      - SQLite (商品ごとの元値・最終値下げ日時)
  pricing.py    - 値下げ判定(純関数、テスト済)
  mercari.py    - Playwright クライアント
  notifier.py   - Gmail 送信
  main.py       - エントリポイント
scripts/
  login.py          - 初回ログイン(headed)
  send_reminder.py  - GitHub Actions から呼ばれるリマインダー送信
.github/workflows/
  reminder.yml      - 3日ごとの cron
tests/
  test_pricing.py   - 値下げロジックのテスト
```

## テスト

```bash
pytest
```

## 値下げロジック

各商品ごとに:

1. 初めて観測した時の価格を **元値** として記録
2. **下限価格** = `floor(元値 × 0.70)`(メルカリ最低出品価格 300円 を下回らない)
3. 実行時、最終値下げから3日経過していれば 100円下げる
4. 下限に到達した商品はスキップ

実行履歴は `state.db` に SQLite で保持。
