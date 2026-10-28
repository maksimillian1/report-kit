| | |
| :--- | :--- |
| run | `rate-04` |
| profile | api |
| duration | 45s |
| rate | 4 |
| window | `2026-10-23T15:12:18Z` .. `2026-10-23T15:13:40Z` (0h01m22s) |
| commit | `1d9d592182a5` (dirty) |
| load exit | 0 |
| guards | clean |
| series exported | 3 (18 points) |
| ceilings_reached | mock-api |
| client | dropped_iterations=0, failed_share=0, p95_ms=94.7892, requests=180, served_per_second=3.99952 |
| peaks | tiers.mock-api=4 |
| doubts | none |

| Ref | What it measures | This run |
| :--- | :--- | ---: |
| M1 | requests served per second | 3.99952 |
| M2 | client-observed latency p95 | 94.7892 |
| M3 | share of requests not served | 0 |
| D8 | offered load actually served | 0.99988 |
| R9 | offered rate, the swept axis | 4 |
