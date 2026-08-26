# 00 · Baseline

| Field | Value |
| :--- | :--- |
| Why this execution exists | the system at rest — what every other execution inherits and does not re-measure |
| Produces | frozen configuration · the denominator · the price basis · the metric register · the floor |
| Expected *(recorded ⟨date⟩)* | ⟨what the floor is expected to be, and which block dominates it⟩ |
| Status | ⟨planning · capturing · closed⟩ |
| Revision | v⟨n⟩ · supersedes ⟨v⟨n-1⟩ · none⟩ |
| Frozen | ⟨date⟩ · commit ⟨sha⟩ · by ⟨name⟩ |
| Optional files | `./concepts.md` ⟨exists · none⟩ · `./metrics.md` ⟨exists · none⟩ |

> **Values here · anything needing a paragraph goes to `./concepts.md` as `M⟨n⟩` · kit rules
> stay in `methodology.md` and are cited, never restated.**

---

# 1 · Plan

## Preconditions for every execution downstream

Nothing may run until these are green. A campaign built on a metric name copied out of chart
documentation dies on its third point, and the points before it are unusable too.

| # | Check | Blocks | Done |
| :--- | :--- | :--- | :--- |
| 1 | Metric names read off the live endpoint, not from docs → §3 Metrics | every execution | |
| 2 | Every ref returns data with the selector executions will actually use | every execution | |
| 3 | Cost attribution active at the source of truth — IaC, not console; controller-created resources included | floor · unit cost | |
| 4 | Retention ⟨⟩ — shorter than the campaign means export after every point | every execution | |
| 5 | Configuration frozen by name and date · tooling dry-run clean | comparability | |

## Idle window rule

| Field | Value |
| :--- | :--- |
| Opens | ⟨fixture in place, triggering disabled — decided **before** the window opens⟩ |
| Closes | ⟨spans a full daily cycle, aligned to billing granularity → M⟨n⟩⟩ |
| Invalidated by | one execution point falling inside it · any human activity |
| Stays on | automated reconciliation, controllers, observability — that is floor, not noise |
| Evidence | proof of idleness exported, never asserted → `./data/` |

## What is captured here and cannot be captured later

| Constant | File | Why not later |
| :--- | :--- | :--- |
| Price basis | `./data/price-⟨YYYY-MM-DD⟩.⟨ext⟩` | negotiated rates appear in no public price list |
| Fixture profile | `./data/⟨name⟩-profile.txt` | the input can be overwritten and is not re-derivable from the report |
| Cluster identity | `./data/identity-⟨YYYY-MM-DD⟩.txt` | chart, AMI and model versions move under you |
| Proof of idleness | `./data/idle-⟨YYYY-MM-DD⟩.⟨ext⟩` | the billing backend does not record what was running |

## What this execution owes the report

| Report section | Expected to produce |
| :--- | :--- |
| §2 Workload contract | unit of work · fixture profile · applicability |
| §4.1 Floor | A / B / C split, line by line |
| §4.3–4.4 | price basis — the amortization and break-even arithmetic happens at report time |
| Coverage | which components are observable, and which are deliberately not |

---

# 2 · Journal

| Event | Date UTC | Commit | Outcome |
| :--- | :--- | :--- | :--- |
| Configuration frozen | | | |
| Fixture profiled | | | |
| Prices captured | | | |
| Idle window | ⟨open⟩ → ⟨close⟩ | | ⟨billing data available ⟨date⟩ · untagged spend resolved ⟨date⟩⟩ |

| Anomaly | Rule applied | Decision |
| :--- | :--- | :--- |
| | | |

> State the rule, not just the outcome. "Re-run" and "excluded" are both defensible;
> silently absorbing an anomaly is not.

---

# 3 · Results

| Block | Present | Feeds |
| :--- | :--- | :--- |
| Constants | yes | report §2 · every execution |
| Metrics | yes | report §4.1 · every execution |
| Applicability | yes | report §2 · every execution |
| Matrix | no | — no axis |
| Saturation | no | — no load |
| Guardrails | ⟨yes · no⟩ | |
| Routing · Open · Retro | yes | |

> Absent blocks are deleted, not left empty.

---

## Constants

Numbers frozen in the system before anything runs. Changing one invalidates comparability
between points; changing one between executions means a new revision of this document.

### Configuration freeze

| Parameter | Value | Where it is set | Why it must be frozen |
| :--- | :--- | :--- | :--- |
| | | ⟨file · CRD field · env var⟩ | ⟨one line — the paragraph version is M⟨n⟩⟩ |

### Input fixture — the denominator of every unit-cost figure

