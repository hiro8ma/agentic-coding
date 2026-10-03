#!/usr/bin/env bash
# このリポジトリのスキルとカスタムエージェントを、ユーザー共通の Codex 設定に入れる。
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
codex_home="${CODEX_HOME:-$HOME/.codex}"

mkdir -p "$codex_home/skills" "$codex_home/agents"

# スキルはシンボリックリンクで読まれるので、リポジトリを正として張る。
for dir in "$repo"/skills/*/; do
  name="$(basename "$dir")"
  # brand-template は書き換えて使う雛形なので、そのままでは入れない。
  [ "$name" = "brand-template" ] && continue
  target="$codex_home/skills/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "skip skills/$name (実体のディレクトリがある)"
    continue
  fi
  ln -sfn "${dir%/}" "$target"
done

# カスタムエージェントの TOML はシンボリックリンクだと読まれなかった（codex-cli 0.160.0）ので複製する。
for file in "$repo"/codex/agents/*.toml; do
  cp "$file" "$codex_home/agents/$(basename "$file")"
done

echo "skills: $(find "$codex_home/skills" -maxdepth 1 -type l | wc -l | tr -d ' ') 個のリンク"
echo "agents: $(ls "$codex_home/agents" | tr '\n' ' ')"
