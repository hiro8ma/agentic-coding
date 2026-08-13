---
title: "Go と AI 支援開発 — 「検証が律速」時代の言語選定と go fix の学習データ介入"
date: "2026-08-13"
source: "https://developers.googleblog.com/en/why-go-is-an-ideal-language-for-ai-assisted-software-engineering/"
tags: [go, ai-assisted-engineering, gofmt, go-fix, agent-skills, mcp, typescript, benchmarks, code-review]
---

# Go と AI 支援開発

Google Developers Blog「Why Go is an ideal language for AI-assisted software engineering」（2026-08-11、Cameron Balahan / Richard Seroter）の整理。
Go チーム自身による自陣営の主張なので、独立の実証データと反論を併記して裏を取った。

## TL;DR

開発の律速が「コードを書く速度」から「AI が書いたコードを検証し保守する速度」に移った、という診断の上で、検証コストを下げるために設計された Go が有利になると主張する記事。
ただし「Go が LLM 生成に向く」ことを示す実証ベンチマークは記事にも外部にも存在せず、最も強い数値（LLM のコンパイルエラーの 94% は型エラー）は静的型付け一般の論拠で TypeScript / Rust にも等しく効く。
一方で調査から出てきた `go fix` の設計動機（OSS コーパスを近代化して将来のモデルの学習内容を変える）は、言語チームによる学習データへの介入という新しい戦略で、記事本文より重要な発見だった。

## 記事の論点 — 検証のどの段階を何が守るか

| 検証の段階 | Go の道具 | AI 時代の効き方 |
|---|---|---|
| 読む前 | gofmt の単一フォーマット | シニアもジュニアも LLM も同じ見た目になり、ハルシネーションした API 呼び出しや論理欠陥を人間が見つけやすい |
| コンパイル | 静的型 + 高速ビルド | 型の矛盾は「コンパイルが通らない」形で自動検出。エージェントの修正ループが速く安く回る |
| 依存導入 | 標準ライブラリ + module mirror + checksum DB | AI が不要な外部依存を持ち込む余地を減らし、改竄を検知する |
| 脆弱性 | govulncheck + ネイティブ fuzzing | 実際に呼んでいる脆弱コードだけを指摘するノイズの少ないフィードバックをエージェントに返せる |
| 長期保守 | Go 1 互換性保証 + go fix | 15 年前のコードが最新ツールチェーンで動く。決定的な書き換えでモダナイズをエージェントに任せられる |
| 本番 | プロファイリング + PGO | 本番データで自動最適化する閉ループ |

売っているのは「言語」ではなく「プラットフォーム」。
AI の反復生成は 1 回目 95% 正しくても回を重ねるとエラーが複利で積むという課題設定に対し、一体のツールチェーンが各反復を検証で挟む、という論法になっている。

## go fix の真の狙いは学習データへの介入（最重要の発見）

Go 1.26 で `go fix` は go/analysis 基盤に全面書き直しされ、モダナイザー 18 個を持つ（`any` / `minmax` / `rangeint` / `stringscut` / `mapsloop` / `fmtappendf` など）。
gopls と同一のアナライザ基盤を共有し、gopls が編集中にリアルタイム提示、`go fix` が複数パッケージへ一括適用する。

設計動機を Alan Donovan が公式ブログ（2026-02-17）で明言している。

> LLM コーディング支援ツールは、学習に使われた大量の Go コードに近いスタイルでコードを生成しがちで、「常に Go 1.25 の最新イディオムを使え」と一般的な指示をしても新しい書き方を拒むことがある

そこで開発者ツールの体裁を取りながら、**オープンソースの Go コーパスそのものを近代化して、将来のモデルが新しいイディオムで学習するようにする**ことを目的に挙げた。
言語チームが自言語の LLM 出力品質を、モデル側ではなくデータ側から制御する戦略で、他言語にも波及しうる。

## 実証データと反論 — 主張の強度を仕分ける

### 「Go が LLM 生成に向く」の実証はない

- 元記事に定量ベンチマークは 1 つもない。Hacker News（293 コメント）でも「測定がない」が最大の批判点
- SWE-bench Multilingual では Go の解決率がエージェント構成次第で 38.1〜57.1% までばらつく。言語の性質よりハーネスとモデルの差が支配的
- SWE-PolyBench（Amazon）は Go を含まない（Java / JS / TS / Python のみ）。ただし同一モデル内で言語ごとのスコアが 30 ポイント以上開くという知見は、Python のスコアを他言語の代理指標に使えないことを示す
- 「Go は未使用変数を許さないため LLM の構文エラー率が高い」という言説が検索結果に繰り返し現れるが、出所とされた論文（arXiv:2608.00661）は Go を対象にしておらず誤帰属。採用しない

### 94% は Go の論拠ではなく「静的型付け一般」の論拠

