# User Flow

Status: **locked in Stage 1**.

## Design rule

The merchant should get value **before typing anything**. Insight is pushed, not
queried. The Assistant is for follow-ups, not for the first answer — a merchant
who has to think of a good question has already been failed by the product.

## Primary flow — "what do I do today?"

```
 1. Open app
        |
 2. Select merchant (demo selector; no login)
        |
 3. DASHBOARD  -> revenue, orders, customers, profit, AOV, sales trend
        |          "What is happening?"
 4. INSIGHTS   -> revenue analysis, trend, product performance,
        |          customer insights, business health
        |          "Why is it happening?"
 5. FORECAST   -> short-term revenue/sales projection
        |          "Where is this heading?"
 6. ACTION PLAN-> High / Medium / Low prioritised actions
        |          "What should I do about it?"
 7. ASSISTANT  -> ask follow-ups in plain language, grounded in the above
```

Steps 3–6 are visible on one scrollable page. The merchant should not have to
navigate to find out their business is in trouble.

## Screen layout (single page, top to bottom)

| Section | Content | Stage |
| --- | --- | --- |
| Header | Merchant selector, date range | 3 |
| Metric cards | Revenue, orders, customers, profit, AOV — each with change vs prior period | 3 |
| Sales trend | Line chart over the selected range | 3 |
| Business health | Overall indicator plus the signals behind it | 4 |
| Insights | Revenue, trend, product performance, customer insights | 4 |
| Forecast | Short-term projection continuing the trend chart | 6 |
| Action plan | High / Medium / Low action cards | 5 |
| Assistant | Question box with suggested starter questions | 6 |

## Assistant sub-flow

```
Merchant types a question
        |
Backend builds context from real analytics
  (metrics + trends + products + customers + forecast + action plan)
        |
LLM answers using ONLY that context
        |
Answer returned, referencing the merchant's actual numbers
```

If the data cannot support an answer, the Assistant says so. It does not guess,
and it does not fall back on general retail advice dressed up as analysis.

Starter questions are shown as one-tap chips, because the target user will not
think to ask "what is my repeat customer rate trend":
- "Why did my sales decrease?"
- "Which product is performing best?"
- "What should I focus on today?"
- "How can I improve next week's revenue?"

## States to handle

Not edge cases — these decide whether the demo survives contact with a judge.

| State | Behaviour |
| --- | --- |
| Data not yet generated | Clear "dataset not loaded" message, not a stack trace |
| Backend unreachable | Frontend shows a reachable-API error (already in Stage 1 placeholder) |
| `LLM_ENABLED=false` or no key | Everything except the Assistant works; Assistant shows a disabled notice |
| Zero-activity day | Renders as zero, never `NaN` or `inf` |
| Insufficient history for a forecast | Say so instead of projecting from two points |
| Merchant with no recommendations | Say the business looks healthy; never show an empty box |

## What this flow is not

No onboarding, no signup, no settings, no export, no multi-merchant comparison,
no notifications. See [MVP_SCOPE.md](MVP_SCOPE.md).
