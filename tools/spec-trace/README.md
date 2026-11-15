# spec-trace

仕様のファイルに書いた規則の ID と、その ID に触れるテストを結ぶ
テストのない規則と、どの仕様にもない ID への参照を出す
ID で結ぶだけで、テストが規則を確かめているかは見ない
判定は決まった規則で行い、LLM は使わない
Python 3.9以降の標準ライブラリだけで動く

## なぜ作ったか

エージェントとの会話で決めた規則は、会話が終わると読めなくなる
「送料無料は税込で判定する」と決めても、次のセッションのエージェントはそれを知らないまま、税抜で判定する実装を書きうる

規則は2つの場所に残す

| 置き場所 | 役目 |
|---|---|
| 仕様のファイル | 規則と理由を書く。なぜその判定なのかを、後から読める |
| テスト | 規則に反した変更を見つける。人が見ていなくても落ちる |

2つを同じ ID で結ぶ
テストの docstring か名前に `SHIP-1` と書いておくと、テストが落ちたときの出力に ID が出る
エージェントは ID で仕様のファイルを引き、規則と理由を読んでから直せる

この結び目は、規則を足したときや、仕様から規則を消したときに切れる
この道具は、切れた結び目を毎回同じ手順で数える

- テストのない規則（仕様に書いたが、どのテストも ID に触れない）
- どの仕様にもない ID への参照（仕様から消した規則を、テストがまだ指している）

同じリポジトリの `tools/harness-inventory` の分け方では、行動の後に決まった規則で確かめる sensor / computational にあたる

## 読むもの

### 仕様

| 場所 | 中身 |
|---|---|
| `ROOT/specs/**/*.md` | 仕様のファイル。SpecKit の `specs/` も含む |
| `ROOT/.steering/*/requirements.md` | [spec-workflow スキル](../../skills/spec-workflow/SKILL.md)の、作業ごとの要求 |

`--spec` を付けると、既定の場所を読まず、渡したファイルかディレクトリ（下の階層の `*.md`）だけを読む
`specs/` と `--spec` のディレクトリの下でも、下の「テスト」と同じディレクトリを飛ばす

箇条書き（番号付きとチェックボックスを含む）と見出しの先頭にある ID を、規則の定義として読む

| 書き方 | 例 | 接頭辞 |
|---|---|---|
| 角括弧で囲む | `- [SHIP-1] 送料無料` / `## [RET-2] 返品` | 英大文字で始まる、英大文字と数字の並び |
| 角括弧なし | `- AC-1: WHEN ...` / `- AC1 ...` / `- **AC-2**:` / `` - `AC-3` `` / `### AC-4` | `AC` と、`--prefix` で足した接頭辞だけ |

- `AC1` と `AC-01` は `AC-1` に揃える
- 角括弧のない形を `AC` に限るのは、`- UTF-8 で保存する` や `- GPT-4 を使う` を規則に数えないため
- 文の途中の ID と、フェンスの中は読まない
- リンクの文（`- [RFC-2119](https://example.com/rfc)`）は、ID の形でも読まない
  - spec-workflow スキルの[要求のテンプレート](../../skills/spec-workflow/assets/steering-requirements-template.md)は、説明の文に `AC-1` があるが、書き込む前の状態では規則0件になる
- 規則の文は、同じ行の ID の後ろの文
  - 空なら、次の行から、空行か次の項目か見出しの前までを読む
  - 見出しの下のフェンスに書いた `WHEN ...` / `THE SYSTEM SHALL ...` も読む

### テスト

既定では、ROOT の下の、名前が次の形のファイルを読む

`test_*.py` / `*_test.py` / `*_test.go` / `*.test.ts` / `*.spec.ts` / `*.test.tsx` / `*.spec.tsx` / `*.test.js` / `*.spec.js`

- `.` で始まるディレクトリと、`node_modules` / `vendor` / `venv` / `dist` / `build` / `target` / `coverage` / `__pycache__` / `fixtures` / `testdata` を飛ばす
- `--tests` を付けると、渡した glob（ROOT からの相対）に当たるファイルだけを読み、ディレクトリを飛ばさない
- 仕様として読んだファイルは、テストとして読まない

テストの中では、仕様が定義する接頭辞と `--prefix` の接頭辞の ID だけを探す
コメント / docstring / 文字列 / 関数名のどこに書いてもよい

| 形 | 例 | 大文字と小文字 |
|---|---|---|
| `-` で区切る | `# SHIP-1 の境界` / `it("RET-1 返品できる")` / `t.Run("AC-2 外す")` | 区別しない |
| `_` で区切る | `def test_ship_1_free()` / `func TestSHIP_1(t *testing.T)` | 区別しない |
| 区切らない | `func TestAC1AddsFee(t *testing.T)` / `def test_SHIP1()` | 区別する |

