# PRレビューのプラグイン例

差分の確認手順をSkillにまとめ、ローカルのマーケットプレイスで配る最小例
レビュー結果は返すだけで、変更や投稿の権限は持たせない

```text
review-pr-plugin/
├── .agents/plugins/marketplace.json
└── plugins/review-pr/
    ├── .codex-plugin/plugin.json
    └── skills/review/SKILL.md
```

導入時はこのディレクトリをマーケットプレイスのルートとして選び、`review-pr`をインストールする
GitHubリポジトリから取り込む場合は、`review-pr-plugin/`の内容を独立した配布用リポジトリのルートへ配置する
この例を含む親リポジトリを指定しても、入れ子になったマーケットプレイスの自動検出は前提にできない
マーケットプレイスの`source.path`は選んだルートからの相対パスで、`.agents/plugins/`からの相対パスではない
プラグインの`skills`はプラグイン自身のルートを基準にする
再起動後にSkill一覧へ`review`が現れることと、読み取りだけでレビューできることを確認する
このサンプルではインストールや実際のレビュー実行は検証していない

この配置は教材に合わせたCodexの互換形式
現在のportable形式はプラグイン直下の`plugin.json`にAgent Pluginsのスキーマを宣言し、OpenAI固有の設定を`extensions.com.openai`へ置く
既存の`.codex-plugin/plugin.json`も互換形式としてサポートされる
形式の移行は単純なファイル名の変更だけで済むとは限らない

出典は[ローカルマーケットプレイスの形式](https://learn.chatgpt.com/docs/enterprise/plugin-management#supported-formats)と[プラグインのパッケージ化](https://developers.openai.com/plugins/build/plugins)
