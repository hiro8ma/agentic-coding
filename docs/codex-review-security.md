---
title: "Codexのローカルレビュー、GitHubレビュー、Securityを使い分ける"
date: "2026-10-11"
tags: [codex, review, security, github]
---

# Codexのローカルレビュー、GitHubレビュー、Securityを使い分ける

レビュー対象と、結果を外部へ投稿するかを先に決める
ローカルの差分確認、GitHubへ投稿されるレビュー、脆弱性を検証するSecurityは、起動と権限が異なる

| 入口 | 主な対象 | 結果の扱い |
|---|---|---|
| CLIの/review | baseとの差分、未コミットの変更、特定コミット、指定した観点 | 作業ツリーを変更せず、指摘を返す |
| GitHubの@codex review | 接続してレビューを有効にしたリポジトリのPR | GitHubへレビューを投稿する |
| GitHubの自動レビュー | 接続したリポジトリと設定したイベント | 個人設定とリポジトリ設定に応じて起動する |
| Code Review Plugin | PRの説明、差分、コメント、Checks | チャットでの調査と、投稿や承認を分ける |
| Codex Security Plugin | 許可されたローカルのリポジトリや変更範囲 | 候補を検証し、根拠と修正案を記録する |
| Codex Security Cloud Plugin | 接続したGitHubリポジトリ | 一度のスキャンや継続監視を設定する |

## ローカルレビュー

/reviewでは対象のbase、コミット、未コミット差分を選ぶ
未コミットのレビューには、staged、unstaged、untrackedのファイルが含まれる
他の作業の差分が混ざっている場合は、対象を具体的に指定する
通常のセッションと別のレビュー用モデルには、config.tomlのreview_modelを指定できる
今回はモデルの変更やレビューの実行を行っていない

指摘は発生条件、影響、対象箇所、根拠を確認して判断する
教材のワークフロー不整合と日本語のブランチ名の例は、今回のリポジトリで再現した不具合ではない
日本語がASCIIの名前へ変換されるだけで不具合と決めず、識別や追跡の契約を確認する

## GitHubでのレビュー

GitHubへの接続、対象リポジトリのアクセス、コードレビューの有効化を確認する
自動レビューの設定にはGitHubのpushまたはadmin権限が必要である
リポジトリの設定と個人のAutomatic review、起動イベントを区別する
@codex reviewを投稿する操作自体も、外部への書き込みである

現在の公式ガイドでは、GitHubのレビューはP0とP1の問題を報告する
ローカルや自作Actionの重要度分類と同じ範囲とは扱わない
観点を一度だけ追加する場合は、メンションの後へ指定する
継続する方針はAGENTS.mdの適用範囲へ置き、共通規約と対象ディレクトリの規約を組み合わせる
根拠のある、対象固有の問題を示し、機械的なformatやlintはCIへ任せる

教材の方針は、実際の適用範囲と例外を添えて書く

- ログへ個人情報を残さないため、出力される値とマスキングの経路を確認する
- 保護対象のルートへ認証が適用され、公開ルートとの区別があるか確認する
- Reactで直接計算できる値を重複した状態として保持し、useEffectによる同期で不整合を起こしていないか確認する

文法や識別子だけで問題と決めず、変更の発生条件と影響を確認する

レビューを読んで修正すること、GitHubへコメントすること、承認やマージは別の操作である
Code Review Pluginのチャット内でレビューしただけでは、コメントや承認は投稿されない
@codex fixなどの修正依頼は、レビューとは異なりブランチへの変更を伴い得る
今回はリポジトリへの許可追加、自動レビュー設定、コメント投稿、修正依頼を行っていない

## Securityの提供形態と結果

教材のCloudスキャンだけでなく、現在はローカル用のCodex Security Pluginと、別のCodex Security Cloud Pluginが案内されている
CLI単体のSecurity実行にはベータアクセスの条件があるため、使えることを前提にしない
対象コードを調べる権限、接続先、スキャンする版、利用できる機能を確認する
教材の画面上のボタン名は、別の提供形態にもそのまま適用しない

検出候補、検証結果、実際の影響、未確認の範囲を読んで判断する
Securityが検証する設計でも、すべての問題を発見する保証や、すべての指摘が正しい保証とは扱わない
ローカル版はreport.md、findings.json、coverage.jsonなどの成果物を作り、Cloud版は検出結果と利用できる修正案を確認する
教材のiOSアプリのAPIキーの例を、今回の検出結果としては記録しない

通常のCode Review、PRのSecurity Review、リポジトリのSecurityスキャンも区別する
Security Reviewは、PRのセキュリティ上の問題を重点的に調べる別のレビューとして案内されている
実行承認のauto_review設定は、これらのコード検査を自動で開始する設定ではない
今回はPluginの導入、スキャン、継続監視、修正PR作成を行っていない

## 出典

- ユーザー提供教材「Codexをコードレビューで活用する」「Codex Security」
- [Code review](https://learn.chatgpt.com/docs/code-review)
- [Review GitHub pull requests with Codex](https://learn.chatgpt.com/docs/third-party/github)
- [Codex Security Plugin](https://learn.chatgpt.com/docs/security/plugin)
- [Codex Security Cloud setup](https://learn.chatgpt.com/docs/security/setup)
