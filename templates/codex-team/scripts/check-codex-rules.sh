#!/usr/bin/env bash
# チームのCodex Rulesが期待どおりの判定を返すかを、codex execpolicy checkで確かめる
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
rules="${1:-$root/.codex/rules/team.rules}"

for tool in codex jq; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool が見つからない" >&2
    exit 2
  fi
done

# 規則のmatchとnot_matchの例が外れていると、読み込みの時点で失敗する
if ! codex execpolicy check --rules "$rules" -- true >/dev/null; then
  echo "規則を読み込めない: $rules" >&2
  exit 1
fi

failures=0

# 標準入力の各行は「期待する判定 コマンド」。判定はallow / prompt / forbidden / none（どの規則にも当たらない）
run_cases() {
  local title="$1"
  shift
  local -a rule_args=()
  local file
  for file in "$@"; do
    rule_args+=(--rules "$file")
  done

  echo "== $title"
  local expected cmd got
  local -a argv
  while read -r expected cmd; do
    [[ -z "$expected" || "$expected" == \#* ]] && continue
    read -r -a argv <<<"$cmd"
    got="$(codex execpolicy check "${rule_args[@]}" -- "${argv[@]}" </dev/null | jq -r '.decision // "none"')"
    if [[ "$got" == "$expected" ]]; then
      printf 'ok  %-9s %s\n' "$got" "$cmd"
    else
      printf 'NG  %-9s %s (期待は %s)\n' "$got" "$cmd" "$expected"
      failures=$((failures + 1))
    fi
  done
}

run_cases "チームの規則だけ" "$rules" <<'EOF'
prompt     gh pr merge 12 --squash
none       gh pr view 12
prompt     git push origin feature/x
prompt     git push origin feature/x --force
forbidden  git push --force origin feature/x
forbidden  git push -f
prompt     git push --force-with-lease origin feature/x
forbidden  rm -rf build
forbidden  rm -Rf build
none       rm build/output.log
prompt     terraform apply
prompt     terraform destroy -target=module.cache
none       terraform plan
prompt     kubectl delete pod web-0
none       kubectl get pods
none       git status
none       git diff
# 前置きのトークンが違う形は規則に当たらない。サンドボックスと承認の設定で扱われる
none       rm -r -f build
none       kubectl -n prod delete pod web-0
none       terraform -chdir=infra apply
EOF

loose="$(mktemp)"
trap 'rm -f "$loose"' EXIT
cat >"$loose" <<'EOF'
prefix_rule(pattern = ["gh", "pr"], decision = "allow")
prefix_rule(pattern = ["git", "push"], decision = "allow")
prefix_rule(pattern = ["rm"], decision = "allow")
prefix_rule(pattern = ["terraform"], decision = "allow")
prefix_rule(pattern = ["kubectl"], decision = "allow")
EOF

run_cases "個人の層でallowを足した場合" "$loose" "$rules" <<'EOF'
prompt     gh pr merge 12 --squash
prompt     git push origin feature/x
forbidden  git push --force origin feature/x
forbidden  rm -rf build
prompt     terraform apply
prompt     kubectl delete pod web-0
# チームが決めていないコマンドは、個人の層の判定がそのまま使われる
allow      gh pr view 12
EOF

if ((failures > 0)); then
  echo "期待と違う判定が${failures}件ある" >&2
  exit 1
fi
echo "すべて期待どおり"
