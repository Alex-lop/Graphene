"""Orders API application service."""

from collections.abc import Mapping

from .request_models import CreateOrder
from .response_models import OrderResponse, public_json


def create_order(payload: Mapping[str, object], *, order_id: str) -> str:
    request = CreateOrder.parse_obj(payload)
    total_cents = sum(item.quantity * item.unit_price_cents for item in request.items)
    response = OrderResponse(
        order_id=order_id,
        customer_id=request.customer_id,
        item_count=len(request.items),
        total_cents=total_cents,
    )
    return public_json(response)
