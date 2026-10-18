---
title: "モバイルアプリの再構築を検証する"
date: "2026-10-18"
tags: [codex, mobile, modernization, verification, worktree]
---

# モバイルアプリの再構築を検証する

ビルドが成功しても、旧版で保存したデータを読めるか、失敗時の画面が要件どおりかは分からない
再構築を任せる前に、残す動作と変更する動作を分け、実行する検査と人間の受け入れ判定を決める
[受け入れ条件の雛形](../templates/mobile-rebuild/acceptance-contract.md)は、1機能の作り直しに使う

## 残す動作を決める

別の言語へ移して動作を保つ作業と、仕様を変える作業では、合否の基準が異なる
旧版との一致を求める範囲と、変更を認める範囲を先に記録する
旧版が動かない場合は、保存データ、画面記録、通信仕様などの代替資料と、比較できない範囲を残す

| 作業 | エージェントへ渡す情報 | 人間が判断すること |
|---|---|---|
| 要件と受け入れ | 対象フロー、期待結果、失敗すべき条件 | 維持する動作と許容する差分 |
| 設計とテスト | 既存の責務、保存形式、対象OS、異常系 | 仕様の不足と比較方法の妥当性 |
| 実装 | 参照先、変更範囲、検証コマンド | 差分と検証結果に基づく採否 |
| 実機と配布 | 端末条件、署名と配布の手順 | 実機の受け入れとリリースの可否 |

これは責任の分担であり、GUIや申請操作が技術的に自動化できないという分類ではない
実装コードを人が読む必要性も、変更の影響と検証で確かめられる範囲から決める

## 検証コマンドを用意する

実プロジェクトの設定を調べてから、繰り返すコマンドをスクリプトへまとめる
コマンドライン（CLI）で実行できれば、エージェントも同じ入口から検証できる
名前は例であり、ファイルを置くだけでは完了条件にならない

| スクリプトの例 | 決めること | 失敗として返す条件 |
|---|---|---|
| `build.sh` | projectまたはworkspace、scheme、対象端末、生成先 | ビルド失敗、対象が不明、成果物がない |
| `run.sh` | インストールする成果物、起動先、ログの取得方法 | インストールや起動の失敗、対象が曖昧 |
| `test.sh` | test target、端末、対象テスト、結果の保存先 | テスト失敗、検査対象が存在しない |

端末が複数ある場合は、任意の1台を自動選択せず指定を求める
端末名や端末の識別子（UDID）は利用者の環境から渡し、共有する設定へ固定しない
ログを保存するためにパイプを使うなら、ビルドやテストの失敗が最終的な終了コードへ伝わることも確認する

開発中は変更に関係するテストへ絞り、リリース前は合意した回帰検証を別に行う
対象テストだけの成功を、アプリ全体の受け入れ成功として報告しない
`AGENTS.md`には実際の実行コマンド、適用条件、未実行時の報告方法を記し、長い手順はこのような文書へ分ける

| 対象 | 公式のCLIで確認できること |
|---|---|
| iOS | `xcodebuild test`へschemeとdestinationを渡し、`-only-testing:TestTarget/TestClass/TestMethod`で対象を絞れる |
| iOSの生成先 | `-derivedDataPath`でDerivedDataの出力先を指定できる |
| Android | `./gradlew test`のローカル単体テストと、`./gradlew connectedAndroidTest`の端末上のテストを区別する |

Codexのローカル環境では、設定画面から共通コマンドをアクションへ登録できる
アクションは呼び出し口であり、エージェントが毎回実行する完了条件は`AGENTS.md`やタスクへ別に書く
生成された`.codex`内の設定は内容を確認して共有し、未確認の設定形式を手書きで推測しない

## worktreeで再現する

worktreeごとに、選んだGitの状態から依存関係を用意して検証を実行できるか確かめる
セットアップでは、プロジェクトのロックファイルとツールの指定に従う
Androidのローカル設定とCocoaPodsの依存解決は、それぞれを使うプロジェクトにだけ適用する
Git管理外ファイルは内容と必要性を確認し、必要な設定だけを用意する

現行のCodexには、`.worktreeinclude`のパターンでignoredファイルをローカルのmanaged worktreeへコピーする方法もある
これは手動で作ったGit worktreeやremote worktreeには適用されず、既存ファイルを上書きせず、元のシンボリックリンクをコピーしない
含めるファイルを必要最小限に選び、機密情報を無差別に複製する設定にしない

ビルド生成物やテスト結果はworktree内の決めた場所へ出力すると、作業ごとに追跡しやすい
ただし、実機、シミュレーター、署名設定、SDK、共有キャッシュはディレクトリを分けただけでは独立しない
同じ実機へのインストールは順番に行い、他の作業の成果物や共有キャッシュを後片付けで消さない

2026年10月18日に確認した公式資料では、新しいworktreeを作る際のセットアップ実行を説明している
教材に登場する`CODEX_SOURCE_TREE_PATH`、`CODEX_WORKTREE_PATH`と削除時スクリプトの設定は、今回読んだ現行資料では確認できなかった
利用中の環境で確認してから使い、これらの機能が廃止されたとも断定しない
アプリによるmanaged worktreeの自動削除と、利用者が書く削除時スクリプトも区別する

## 受け入れの証拠を残す

安い検査から始め、通過した変更を旧新比較と実機確認へ進める
たとえば保存機能なら、正常な保存と復元に加え、旧形式、破損データ、保存失敗を入力にする
何を入力し、どの版と端末で、何を観測したかを結果へ添える

運用時のクラッシュ指標は、対象バージョン、期間、分母をそろえて見る
Crashlyticsのusersはアプリのinstallationを指すため、人数と無条件に同一視しない
非致命的なエラーや、クラッシュせずに起きる機能不良も別に確認する
クラッシュが少ないことだけでは、移行の互換性や要件の充足は判定できない

## 参照資料

- [Codexのローカル環境](https://learn.chatgpt.com/docs/environments/local-environment)
- [Codexのworktree](https://learn.chatgpt.com/docs/environments/git-worktrees)
- [Appleのコマンドラインテスト](https://developer.apple.com/library/archive/technotes/tn2339/_index.html)
- [AppleのDerivedData出力先の例](https://developer.apple.com/documentation/xcode/distributing-documentation-to-other-developers)
- [Androidのコマンドラインテスト](https://developer.android.com/studio/test/command-line)
- [Firebase Crashlyticsのクラッシュ指標](https://firebase.google.com/docs/crashlytics/crash-free-metrics)
- [タスク設計](task-design.md)
- [再構築の判定条件を設計するSkill](../skills/modernization-certificate/SKILL.md)
