| | |
| :--- | :--- |
| run | `rate-40` |
| profile | api |
| duration | 45s |
| rate | 40 |
| window | `2026-10-23T15:18:11Z` .. `2026-10-23T15:19:55Z` (0h01m43s) |
| commit | `1d9d592182a5` (dirty) |
| load exit | 0 |
| guards | clean |
| series exported | 3 (21 points) |
| ceilings_reached | mock-api |
| client | dropped_iterations=315, failed_share=0.0491252, p95_ms=9839.97, requests=1486, served_per_second=27.3007 |
| peaks | tiers.mock-api=4 |
| doubts | none |

| Ref | What it measures | This run |
| :--- | :--- | ---: |
| M1 | requests served per second | 27.3007 |
| M2 | client-observed latency p95 | 9839.97 |
| M3 | share of requests not served | 0.0491252 |
| D8 | offered load actually served | 0.682518 |
| R9 | offered rate, the swept axis | 40 |
