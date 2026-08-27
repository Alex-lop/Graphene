import pytest

from orders_api.request_models import CreateOrder
from orders_api.response_models import OrderResponse


def test_request_normalizes_skus_without_mutating_the_payload() -> None:
    payload = {
        "customer_id": "cust-a",
        "items": [{"sku": " bolt-m8 ", "quantity": 1, "unit_price_cents": 75}],
    }
    request = CreateOrder(**payload)

    assert request.items[0].sku == "BOLT-M8"
    assert payload["items"][0]["sku"] == " bolt-m8 "


def test_response_is_immutable() -> None:
    response = OrderResponse(
        order_id="ord-001", customer_id="cust-a", item_count=1, total_cents=75
    )

    with pytest.raises((TypeError, ValueError)):
        response.total_cents = 0
