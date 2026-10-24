| | |
| :--- | :--- |
| run | `rate-32b` |
| profile | api |
| duration | 45s |
| rate | 32 |
| window | `2026-10-23T15:30:40Z` .. `2026-10-23T15:32:09Z` (0h01m28s) |
| commit | `1d9d592182a5` (dirty) |
| load exit | 0 |
| guards | clean |
| series exported | 3 (18 points) |
| ceilings_reached | mock-api |
| client | dropped_iterations=6, failed_share=0, p95_ms=813.415, requests=1435, served_per_second=31.7508 |
| peaks | tiers.mock-api=4 |
| doubts | none |

| Ref | What it measures | This run |
| :--- | :--- | ---: |
| M1 | requests served per second | 31.7508 |
| M2 | client-observed latency p95 | 813.415 |
| M3 | share of requests not served | 0 |
| D8 | offered load actually served | 0.992212 |
| R9 | offered rate, the swept axis | 32 |
