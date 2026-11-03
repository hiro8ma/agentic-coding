# claim-check

エージェントの報告（Markdown）から、使う前に確かめる主張を拾う検査
CLI として動き、Claude Code ではサブエージェントの報告が届いたときに hook でも動く
Python 3.9以降の標準ライブラリだけで動く

## なぜ作ったか

サブエージェント（リサーチ / 業務分析 / 実装）の最終報告を、そのままナレッジのノートに使うと、報告の誤りがノートに残る
同じ形の誤りが続いた

- 論文の値を「ベースライン → 提案手法」と書いた報告が、原典では部品を1つ外した版の値だった。原典を開いて気づいた
- 「メール形式の検索語を除くフィルタが無い」と書いた報告が、import 先のモジュールにあるフィルタを見ていなかった。探した範囲を書いていない不在の主張で、誰も確かめずに1日ノートに残った
- リード役のエージェントが「結果を画面に保存した」と書いたが、保存されていなかった。証拠を添えていない完了の主張だった

Addy Osmani の記事「Critical thinking when agents do the work」（X、2026-11-03）は、次のように書く

- 終わりの通知を受けたら、要約より先に、実行したコマンドとその出力を読む
- 緑のチェックが示すのは1つの性質だけである
- 「確かめた」の基準は先に決める。後からだと、どんな結果にも理屈を付けてしまう
- 各エージェントが前のエージェントの要約だけを受け取ると、3つ目のエージェントは原文を読んでいない
- 基準に満たなかったものは、理由を共有の設定 / hook / テストに書き、繰り返さないようにする

この検査は、要約を使う前に確かめる主張を、決まった規則で毎回同じように並べる
主張が正しいかは判定しない
範囲 / 出典 / 証拠の書き忘れだけを拾う

## 拾うもの

| 種類 | 拾う書き方 | 同じ主張にあれば通すもの | 優先度 |
|---|---|---|---|
| 不在の主張 | 「無い」「見つからない」「見当たらない」「存在しない」「〜していない」「〜されていない」「未実装」「なし」、"no ..."、"not found"、"none"、"does not exist"、"never called" など | 探した方法（「〜を検索した」「grep」「gh search」「〜を読んだ」「〜の範囲で」、"searched"）、コマンド、ファイルのパス、`path@sha:行`、読んだ資料の URL か `[S1]` の番号 | 1 |
| 出典のない数値 | %/件/人/倍/割/pt/ポイント/pp の付いた数と、小数 | URL、`path@sha:行` か `path:行`、コマンド、脚注、`Table 2` / `表3` / `p.12`、`出典:` の札、著者と年、ファイルのパス、表の出典の列 | 結論の節（結論 / まとめ / 要約 / TL;DR / Summary など）は1、ほかは3 |
| 証拠のない完了 | 「保存した」「push した」「反映した」「コミットした」「通った」「緑になった」「確認済み」、"saved"、"pushed"、"merged"、"tests passed" など | コマンド、出力（コードブロック / 引用の `>` / `Ran 12 tests` のようなコード）、URL、commit の sha、`path@sha:行` | 2 |
| 引用の誤り | `path@ref:行` の ref が sha でない、行の範囲が逆、リポジトリの外のパス。`--repo` を付けたときは、ファイルが無い / 行がファイルの外 | なし | 1 |

「同じ主張」の範囲は次のとおり

- 主張の単位は、箇条書きの1項目 / 表の1行 / 段落の1文
- 範囲 / 出典 / 証拠は、その文、すぐ下にネストした項目、続くコードブロックと引用（`>`）から探す
- 不在の主張の範囲は、同じ項目か段落の直前の文と、親の項目にあってもよい
- 数値の出典は、親の項目と見出しにあってもよい
- 同じ表の行の数値は、1件にまとめて拾う

## 拾わないもの

| 例 | 拾わない理由 |
|---|---|
| `フィルタの有無は未確認` / `夜間のジョブは確認していない` / `is unverified` | 確かめていないと書いてある |
| `## 確かめていないこと` / `## 限界` の節の中 | 同上 |
| `「フィルタはない」と書いてある` / `"no filter is applied"` / `` `if not term:` `` / コードブロック | 引用符とコードの中 |
| `必要はない` / `ではない` / `かもしれない` / `しかない` / `no longer` / `No action is required.` / `Do not edit` | 存在についての主張でない言い回し |
| `呼び出し元がない場合` / `ないか確かめる` / `Is there no filter?` | 条件と疑問 |
| `まだ push していない` / `書き込みはしていない` / `We did not run the load test.` | 自分の作業の報告 |
| `保存したら` / `will be saved` / `The saved file` / `- [ ] デプロイした結果を確かめる` | 完了の主張でない |
| `Python 3.9 と 3.15` / `section 15.5` / `arXiv:2401.12345` / `v2.1.271` | 版 / 節 / 論文の番号 |

