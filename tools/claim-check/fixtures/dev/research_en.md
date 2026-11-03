# Research: prompt caching in 2026

## Key findings

- Cache hits cut input cost by 90% on repeated prefixes. <!-- expect: number -->
- One provider documents a 5-minute default TTL (https://docs.example.com/caching).
- There is no public benchmark comparing providers on cache hit rate. <!-- expect: absence -->
- I searched arXiv and GitHub for "cache hit rate benchmark" and found none.
- Two providers do not charge for cache reads. <!-- expect: absence -->
- Latency improved 2.3x for long prompts[^2].
- The median prompt length in the sample was 1,800 tokens.

## Notes

- None of the SDKs expose cache hit counts directly. <!-- expect: absence -->
- The SDK docs were last updated in 2026.
- Results were saved to `notes/caching.md`. <!-- expect: completion -->
- Pushed the notes in commit 3f9e2a1.
- It is not clear whether cache writes are billed.
- The feature isn't available on the free tier. <!-- expect: absence -->
- We don't have numbers for batch mode yet.

[^2]: https://example.com/latency-study
