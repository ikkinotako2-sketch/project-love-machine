# Work単独 YouTube OFFLINE実装 — 2026-10-12

## 実行範囲
main e2732570e26b40fc8e10c9422379b01a37486880 を基準に、新しい独立branchで実装。
既存VOICЕVOX、FFmpeg、Quality Gate、投稿pipeline、adapter、Metrics/Improvementは変更しない。
OAuth r1/r2 marker、チャンネル照合branch d6733481fffa16fcdc8d53d0fad46fd64301d237 は変更も消費もしない。
Cloudflare sandbox 8d6bd43d17b1a0cb787897285694ca7adb713e1c のsource/schemaを、完全同一bytesのOFFLINE fixtureとして再利用。Sandboxへの書き込みなし。

## 動画
固定job plm-private-channel-recovery-20261012-r1。
オリジナルの技術確認台本、FFmpegの図形のみ、音楽・外部素材・キャラクター画像なし。
VOICEVOX:ずんだもん（ノーマル、speaker 3）を利用。ローカルengineのspeakersレスポンスで実際の名前とstyle一致を確認してから音声生成。
VOICEVOX規約 https://voicevox.hiroshiba.jp/term/ と音源規約 https://zunko.jp/con_ongen_kiyaku.html に基づき説明欄にクレジットを固定。許可された用途の技術確認動画であり、政治・宗教・情報商材・フェイク等には使わない。音源の所有権をユーザーが持つという主張はせず、ライセンスに基づく利用。
文章ごとに既存generate_voiceを使用しPCMを連結。その実測フレーム数で字幕区間を決める。字幕は文単位同期であり、単語ごとの強制アラインメントは未実装。
1080×1920、30fps、H.264/AAC、字幕、明度、音量、duration、FFmpeg全体decodeを検証。最終MP4と音声・字幕hashはCI artifactのrender-evidence.jsonで固定する。
既存renderer dependenciesと同じVOICEVOX cpu-latestを使用し、実際のimage IDをartifactへ保存。モデルや依存versionが変われば音声hashも変わるため、将来アップロードは今回のartifact SHAへ固定して再生成を代用しない。
private、notify false、made_for_kids false（成人向け技術確認）、contains_synthetic_media trueを固定。

## Strict one-shot
plm/automation/strict_upload.py は既存legacy APIを置換しない独立経路。
POST init 1回、media PUT 1回、status query 0、resume/retry/redirect/fallback 0。
SQLite reference ledgerのunique job/identityとSENT永続化が最初のPOSTより先。
mediaを非公開・unlink済み一時fileへsnapshotし、その同一descriptorでhash検証と送信を行う。upload session URLのHTTPS/host/path/queryを検証し、別host・userinfo・二重query・redirectを拒否。
タイムアウト、308、HTTP失敗、ACKのchannel/privacy不一致、不正JSONはUNKNOWNへ永久隔離。POST/PUTの後に別認証通信は追加しない。
同一memory-only ChannelSessionをfresh channels.mineレスポンスとuploadに使用する。実チャンネル一致はUNVERIFIEDのまま。古いOAuth PASS/公開チャンネル情報をfresh channel proofに代用しない。
TokenはSession reprから除外、API error本文は読まず、固定reason codeだけ保存。Sessionはpreflight失敗時もclearする。
Upload marker schemaと純粋なhistory/source gateを用意。新identityは候補のみ、marker未作成。

**本番execution workflowは作成していない。** LedgerはOFFLINE SQLite参照実装で、GitHub hosted runner間の本番durable storeではない。未来の実投稿前には、実際の永続claim/markerとこのgateの接続を別承認下の準備で固定する必要がある。`facts`はテストで注入する値であり、それだけで実GitHub provenance確認済みとは扱わない。

## ローカルループ
テーマ・台本・Metricsは明示mock。実動画を投稿mockへ渡し、結果をSQLiteへ保存、既存guidance関数を再利用して改善仮説を記録。
Pending/Processing/Done/Failed/UNKNOWN、claimのowner/epoch/fence、lease、永久tombstone、競合CAS、crash後UNKNOWN回収、ローカル通知outbox、成功率/進捗JSONを追加。
SENT前のleaseだけ再取得可。SENT後はTTL切れでも再送不可。
予算はjob/minute/API unit/bytesの上限見積りをatomicに予約する。例示設定は2job/day、40minute/dayであり、実利用枠の確認結果ではない。超過時停止。有料fallbackなし。
24時間の定期tickを仮想時刻で検証。実cronは0、Worker factory/consumerは有効化しない。一般生成の失敗は通知して停止し、投稿を伴わない独立renderの再実行だけを将来明示的に設計する。
通知はdurable local outboxまで。外部通知配送、liveテーマ取得、live台本生成、analytics認証、production durable ledger、Worker→Actionsの本番起動は未接続。

## Cloudflare契約
sandbox source fixtureは、本番を変更するコードではない。
0008/0009/0010 SQLをローカルSQLiteだけへ適用し、既存runtime compositionの53契約テストを再利用。
Generation→Queue→claim→outbox SENT→dispatch mock→exact run binding→render checkpoint→HMAC callback→COMPLETE。
owner/fence、payload/workflow hash、attempt1、replay、timeout/no resend、PARKED/disabled cron/consumerを検証。
過去のparked postdeploy成功はhistorical evidence。今回のOFFLINE Workerテストをfresh remote inspectionとは扱わない。
本番のoperational ledger/route/key readiness、immutable ref dispatch acceptance、runtime activationは未承認・未検証。

## 次の最小作業
チャンネル照合r1は既存準備をそのまま使う。新しい再認可やSecret手動更新は現在要求しない。
ユーザーが通信再開を承認した場合だけ、既存チャンネル照合identityでrefresh POST max1 + channels.mine GET max1。
一致PASS後、今回の動画artifact/hashを再利用し、本番durable storeとmarker gateを接続する単発upload専用workflowを固定してから別途upload承認。
チャンネル照合の承認をuploadやCloudflare activationへ拡大解釈しない。
24時間運用前にはGoogle Testingによるrefresh token期限、grant/quota、$0利用枠、監視通知、閉ループE2Eの検証が必要。これらが不明なら停止。