## 出力

```text
claim-check: report.md
確かめる主張4件（不在の主張1 / 出典のない数値1 / 証拠のない完了1 / 引用の誤り1）、読んだ主張5件

## 優先度1（不在の主張 / 結論の数値 / 引用の誤り）
- [ ] L5 出典のない数値: 85.82%, 94.78% に出典がない（結論）
  「論文は精度が 85.82% から 94.78% に上がったと報告している」
  → 原典の該当箇所を開き、値と、何と比べた値かを確かめる
- [ ] L6 不在の主張: 「が無い」と書いたが、探した範囲と方法がない
  「スクリプトにはメール形式の検索語を除くフィルタが無い」
  → どこを、どの方法で探したかを確かめる。import 先 / 設定 / 呼び出し元も含める
- [ ] L8 引用の誤り: main は commit の sha でない。ブランチなら後で中身が変わる
  「src/guard.py@main:19」
  → 引用元のファイルと行を開き、主張の根拠になっているかを確かめる

## 優先度2（証拠のない完了と保存）
- [ ] L7 証拠のない完了: 「保存した」と書いたが、コマンド / 出力 / URL がない
  「結果を画面に保存した」
  → 実行したコマンドと出力、または保存先の URL を開いて確かめる
```

拾った主張がないときも「主張が正しいことは示さない」と出す
緑のチェックと同じく、この検査も書き忘れという1つの性質しか見ないため

## 使う

```bash
python3 tools/claim-check/claim_check.py report.md
pbpaste | python3 tools/claim-check/claim_check.py
python3 tools/claim-check/claim_check.py --repo OWNER/NAME report.md
python3 tools/claim-check/claim_check.py --strict report.md
```

| 引数 | 動き |
|---|---|
| なし | 終了コードは常に0。読めないファイルを渡したときだけ2 |
| `--strict` | 拾った主張があれば終了コード1 |
| `--repo OWNER/NAME` | `path@sha:行` の引用ごとに `gh api repos/OWNER/NAME/contents/<path>?ref=<sha>` でファイルを取り、ファイルが無いことと行がファイルの外にあることを拾い、引用した行を表示する。付けなければ通信しない |

`--repo` は `gh` の認証を使う
private のリポジトリも、`gh` で読めれば照合できる
認証の失敗などで取れなかった引用は、拾わずに「照合できなかった」と並べる

## Claude Code に入れる

サブエージェントの報告がリード役に届いたときに検査し、拾った主張を `additionalContext` としてリード役の文脈に足す
止めない
報告はそのまま届き、確かめる主張が添えられる

報告が届く経路で、使う hook が変わる

| 経路 | hook | 読むもの |
|---|---|---|
| フォアグラウンドのサブエージェント | `PostToolUse`（matcher は `Agent`） | `tool_response.content` の文 |
| バックグラウンドのサブエージェント | `UserPromptSubmit` | `prompt` の `<task-notification>` の `<result>` |
| `SubagentHandback` で報告を渡すサブエージェント（auto mode） | `UserPromptSubmit` | `prompt` の `<agent-message>` の中の、2文字下げた報告 |

`SubagentStop` と `Stop` は使わない

- 公式の文書では、`SubagentStop` の `additionalContext` と `decision: "block"` は、サブエージェントを止めずに続けさせ、理由をサブエージェント自身に渡す
- 同じ文書は、リード役の文脈に足すなら `Agent` の `PostToolUse` を使うよう書いている
- `Stop` も、リード役のターンを続けさせる
- どちらも「止めずにリード役へ知らせる」に合わない

`UserPromptSubmit` は利用者が打った文でも動く
`<task-notification>` と `[Subagent hand-back]` の枠がない文は読まない
この2つの枠の形は公式の文書になく、Claude Code 2.1.304と2.1.312の transcript で見た形に合わせた

このリポジトリの設定には登録していない
入れるときは、スクリプトを置き、`~/.claude/settings.json`（全部のリポジトリ）か `.claude/settings.json`（1つのリポジトリ）に足す
すでに同じ event があれば、その配列に足す

```bash
mkdir -p ~/.claude/hooks
cp tools/claim-check/claim_check.py ~/.claude/hooks/
```

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          { "type": "command", "command": "python3 \"$HOME/.claude/hooks/claim_check.py\" --hook" }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "python3 \"$HOME/.claude/hooks/claim_check.py\" --hook" }
        ]
      }
    ]
  }
}
```

拾った主張がないときと、hook の中で失敗したときは、何も出さずに終了コード0で通す
Claude Code は `additionalContext` を1万字で切るので、9,000字を超えたら切る

```bash
echo '{"hook_event_name":"PostToolUse","tool_name":"Agent","tool_response":{"status":"completed","content":[{"type":"text","text":"- スクリプトにはフィルタが無い"}]}}' \
  | python3 tools/claim-check/claim_check.py --hook
