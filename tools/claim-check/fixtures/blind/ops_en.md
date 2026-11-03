# Ops report

## TL;DR

- The nightly export finished and the file was uploaded to the bucket. <!-- expect: completion -->
- Error rate is 0.4% after the change. <!-- expect: number -->
- Error rate is 0.4% after the change (dashboard: https://grafana.example.com/d/errors).
- No alerts fired overnight. <!-- expect: absence -->
- No alerts fired overnight (`gcloud alpha monitoring incidents list --filter=state=open` returned an empty list).
- The old cron entry is gone. <!-- expect: absence -->
- Retries were never triggered. <!-- expect: absence -->

## Details

- I restarted the worker at 09:10.
- The fix was merged in https://github.com/octo/ops/pull/77.
- The config change was pushed but not deployed. <!-- expect: completion -->
- Disk usage went from 71% to 64%. <!-- expect: number -->
- p95 latency is 210 ms, unchanged.
- We have not seen the timeout since Monday. <!-- expect: absence -->
- There are 3 open incidents.
- The backup job does not run on weekends. <!-- expect: absence -->
