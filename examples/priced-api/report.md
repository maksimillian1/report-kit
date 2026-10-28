# Executive Engineering Report — mock-api, priced (example)

> **This is the kit's worked example, not a real report, and its dollars are
> not costs.** Every replica, request and window comes from a real run on a
> single-node local cluster — see `execution.md` and `scripts/data/`. The
> rates they are priced at are **invented**, so the arithmetic from rate to
> cost is real and the proportions between the lines are not. It is here to
> show OpenCost's prices travelling from Prometheus to a cost per request.

Legend — ᴰ derived · ᴿ recorded during the run

---

## Coverage

| Area | Status | Evidence |
| :--- | :--- | :--- |
| The service's own cost per request vs offered load | measured, at invented rates | `execution.md` §4 |
| The shared pool's cost per window | measured, at invented rates | `execution.md` §4 |
| Floor, split shared / dedicated | **declared, not measured** | No idle window was recorded; §8's split needs one |
| Prices checked against a provider's | **out of scope** | The node is not an EC2 instance; `prices_match_aws` stays off |
| Any proportion between the lines | **out of scope** | Set by the invented rates, not by the service |

---

## 1. BLUF

At these rates the service's own cost falls from **$0.0075<!--VD5--> per
thousand requests** at 2<!--VR5--> req/s to **$0.0013<!--VD10-->** at
16<!--VR7-->: nearly all of it is a load balancer that costs
$0.025<!--VR4-->/h whatever the load, so eight times the rate is almost six
times cheaper per request. The pool it runs on costs about six times more per
window than the service itself, and that part is not the service's to divide.

---

## 2. Cost per unit

One unit is one request served with status 200. B is what would go if the
service did — its replicas' requests, its volume and its load balancer; A is the
pool's price less those requests.

| Offered | Requests | B over the window ᴰ | A over the window ᴰ | B per thousand requests ᴰ |
| ---: | ---: | ---: | ---: | ---: |
| 2<!--VR5--> req/s | 91<!--VR6--> | $0.000678<!--VD3--> | $0.00442<!--VD4--> | $0.0075<!--VD5--> |
| 8<!--VR9--> req/s | 360<!--VR10--> | $0.000638<!--VD13--> | $0.00393<!--VD14--> | $0.0018<!--VD15--> |
| 16<!--VR7--> req/s | 720<!--VR8--> | $0.000906<!--VD8--> | $0.00544<!--VD9--> | $0.0013<!--VD10--> |

**Boundary.** One node, the autoscaler's ceiling of four replicas reached at
8<!--VR9--> and 16<!--VR7--> req/s, 45 s of load per point. The replicas' share of B is priced by
their requests; OpenCost's own allocation of the same containers trailed it by a
fifth to two fifths over windows this short (`execution.md`, Journal).
