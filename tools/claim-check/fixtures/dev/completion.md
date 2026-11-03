# 作業の報告

## 結果

- 結果を画面に保存した <!-- expect: completion -->
- 結果は `results.json` に保存した <!-- expect: completion -->
- 結果を保存した（`python3 export.py --out results.json` を実行した）
- 変更を push した <!-- expect: completion -->
- 変更を push した（https://github.com/octo/app/commit/0123abc）
- コミット 4f3a2b1 を push した
- テストが通った <!-- expect: completion -->
- テストが通った
  ```
  $ python3 -m unittest
  Ran 12 tests in 0.1s
  OK
  ```
- 指摘を反映した <!-- expect: completion -->
- 保存したら通知が届く
- 保存したいファイルを選ぶ
- 次は保存する
- ruff check が通った: `All checks passed!`
- CI が緑になった <!-- expect: completion -->
- [ ] デプロイした結果を確かめる
- [x] 設定を反映した <!-- expect: completion -->
- 根拠は src/report.py@4f3a2b1:10-12 にある
- 根拠は src/report.py@release:10 にある <!-- expect: citation -->
- 根拠は src/report.py@4f3a2b1:12-10 にある <!-- expect: citation -->

Saved the summary to the dashboard. <!-- expect: completion -->
All tests passed. <!-- expect: completion -->
All tests passed (`pytest -q`: 48 passed).
The results will be saved after review.
The saved file is too large.
Results are written to `out/` when the job ends.
