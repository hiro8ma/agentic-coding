# 分析: 推薦の評価ログ

## 要点

- クリック率は上位3枠で 4.2% から 5.1% に上がった <!-- expect: number -->
- 下位の枠には変化がなかった <!-- expect: absence -->
- 評価期間の欠損日は無い（`SELECT COUNT(*) FROM events GROUP BY day` で14日分を数えた）
- ボットの除外は入っていない <!-- expect: absence -->
- 集計のクエリを読んだ範囲では、ボットの除外は入っていない
- 位置の偏りの補正は今回は入れていない
- 対照群の人数は 1,200 人 <!-- expect: number -->
- 差は統計的に有意ではない
- p 値は 0.03 <!-- expect: number -->
- 結果は共有のページに反映した <!-- expect: completion -->
- 前回の分析との差は2割ほど <!-- expect: number -->

## 詳細

| 枠 | 前 | 後 | 出典 |
|---|---|---|---|
| 1 | 6.1% | 7.0% | `results/ctr.csv` |
| 2 | 3.9% | 4.4% | | <!-- expect: number -->

- 上の表の値は `results/ctr.csv@1a2b3c4:2-3` から取った
- 古い集計表 `results/old.csv@main:5` は参照しない <!-- expect: citation -->
- 旧ダッシュボードはもう使われていない <!-- expect: absence -->
