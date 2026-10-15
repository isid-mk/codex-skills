# 同じテストの実行

作業フォルダーをカレントにし、Node・Pythonのランタイムを確認する。このPCでは既存`automation/実行.ps1`を優先する。

## ローカル確認と接続

1. スキルの`check_workspace.py`を実行する。`pending`があれば保存済み状態を参照確認する。資料変更時は`catalog`で再読込する。
2. `./automation/実行.ps1 doctor`。必要時だけ`catalog`・`accounts`で一覧・回答Excelを確認する。キャッシュやプロファイル名から姓を推定しない。
3. CDPは`http://127.0.0.1:9223`。`src/cdp.ts`のループバック・所有者・専用プロファイル検証を維持する。
4. ローカルCDPだけをプロキシ除外へ追加する。SalesforceのVPN・プロキシ経路は変更しない。
   ```powershell
   $utNoProxy = @($env:NO_PROXY, $env:no_proxy, '127.0.0.1', 'localhost', '::1') | Where-Object { $_ }
   $env:NO_PROXY = $utNoProxy -join ','
   $env:no_proxy = $env:NO_PROXY
   ```
5. 専用Edgeがない場合だけ、以下の2段階の案内をそのまま使う。バッチ画面・起動確認ページと返信文言を統一し、起動確認前にログイン完了を求めない。
   > ① PCで「C:\Users\li4630\Documents\ChatGPT\国民CRM\単体テスト自動化\automation\CDPブラウザー起動.cmd」を実行してください。バッチが約45秒の起動確認を自動で行います。「CDP startup complete」が表示されたら、そのEdgeを開いたまま「PCのバッチで起動確認完了」と返信してください。表示後に追加で45秒待つ必要はありません。
   >
   > ② 起動確認後、CodexがそのEdgeでSalesforce画面を開きます。管理者で手動ログインし、管理者でログイン済みの画面を確認できたら「管理者ログイン完了」と返信してください。

   起動確認ページはログインフォームではない。①の返信後に待受・所有者・専用プロファイルを参照確認し、既存Edgeで指定Sandboxを開いて②へ案内する。起動確認エラーは完了にせず、エラー表示を受けて復旧へ進む。②の返信はログイン操作の完了連絡であり、組織・実ユーザーの照合はCodexが行う。管理者以外は回答Excelの対象ユーザーへ既存の代理ログインを行う。起動済みEdgeは再利用し、対象のログイン状態を確認済みなら該当する準備段階を省略する。別案件ではバッチパスと接続先をその案件のものに置き換える。
6. 非対話端末でログイン待ちを残さない。終了時は自身のrouteだけ解除し、既存CDPブラウザー・コンテキスト・Salesforceタブは閉じない。

## 入力規則テストの必須条件

仕様書の入力条件・基準レコード・期待結果を正とする。保存前に、仕様書で指定されていない検証対象外の必須項目を基準レコードに従って入力する。指定された空欄・未チェック・基準値を、別の必須チェックや入力規則を回避するために補完しない。未指定の必須項目を補完する場合は項目・値・根拠を計画と実施一覧の備考に残す。

2026-10-09の利用者指示により、件名の画面必須チェックが先に働くケースや、報告先不足によって別の入力規則が先に働くケースも、実結果が仕様書の期待結果と異なればNGとして記録する。実際に表示されたエラー・保存可否・表示位置と、目的の入力規則に到達していないことを併記する。期待メッセージを実際の必須エラーに置換しない。自動化の未完了・通信障害で実結果を確認できないケースとは区別する。

必須エラーや別規則エラーを確認した先行試行は履歴とNG判定を残す。再実施が必要な場合も原仕様の条件を維持し、保存済み試行は新規専用レコードを準備する。保存未実施・保存拒否の試行は同一ユーザーの現在保存値が基準値と一致することを参照確認してから再実施する。

## No.58枝番4

再実施元・資料整合性・既存の更新承認を確認する。未確認の保存がないことを確かめてから実行。

```powershell
./automation/実行.ps1 rerun --run $parentRunId --cases O01:58:4
```

コードが組織・ユーザーを画面で照合する。条件を満たすための姓変更は不要・禁止。`state.json`の`pending:null`、画面・設定・最終判定を確認し、終了コード0だけで成功にしない。

今回のIDで追加参照確認する。

```powershell
& $nodeExe automation/scripts/debug/post-result-health.ts $newRunId
```

このスクリプトはNo.58枝番4の保存確認済みOKだけに対応する。氏名一致・通信エラー非出現を30秒観測して画像を出力する。観測時間は遅れて出るエラーの確認であり、要素準備を固定秒数で代用するものではない。他ケースへそのまま使わない。

## 成果物確認

保存先は evidence-format.md に従う。顧客は`エビデンス出力/O01_UT_OBJ_顧客_テスト_<出力日時>/`の同じフォルダに、`O01_UT_OBJ_顧客_テスト実施結果.xlsx`と`O01_UT_OBJ_顧客_テスト仕様書.xlsx`を格納する。出力日時は日本時間の`yyyy-MM-ddTHH-mm-ss`。エビデンスは仕様書単位で、B列ケースNo別の`ケースNo58`等のシートへ各枝番を `エビデンス出力用のテンプレ.xlsx` のケースブロックとして配置する。書式・転記・画像の配置は [evidence-format.md](evidence-format.md) に従う。最新判定は実施一覧に記載する。説明は実施一覧の備考、試行履歴はローカル結果に保持する。

```powershell
$runOutputs = Get-Content -LiteralPath "automation/runs/$newRunId/outputs.json" -Raw | ConvertFrom-Json
$manifestPath = Join-Path (Split-Path -Parent $runOutputs[0].evidence) "O01_report-manifest.json"
& $pythonExe automation/scripts/verify_pilot_output.py "automation/runs/$newRunId" $manifestPath OK
```

上記はNo.58枝番4用。実結果が保留・NGならそれに合う検証をし、OKに固定して失敗を隠さない。枠と実対象、日時・試行対応、エラー表示有無を目視する。ZIP取得日時は保持し、実行日時に置換しない。

Excelだけ再生成：`./automation/実行.ps1 report --run $runId`。実施者・承認者は空欄、原本・式・書式を保持する。成功範囲をNo.58全体・52ファイルへ広げない。

## 基盤を変更したときの回帰検証

専用Edge稼働中は別Edgeを起動する全`test`を走らせない。別ブラウザー検証後に専用Edge終了の事象があり、原因は未確定。以下は実機ブラウザーを起動しない個別検証。

```powershell
& $nodeExe --test --test-concurrency=1 automation/tests/capture-alignment.test.ts automation/tests/browser-lifecycle.test.ts automation/tests/screen-health.test.ts automation/tests/closed-selection.test.ts automation/tests/display-reads.test.ts automation/tests/navigation.test.ts automation/tests/network-diagnostics.test.ts
```

ローカル検証成功と実機完了は分けて報告する。