- ID の前は、行頭 / 英数字でない文字 / `Test` の直後のどれか。`_` と和文の文字は区切りに数える
- `XSHIP-1` と `LatestAC1` は数えない。`SHIP-10` は `SHIP-10` に数え、`SHIP-1` には数えない
- 区切らない形だけ大文字と小文字を区別するのは、`ac12ef` のような小文字の16進に当てないため
- 接頭辞を仕様のものに限るのは、`UTF-8` / `SHA-256` / `ISO-8601` を、どの仕様にもない ID への参照に数えないため

## 出力

`fixtures/drift` に流した出力は次のとおり

```text
$ python3 tools/spec-trace/spec_trace.py tools/spec-trace/fixtures/drift
# spec-trace

ルート tools/spec-trace/fixtures/drift
読んだ仕様3件 / テスト2件
規則4件のうち、テストが ID で参照する規則2件（50.0%）
テストのない規則2件
どの仕様にもない ID への参照1件
複数の場所で定義された ID 1件

ID で結ぶだけで、テストが規則を確かめているかは見ない

## 規則とテスト

| ID | 仕様 | 規則 | テスト |
|---|---|---|---|
| AC-1 | .steering/20261101-gift-wrap/requirements.md:9 | WHEN 利用者がギフト包装を選ぶ THE SYSTEM SHALL 包装料30… | gift_wrap_test.go:5 |
| AC-2 | .steering/20261101-gift-wrap/requirements.md:10 | WHEN 利用者がギフト包装を外す THE SYSTEM SHALL 包装料を合… | なし |
| AC-1 | .steering/20261105-coupon/requirements.md:9 | WHEN 利用者が期限の切れたクーポンを使う THE SYSTEM SHALL … | gift_wrap_test.go:5 |
| RET-1 | specs/returns.md:5 | 受け取りから30日以内の注文は返品できる | returns.test.ts:5 |
| RET-2 | specs/returns.md:7 | セールの商品は返品できない | なし |

## テストのない規則

- AC-2 .steering/20261101-gift-wrap/requirements.md:10「WHEN 利用者がギフト包装を外す THE SYSTEM SHALL 包装料を合…」
- RET-2 specs/returns.md:7「セールの商品は返品できない」

## どの仕様にもない ID への参照

- RET-3 returns.test.ts:9「it("RET-3 返品の送料は店が持つ", () => {」

## 複数の場所で定義された ID

- AC-1 .steering/20261101-gift-wrap/requirements.md:9 / .steering/20261105-coupon/requirements.md:9
```

- パスは ROOT からの相対で出す
- 規則の件数は ID の数で、表の行は定義の場所の数
  - 同じ ID の定義が2つあると、表に2行出て、件数は1件になる
- 割合は、テストが ID で参照する規則の数を、規則の数で割ったもの
- テストの欄は `ファイル:行` で、同じファイルの行はカンマでつなぐ
- 規則の文は40文字で切る

`--json` を付けると、次の形で出す

| キー | 中身 |
|---|---|
| `root` / `spec_files` / `test_files` | 読んだルートとファイル |
| `summary` | `rules`（ID の数）/ `tested` / `coverage`（0から1。規則が無ければ null）/ `untested` / `stale` / `duplicated` |
| `rules` | 定義ごとの `id` / `file` / `line` / `text`（切らない文）/ `tests`（`file` と `line`） |
| `untested` | テストのない規則の定義 |
| `stale` | どの仕様にもない ID への参照の `id` / `file` / `line` / `text`（その行） |
| `duplicates` | 複数の場所で定義された ID と、その場所 |

| 終了コード | 意味 |
|---|---|
| 0 | テストのない規則も、どの仕様にもない参照もない。`--report-only` を付けたときも0 |
| 1 | どちらかがある |
| 2 | ROOT がディレクトリでない / `--spec` のパスが無い / `--tests` が絶対のパス / `--prefix` の形が違う |

複数の場所で定義された ID は出すが、終了コードには含めない

## 使う

```bash
python3 tools/spec-trace/spec_trace.py
python3 tools/spec-trace/spec_trace.py --json . > trace.json
python3 tools/spec-trace/spec_trace.py --spec docs/rules.md --tests 'tests/**/*.py'
python3 tools/spec-trace/spec_trace.py --prefix FR
python3 tools/spec-trace/spec_trace.py --report-only
```