```

## Codex で使う

Codex の hook では、サブエージェントの報告をリード役の文脈に足せない

- `SubagentStop` は、`decision: "block"` でサブエージェントを続けさせることしかできない
- `PostToolUse` は matcher の `Agent` で `spawn_agent` に当たるが、`spawn_agent` は報告を待たずに返る
- 報告は `wait_agent` の出力で届く。`wait_agent` の `tool_response` の形は hooks の文書に載っておらず、この hook は読まない

Codex では CLI を使う
AGENTS.md に次のように書くと、リード役が報告を使う前に検査を流す

```markdown
- サブエージェントの報告をノートや結論に使う前に、報告を `python3 tools/claim-check/claim_check.py` の標準入力に渡し、優先度1の主張を原典かコマンドの出力で確かめる
```

これはプロンプトの規則なので、モデルが読み落とせば検査は流れない

## テスト

```bash
python3 -m unittest discover -s tools/claim-check
python3 tools/claim-check/score_fixtures.py
```

`score_fixtures.py` は、fixture の各行の末尾の `<!-- expect: absence -->` を正解にし、行と種類の組で適合率と再現率を出す

| fixture | 中身 | 適合率 | 再現率 |
|---|---|---|---|
| `fixtures/dev/` | 実装しながら調整に使った8件 | 1.00 | 1.00 |
| `fixtures/blind/` | 実装を固めた後に書き、調整に使っていない4件 | 0.96 | 0.81 |

blind の種類ごとの値

| 種類 | TP | FP | FN | 適合率 | 再現率 |
|---|---|---|---|---|---|
| 不在の主張 | 7 | 1 | 5 | 0.88 | 0.58 |
| 出典のない数値 | 9 | 0 | 0 | 1.00 | 1.00 |
| 証拠のない完了 | 5 | 0 | 0 | 1.00 | 1.00 |
| 引用の誤り | 1 | 0 | 0 | 1.00 | 1.00 |

fixture はすべて合成の報告で、正解も自分で付けた
blind の正解のうち1行（「指摘は2点」。「点」は単位の一覧にない）は付け間違いで、採点の後に直した
実装は blind の採点の後に変えていない
テストは Python 3.9.6 / 3.14.8 / 3.15.0で通ることを確かめた

## 誤検知と見逃し

blind で見逃した書き方

- 「API の層にしか無い」。「しかない」を言い回しとして除くため
- 「影響は無いと判断した」。「ないと」を条件か伝聞として除くため
- "is gone"、"have not seen"
- "does not run"。"did not run" を除くための動詞の一覧が、三人称の現在形にも効いてしまう

blind で誤って拾った書き方

- 「共有のページへの反映はまだしていない」。自分の作業の報告

そのほかに分かっている限界

- 主張が正しいかは見ない。出典の URL があれば、その URL が値を支えていなくても通す。1つ目の失敗は URL を添えても起きうる
- ファイルのパスを書いた不在の主張は、範囲を書いたとみなして通す。import 先や設定から入る処理までは見ない。2つ目の失敗はパスを書いても起きうる
- 英語の数値は「%」「x」「percent」「points」「pp」の付いた数と小数だけを拾う。"1,800 tokens" や "3 open incidents" は拾わない
- 単位の一覧にない数（「2点」「10回」「210 ms」）は拾わない
- 評価の否定（「進んでいなかった」「示せていなかった」）を不在の主張として拾うことがある
- hook で拾った主張の行の番号は、取り出した報告の中での番号になる

## 確かめていないこと

- Claude Code の実際のセッションで、この hook が動き、`additionalContext` がリード役に届くこと。入出力の形は公式の文書と、手元の transcript で見た通知の形に合わせ、テストでは標準入出力だけを確かめた
- `<task-notification>` と `[Subagent hand-back]` の枠の形が、今後の版でも変わらないこと
- Codex の `wait_agent` の出力を読む hook を作れるか

## 参照資料

- [Critical thinking when agents do the work（Addy Osmani、X、2026-11-03）](https://x.com/i/article/2116367635365695488)
- [Claude Code の hooks](https://code.claude.com/docs/en/hooks)
- [Codex の hooks](https://learn.chatgpt.com/docs/hooks)
- [Codex のサブエージェント](https://learn.chatgpt.com/docs/agent-configuration/subagents)
