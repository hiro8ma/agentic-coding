# Agent rules

## Release

- Run the release script before tagging. Use `scripts/release.sh`
  - **Why:** 2025-03-04, a tag was pushed without the changelog
  - **Why:** On 2025-05-06 the same tag went out without the changelog again
- Never force push to the release branch
- Ask for approval right before every deploy, every time
  - A short "go" counts as approval only when it names the target
    - **Why:** 2025-06-01, "sounds good" was read as approval for a deploy

## 下書きの扱い

下書きは共有のフォルダに置く

- 下書きを外部の場所に貼らない
- 公開の前に、毎回所有者の許可を取る
- **Why:** 2025/7/8、下書きを外部の場所に貼った。7/20、同じ下書きを別の外部の場所に貼った
- タイトルは40字以内にする

## 設定の変更

- 本番の設定を書き換えるコマンドは PreToolUse の hook で止める
  - **理由:** 2025-08-09、確認なしに設定を書き換えた。2025-09-10、別のセッションでも同じ書き換えをした

## Index

- [release notes](release.md)
- [drafts](drafts.md)

```text
- **Why:** 2020-01-01 this line is inside a code block
```

## Notes

**Why**: 3/4, a note was filed without a year. On 4/5 it happened again, after 1/2 of the notes had moved
