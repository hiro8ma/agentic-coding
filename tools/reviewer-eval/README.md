# reviewer-eval

AI のコードレビューに、過去に revert された変更を見せ、不具合の場所を指摘できたかを測る
あわせて、問題の見つかっていない変更に出した指摘の数を数え、ノイズの目安にする

障害を起こした変更から評価セットを作り、レビューを定期的に採点し、ノイズも測るという運用を、手元の git の履歴だけで試すための道具
Python 3.10以降の標準ライブラリと git だけで動く

## 測るもの

| 指標 | 意味 |
|---|---|
| `recall` | revert のケースのうち、revert が変えた行（前後 `--tolerance` 行を含む）を指す指摘が1件以上あった割合 |
| `strict_recall` | 語を付けた revert のケースのうち、範囲内の指摘の `summary` に語のどれかを含むものがあった割合 |
| `findings_per_clean_case` | clean のケース1件あたりの指摘の数。ノイズの主な指標 |
| `findings_per_case` | revert のケース1件あたりの指摘の数 |
| `noise_share` | revert のケースの指摘のうち、revert が変えた行の外を指すものの割合。ノイズの補助の指標 |

`strict_recall`は、別の問題の指摘がたまたま同じ行に重なったものを検出に数えない
語のない revert のケースは`strict_recall`の分母に入れない

## ケースの作り方

revert のケース

- 件名が`Revert "`で始まるか、本文に`This reverts commit <sha>`を含むコミットを`git log`で探す
- 本文の sha が指す元のコミットの、最初の親との差分をレビューに渡す
- revert のコミットが変えた行を、元のコミットの変更後の行番号で記録し、正解の範囲にする
- 次のものは除き、理由ごとの件数を`skipped`に出す

| 理由 | 中身 |
|---|---|
| `no_trailer` | 本文に`This reverts commit <sha>`がない |
| `target_not_found` / `multiple_targets` | 対象の sha が履歴にない / 複数ある |
| `revert_reverted` | revert 自体が後で取り消された。元の変更は不具合ではなかったとみなす |
| `target_is_revert` | 対象が revert か、取り消しの取り消し（`Reapply "`） |
| `empty_diff` / `diff_too_large` | 差分が空 / `--max-diff-bytes`を超える |
| `over_limit` | `--max-cases`を超えた古いもの |

clean のケース

- revert でも revert の対象でもなく、後の`--clean-window`件（既定20件）のコミットが同じファイルを触っていないコミットを、新しい順に`--clean-cases`件（既定10件）選ぶ
- 新しい側に`--clean-window`件のコミットがないものは除く。まだ問題が見つかっていないだけかもしれないため
- マージコミットと最初のコミットは除く
- clean のケースへの指摘は、すべてノイズとして数える

## 実行

```bash
# 試し用のリポジトリを作る（DIR/repo と DIR/keywords.json）
python3 tools/reviewer-eval/fixture_repo.py /tmp/reviewer-eval-fixture

# 抽出したケースだけを見る。レビューは呼ばない
python3 tools/reviewer-eval/reviewer_eval.py --repo /tmp/reviewer-eval-fixture/repo --dry-run --clean-window 3

# 決定的な偽のレビューで採点する
python3 tools/reviewer-eval/reviewer_eval.py --repo /tmp/reviewer-eval-fixture/repo \
  --reviewer "python3 tools/reviewer-eval/fake_reviewer.py" \
  --clean-window 3 --keywords /tmp/reviewer-eval-fixture/keywords.json

# テスト
python3 -m unittest discover -s tools/reviewer-eval
```

上の採点の出力は次のとおり
表のあとに同じ結果の JSON が続く
`--json-out PATH`を付けると、JSON はファイルに書き、標準出力には表だけを出す

```text
kind      revert    target    findings  hits  strict  noise  result   subject
reverted  f537a6cd  b6708848  0         0     0       0      missed   Truncate tax to whole units
reverted  9d41e15a  2fb2eb8b  2         1     1       1      caught   Lengthen retry backoff
reverted  737f4f47  eb8f54ad  1         1     0       0      caught   Add member discount
clean     -         c517d732  1         -     -       1      flagged  Document usage
clean     -         e85525c4  0         -     -       0      quiet    Add CSV report

cases 3  caught 2  keyword_cases 3  strict_caught 1  clean_cases 2  errors 0
recall 0.67  strict_recall 0.33  findings_per_clean_case 0.50
findings_per_case 1.00  noise_share 0.33  tolerance 3
skipped  no_trailer 1  revert_reverted 1  target_is_revert 1
```

`Add member discount`は、範囲内の指摘が`TODO`についてで、語の`discount` / `rate`を含まないので、strict では検出に数えない

## レビューのコマンド

`--reviewer`に渡すコマンドは、差分を標準入力で受け取り、1行に1件の JSON を標準出力に書く
`line`は変更後のファイルの行番号

```json
{"file": "app/client.py", "line": 9, "summary": "待ち時間が30秒に延びる"}
```

- JSON として読めない行は、ケースごとの`invalid_lines`に数える。コードフェンスの行は読み飛ばす
- 終了コードが0以外のケースと、`--timeout`を超えたケースは`error`にし、recall の分母から外す。このときツールの終了コードは1になる

`--claude`を付けると、`claude -p`にレビューさせる

- ツールを渡さず（`--tools ""`）、セッションを保存せず、空の一時ディレクトリで動かす。差分の外にある revert の後の版を読ませないため
- 利用料がかかる。先に`--dry-run`でケースの数を確かめ、`--max-cases`と`--clean-cases`で絞る
- テストでは呼ばない

## 語のファイル

`--keywords`には、revert か元のコミットの sha（先頭7文字以上）から語の配列への JSON を渡す

```json
{"2fb2eb8b": ["sleep", "backoff"]}
```

大文字と小文字を区別せず、指摘の`summary`に部分一致で探す
どのケースにも合わないキーは、標準エラーに出す

## 限界

- revert は不具合の代わりの目印でしかない。仕様の変更やリリースの都合でも revert され、revert されずに後の修正で直った不具合は拾えない
- 行の一致は粗い。変更の全体を revert したケースは差分のほぼ全体が正解の範囲になり、差分のどこを指しても検出に数える。一部だけを revert したケースと strict の判定のほうが、検出の意味がはっきりする
- 行番号は revert の直前の版で数える。元のコミットと revert の間に同じファイルの別の変更があると、範囲がずれる
- clean は問題が見つかっていないだけで、問題がないことの保証ではない。clean への指摘に本物の問題が混ざりうる
- 「後の N 件」は`git log`の並びで数える。マージの多い履歴では、時間の近さと一致しない
- clean の選定は`git log --name-only`で範囲の履歴全体を読む。大きなリポジトリでは`--rev`で範囲を絞る
- 改行や引用符を含むファイル名（git が C の形式で引用するもの）は扱わない
