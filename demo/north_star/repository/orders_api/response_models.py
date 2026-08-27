"""Public order response model and its stable wire representation."""

import json
from typing import Literal

from pydantic.v1 import BaseModel


class OrderResponse(BaseModel):
    order_id: str
    customer_id: str
    item_count: int
    total_cents: int
    status: Literal["accepted"] = "accepted"

    class Config:
        allow_mutation = False


def public_json(response: OrderResponse) -> str:
    return json.dumps(response.dict(), sort_keys=True, separators=(",", ":")) + "\n"
