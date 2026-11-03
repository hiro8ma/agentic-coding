# リサーチ: 検索の評価の手法

## 要点

- 評価の判定に LLM を使うと、人手との一致は κ 0.6 前後になる <!-- expect: number -->
- 評価の判定に LLM を使うと、人手との一致は κ 0.6 前後になる（https://example.org/judge-study の表2）
- 位置の偏りを補正しない評価は、上位の方式を過大に見積もる[1]
- 位置の偏りを測った公開データセットは少ない
- 日本語での比較研究は無い <!-- expect: absence -->
- 日本語での比較研究は、Google Scholar と arXiv を「日本語 検索 評価 LLM 判定」で検索した範囲では見つからなかった
- 判定の費用は人手の約1/20
- 2025年以降の論文の7割が LLM の判定を使う <!-- expect: number -->

## 読んだ資料

| 資料 | 要点 | URL |
|---|---|---|
| 判定の一致の研究 | κ は 0.55〜0.65 | https://example.org/judge-study |
| 位置の偏りの解説 | 補正で順位が入れ替わる例が 3 件 | | <!-- expect: number -->

[1]: https://example.org/position-bias
