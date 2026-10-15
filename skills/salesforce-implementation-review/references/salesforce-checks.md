# Salesforce静的レビュー観点

実装種別に該当する観点だけを適用する。個々の制限値、サポート操作、リリース固有挙動は対象APIバージョンのSalesforce公式資料で再確認する。

## 共通

- 設計の実行条件、分岐、項目、値、順序、成功・失敗結果が実装と一致するか
- 設計にない処理、ハードコード、環境固有ID・名称・URLがないか
- 標準機能で実現できる要件を不要に個別実装していないか
- 同じ業務ルールが複数のFlow、Apex、Validation Rule等へ重複していないか
- NULL、空文字、0、未設定、削除済み参照、重複、境界値を区別しているか
- 全成功、部分成功、ロールバック、再送、再実行時の結果が設計されているか
- 実行ユーザー、共有、CRUD/FLS、権限セット等による結果差を考慮しているか
- 監査ログや例外ログに個人情報、アクセストークン、機密データを出していないか
- メタデータ間の参照、削除・改名影響、配備順、APIバージョンが整合するか
- ラベルではなくAPI名で参照すべき箇所、逆に翻訳・表示ラベルを使うべき箇所を取り違えていないか

## Apex・Trigger・非同期処理

- 複数レコードを前提とし、SOQL、DML、callout、重い計算をレコード単位ループで実行していないか
- SOQL回数だけでなく、取得行数、DML文数・行数、CPU、ヒープ、callout、非同期投入数等をトランザクション全体で評価しているか
- Triggerの実行イベント、before/after、再帰、他のFlow・Triggerとの実行順序を考慮しているか
- MapやSetのキーが業務上・Salesforce上の一意性を満たすか。DeveloperName、Name、外部ID等のスコープを確認する
- `with sharing`、`without sharing`、`inherited sharing` と実行入口の組合せが意図どおりか
- CRUD/FLSの強制が必要な入口で、ユーザーモード、`stripInaccessible` 等の適切な方式を使っているか
- 動的SOQL/SOSLでバインドまたはエスケープが不足していないか
- DMLのall-or-none、`Database.SaveResult`、例外再送出、Savepointの範囲が設計と一致するか
- catchが例外を握りつぶして成功扱いにしていないか。`LimitException` 等、捕捉・回復できない例外を誤解していないか
- Queueable、Batch、Scheduled、Future等の選択、連鎖、重複実行、再試行、順序、callout可否が妥当か
- Batchのscope単位、stateful状態、失敗単位、finish処理、再実行時の冪等性を考慮しているか
- setup objectとnon-setup objectのDML、共有・公開グループ変更、ロック競合等の特殊仕様を確認したか

## Flow

- 種別、トリガー条件、実行タイミング、Fast Field UpdatesかActions and Related Recordsかが設計と一致するか
- 実行コンテキストと共有・権限の扱いが意図どおりか
- レコードトリガーFlowの再入、更新ループ、他Flow・Apexとの循環がないか
- ループ内にGet/Create/Update/Delete、Subflow、Apex Action等を置いていないか
- Collection処理で複数件を保持し、更新をまとめているか
- Get Recordsの件数、並び順、最初の1件取得の決定性が十分か
- Decisionの既定経路、NULL、未一致、境界条件が定義されているか
- Fault Pathが必要な処理にあり、失敗を成功として隠していないか
- 非同期パス、Scheduled Path、Pause、Platform Event等のトランザクション境界と重複実行を考慮しているか
- 有効版、開始条件、APIバージョン、参照Subflow/Apex Actionの配備状態が整合するか

## Validation Rule

- 設計の対象レコードタイプ、ユーザー、状態、操作種別を正しく限定しているか
- `ISNEW`、`ISCHANGED`、`PRIORVALUE`、`BLANKVALUE`、`ISBLANK` 等の意味を取り違えていないか
- NULL、空文字、数値0、選択リスト、複数選択リストの扱いが設計と一致するか
- 条件のAND/OR優先順位、否定、境界値、日付・日時・タイムゾーンが正しいか
- データ移行、連携ユーザー、管理者、承認プロセス等の例外条件が過剰または不足していないか
- 他のValidation Rule、Flow、Apex、必須項目と競合して更新不能にしないか
- エラーメッセージと表示位置が、利用者が修正できる内容になっているか

## 権限・共有

- Profile、Permission Set、Permission Set Groupの役割分担と最小権限が保たれているか
- オブジェクト権限、FLS、システム権限、Apex Class、Flow、Custom Permission等の依存が揃うか
- Muting Permission Setを含む実効権限を単一ファイルだけで判断していないか
- OWD、Role、Sharing Rule、Team、Manual Share、Apex Managed Sharing等との組合せを確認したか
- View All、Modify All、View All Data、Modify All Data等の強い権限が必要以上に付与されていないか
- 権限削除・名称変更時に、利用者や自動処理を意図せず停止しないか
- 実装が権限不足を迂回する場合、その必要性と監査方法が設計されているか

## オブジェクト・項目

- API名、データ型、桁数、小数、必須、初期値、ユニーク、外部ID、大文字小文字区別が設計と一致するか
- Lookup/Master-Detail、削除動作、親子件数、共有継承、積み上げ集計の影響を確認したか
- 選択リスト値、Global Value Set、制限付き選択リスト、レコードタイプ別値が整合するか
- 数式、Roll-Up Summary、自動採番、暗号化項目等の特殊な読書き制約を考慮しているか
- 項目の改名・削除・型変更がApex、Flow、Validation Rule、レポート、連携へ与える影響を確認したか
- 標準項目とカスタム項目、Person Account等の有効機能に依存する違いを確認したか

## テストコード・提供テスト結果

- `SeeAllData=false` を基本とし、必要な設定・データをテスト自身が準備するか
- 固定のProfile名、ユーザー名、組織データ、日時、既存レコードの不在等に依存していないか
- 成功したことだけでなく、期待するレコード、項目、件数、削除、非変更を厳密にassertするか
- 誤った実装へ変えたときにテストが失敗する強さがあるか
- 新規、更新、削除、未変更、NULL遷移、対象外、重複、失敗、ロールバックを覆うか
- 1件だけでなく、200件相当の一括処理、混在分岐、複数親・複数キーを確認するか
- 権限差、共有差、`runAs` の目的と限界を理解しているか
- `Test.startTest/stopTest` の位置が非同期処理と制限測定の目的に合うか
- Mixed DML、callout mock、Platform Event、Batch等のテスト固有制約を考慮しているか
- 提供テスト結果の組織、日時、対象版、実行範囲、失敗・スキップが特定できるか

## 連携・運用上の確認

- 外部ID、upsertキー、重複ルール、再送時の冪等性が設計されているか
- 部分失敗、タイムアウト、再試行、順序逆転、遅延、重複、欠落を考慮しているか
- 大量データ時のバッチサイズ、API制限、ロック、共有再計算等を考慮しているか
- 連携元とSalesforce側の加工・検証・エラー処理の責任分界が正式方針と一致するか
- 運用監視、エラー通知、再実行手順、手動補正、監査証跡が用意されているか

