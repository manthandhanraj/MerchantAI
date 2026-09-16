"""FastAPI routers.

One module per feature area. Routers are registered in `backend/app/main.py`.

    health.py          - service + data readiness probe
    dataset.py         - merchant list, dataset summary, validation report
    dashboard.py       - merchant KPIs and the daily trend series
    insights.py        - explainable business findings
    recommendations.py - actions mapped from those findings
    action_plan.py     - the short prioritised High/Medium/Low list
    forecast.py        - short-term projection
    assistant.py       - grounded natural-language Q&A

Shared:
    dependencies.py    - loads the dataset, validates merchant + date range
"""
