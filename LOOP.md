# LOOP.md — このリポジトリで回すループの宣言

形式は cobusgreyling/loop-engineering に倣う。
ループの実態（発見事項）は STATE.md、予算は loop-budget.md、実行記録は loop-run-log.md に置く。

## Loop: docs-triage

| 項目 | 値 |
|---|---|
| 目的 | ナレッジ文書の劣化検出（リンク切れ・README とディレクトリ実態の乖離） |
| non-goals | 文書内容の書き換え、スタイル修正 |
| 監視対象 | `docs/` `skills/` `README.md` |
| 段階 | **L1（レポートのみ）** |
| 実行 | GitHub Actions `daily-triage.yml`、週 1（月曜 09:00 JST） |
| 出力 | 検出結果を Issue として起票（既存の open Issue があれば追記しない） |
| エスカレーション | すべて人間へ。自動修正はしない |
| denylist | `.claude/hooks/` `.github/` の自動変更禁止 |
| L2 昇格条件 | L1 を 4 週回して誤検知率を確認し、単一ファイルのリンク修正のみ L2 化を検討 |
