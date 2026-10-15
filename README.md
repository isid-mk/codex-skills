# codex-skills

Codexで独自に作成したスキルを管理するリポジトリです。

## スキル一覧

| スキル | 用途 |
| --- | --- |
| [national-crm-sandbox-data](skills/national-crm-sandbox-data/SKILL.md) | Salesforce Sandboxへの業務データ移植・補完、明示依頼時のユーザー作成 |
| [object-label-design-doc-rollout](skills/object-label-design-doc-rollout/SKILL.md) | 承認済みの名称変更一覧をExcel設計書のコピーへ反映 |
| [object-label-rollout-list](skills/object-label-rollout-list/SKILL.md) | オブジェクト名称のGrep結果からExcelの影響箇所一覧を作成 |
| [salesforce-implementation-review](skills/salesforce-implementation-review/SKILL.md) | Salesforce設計書と実装メタデータを照合し、レビュー結果をExcelへ出力 |
| [salesforce-playwright-ut](skills/salesforce-playwright-ut/SKILL.md) | Salesforce Sandboxの入力規則・数式・ボタン表示条件を検証し、Excel証跡を作成 |

各スキルは `skills/<スキル名>/` に配置し、`SKILL.md` と、付属する `agents/`・`scripts/`・`references/`・`assets/` をまとめて管理します。

## Codexへの導入

Codexに次のように依頼します。必要なスキルのフォルダーを指定してください。

```text
$skill-installer を使って、次のGitHubリポジトリのスキルをインストールしてください。
https://github.com/isid-mk/codex-skills/tree/main/skills/object-label-rollout-list
```

既存の同名スキルがある場合は、差分とバックアップを確認してから更新します。

## 更新方法

1. ローカルでスキルを変更し、対象業務に必要な検証を行います。
2. 対応する `skills/<スキル名>/` へ、付属ファイルも含めて変更を反映します。
3. 差分を確認し、コミットしてGitHubへ反映します。

インストール済みスキルとこのリポジトリは自動同期しません。原本と管理用コピーのどちらを編集したか確認してください。

## 実行上の注意

- Salesforce向けスキルは、対象環境の認証・権限・資料・実行許可を別途確認して利用します。
- `salesforce-playwright-ut` は、参照資料に記載された外部の自動化基盤を利用します。このリポジトリだけで実機テスト全体が動作する構成ではありません。
- Python・Node.js・Excel等の依存環境は各スキルの手順に従って準備します。
- 認証ファイル、パスワード、アクセストークン、実行ログ、ブラウザープロファイル、キャッシュは格納しません。
- 標準添付スキル・プラグイン配布スキル・第三者からインストールしたスキルは今回の対象外です。

構成の参考: [OpenAI公式ドキュメント: Skills](https://developers.openai.com/plugins/concepts/skills)
