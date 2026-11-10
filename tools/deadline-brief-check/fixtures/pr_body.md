## TL;DR

検索の結果の並びを、新しい順から関連の高い順に変える

## Overview

- 並べ替えは `sort=relevance` のときだけ効く

```bash
curl "https://api.example.com/search?since=2026/01/01"
```

## Debug List

- [x] 2026/11/02 のログで、件数が変わらないことを確かめた

## Review Deadline

2026/11/20 17:00（目安、11/25の社内のデモより前に入れたい）

- 遅れるとデモで古い並びを見せることになる
- 間に合わなさそうなら、11/19の昼までにこの PR のコメントで知らせてほしい

<!-- footer -->
---
<a href="https://example.com/track?expires=2026/12/01">Open</a>
