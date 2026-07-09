from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Export columns that must never be sent to idgod.ph
EXPORT_ONLY_FIELDS = frozenset({
    "order id", "account", "order date", "status", "payment",
    "payment method", "shipping", "tracking #", "tracking",
    "order note", "export note", "order total",
})

FIELD_ALIASES: dict[str, str] = {
    "state": "state",
    "first name": "first_name",
    "middle name": "middle_name",
    "last name": "last_name",
    "dob": "dob",
    "date of birth": "dob",
    "issue date": "issue_date",
    "street": "street",
    "address": "street",
    "address1": "street",
    "city": "city",
    "zip": "zip",
    "zip+4": "zip4",
    "sex": "sex",
    "gender": "sex",
    "height": "height",
    "weight": "weight",
    "eye color": "eye_color",
    "eyes": "eye_color",
    "hair color": "hair_color",
    "hair": "hair_color",
    "photo url": "photo",
    "photo": "photo",
    "picture": "photo",
    "signature url": "signature",
    "signature": "signature",
    "state variant": "state_variant",
    "email": "email",
}


@dataclass
class Person:
    first_name: str
    last_name: str
    state: str
    dob: str
    city: str
    zip: str
    middle_name: str = ""
    issue_date: str = ""
    street: str = ""
    zip4: str = ""
    sex: str = ""
    height: str = ""
    weight: str = ""
    eye_color: str = ""
    hair_color: str = ""
    photo: str = ""
    signature: str = ""
    state_variant: str = ""
    email: str = ""
    source_row: int | None = None
    export_order_id: str = ""

    @property
    def display_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "last_name": self.last_name,
            "state": self.state,
            "dob": self.dob,
            "issue_date": self.issue_date,
            "street": self.street,
            "city": self.city,
            "zip": self.zip,
            "sex": self.sex,
            "height": self.height,
            "weight": self.weight,
            "eye_color": self.eye_color,
            "hair_color": self.hair_color,
            "photo": self.photo,
            "signature": self.signature,
            "state_variant": self.state_variant,
            "display_name": self.display_name,
            "source_row": self.source_row,
            "export_order_id": self.export_order_id,
        }


@dataclass
class OrderResult:
    person: Person
    success: bool
    message: str = ""
    state_selected: str = ""
    cart_index: int | None = None
    price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "person": self.person.to_dict(),
            "success": self.success,
            "message": self.message,
            "state_selected": self.state_selected,
            "cart_index": self.cart_index,
            "price": self.price,
        }


@dataclass
class CheckoutResult:
    success: bool
    message: str = ""
    submitted_ids: list[str] = field(default_factory=list)
    payment_url: str = ""
    payment_info: str = ""
    total_price: float | None = None
    price_per_id: float | None = None
    discount_code: str = ""
    discount_applied: bool = False
    cart_count: int = 0
    order_results: list[OrderResult] = field(default_factory=list)
    dry_run: bool = False
    proxy_used: str = ""
    probe_results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "submitted_ids": self.submitted_ids,
            "payment_url": self.payment_url,
            "payment_info": self.payment_info,
            "total_price": self.total_price,
            "price_per_id": self.price_per_id,
            "discount_code": self.discount_code,
            "discount_applied": self.discount_applied,
            "cart_count": self.cart_count,
            "dry_run": self.dry_run,
            "proxy_used": self.proxy_used,
            "probe_results": self.probe_results,
            "orders": [o.to_dict() for o in self.order_results],
        }
