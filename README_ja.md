# AUDIT-VIEWER

[English README](README.md)

[claude-audit](../claude-audit) / [codex-audit](../codex-audit) / [antigravity-audit](../antigravity-audit) の**実行・閲覧・日時比較**を行うローカル GUI ツールです。
各社 AI コーディングエージェントのローカル監査結果を、共通スキーマで統合管理することを目的としています。

> **Unofficial project.** Not affiliated with Anthropic or OpenAI.

## 特徴

- **Python 標準ライブラリのみ** — pip install 不要、`python3 audit_viewer.py` で起動
- **英語 / 日本語 UI** — デフォルトは英語。右上のボタンで日本語に切替（選択はブラウザに保存）
- **ローカル専用** — 127.0.0.1 のみで待ち受け。監査データは外部に送信されません
- **スナップショット管理** — 実行結果を `snapshots/<tool>_<UTC日時>.json`（mode 600）として保存
- **.env で設定変更可能** — 監査スクリプトの場所・ポート・スナップショット保存先
- **拡張可能** — 共通スキーマに従う監査スクリプトなら .env への1行追加で対応可能

## 機能

### 1. 監査の実行
ツールを選択して「実行」を押すと、登録された監査スクリプトを `--json` で実行し、タイムスタンプ付きスナップショットとして自動保存します。

### 2. 閲覧
スナップショットをクリックすると表示:
- WARN / REVIEW / INFO のサマリカード
- 重大度フィルタ付きの findings テーブル
- インベントリのタブ表示（MCP サーバ・projects・hooks・plugins・automations・skills・retention 等）

### 3. 日時比較
同一ツールのスナップショットを2つ選択すると差分を表示:
- サマリ件数の増減（+/-）
- findings の追加（緑）/ 削除（赤）
- インベントリ項目の追加・削除・**フィールド単位の変更**（例: MCP サーバのコマンドや env が変わった場合に新旧を並記）

新しい MCP サーバの出現、信頼済みプロジェクトの追加、フックの変更など、前回監査からの環境変化を一目で確認できます。

## インストールと起動

```sh
cp .env.sample .env     # 環境に合わせてパス等を編集
python3 audit_viewer.py                       # ブラウザが自動で開く
python3 audit_viewer.py --no-browser --port 8765
python3 audit_viewer.py --snapshots-dir /path/to/snapshots
```

Windows では PowerShell から `python audit_viewer.py`（または
`py -3 audit_viewer.py`）で起動します。

`.env` が無い場合は、監査ツールが隣接ディレクトリ（`../claude-audit`、`../codex-audit`、`../antigravity-audit`）にある前提のデフォルト値で動作します。スクリプトが見つからないツールは一覧に出たうえで選択不可になるため、実際に使うものだけ用意すれば構いません。Windows では PowerShell 版、macOS では zsh 版を自動選択します。

> macOS のシステム python3 が Xcode ライセンス未同意で動かない場合は
> `/opt/homebrew/bin/python3 audit_viewer.py` を使うか、`sudo xcodebuild -license` に同意してください。

## 設定（.env）

| キー | デフォルト | 説明 |
|---|---|---|
| `CLAUDE_AUDIT_SCRIPT` | OS 別の隣接スクリプト | claude-audit のパス |
| `CODEX_AUDIT_SCRIPT` | OS 別の隣接スクリプト | codex-audit のパス |
| `ANTIGRAVITY_AUDIT_SCRIPT` | OS 別の隣接スクリプト | antigravity-audit のパス |
| `SNAPSHOTS_DIR` | `snapshots` | スナップショット保存先 |
| `PORT` | `8765` | HTTP ポート（`--port` でも上書き可） |
| `TOOL_<ID>` | — | 追加ツールの登録: `<ラベル>:<スクリプトパス>` |

相対パスは audit-viewer ディレクトリ基準で解決されます。

## ディレクトリ構成

```
audit-viewer/
├── audit_viewer.py   # HTTP サーバ + 監査実行 + diff エンジン
├── index.html        # シングルページ GUI
├── .env.sample       # 設定テンプレート（.env にコピーして使用）
├── snapshots/        # 保存された監査結果（git 管理外推奨）
└── README.md
```

## 監査ツールの追加方法

他社の audit プログラムを統合するには、`.env` に1行追加します。

```ini
TOOL_GEMINI=gemini-audit:../gemini-audit/gemini_audit.sh
```

監査スクリプト側の前提は、`--json` で以下の**共通スキーマ**を出力することだけです:

```json
{
  "timestamp": "...", "hostname": "...", "username": "...",
  "summary": { "warn": 0, "review": 0, "info": 0 },
  "findings": [ { "severity": "WARN|REVIEW|INFO", "section": "...", "message": "...", "detail": "..." } ]
}
```

トップレベルにオブジェクト配列を追加すると、閲覧画面のタブとして自動表示されます。diff の対象にするには `audit_viewer.py` の `INVENTORY_KEYS` に同一性判定フィールドを登録してください。

## API

| Method | Path | 説明 |
|---|---|---|
| GET | `/api/tools` | 登録ツールと利用可否 |
| GET | `/api/snapshots` | スナップショット一覧 |
| GET | `/api/snapshot?file=NAME` | スナップショット本体 |
| GET | `/api/diff?old=A&new=B` | 2スナップショットの差分（同一ツールのみ） |
| POST | `/api/run` `{"tool":"claude"}` | 監査を実行して保存 |
| POST | `/api/snapshot/delete` `{"file":NAME}` | スナップショット削除 |

## 動作要件

- Python 3.9+（標準ライブラリのみ）
- 監査スクリプトの動作要件（macOS / zsh / jq）はそれぞれの README を参照

## セキュリティ上の注意

- スナップショットには設定パス・プロジェクト一覧などの環境情報が含まれます。リポジトリにコミットしないよう `snapshots/` を `.gitignore` に追加してください
- サーバは認証を持たないローカル開発用ツールです。127.0.0.1 以外にバインドしないでください

## License

MIT
