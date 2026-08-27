# Orders API migration target

A small Orders API pinned to Pydantic 2.13.4 but still using its temporary
`pydantic.v1` compatibility namespace and v1 validation/serialization calls.

This is the **Graphene North Star demo target**: a live Graphene mission
edits a copy materialized by `scripts/materialize_north_star.py`.

## Layout

| Path | Role |
| --- | --- |
| `orders_api/request_models.py` | request validation and SKU normalization |
| `orders_api/api.py` | request validation and response assembly |
| `orders_api/response_models.py` | immutable response and stable JSON encoding |
| `requirements.in` | direct dependency declaration |
| `requirements.lock` | exact prepared-runtime dependency version |

## Not there yet

Migrate request handling and response handling independently to native
Pydantic v2. Each source branch must preserve the full immutable suite by
itself. After both land, make the exact dependency declaration/lock update;
that final state activates the test forbidding compatibility APIs.

## Runtime policy check

```
python -m orders_api.verify_migration          # task-local, partial-safe
python -m orders_api.verify_migration --final  # assembled final gate
```

Both fixed checks use the standard library plus the target's Pydantic runtime;
they do not require Pytest. The final gate rejects the untouched compatibility
baseline. Development can additionally run
`python -m pytest -q -p no:cacheprovider`.
