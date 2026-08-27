import json

from orders_api import create_order


def test_create_order_keeps_the_public_json_contract() -> None:
    result = create_order(
        {
            "customer_id": "cust-123",
            "items": [
                {"sku": " bolt-m8 ", "quantity": 2, "unit_price_cents": 75},
                {"sku": "NUT-M8", "quantity": 3, "unit_price_cents": 25},
            ],
        },
        order_id="ord-001",
    )

    assert result == (
        '{"customer_id":"cust-123","item_count":2,"order_id":"ord-001",'
        '"status":"accepted","total_cents":225}\n'
    )
    assert json.loads(result)["status"] == "accepted"


def test_create_order_rejects_invalid_or_extra_input() -> None:
    for payload in (
        {"customer_id": "cust-123", "items": []},
        {
            "customer_id": "cust-123",
            "items": [{"sku": "BOLT", "quantity": 0, "unit_price_cents": 10}],
        },
        {"customer_id": "cust-123", "items": [], "debug": True},
    ):
        try:
            create_order(payload, order_id="ord-invalid")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid payload was accepted: {payload!r}")
