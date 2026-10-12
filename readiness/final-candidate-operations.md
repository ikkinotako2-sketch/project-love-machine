# OFFLINE統合候補／本番未承認

基準：残接続0b2ae2b5e1031eb7336e57abf0a632141b2d44b6。
既存MP4、renderer、VOICEVOX、StrictUploader、SQLite Ledger、Worker schema/runtime、署名・binding契約を再利用。
既存main・OAuth・チャンネル照合・sandbox branchは変更しない。

## 実装した接続

IntegratedCandidate：ThemeAdapter → ScriptAdapter → 保存済みrender/Quality Gate → budget → Ledger claim → fixture channel/session/scope → StrictUploader → durable result → callback ACK → MetricsAdapter → improvement → 次job。
Scriptは既存の固定テスト動画の台本を使用し、そのbytesを動画証拠と比較する。任意の新台本はこの保存済み動画に載せ替えない。新テーマの実動画には既存rendererでの新renderが必要。
Pythonの実動画uploadモック結果をJSONでNodeの既存Worker fixtureへ渡し、同じjob/media/video identityでcheckpoint/binding/result、HMAC、独立provenanceを確認。processed/private readbackは明示的MOCK_ONLYであり、実YouTube処理完了証明ではない。
実動画の台本・字幕区間からWorker形式のscriptを構築し、raw SHA256をPython/Node間で完全一致させる。保存済みasset再利用を検証しており、Worker既存mapCheckpointのspeaker=1で新しく生成した動画とは主張しない。新render時のvoice=3の設定は新successor mappingで明示固定が必要な残接続。

Journalは停止状態・未配送outbox・callback状態をSQLiteへ保持。SENTクラッシュやDone後callback未確認を再起動時に隔離。48時間仮想時計は4件、2件/dayまで。異常fixtureはAPI/render/Actions/Worker/重複/D1・GitHub不明/upload不明/auth/quota/free-budget/callback/signature/SHA/artifact/secret/rights/emergencyを検証。
外部通知は送信しない。outbox delivered=0を表示。

## 本番入口とState

production-candidate-parked workflowはjob if=false、Secret参照0、通信コード0。entrypointも無条件PARKED。safe flagsをfalseへ変えてもlive factoryは存在しない。
publication_gateはsource/workflow/commit/run attempt/marker/media origin/expiry/scope/channel/budget/provenanceを全件要求する純粋validator。本番からfactsを検証・供給するlive wrapperは未接続であり、テストのtrueを本番証明にしない。

GitHub Contents backendはexact repository / plm-execution-state / youtube-once/*.jsonへ限定。GET/PUT不明はプロセス内latched STOP。
ExclusiveGitClaimLedgerはglobal create-if-absent tombstoneを先に保存。ACK喪失時に別runnerから別jobで再起動しても既存tombstoneで停止。guard2＋job4＝最大6 GitHub request、retry0。**これは単発専用であり再利用scheduler lockではない。** 成功時もrelease/deleteしない。
State branchは未作成。将来の明示承認で正確なrepository・initial commitを固定し、Contents writeだけのfine-grained token又はApp tokenを利用する。branch限定API権限を仮定しない。コードとrulesetでmain書込拒否を追加確認。Secret名PLM_GITHUB_STATE_TOKENは候補のみ、未登録。runnerローカルSQLiteを跨runner本番durabilityの証拠にしない。
一日2job以上の実運用には新しい長期shared admission/state lifecycleとレビューが必要。今回未実装部分を24時間稼働完成とは報告しない。

## Cloudflare適用計画（実行不可）

0008/0009/0010は既存FULL_APPLIED証拠継承、今回remote確認0。
0011は候補のまま。schema構造・protected rowsのexact precheck、予算2jobs/1000unit、対象DB、SQL path/SHA256、exclusive window、future独立consumed markerを固定した別承認が必要。
DDLのACKだけでは完了としない。別承認read-only postcheck必須。UNKNOWNで再送しない。
Worker source更新にもfresh source/exposure/D1 binding/key metadata/target identity/最小権限と独立markerが必要。既存deploy/postcheck identityは永久再実行禁止。
現WorkerはPARKEDの既存証拠を継承。新candidateは未deploy。新live factory、cron、consumer、routes、immutable dispatch acceptance、独立run provenance readerが本番blocker。

## OAuth／投稿／観測の最短順

1. 本人が既存client/対象channelでyoutube.upload＋youtube.readonly再認可。Secretを本人UIで安全登録。Testing公開状態・token期限は未確認。Testingで外部YouTube scopeのrefresh tokenは通常7日失効するため、長期運用前にGoogleの正規production-readinessを確認（無断設定変更なし）。
2. 未消費channel identityのgateを最新証拠で再監査後、POST1＋channels.mine GET1を別承認。scope不足/UNKNOWN/channel mismatchは投稿禁止。
3. 認証とchannel一致後、動画artifactが未失効、media SHA exact、durable state、fresh budget、operation、rights/credit/audience/synthetic/private/no notifyを固定した新upload execution preparationをレビュー。upload専用identityは未消費。
4. private1本はinit POST1＋media PUT1だけ、retry/resume0。upload ACK不明は永久UNKNOWN。Callbackに必要なprivate/processed readbackは別承認、HMACだけでGitHub provenanceやYouTube処理完了を主張しない。
5. 単発成功後にshared loop/deploy/migration/activationの別承認。24h観測は最大2jobs、全サービスの実残量がunknownならadmission0。固定reason、claim conflict、render率、実API回数、callback遅延、未配送outboxを観測。

## 無料枠

プラットフォーム一般の公開上限と実account残量は別。実残量はUNKNOWNでlive gate停止。
GitHub公開repoのstandard hosted runnersの実行は無料。Artifact保持はこのCI7日、既存動画は2026-11-11T12:43:33Zまで（2026-10-12 metadata確認時点）。retention/課金設定が未確認なら長期運用不可。
Workers Free100000requests/day、D1 Free5million rows read/day、100000 rows write/day、5GB共有。アカウント内の他プロジェクト使用量は不明。
YouTube quotaはprojectの実quotaとmethod別計数を確認。古い一律upload1600units等を固定しない。候補内units200はsimulation予算であり、公式upload単価・実残量を証明しない。
公式参照：
https://docs.github.com/en/billing/concepts/product-billing/github-actions
https://developers.cloudflare.com/workers/platform/limits/
https://developers.cloudflare.com/d1/platform/pricing/
https://developers.google.com/youtube/v3/determine_quota_cost
https://developers.google.com/identity/protocols/oauth2

## 停止／復旧／rollback

停止時はadmission0、未配送通知を保持。UNKNOWN jobと全consumed tombstonesは削除・再claim・再uploadしない。
GitHub write不明の場合は追加writeも禁止。global tombstoneが不明な場合は新runnerもread-onlyに停止。
コード復帰・Worker修復・notification配送は別承認。D1破壊的rollbackや自動rollbackなし。
資格情報をlog/結果/commitへ保存しない。公開Command Centerはallowlist字段とHTML escapeのみ。真の利用規約・素材権利・ユーザー同意・OAuth審査はコードテストのPASSで代替しない。
