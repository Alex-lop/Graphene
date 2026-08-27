# North Star mission goal

This is the goal handed to `graphene mission start` for the Orders API target.
`scripts/materialize_north_star.py DEST` reads the machine-readable twin below.

## Goal

> Migrate the Orders API from Pydantic's v1 compatibility APIs to native Pydantic v2 and freeze its dependency declarations while preserving its exact public behavior.

## Success criteria

1. orders_api/request_models.py imports native Pydantic v2 APIs, uses ConfigDict and field_validator, and orders_api/api.py validates with model_validate while keeping all request validation and SKU normalization behavior.
2. orders_api/response_models.py uses native Pydantic v2 configuration and model_dump while keeping the immutable response model and byte-for-byte public JSON response.
3. requirements.in is exactly pydantic==2.13.4 and requirements.lock contains exactly the native-v2 lock header followed by pydantic==2.13.4, with no install or network step.
4. The immutable python -m orders_api.verify_migration check passes, no use of pydantic.v1, parse_obj or dict serialization remains in the three production source files, and no file outside orders_api/request_models.py, orders_api/api.py, orders_api/response_models.py, requirements.in and requirements.lock is created or modified.

## Expected plan shape (an expectation, not a fixture)

- Work task A (parallel) owns `orders_api/request_models.py` and
  `orders_api/api.py`: replace the compatibility import, v1 configuration and
  validator with `ConfigDict` and `field_validator`, then use `model_validate`.
- Work task B (parallel) owns `orders_api/response_models.py`: replace v1
  configuration with `ConfigDict(frozen=True)` and serialize `model_dump`.
- Integration task C depends on A and B and owns `requirements.in` and
  `requirements.lock`: write the exact final declarations specified above.
- Deterministic assembly and the fixed `orders-migration-check` verification follow.

A and B have disjoint ownership and each passes the full immutable suite alone.
C activates the suite's no-legacy-API assertions only after both roots converge.

## Retry budget

`policy.template.json` permits one retry. A killed model-only attempt may be
replaced once under a higher fence with its committed, bounded diagnostic;
repeating the same failure signature terminalizes the task instead of spending
another provider call.

The checked-in schema-2 policy pre-authorizes only this five-file, network-denied
plan and automatic finalization to Graphene's isolated internal result ref. The
initial `start_goal` request is therefore the only human authorization boundary
on the hero path; any wider plan stops for review before dispatch.

## Machine-readable twin

The block below is byte-for-byte the content of `goal.json`:

```json
{
  "schema_version": 1,
  "goal": "Migrate the Orders API from Pydantic's v1 compatibility APIs to native Pydantic v2 and freeze its dependency declarations while preserving its exact public behavior.",
  "success_criteria": [
    "orders_api/request_models.py imports native Pydantic v2 APIs, uses ConfigDict and field_validator, and orders_api/api.py validates with model_validate while keeping all request validation and SKU normalization behavior.",
    "orders_api/response_models.py uses native Pydantic v2 configuration and model_dump while keeping the immutable response model and byte-for-byte public JSON response.",
    "requirements.in is exactly pydantic==2.13.4 and requirements.lock contains exactly the native-v2 lock header followed by pydantic==2.13.4, with no install or network step.",
    "The immutable python -m orders_api.verify_migration check passes, no use of pydantic.v1, parse_obj or dict serialization remains in the three production source files, and no file outside orders_api/request_models.py, orders_api/api.py, orders_api/response_models.py, requirements.in and requirements.lock is created or modified."
  ]
}
```
