## Status

- Deployed the fix to staging. <!-- expect: completion -->
- Deployed the fix to staging: https://ci.example.com/runs/812
- The migration was applied and verified. <!-- expect: completion -->
- I haven't checked the production logs.
- Lint passed locally. <!-- expect: completion -->
- The build is green on main as of 10:42. <!-- expect: completion -->
- Nothing was written to the audit table. <!-- expect: absence -->
- The cache is never invalidated on deploy. <!-- expect: absence -->
- Coverage went from 71% to 78%. <!-- expect: number -->
- Coverage went from 71% to 78% (`pytest --cov` output in the CI log above).
- See `src/cache.py@0f1e2d3:40-38` for the TTL. <!-- expect: citation -->
