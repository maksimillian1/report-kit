| | |
| :--- | :--- |
| run | `rate-16` |
| profile | api |
| duration | 45s |
| rate | 16 |
| window | `2026-10-24T09:28:59Z` .. `2026-10-24T09:30:49Z` (0h01m49s) |
| commit | `d0944b2357a8` (dirty) |
| load exit | 0 |
| guards | clean |
| series exported | 7 (56 points) |
| ceilings_reached | mock-api |
| client | dropped_iterations=0, failed_share=0, p95_ms=249.565, requests=720, served_per_second=15.9902 |
| peaks | tiers.mock-api=4 |
| doubts | none |

| Ref | What it measures | This run |
| :--- | :--- | ---: |
| M1 | requests served per second | 15.9902 |
| M2 | client-observed latency p95 | 249.565 |
| M3 | share of requests not served | 0 |
| R5 | requests served in the point | 720 |
| D12 | mean pool price over the window, USD/h | 0.182856 |
| D13 | mean price of the service's requests, USD/h | 0.00446875 |
| D14 | mean of OpenCost's allocation, USD/h | 0.00307983 |
| D15 | mean price of the service's volumes, USD/h | 0.00024 |
| D16 | mean price of the service's load balancers, USD/h | 0.025 |
| D17 | mean control-plane fee over the window, USD/h | 0 |
| D18 | the service's own cost over the window, USD | 0.000905729 |
| D19 | shared cost over the window, USD | 0.00543849 |
| D20 | the service's own cost per thousand requests, USD | 0.00125796 |
| R21 | offered rate, the swept axis | 16 |
