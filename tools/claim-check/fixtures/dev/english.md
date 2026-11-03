# Investigation notes

## Summary

- The script has no filter for e-mail-like terms. <!-- expect: absence -->
- I searched the module with gh search; the filter exists at src/guard.py@abc1234:19.
- Retention is not configured anywhere. <!-- expect: absence -->
- Retention is not configured in `config/retention.yaml`.
- Recall improved from 0.62 to 0.71. <!-- expect: number -->
- Recall improved from 0.62 to 0.71 (Table 4).
- Latency dropped by 35%. <!-- expect: number -->

## Details

- No tests cover the export path. <!-- expect: absence -->
- No tests cover the export path (searched `tests/` with `rg -n export tests/`).
- The function does not validate its input. <!-- expect: absence -->
- The handler is never called. <!-- expect: absence -->
- I could not find a caller. <!-- expect: absence -->
- I could not find a caller after reading `src/app.py` and `src/cli.py`.
- No longer needed after the refactor.
- No action is required.
- It returns None when the list is empty.
- The docs say "no filter is applied".
- Run `grep -v none` to drop blank rows.
- Whether the job runs nightly is unverified.
- We did not run the load test.
- Do not edit generated files.
- It doesn't matter which order the items come in.
- Uses Python 3.12 and Node 20.
- See RFC 9110 section 15.5.
- The model scored 0.84 on the held-out set. <!-- expect: number -->
- That is about 3x faster. <!-- expect: number -->
- Is there no filter?

The export job was rewritten last week and the old filter is <!-- expect: absence -->
not present in the new code.
