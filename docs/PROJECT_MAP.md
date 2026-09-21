# Project Map

このリポジトリ全体の正式名称は **Project Love Machine (PLM)** です。

## 役割ごとの名前

| Name | Role | Current status |
|---|---|---|
| PLM Core | 共通基盤・設定・ジョブ管理 | Planned |
| PLM Content Engine | テーマ、台本、字幕、投稿文の生成 | n8n/Geminiで稼働中 |
| PLM Render Cloud | VOICEVOX + FFmpeg + Quality Gateで動画生成 | GitHub Actionsで初回成功 |
| PLM Social Hub | 各SNSへの投稿Adapterをまとめる層 | Planned |
| PLM YouTube Adapter | YouTube投稿・状態取得 | V1/V2で一部稼働 |
| PLM Bluesky Adapter | Bluesky投稿・反応取得 | 既存n8n基盤あり |
| PLM Live Engine | Twitch / ツイキャス等のLIVE配信共通基盤 | Planned |
| PLM Note Adapter | note記事生成・下書き・公開支援 | Planned |
| PLM Account Manager | 複数アカウントの設定・認証・実行順管理 | Planned |
| PLM Improvement Engine | 投稿結果から次回改善を決める | Planned |
| PLM Trend Radar | YouTube等の編集・コンテンツ傾向監視 | Planned |
| PLM Tool Radar | GitHub OSS / MOGEの新技術を監視 | Planned |
| PLM Quality Gate | 動画・音声・字幕・出力品質の検査 | 初期版稼働 |
| PLM Command Center | 全SNS・エラー・収益・実行状態の監視画面 | Planned |

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
