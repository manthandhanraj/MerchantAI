"""Business logic layer.

Services hold all analysis and decision logic. Routes stay thin: they parse
input, call one service, and return the result. Services never touch FastAPI
objects, which keeps them unit-testable and reusable by the assistant.

    validation.py      - dataset-level rules that span rows (Stage 2)
    data_loader.py     - load, validate, normalise and cache the CSVs (Stage 2)
    metrics.py         - revenue, orders, customers, profit, AOV, products,
                         categories, inventory (Stage 2)
    analysis.py        - explainable findings with documented severity
                         thresholds (Stage 4)
    recommendations.py - maps findings to actions, traceably (Stage 5)
    action_plan.py     - prioritised High/Medium/Low shortlist (Stage 5)
    forecasting.py     - linear trend + weekday seasonality projection (Stage 6)
    llm.py             - the only module that talks to a model provider (Stage 6)
    assistant.py       - assembles context from the above and answers
                         questions, offline by default (Stage 6)
"""
