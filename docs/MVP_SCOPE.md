# MVP Scope

Status: **locked in Stage 1**. Changing anything here means changing the plan,
not just the code.

## Problem statement

Small and mid-sized merchants sit on transaction data they cannot use. They can
see *what* happened (yesterday's sales total) but not *why* it happened or *what
to do next*. Hiring an analyst is not realistic at their scale, and generic
BI dashboards stop at charts — they leave the interpretation, the prioritisation
and the decision to the merchant.

The result: decisions on pricing, stock and promotions get made on gut feel, and
problems (a product sliding, customers not returning, stock about to run out)
are noticed weeks late.

## Target user

A small/mid-sized merchant — retail shop, kirana store, D2C seller, or small
online store — who:

- sells tens to hundreds of orders per day across a handful of products,
- has no analyst, no data team and no BI tooling,
- is not technical and will not write queries or read a spreadsheet,
- has minutes, not hours, to decide what to do today.

Secondary user: a business manager overseeing one or two such merchants.

## Product definition

MerchantAI is an **AI business partner**, not a dashboard. It answers three
questions in order:

1. **What is happening?** — metrics and trends
2. **Why is it happening?** — analysis and business health
3. **What should I do about it?** — prioritised, concrete actions

The AI Assistant grounds every answer in the merchant's own data, so it behaves
like a partner who has read the books, not a generic chatbot.

## In scope (the locked MVP)

### A. Merchant dashboard
Revenue, orders, customers, profit, average order value, and sales trends over time.

### B. Business intelligence
Revenue analysis, sales trend analysis, product performance, customer insights,
business health indicators.

### C. Growth intelligence
Growth recommendations, product recommendations, customer-retention suggestions,
inventory suggestions, priority-based actions.

### D. Forecasting
Short-term revenue/sales forecast (days-to-weeks horizon, not months).

### E. AI merchant assistant
Natural-language Q&A over the merchant's real analytics. Must handle at least:
- "Why did my sales decrease?"
- "Which product is performing best?"
- "What should I focus on today?"
- "How can I improve next week's revenue?"

### F. Action plan
A short prioritised list of actions bucketed **High / Medium / Low**.

## Explicitly out of scope

Excluded deliberately to protect the deadline. Not "later in the MVP" — not in it.

| Excluded | Why |
| --- | --- |
| User accounts, login, auth, roles | Demo runs as a selected merchant; auth adds no track value |
| Real payment/Paytm data or APIs | We use synthetic data only and make no claim of private data access |
| Live transaction ingestion, webhooks | CSV is sufficient to prove the intelligence layer |
| Databases (PostgreSQL/Mongo/Redis) | Dataset is small and read-only; CSV + pandas is enough |
| Docker, Kubernetes, microservices | One API + one frontend deploys fine without them |
| Multi-tenancy, billing, notifications, email/SMS | Not part of the track goal |
| Mobile app | Responsive web is enough |
| Long-horizon or ML-heavy forecasting | Short-term forecast only; accuracy theatre is not the point |
| Write-backs (editing inventory/orders) | MerchantAI advises; it does not operate the business |

## Non-negotiable constraints

1. **Synthetic data only.** No claim of access to private Paytm data or APIs.
2. **No hard-coded secrets.** API keys come from the environment, always.
3. **Runs without an LLM key.** With `LLM_ENABLED=false` everything except the
   Assistant still works, so the app is always demoable.
4. **Every dependency needs a stated reason.** See [ARCHITECTURE.md](ARCHITECTURE.md).

## Definition of done for the MVP

A merchant opens the app and, without typing anything, sees their metrics,
what changed and why, a forecast, and a prioritised action plan for today —
then can ask follow-up questions in plain language and get answers drawn from
their own numbers.
