# priced-api/scripts — the machinery behind `../execution.md`

The service from `simple-api` with a volume and a load balancer added, and,
beside it in a namespace of their own, the three things that price it:
kube-state-metrics, the kubelet's cAdvisor endpoint and OpenCost, all
scraped by one Prometheus. The runner is `simple-api`'s, unchanged; what is new
is in `../metrics.yaml`, and none of it is code.

```bash
./up.sh                                          # onto the current kubectl context
./api_point.py --set-freeze                      # once, at the start of the sweep
./api_point.py --run rate-02 --rate 2
./api_point.py --run rate-16 --rate 16           # ends and middle first,
./api_point.py --run rate-08 --rate 8            #   methodology.md §6
./down.sh                                        # what up.sh applied, and the node label
```

About **two minutes per point**, like `simple-api`'s. The runs left six
minutes between points, against OpenCost carrying one point's replicas into
the next; it does not. It recomputes its allocation once a minute, and a pod
leaves it at the first recomputation after the pod is gone, so a minute or
two between points is enough. What it does do is run that minute behind the
replicas within a point, which is why M7, read from kube-state-metrics, is the
price and M8 the second opinion — `../execution.md` has the measurement.

## Files

| | |
| :--- | :--- |
| `api_point.py` | `simple-api`'s runner, unchanged |
| `load.js` | k6, constant arrival rate; writes its summary next to the point |
| `env.yaml` | addresses, port-forwards, the generator command |
| `image-freeze.json` | the image the sweep measured, written by `--set-freeze` |
| `../metrics.yaml` | the measurement, M1–R5 as in `simple-api`; the prices, M6–M11 from OpenCost and kube-state-metrics; and what a point cost, D12–D20, worked out of them |
| `../execution.yaml` | what a point is run with, the deployment the window waits for, what makes a point invalid — and `prices_match_aws`, left off |
| `manifests/namespace.yaml` | the service alone in one namespace, what prices it in another |
| `manifests/mock-api.yaml` | the service, its HPA, a 2 GiB volume, a Service of type LoadBalancer |
| `manifests/prometheus.yaml` | scraping the service per pod, kube-state-metrics, OpenCost and cAdvisor |
| `manifests/kube-state-metrics.yaml` | with `--metric-labels-allowlist=nodes=[karpenter.sh/nodepool]`, which M6 joins on |
| `manifests/opencost.yaml` | OpenCost on the custom provider, at the **invented** rates in its ConfigMap |
| `data/` | what the runs wrote — the evidence `../execution.md` cites |

## What the run shows

The end of `data/rate-16.point.md`, as `report-kit point finish` wrote it —
every price exported over the window and every cost worked out of them by the
kit, none of it by the runner:

```
| D12 | mean pool price over the window, USD/h | 0.182856 |
| D13 | mean price of the service's requests, USD/h | 0.00446875 |
| D14 | mean of OpenCost's allocation, USD/h | 0.00307983 |
| D15 | mean price of the service's volumes, USD/h | 0.00024 |
| D16 | mean price of the service's load balancers, USD/h | 0.025 |
| D17 | mean control-plane fee over the window, USD/h | 0 |
| D18 | the service's own cost over the window, USD | 0.000905729 |
| D19 | shared cost over the window, USD | 0.00543849 |
| D20 | the service's own cost per thousand requests, USD | 0.00125796 |
```

D13 is the replicas' requests averaged over the window — 2.75 replicas'
worth, four at the peak; D14 is the same containers as OpenCost allocated
them, almost a third lower because OpenCost caught up with the scale-out a
minute late. D15 is the 2 GiB volume at the
invented storage rate, D16 the invented load balancer.

## The cluster these runs used, and why not kind

`up.sh` applies to whatever cluster `kubectl` points at and creates none. The
committed runs used a single-node **k3s** v1.31, because the machine that
recorded them could not run kind: containers inside a kind node failed to
start there. k3s also brings two things this example needs and kind does not:
a LoadBalancer implementation (servicelb), so OpenCost has a load balancer to
price, and metrics-server. On kind, `up.sh` installs metrics-server, and the
LoadBalancer Service stays pending unless cloud-provider-kind runs beside it —
untested.

The same machine could not reach `ghcr.io` or `registry.k8s.io`, so the runs
used OpenCost built from its `v1.115.0` tag and kube-state-metrics v2.13.0
from Rancher's mirror on Docker Hub. `up.sh` takes them as `OPENCOST_IMAGE`
and `KSM_IMAGE`; the manifests name the upstream images.

The node carries `karpenter.sh/nodepool=apps` because `up.sh` puts it there —
no Karpenter runs. It is the label M6 sums one pool by, and the reason
kube-state-metrics' allowlist is in the manifest.

## What a local cluster can and cannot test

| Part | Here | Why |
| :--- | :--- | :--- |
| OpenCost's prices as `M` refs, exported per window | **yes** | a real OpenCost publishing into a real Prometheus |
| A cost per point as `D` refs, worked out by `point finish` | **yes** | D12–D20 in every `data/<run>.point.md` |
| The nodepool join, the volume, the load balancer, the control-plane fee | **yes** | each line has a series here; the fee is 0, which is right for k3s |
| OpenCost's lag behind its pods | **yes** | M7 against M8 in every point |
| `prices_match_aws` against AWS | **no** | the node is not an EC2 instance and the rates are invented; `selftest` and `tests/test_price_check.py` drive it against fakes |
| What OpenCost's AWS provider publishes | **no** | it needs EKS: spot, the $0.025 load balancer default and the managed-node-group fee are read from its source, not observed |
| Any number as a cost | **no** | the rates are invented |
