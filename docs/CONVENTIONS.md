# Development Conventions

Status: **locked in Stage 1**. Small set, chosen so the codebase stays readable
under deadline pressure. Follow them; don't extend them.

## Naming

| Thing | Convention | Example |
| --- | --- | --- |
| Python files, functions, variables | `snake_case` | `get_revenue_trend()` |
| Python classes / Pydantic models | `PascalCase` | `SalesRecord` |
| Python constants | `UPPER_SNAKE_CASE` | `SALES_COLUMNS` |
| React components + their files | `PascalCase.jsx` | `MetricCard.jsx` |
| JS functions and variables | `camelCase` | `fetchDashboard()` |
| Non-component JS files | `camelCase.js` | `api.js` |
| API routes | lowercase, hyphenated | `/api/action-plan` |
| JSON fields | `snake_case` (matches Python) | `average_order_value` |
| CSV columns | `snake_case` | `new_customers` |

JSON stays `snake_case` end to end. Converting cases at the boundary costs more
than it's worth here, and mismatches are a common source of silent UI bugs.

## Backend rules

1. **Routes stay thin.** Parse input, call one service, return. No analysis in a route.
2. **Services never import FastAPI.** Keeps them unit-testable and reusable by the Assistant.
3. **Load the data once.** Read CSVs through `data_loader`, cached. Never read a CSV in a route or component.
4. **Type your signatures.** Function arguments and returns get type hints; API responses get Pydantic models.
5. **Guard every division.** Zero orders and zero revenue are valid data. No `inf`, no `NaN` in a response.
6. **Config comes from `settings`.** No `os.getenv` scattered through the code, no hard-coded paths or keys.
7. **Money is a plain float in INR.** Format for display in the frontend, not in the API.

## Frontend rules

1. **All fetches live in `services/api.js`.** No `fetch` calls inside components.
2. **Components render; they do not calculate.** If a number needs deriving, derive it in the backend.
3. **Handle three states every time**: loading, error, empty. The empty state is not optional.
4. **Tailwind utilities inline.** No CSS modules, no styled-components, no separate stylesheets.
5. **Keep components small.** If a component handles more than one section of the page, split it.

## Comments

Explain **why**, not what. Comment the non-obvious decision, the guard whose
reason isn't visible, the invariant a reader might otherwise break. Skip comments
that restate the code.

## Git

- Work on `main` for the MVP; branch only for something genuinely risky.
- Commit per logical unit, present tense, and say what changed:
  `Add dashboard metrics endpoint`, not `update`, `fix`, or `stage 3`.
- Reference the stage where useful: `Stage 3: add revenue trend chart`.
- **Never commit `.env`, API keys, `node_modules/`, `.venv/`, or `dist/`.**

## Stage discipline

This is the convention most likely to save the deadline: **build the current
stage only.** No stubs for stages that haven't started, no speculative
abstractions, no "we'll need this later" parameters. Later stages have their own
budget; borrowing against it is how MVPs miss deadlines.

Before adding anything, check it against [MVP_SCOPE.md](MVP_SCOPE.md). If it
isn't there, it isn't in the MVP.
