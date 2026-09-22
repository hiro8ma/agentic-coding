# 脅威と信頼境界

設計レビューで脅威を漏れなく当てるための対応表。
OWASP の LLM Top 10（2026 年版）と Agentic Applications Top 10、STRIDE を、チェック項目に紐づける。
名前と番号は版で変わる。レビューの前に、使っている版を確かめる。

- LLM Top 10 の 2026 年版は 2026-08-03 に v1.0 が公開された。項目名は公式の PDF では未確認で、二次情報に拠る。2025 年版からの主な変更は、Excessive Agency が LLM06 から LLM03 へ、System Prompt Leakage が Hidden Context Exposure（LLM08）への改称
- Agentic Applications Top 10 は 2025-12-09 公開の v1.0（2026 年版と銘打つ）が最新
- 脅威を層ごとに洗い出す枠組みとして、CSA の MAESTRO（7 層）と、OWASP の Multi-Agentic System Threat Modeling Guide がある。STRIDE を補う位置付け

## 信頼境界

| 層 | 信頼 | 中身 | 境界で行うこと |
| --- | --- | --- | --- |
| 利用者 | 低 | 利用者の入力、フロントエンド、API Gateway | 認証、入力の長さと形の検査、レート制限（境界 A） |
| エージェント | 中 | LLM の出力、エージェント、ツールの実行、State | LLM の出力を SQL やシェルにそのまま渡さない。State を権限の判断に使わない |
| 外部システム | 条件付き | DB、外部 API、MCP サーバー、他のエージェント（A2A） | ツールごとの最小権限の認証情報、タイムアウト、結果の検査（境界 B） |

境界 B の「結果の検査」は、ツールの結果を利用者の入力と同じく信頼しないデータとして扱うこと。
利用者の発話だけを見る入力のガードレールは、ツールの結果や RAG の文書に仕込まれた指示を通す（間接プロンプトインジェクション）。

攻撃の経路は、利用者の入力のほかに、ツールの結果、A2A、MCP、保存された State とメモリがある。

## OWASP LLM Top 10（2026 年版）とチェック項目

| ID | リスク | 主に見る項目 | 見落としやすい点 |
| --- | --- | --- | --- |
| LLM01 | Prompt Injection | S-2、S-3、Q-4 | ツールの結果、RAG、メモリ経由の間接の注入。形の照合だけでは言い換えを通す |
| LLM02 | Sensitive Information Disclosure | S-5、S-8 | span とログにプロンプトと応答が既定で入る |
| LLM03 | Excessive Agency | S-1、S-6 | 権限や自律のレベルを State から読むと、呼び出し元が書き換えられる |
| LLM04 | Supply Chain | S-4、A-4 | MCP サーバーとツールの定義、A2A の Agent Card の出所。署名は既定では検証されない |
| LLM05 | Data and Model Poisoning | Q-1、O-5 | RAG の文書とメモリに入る前の検査と、出所の記録 |
| LLM06 | Unbounded Consumption | O-4、C-4 | ループの上限が既定で 500 回、または無い |
| LLM07 | Misinformation | Q-2、Q-5 | 根拠の無い金額や規約を確定事項として返す |
| LLM08 | Hidden Context Exposure | S-8 | システムの指示や内部の規則が出力に出る |
| LLM09 | Vector and Embedding Weaknesses | S-1、S-5 | 検索の範囲が利用者や組織をまたぐ |
| LLM10 | Improper Output Handling | S-2、O-2 | 生成した SQL、シェルの引数、コードをそのまま実行する |

## OWASP Agentic Applications Top 10 とチェック項目

| ID | リスク | 主に見る項目 |
| --- | --- | --- |
| ASI01 | Agent Goal Hijack | S-3、A-3 |
| ASI02 | Tool Misuse and Exploitation | S-1、S-2、S-6 |
| ASI03 | Identity and Privilege Abuse | S-6、S-4 |
| ASI04 | Agentic Supply Chain Vulnerabilities | S-4、A-4 |
| ASI05 | Unexpected Code Execution | S-2、O-2 |
| ASI06 | Memory & Context Poisoning | O-5、S-3 |
| ASI07 | Insecure Inter-Agent Communication | S-6、A-4 |
| ASI08 | Cascading Failures | O-3、O-4、S-7 |
| ASI09 | Human-Agent Trust Exploitation | S-6、Q-4 |
| ASI10 | Rogue Agents | S-7、O-1 |

ASI04（実行時に読み込む MCP サーバーや A2A の相手の汚染）、ASI05（自然言語からコードやコマンドの実行に至る経路）、ASI09（整った説明が人の承認者を誤らせ、HITL をすり抜ける）は、書籍などで省かれることがある。承認を入れた設計でも ASI09 は残る

## STRIDE とチェック項目

| STRIDE | エージェントでの例 | 主に見る項目 |
| --- | --- | --- |
| Spoofing | 利用者や他のエージェントのなりすまし。署名を検証しない Agent Card | S-6 |
| Tampering | State やツールの結果の改ざん。呼び出し元からの `state_delta` | S-6、S-3 |
| Repudiation | 誰の操作か追えない。拒否した呼び出しが監査に残らない | S-6、O-1 |
| Information Disclosure | システムの指示や個人情報の漏れ | S-5、S-8 |
| Denial of Service | ループ、費用の暴走 | O-4、C-4 |
| Elevation of Privilege | ツールの権限を超えた操作 | S-1、S-6 |

## 確かめた見落とし

ADK 2.2.0 と a2a-sdk 0.3.26 で確かめたもの。

- Agent Card の署名は、検証の関数を渡さなければ検証されない。ADK の `RemoteA2aAgent` は渡さない（2.9.2 でも同じ）。署名には `a2a-sdk[signing]` が要る。A2A v1.0 の仕様でも、クライアントの検証は SHOULD で MUST ではない
- a2a-go には署名の生成と検証の API が無い（v2.5.0 時点）。Go で検証するなら自前で組む
- A2A v1.0 の仕様は、署名の対象を RFC 8785（JCS）で正規化し、`signatures` と既定値のフィールドを除く。古い SDK で作った署名は、ほかの実装で検証に通らないことがある
- 検証の鍵は、署名のヘッダーの `jku`（鍵の置き場所）を信じて取らない。攻撃者は自分の鍵の置き場所を指し、自分で署名した Agent Card を通せる。鍵は固定するか、許可した置き場所だけから取る
- 署名の `alg` を指定しないと HS256（共有の秘密）になる。公開する Agent Card には、公開鍵の方式（ES256 など）を使う
- 利用者の発話だけを見る入力のガードレールは、ツールの結果に仕込まれた指示を通す。ツールの結果を検査すれば止められるが、形の照合は言い換えに弱い。書き込みのツールを持たせない設計を併せて使う
- ADK 本体の Model Armor のプラグインも、検査するのは利用者の入力とモデルの出力で、ツールの結果は対象外に見える（コードを読んだだけで未検証）。ツールの結果は after_tool_callback で別に検査する
- 間接の注入には、単独で効く対策が無い。モデルの外の決定論的なポリシー（権限、許可リスト、承認）で行動を止めることを主にし、検出は補助にする
