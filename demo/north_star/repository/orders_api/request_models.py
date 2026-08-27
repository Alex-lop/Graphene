"""Incoming order models using Pydantic's temporary v1 compatibility API."""

from pydantic.v1 import BaseModel, Field, validator


class OrderItem(BaseModel):
    sku: str = Field(min_length=1, regex=r"^[A-Z0-9-]+$")
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)

    @validator("sku", pre=True)
    def normalize_sku(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class CreateOrder(BaseModel):
    customer_id: str = Field(min_length=1, regex=r"^cust-[a-z0-9-]+$")
    items: list[OrderItem] = Field(min_items=1)

    class Config:
        extra = "forbid"
