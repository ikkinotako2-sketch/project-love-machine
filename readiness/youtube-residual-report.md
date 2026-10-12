# 残接続候補 — OFFLINE検証済み／本番未有効化

基準: OFFLINE branch 4b881ed39a867769f99613327c6c7653b152c7f0。
旧PASSのVOICEVOX音声、MP4、StrictUploader、SQLite参照台帳、53 Worker契約を再実装しない。

## 新規接続
- GitClaimLedger / GitHubContentsBackend / BoundedGitHubTransport: 指定repositoryの独立plm-execution-state branchのみ。1 GET +最大3 CAS PUT。create-if-absent、SENT前の永続化、Done/UNKNOWN・通知状態を記録。409/timeout/不明SHAは永久STOP。曖昧なstate write後は追加writeも禁止。消費は永久で再claimしない。
- execute_private: scope事前gate→GitHub marker/provenance gate→既存media証拠→永続claim→memory-only fresh ChannelSession→既存StrictUploader→結果保存→callback1回。callback失敗は再uploadに戻らない。
- 本番workflowはNOT_CREATED。本番state branchも未作成。Future outer gateの実GitHub履歴読取・Secret注入を実行可能workflowへ固定するのは認証scopeの解決と別承認後。テストで渡したprovenance factsを本番確認結果に昇格しない。
- Worker connection: 既存runtime compositionを再利用。Generation→enqueue→D1 budget admission→outbox SENT→dispatch mock→bind→既存media hash→render checkpoint→result callback。HMACとは独立したGitHub run/attempt/SHA照合関数必須。default fetch503、cron/consumer disabled。
- D1Admission: D1 withSession('first-primary') / batchインターフェース。追加0011候補は予算・通知の2 tablesと1 triggerのみ。既存0008/0009/0010を変更せずローカルSQLiteで検証。0011は未適用なので本番admissionはBLOCKED_SCHEMA_NOT_APPLIED。migration実行workflowなし。
- ThemeAdapter / ScriptAdapter / MetricsAdapter: rights・capability・scope不足をBLOCKEDへ。任意の無料外部APIへのfallbackなし。既存guidanceを再利用し、成功jobだけ次jobを一意に生成。不明投稿から次jobは作らない。

## 素材・投稿gate
保存済みartifact 11746833809 / run38250671983 は調査時点で未失効。
実MP4 hash 4157384237670fb10ffd83de891d2d207003367601bc5970b0c6a37b13ff2110。
media_gateは固定job/channel、private、notify false、made_for_kids false、synthetic true、台本とVOICEVOX credit、動画仕様、実測字幕区間、voice style、media bytes SHAを機械検証。
今回再レンダリングは0。CIでは旧media検査結果とhashを再利用し、新しいgate分岐だけを検証。実ファイル照合はWorkで実施。
アップロードACKはprocessing完了ではない。既存callback contractのprivate/processed条件には、別途許可された独立readbackが必要。upload結果不明時にstatus recovery PUTや再uploadを追加しない。

## Scope — チャンネル照合identityは消費しない
Google公式 googleapis/google-api-python-client Discovery、youtube.v3.json revision20261001、blob19f8ac1304cb095521f751c5c13ca0fad070af4d のchannels.list.scopesにyoutube.uploadは含まれない。
最小追加scopeはyoutube.readonly。現在のgrantは未読・未証明。過去upload-only認可だけなら不足で、refreshだけでは権限を増やせない。
新コードscope_gateはproven=false又はupload-onlyなら、OAuth/session/state I/O前にSTOP。
既存チャンネル照合branchとidentityは変更・消費しない。既存workflowにはこの新scope gateは未接続のため、現在の承認候補に使わずHOLDする。
Analyticsは必要になった時にyt-analytics.readonlyを別途確認。Google OAuth Testing期限・quota・billing capもlive前に確認。

## 本番起動条件・停止・rollback
全safe flags trueのまま。実動作には別の一度限りoperation grantが必要。
未解決: channel read grant、認証済みchannel一致、state branch/権限の準備、0011 migrationの承認と適用、Worker新sourceの承認とdeploy、immutable ref dispatch受理、callback readback、production provenance/notification配送、無料枠の実残量。
これらの不明をPASSにしない。Cloudflare状態は旧postdeploy証拠を継承し今回fresh remote呼出し0。
24時間観測では2jobs/dayを上限例とし、UNKNOWN・auth expiry・quota/errorで全admission停止し通知。外部通知permissionがなければdurable outboxでBLOCKED_DELIVERYとして保持。
rollbackは自動実行しない。新admission停止→consumed markers/UNKNOWNを保持→別承認のsource復帰。D1破壊的rollback・marker削除・再投稿を禁止。

## 最小の所有者操作
現grantに読み取りscopeがある非秘密証拠を提示できるなら再認可は不要。upload-onlyの場合だけ、既存OAuth client/正しいchannelでyoutube.upload + youtube.readonlyをまとめてoffline-access再認可し、GitHub Secretを安全なUIで置換。値をチャットへ貼らない。
今回この操作・OAuth/YouTube通信を承認として扱わない。scopeが確認された後に、安全な独立successor channel verificationを準備して1回のみ承認する。旧未実行r1を無断consumeしない。
