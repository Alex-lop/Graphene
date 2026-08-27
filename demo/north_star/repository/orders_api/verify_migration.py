"""Pytest-free acceptance check for the Orders API migration target."""

import argparse

from pathlib import Path

import pydantic

from .api import create_order
from .request_models import CreateOrder
from .response_models import OrderResponse

ROOT = Path(__file__).resolve().parents[1]
BASELINE_REQUIREMENTS = "pydantic>=2.11,<3\n"
BASELINE_LOCK = (
    "# Compatibility baseline resolved from requirements.in.\npydantic==2.13.4\n"
)
FINAL_REQUIREMENTS = "pydantic==2.13.4\n"
FINAL_LOCK = "# Native Pydantic v2 runtime resolved from requirements.in.\npydantic==2.13.4\n"


def verify(*, final: bool = False) -> None:
    payload = {
        "customer_id": "cust-123",
        "items": [
            {"sku": " bolt-m8 ", "quantity": 2, "unit_price_cents": 75},
            {"sku": "NUT-M8", "quantity": 3, "unit_price_cents": 25},
        ],
    }
    assert create_order(payload, order_id="ord-001") == (
        '{"customer_id":"cust-123","item_count":2,"order_id":"ord-001",'
        '"status":"accepted","total_cents":225}\n'
    )
    assert CreateOrder(**payload).items[0].sku == "BOLT-M8"
    try:
        CreateOrder(**{**payload, "debug": True})
    except ValueError:
        pass
    else:
        raise AssertionError("extra request fields must be rejected")

    response = OrderResponse(
        order_id="ord-001", customer_id="cust-123", item_count=2, total_cents=225
    )
    try:
        response.total_cents = 0
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError("responses must be immutable")

    declarations = (
        (ROOT / "requirements.in").read_text(encoding="utf-8"),
        (ROOT / "requirements.lock").read_text(encoding="utf-8"),
    )
    if final:
        assert declarations == (FINAL_REQUIREMENTS, FINAL_LOCK)
    else:
        assert declarations in {
            (BASELINE_REQUIREMENTS, BASELINE_LOCK),
            (FINAL_REQUIREMENTS, FINAL_LOCK),
        }
    if declarations == (FINAL_REQUIREMENTS, FINAL_LOCK):
        assert pydantic.__version__ == "2.13.4"
        source = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "orders_api/request_models.py",
                "orders_api/api.py",
                "orders_api/response_models.py",
            )
        )
        for legacy_api in ("pydantic.v1", ".parse_obj(", ".dict()"):
            assert legacy_api not in source
        for native_api in ("model_validate(", "model_dump(", "ConfigDict", "field_validator"):
            assert native_api in source


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--final", action="store_true")
    verify(final=parser.parse_args().final)
    print("orders migration verified")
