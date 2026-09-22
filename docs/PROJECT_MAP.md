# Project Map

このリポジトリ全体の正式名称は **Project Love Machine (PLM)** です。

## 役割ごとの名前

| Name | Role | Current status |
|---|---|---|
| PLM Core | 共通基盤・設定・ジョブ管理 | Account/Social初期版実装済み |
| PLM Content Engine | テーマ、台本、字幕、投稿文の生成 | n8n/Geminiで稼働中 |
| PLM Render Cloud | VOICEVOX + FFmpeg + Quality Gateで動画生成 | GitHub Actionsで初回成功 |
| PLM YouTube Pipeline | RenderからYouTube結果までの一括実行 | v1実装済み |
| Pipeline Result Fetcher | job_idだけでPipeline結果をHTTP取得 | v1実装済み |
| PLM Social Hub | 各SNSへの投稿Adapterをまとめる層 | 共通Interface・再試行・重複防止を実装済み |
| PLM YouTube Adapter | YouTube投稿・予約・状態・分析 | v1実装・private実投稿成功 |
| PLM Bluesky Adapter | Bluesky投稿・反応取得 | 既存n8n基盤あり |
| PLM Live Engine | Twitch / ツイキャス等のLIVE配信共通基盤 | Planned |
| PLM Note Adapter | note記事生成・下書き・公開支援 | Planned |
| PLM Account Manager | 複数アカウントの設定・認証・実行順管理 | 設定Registry・100件検証を実装済み |
| PLM Improvement Engine | 投稿結果から次回改善を決める | YouTube v1 実装。Geminiレビューは任意キー設定後 |
| PLM Trend Radar | YouTube等の編集・コンテンツ傾向監視 | Planned |
| PLM Tool Radar | GitHub OSS / MOGEの新技術を監視 | Planned |
| PLM Quality Gate | 動画・音声・字幕・出力品質の検査 | 初期版稼働 |
| PLM Command Center | 結果・エラー・日時の閲覧画面 | YouTube V2最小版実装、全SNS・収益は未実装 |

## 既存n8nワークフローの整理

### YouTube V1
- 旧安定版
- 触らず保管
- ローカルVOICEVOX / FFmpeg依存あり

### YouTube V2
正式名称: **PLM YouTube Shorts V2**

役割:
- GeminiでV2 payload生成
- title / hook / narration / scenes / captions / bgm を出力
- Cloud Render Payloadを作る
- GitHub Actionsへ送る

### Cloud Render Payload
正式名称: **PLM Render Request**

必須フィールド:
- title
- hook
- narration
- speaker
- scenes
- captions
- bgm
- output

### GitHub workflow
正式名称: **PLM Render Cloud**

File:
`.github/workflows/render-short.yml`

役割:
- GitHub-hosted runnerを起動
- VOICEVOX Engineを起動
- FFmpegでShortsを生成
- Quality Gate
- MP4を出力

## 今後のフォルダ構成

```
project-love-machine/
├─ plm/
│  ├─ account_manager/
│  └─ social_adapters/
├─ core/
├─ config/
│  ├─ accounts/
│  ├─ platforms/
│  └─ styles/
├─ content-engine/
├─ render-worker/
├─ social-adapters/
│  ├─ youtube/
│  ├─ bluesky/
│  ├─ twitch/
│  ├─ twitcasting/
│  ├─ note/
│  ├─ patreon/
│  ├─ tiktok/
│  ├─ instagram/
│  └─ x/
├─ live-engine/
├─ account-manager/
├─ improvement-engine/
├─ trend-radar/
├─ tool-radar/
├─ dashboard/
├─ tests/
└─ .github/workflows/
```

現在の実装では、Pythonから利用する共通基盤を `plm/` パッケージに配置する。
`config/accounts/` は秘密情報を含まないアカウント設定、`config/platforms/` は
Adapterの接続状態と検証方針を保持する。既存の `render-worker/` と
`render-short.yml` は独立しており、今回の共通基盤から変更していない。

## Account Manager v1

- `account_id`: `<platform>_<genre>_<number>`
- 対応ID: YouTube / Bluesky / Twitch / TwitCasting / note / Patreon / TikTok / Instagram / X
- 最大100件を設定ファイルから一括読み込み
- `enabled: false` が既定
- 認証情報本体は禁止し、`n8n://` / `github-secret://` / `env://` の参照のみ保持
- 同一ID、platform不一致、上限超過、秘密情報らしいキーを拒否

## Social Adapter v1

共通処理:
- account解決
- Adapter選択
- 有効/無効判定
- 投稿・予約投稿の振り分け
- 有限再試行
- idempotency keyによる重複防止
- 共通PostResult / PostState / AnalyticsSnapshot

SNS固有処理:
- 公式APIのリクエスト形式
- 認証更新
- メディアアップロード
- 状態・分析値のマッピング
- 公式仕様に基づくrate limit判定