| 引数 | 動き |
|---|---|
| `ROOT` | リポジトリのルート。既定は `.` |
| `--spec PATH` | 読む仕様のファイルかディレクトリ。ROOT からの相対。何度でも付けられる |
| `--tests GLOB` | 読むテストの glob。ROOT からの相対。何度でも付けられる |
| `--prefix NAME` | ID の接頭辞として扱う名前。角括弧のない形も仕様から読み、定義が無くてもテストで探す。SpecKit の `- **FR-001**: ...` は `--prefix FR` で読む |
| `--json` | JSON で出す |
| `--report-only` | 見つけても終了コード0を返す |

### CI と Claude Code の hook

CI では、テストと同じ job に `python3 tools/spec-trace/spec_trace.py` の段を足す
見つけると終了コード1で段が落ちる
テストのない規則がすでに多いうちは、`--report-only` を付けて件数だけを出し、0件にしてから外す

Claude Code では、Stop の hook で、エージェントが答えを返す前に流せる

- Stop の hook は、終了コード2で標準エラーの文を返すか、終了コード0で `decision` が `block` の JSON を返すと、その文を Claude に渡して答えを止める
  - 終了コード1では止まらない。spec-trace は見つけたときに1を返すので、そのままでは止まらない
  - spec-trace の終了コードが1のときだけ、出力を止める理由として返す短いラッパーを挟む。入力の誤りの2では止めない
- 標準入力の `stop_hook_active` が true のときは、流さずに通す
  - 止めた後の答え直しをまた止め、抜けられなくなるのを防ぐため
- テストのない規則が残っている間は、関係のない作業の答えも毎回止まる
  - 先に CI で0件にしてから入れる

## テスト

```bash
python3 -m unittest discover -s tools/spec-trace
```

fixture は架空の店のリポジトリで、実在の組織や人の情報は含まない
18件のテスト（42件のサブテスト）が Python 3.9.6と3.15.0で通り、ruff check と ruff format で確かめた

`fixtures/` には `__init__.py` を置かない
fixture のテスト（`fixtures/shop/test_shipping.py`）は discover に拾われず、この道具のテストの中から読み込み、正しい実装と変異の両方に対して流す

次のように壊すと、テストが落ちることも確かめた
壊した実装は、リポジトリの外の複製で試した

| 壊したところ | 落ちたテスト |
|---|---|
| `_` を ID の前の区切りに数えない | 参照の形（`test_ship_1` / 区切らない大文字） |
| `Test` の直後を ID の前の区切りに数えない | 参照の形（Go の `TestAC1` / `TestSHIP_1`）/ drift の fixture / Markdown の出力 |
| 区切らない形も大文字と小文字を区別しない | 参照の形（区切らない小文字） |
| `-` と `_` の形も大文字と小文字を区別する | 参照の形（`test_ship_1`） |
| 番号を数として揃えない | 定義の形（`AC-01`）/ `--prefix` の定義 |
| フェンスを読み飛ばさない | 定義の形（フェンスの中 / 下げたフェンス） |
| 箇条書きの途中の ID も読む | 定義の形（箇条書きの途中） |
| リンクの文も ID として読む | 定義の形（リンクの文） |
| 段落の行も読む | 定義の形（段落の中） |
| 角括弧のない ID を、接頭辞を問わず読む | 定義の形（別の接頭辞 / AC で始まる別の語）/ `--prefix` の定義 |
| 定義の無い接頭辞もテストで探す | 参照の形（定義の無い接頭辞 / 前に英字 / `TestSHIP_1`）/ 既定の場所 / shop の fixture |
| 見出しや箇条書きだけの規則で、次の行を読まない | 規則の文（見出しの下のフェンス / 下げた行）/ drift の fixture |
| 同じ ID の定義を1つにまとめる | drift の fixture / Markdown の出力 |
| 見つけても終了コード0を返す | drift の fixture / Markdown の出力 / `--prefix` の参照 / `--spec` と `--tests` |
| `--report-only` でも1を返す | `--report-only` |
| 既定の探索で `fixtures` と隠しディレクトリを読む | 既定の場所 |
| `--spec` を付けても既定の場所を読む | `--spec` と `--tests` |
| fixture の見分けるテストの入力を、税抜10,000円にする | 変異を見分けるテスト |
| fixture の税込の1円未満を、四捨五入にする | fixture の計算 / 変異を見分けるテスト |

## 限界

### ID で結んでも、テストが規則を押さえているとは限らない

`fixtures/shop` の仕様は、規則 `SHIP-1` を1つだけ持つ

```markdown
- [SHIP-1] 注文の合計が5,000円以上なら送料無料。合計は税込で判定する
  - 税込の合計は、税抜の合計に1.1を掛け、1円未満を切り捨てる。商品ごとではなく、注文の合計に1回だけ掛ける
```

2つのテストが docstring で `SHIP-1` に触れるので、spec-trace は100%と出し、終了コード0を返す

