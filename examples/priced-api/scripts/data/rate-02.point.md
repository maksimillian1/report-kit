| | |
| :--- | :--- |
| run | `rate-02` |
| profile | api |
| duration | 45s |
| rate | 2 |
| window | `2026-10-24T09:21:05Z` .. `2026-10-24T09:22:34Z` (0h01m28s) |
| commit | `d0944b2357a8` |
| load exit | 0 |
| guards | clean |
| series exported | 7 (42 points) |
| ceilings_reached | none |
| client | dropped_iterations=0, failed_share=0, p95_ms=45.6656, requests=91, served_per_second=2.02016 |
| peaks | tiers.mock-api=2 |
| doubts | none |

| Ref | What it measures | This run |
| :--- | :--- | ---: |
| M1 | requests served per second | 2.02016 |
| M2 | client-observed latency p95 | 45.6656 |
| M3 | share of requests not served | 0 |
| R5 | requests served in the point | 91 |
| D12 | mean pool price over the window, USD/h | 0.182856 |
| D13 | mean price of the service's requests, USD/h | 0.0024375 |
| D14 | mean of OpenCost's allocation, USD/h | 0.00189583 |
| D15 | mean price of the service's volumes, USD/h | 0.00024 |
| D16 | mean price of the service's load balancers, USD/h | 0.025 |
| D17 | mean control-plane fee over the window, USD/h | 0 |
| D18 | the service's own cost over the window, USD | 0.000678188 |
| D19 | shared cost over the window, USD | 0.00442084 |
| D20 | the service's own cost per thousand requests, USD | 0.00745261 |
| R21 | offered rate, the swept axis | 2 |
