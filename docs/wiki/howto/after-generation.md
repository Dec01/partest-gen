---
title: Turning stubs into tests
status: current
verified: 2026-09-06
sources: [partest_gen/emitters/tests_p1.py, partest_gen/emitters/tests_default.py, partest_gen/emitters/payloads.py]
audience: user
ships_in_wheel: true
---

# Turning stubs into tests

What to do after a generation, until the suite is worth running. This is the long part of the
work; the generator only removed the typing.

## 0. Order the work by impact

The checklist is not a queue. Do authentication, money and personal-data writes before catalog
reads — a missing case on a payment endpoint and a missing case on a reference list are the
same line in a report and nothing alike in consequence.

Within an endpoint: the positive path first, then the access cases, then the malformed input.
A negative case that passes because the endpoint is broken in a different way teaches nothing.

## 1. One endpoint at a time

Open the stubs for a tag under `src/api/tests/<tag>/`. For each:

1. **Confirm the subtype** in `.partest/openapi_summary.md`. If it is wrong, everything below
   it is wrong — fix the classification before writing assertions against it.
2. **Unskip** only when the data it needs exists: a seed record, a path parameter, a role.
3. **Fill the TODOs** — `add_url1` and ids, foreign keys through
   `payload.set_payload_field(...)`, the expected status.
4. **Assert in three layers**: status, then the response model, then values. Status alone is
   not coverage; it only proves the server answered.
5. **Keep `type=`** exactly as generated. It is what puts the case in the right cell.

For create and update, write the vertical case — create, then read back what was created —
not only the default call against a pre-existing record. A create that returns 201 and stores
nothing passes the default case.

## 2. Use the generated facades

```python
from src.api.resources import models

await api_client.make_request(
    "GET",
    models.orders.paths.order_by_id,
    add_url1=f"/{order_id}",
    expected_status_code=200,
    validate_model=models.orders.validate.order,
    type=types.request_default,
)
```

Raw path strings drift away from the specification silently; the facades are regenerated with
it. The same applies to payloads (`.payload.*()`), validations (`.validate.*`) and headers
(`.headers.read` / `.headers.write`).

## 3. Malformed bodies go through the client

```python
await api_client.make_request(
    "POST", models.orders.paths.orders,
    content=b'{"a":',
    content_type="application/json",
    expected_status_code=400,
    type=types.request_incorrect_body,
)
```

Reaching for a raw HTTP client here is the most common way a suite loses coverage counters:
the call happens, the endpoint is exercised, and the report never hears about it.

## 4. Clean up what you create

Use the tracking client and let the registry undo things in reverse order. Test data carries
the marker, and cleanup matches on it. Do not write deletion SQL: a query that is one typo
away from removing production rows does not belong in a test suite.

## 5. Measure, then choose the next slice

```bash
pytest src/api/tests -q
pytest src/api/tests/test_zorro.py -q      # coverage report, run it last
```

The report's missing-case list per endpoint is the next backlog. Run the coverage report
serially — under parallel workers a report written inside a test sees only its own worker.

Prefer an empty missing list on critical writes over a uniform spread of shallow cases
everywhere. Coverage is a map of what you have checked, not a score to raise.

## 6. If a UI tree was generated

Treat it as a separate job with its own schedule: selectors first, then seeding through the
API, then smoke, and baselines only once the selectors are stable. Details:
[[components/ui-layer]].

## 7. Done, for a slice

- [ ] the priority-one cases exist for the chosen endpoints, with the generated `type=`
- [ ] a vertical case wherever the API creates or updates
- [ ] positive cases assert status, model and values
- [ ] the missing-case list is empty for those endpoints in a serial run
- [ ] created records are cleaned up; no secrets and no stand URLs in the repository
- [ ] UI (if any): smoke green, baselines committed only after selectors settled