```text
$ python3 tools/spec-trace/spec_trace.py tools/spec-trace/fixtures/shop
（中略）
規則1件のうち、テストが ID で参照する規則1件（100.0%）
（中略）
| SHIP-1 | specs/shipping.md:5 | 注文の合計が5,000円以上なら送料無料。合計は税込で判定する | test_shipping.py:20,25 |
```

規則を押さえているのは、そのうち1つだけ

| テスト | 入力（税抜） | 税込（切り捨て） | 正しい実装 | 税抜で判定する変異 |
|---|---|---|---|---|
| `test_free_from_tax_included_5000` | 4,546円 / 4,545円 | 5,000円 / 4,999円 | 通る | 落ちる |
| `test_free_for_large_order` | 10,000円 | 11,000円 | 通る | 通る |

- 税抜10,000円は、税込で読んでも税抜で読んでも5,000円以上なので、どちらの実装でも通る
- このテストだけを残しても、spec-trace の出力は100%のまま変わらない。この道具のテストで確かめた
- 境界の税抜4,545円は、四捨五入なら4,999.5円が5,000円になって送料無料になるので、切り捨てとの違いも見分ける

変異に対して流すと、見分けるテストだけが落ち、docstring の ID が出力に出る

```text
$ cd tools/spec-trace/fixtures/shop
$ SHIPPING_IMPL=shipping_mutant python3 -m unittest
.F
======================================================================
FAIL: test_free_from_tax_included_5000 (test_shipping.FreeShippingTest.test_free_from_tax_included_5000)
SHIP-1 税抜4,546円は税込5,000円で無料、税抜4,545円は税込4,999円で有料
----------------------------------------------------------------------
（中略）
AssertionError: False is not true : 税込5,000円は送料無料
```

テストが規則を押さえているかは、変異テスト（mutation testing）で確かめる

- 実装を少しずつ壊し（`>=` を `>` にする、税込を税抜にする）、落ちるテストがあるかを見る
- 道具には、Python の mutmut、JavaScript と TypeScript の StrykerJS などがある
- spec-trace は ID の結び目を見て、変異テストはテストの中身を見る。2つを合わせて使う

### そのほか

- ID の参照は語の一致で見る
  - テストのファイルのどこに書いても数え、その行がテストの中かは見ない。ヘルパーのコメントや import の行でも数える
  - テストが skip されていないか、実際に流れるかは見ない
- 同じ ID を複数の場所で定義すると、どの定義の規則かを区別しない
  - spec-workflow スキルの要求は作業ごとに `AC-1` から振るので、`.steering` の作業が2つ以上あると `AC-1` が重なる
  - `fixtures/drift` では、クーポンの `AC-1` も、ギフト包装のテストで「参照あり」になる
  - 重ならないようにするには、作業ごとに角括弧の接頭辞を変える（`[GIFT-1]` / `[COUPON-1]`）
- 仕様から消した接頭辞の参照は、`--prefix` で渡さないと探さない
- 角括弧のない ID は、`AC` と `--prefix` の接頭辞しか読まない。`- SHIP-1: ...` は `--prefix SHIP` が要る
- 表の行（`| AC-1 | ... |`）と段落の行の ID は、定義として読まない
- フェンスのほかは飛ばさない。HTML のコメントの中の ID も定義として読む
- 4字下げのコードブロックと、下線で書く見出しは扱わない

## 確かめていないこと

- CI と Claude Code の Stop の hook に入れたときの動き
  - ラッパーは書いていない。hook の入出力は、公式の文書と、同じリポジトリの `tools/ref-link-check` の説明に合わせて書いた
- 実在のリポジトリの仕様とテストで、取りこぼしと誤検知がどれだけあるか
  - 仕様5,157件とテスト6,068件のあるリポジトリで1回走らせた。`AC-n` の規則は4,923行あったが、作業ごとに `AC-1` から振り直すので ID は34種類しかなく、27種類が複数の場所で定義されていた
  - テストの `AC1` は自分の要求の AC-1 を指すつもりで書かれていたが、道具は同じ番号を持つ無関係の仕様とも結んだ。割合（17.6%）は意味を持たず、重複の一覧のほうが問題を示した
  - 取りこぼしの件数は数えていない
- SpecKit の `specs/` の実物での動き。`--prefix FR` で `- **FR-001**: ...` を読むことは、テストの例で確かめた
- `fixtures/drift` の Go と TypeScript のテストは読むだけで、流していない

## 参照資料

- 教材（規則を仕様のファイルに書き、テストと ID で結ぶ例）
- [spec-workflow スキル](../../skills/spec-workflow/SKILL.md)
- [Claude Code の hooks](https://code.claude.com/docs/en/hooks)（Stop の hook の終了コードと decision control）