詳細は `docs/SOCIAL_ADAPTER_SPEC.md` を正式規格とする。実API Adapterは、
現行の公式仕様・費用・利用条件を検証するまで有効化しない。

## YouTube Adapter v1

- `videos.insert` のresumable upload
- `status.publishAt` によるprivate動画の未来時刻予約
- `videos.list` によるupload / processing / privacy状態取得
- YouTube Analytics `reports.query` による動画単位の共通指標取得
- HTTP 429 / 500 / 502 / 503 / 504と通信障害だけを一時エラーとして再試行
- quota・認証・入力・ポリシーエラーは恒久エラーとして即時停止
- n8nから `youtube-adapter.yml` をworkflow dispatchして呼び出し
- 同一Adapterを全YouTubeアカウントで共有し、認証Secretだけを切り替え

公式仕様と運用境界は `docs/YOUTUBE_ADAPTER_V1.md` を参照する。OAuth接続済み
アカウントでprivate実投稿とvideo_id取得まで成功している。既存YouTube V1は維持し、
Render CloudとAdapterには単独実行を保ったまま再利用用入口と結果出力だけを追加する。

## YouTube Pipeline v1

- n8nは `.github/workflows/youtube-pipeline.yml` を1回dispatchする
- `job_id`を同じ`render_id`とidempotency keyとして全工程で使用
- Render Run IDとArtifact名はGitHub Actions内で自動的に受け渡す
- 既存`render-short.yml`と`youtube-adapter.yml`をreusable workflowとして呼ぶ
- YouTube結果はReusable Workflow outputではなく既存の安全なArtifactで受け渡す
- 最終結果を`pipeline-result-<job_id>`へ保存
- `failed_stage`でRender Request、VOICEVOX、Render、Quality Gate、YouTubeを識別
- 投稿はprivateが既定で、既存の二重投稿防止をそのまま使用

入力・出力契約は `docs/YOUTUBE_PIPELINE_V1.md` を正式仕様とする。

## Pipeline Result Fetcher v1

- Pipeline開始時に`processing`を`plm-results`ブランチへ保存
- Pipeline終了時に同じ`job_id`のJSONを`succeeded`または`failed`へ更新
- n8nは固定形式のRaw URLを1回GETし、Run ID / Artifact ID探索を不要化
- 公開JSONはstatus / video_id / youtube_status / youtube_url / failed_stage /
  errorの許可項目だけに限定
- 従来の30日間保持artifactは互換性のため継続
- 詳細: `docs/PIPELINE_RESULT_FETCHER_V1.md`

## PLM Command Center 最小版

- `docs/COMMAND_CENTER.md` は公開済み `plm-results` 結果JSONから生成する読み取り専用一覧
- job_id / status / video_id / youtube_url / failed_stage / error / 実行日時を最大200件表示
- `.github/workflows/command-center.yml` が毎時更新し、手動更新にも対応
- n8nのExecution、Render、YouTube投稿を追加実行しない
- private動画の閲覧権限は変更しない。全SNS・収益集約は次段階

## YouTube Improvement Engine v1

- 別のGitHub Actionsが毎時、成功結果の確定時刻から約1h/24h後に指標を観測する
- `videos.list` のviews/likes/commentsを保存し、Analytics権限・反映状況に応じて視聴維持と登録者指標を補う
- 指標が未反映ならnull、収集し損ねた過去の時点は`missed`。最大3回の一時エラー再試行
- 結果は`plm-results/improvement-results/<job_id>.json`に分離。投稿Pipelineは非依存
- 一般化された7項目の改善JSONと最新フィードバック`latest.json`を生成する
- Gemini APIキーがない場合は`analysis_method=rules`。無料枠キー設定後はGeminiレビュー可能
- 詳細: `docs/YOUTUBE_IMPROVEMENT_V1.md`

## 命名ルール

- 全体: `PLM`
- GitHub上の処理: `PLM <役割>`
- n8nワークフロー: `PLM - <Platform> - <Purpose>`
- アカウントID: `<platform>_<genre>_<number>`
- Style profile: `<platform>_<genre>_v<number>`

例:
- `PLM - YouTube - Shorts V2`
- `PLM - Bluesky - Auto Post`
- `youtube_game_001`
- `youtube_game_v3`

## 開発方針

1. まずGitHub OSS / MOGEで再利用できるものを探す
2. ライセンス・更新頻度・安全性を確認
3. GitHub Actionsでテスト
4. 足りない部分だけ自作
5. n8nは「司令塔」、重い処理はGitHub側へ寄せる
6. 同じ処理を100個複製せず、共通基盤 + account configで増やす

## 次の優先実装

1. 修正後Pipelineをprivateで1回再実行し、video_id / status / URLのhandoffを確認
2. pipeline resultをGoogle Sheets / Command Centerへ自動記録
3. durable idempotency / job state store（無料構成を優先）
4. 既存n8n資産を移植するBluesky Adapter
5. Command Centerへaccount/job/error状態を公開