GitHub Blog（2026-01）が「LLM 生成コードのコンパイルエラーの 94% は型チェック失敗」を提示した（一次出所は ETH Zurich らの Type-Constrained Code Generation、arXiv:2504.09246）。
この数字は TypeScript / Rust にも等しく効くため、Go を差別化しない。
Octoverse 2025 では TypeScript が月間コントリビュータ前年比 +66.6% で GitHub 首位に立ち、GitHub は AI 支援開発との相関を要因に挙げている。
**Go 固有の主張として残るのは型以外の要因（gofmt の単一フォーマット / コンパイル速度 / 標準ライブラリによる依存削減 / Go 1 互換性保証 / go fix）**。

### Go 固有の AI 失敗モード（技術ブログ由来、研究ではない）

- エラーチェックの欠落（特に goroutine のオーケストレーションで顕著）
- goroutine のライフサイクルとデッドロック
- 意図せずインタフェースを満たす構造体（コンパイラが検知できない）
- nil と部分初期化された構造体はコンパイラが防げない、という型システムの弱さへの批判もある（Rust 陣営との主戦場）

## エコシステムの実体 — 言説より投資を見る

| 動き | 実体 |
|---|---|
| MCP 公式 Go SDK | `modelcontextprotocol/go-sdk`。Approver は Go チームと Anthropic の共同。v1.0.0 で互換性保証を形式化、現 v1.5.0 |
| gopls の MCP サーバ | `gopls mcp -instructions` でモデル向け指示文を出力。LSP の機能を MCP 経由でエージェントに渡す公式機能 |
| ADK for Go | 2026-06-30 に 2.0 Core GA（`google.golang.org/adk/v2`）。a2a-go でマルチエージェント委譲 |
| Genkit | TS / Go / Dart / Python 対応。ADK が複雑な編成、Genkit が高速開発という住み分け |
| spf13/go-skills | Cobra / Viper / Hugo 作者による Agent Skills（SKILL.md）形式の Go 開発スキル集。スキル 6 種、Claude Code マーケットプレイス対応。Clean Architecture のレイヤ構成を明示的に否定しドメイン単位パッケージを推す。ただしスター 476 でまだ初期段階（samber/cc-skills-golang は 2.9k） |
| llms.txt | `go.dev/llms.txt` は 404。ドキュメント側の LLM 向け整備は未着手で、`gopls mcp` が実質の代替 |

「エージェントが Go を書く」の言説に対し、実投資は「エージェント基盤を Go で書く」（MCP SDK / ADK / Genkit）に向いている。

## 自分の実装との接続

このリポジトリと ../agent/go の体験がそのまま記事の検証になっている。

- agent/go の genkit / ADK 実装では、型付き API に対する「コンパイルが通る = イベント写像の型整合が取れている」がエージェント生成コードの一次検証として機能した。一方で FunctionCall の重複記録のような論理バグは型では捕まらず、記事の主張の限界（型は安全網の一層でしかない）も同時に体験している
- 型エラーの往復が数秒で回るコンパイル速度が、エージェントの修正ループの実効速度を決めていた。記事の「faster, cheaper, and more reliably」の実感値
- spf13/go-skills は genkit の middleware.Skills で検証したのと同じ SKILL.md 形式。Go エコシステムの中心人物が Agent Skills に乗ったことは、skills/ ディレクトリでスキルを版管理するこのリポジトリの方針の追い風
- gopls の MCP サーバは未検証。Claude Code / Gemini CLI に `gopls mcp` を接続して、エージェントの Go コード理解がどう変わるかは次の実験候補

## 出典

- Why Go is an ideal language for AI-assisted software engineering（Google Developers Blog、2026-08-11）https://developers.googleblog.com/en/why-go-is-an-ideal-language-for-ai-assisted-software-engineering/
- Modernizing Go code with go fix（Go Blog、2026-02-17、Alan Donovan）https://go.dev/blog/gofix
- Go 1.26 Release Notes https://go.dev/doc/go1.26
- spf13/go-skills https://github.com/spf13/go-skills
- Hacker News スレッド（293 コメント）https://news.ycombinator.com/item?id=49261133
- Why AI is pushing developers toward typed languages（GitHub Blog）https://github.blog/ai-and-ml/llms/why-ai-is-pushing-developers-toward-typed-languages/
- Type-Constrained Code Generation with Language Models（arXiv:2504.09246）https://arxiv.org/pdf/2504.09246
- Beyond Pass Rate（arXiv:2606.08840）https://arxiv.org/html/2606.08840v1
- SWE-PolyBench（arXiv:2504.08703、Go 非対象）https://arxiv.org/html/2504.08703
- gopls MCP https://go.dev/gopls/features/mcp
- MCP 公式 Go SDK https://github.com/modelcontextprotocol/go-sdk