| Field | Value |
| :--- | :--- |
| Source · snapshot | |
| **Exact unit count** | ⟨the denominator — one, never two⟩ |
| Distribution | median ⟨⟩ · p95 ⟨⟩ · total ⟨⟩ · size ⟨⟩ |
| Unit of work | ⟨one sentence, including the exact moment a unit counts as done⟩ |
| Frozen | ⟨date⟩ · commit ⟨sha⟩ · `./data/⟨name⟩-profile.txt` |

### Price basis

| Field | Value |
| :--- | :--- |
| File | `./data/price-⟨YYYY-MM-DD⟩.⟨ext⟩` |
| Rate type | ⟨list · EDP / PPA · Savings Plan · spot historical average⟩ |
| Region · currency | |
| Not in the public list | ⟨negotiated lines — the part no API returns later⟩ |
| Covers | ⟨every rate any figure will use, including ones only later executions need⟩ |

---

## Metrics

> **Extract to `./metrics.md`** when these three tables stop fitting on one screen. The file
> takes all of them and nothing else.

### Exposed — read off the live endpoint

| Ref | Component | What it measures | Name as exposed | Status | Required selector |
| :--- | :--- | :--- | :--- | :--- | :--- |
| E⟨n⟩ | | | `⟨name⟩` | ⟨available · pending · retired in v⟨n⟩⟩ | ⟨when the raw series mixes producers⟩ |

> Refs are permanent and global: a retired metric keeps its number and gains a status, so
> links from older revisions resolve. Never renumber, never reuse. **Runs are named, metrics
> are numbered** — never let one identifier mean both.

### Reaches zero

Whether any claim about elastic cost survives contact with an invoice is decided here.

| Component | Scales on | Floor | Ceiling | Zero on idle |
| :--- | :--- | :--- | :--- | :--- |
| | | | | ⟨yes · no · partially⟩ |

### Floor — cost with the system running and no load

Split, never totalled. For anything claiming scale-to-zero economics the floor is the whole
argument, and it is where published architectures are least honest.

| Block | What it is | ⟨$/month⟩ | Source |
| :--- | :--- | :--- | :--- |
| A | shared — exists without this subject | | ⟨measured · derived⟩ |
| **B** | **dedicated — disappears with it. The headline** | | |
| C | standalone — A + B | | derived |

| Line | Block | ⟨$/month⟩ | Billed | Source |
| :--- | :--- | :--- | :--- | :--- |
| | | | ⟨regardless of traffic · per unit of data moved⟩ | ⟨measured · derived · recorded · estimated⟩ |

| Field | Value |
| :--- | :--- |
| Reference value | ⟨always-on alternative · previous revision · prior public claim⟩ |
| Never divided by | an assumed number of tenant subjects — that divisor is arbitrary |
| Raw data | `./data/idle-⟨YYYY-MM-DD⟩.⟨ext⟩` |

### Derived

| Figure | Formula | Inputs | Value |
| :--- | :--- | :--- | :--- |
| | `⟨formula⟩` | ⟨E refs · § of this file⟩ | |

> An unmarked derived figure is indistinguishable from a measured one, and one bad case
> discredits both. That is what the Source column exists for.

---

## Applicability

Conditions under which every figure downstream holds. Each execution adds its own on top.
Stated forward-looking, as scope and never as apology.

| Dimension | Figures hold for | Re-measure outside |
| :--- | :--- | :--- |
| Platform | ⟨cluster · region · capacity types⟩ | |
| Scale | ⟨volume and concurrency range⟩ | |
| Input | ⟨fixture profile — Constants⟩ | |
| Environment | ⟨tenancy · network path · what else runs here⟩ | |
| Commercial | ⟨rate type and date — Constants⟩ | |

---

## Routing

| Result | Destination | Applied |
| :--- | :--- | :--- |
| | ⟨report §⟨n⟩ · execution ⟨NN⟩ · nothing⟩ | |

| Gate condition | Met |
| :--- | :--- |
| §1 rows 1–5 green | |
| Idle window closed, proof exported, untagged spend resolved | |
| Every Open item below resolved, or carried into the report as declared scope | |
| Date · by | ⟨date⟩ · ⟨name⟩ |

---

## Open

Assumptions that fail silently rather than loudly.

| Item | What it invalidates if wrong | Resolved |
| :--- | :--- | :--- |
| | | |

Deliberately not observable — instrumentation without a consumer generates work, not evidence:

| What | Why nothing needs it |
| :--- | :--- |
| | |

---

## Retro

| Field | Value |
| :--- | :--- |
| Expectation | ⟨held · inverted — what actually happened⟩ |
| Cost against estimate | |
| What should have been checked earlier | ⟨and which check should have caught it⟩ |
| What belongs back in the kit | |
