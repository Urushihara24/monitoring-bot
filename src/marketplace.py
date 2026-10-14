"""Marketplace client contracts and a credential-free in-memory implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .api_client import Product


@runtime_checkable
class MarketplaceClient(Protocol):
    """Core marketplace operations required by the pricing runtime.

    The full GGSEL/DigiSeller clients expose additional marketplace-specific
    methods. This protocol intentionally captures only the shared pricing
    surface so orchestration and tests can depend on a stable contract.
    """

    def check_api_access(self, timeout: int = 10) -> bool: ...

    def get_product(self, product_id: int, timeout: int = 10) -> Product | None: ...

    def get_my_price(self, product_id: int, timeout: int = 10) -> float | None: ...

    def update_price(
        self,
        product_id: int,
        new_price: float,
        timeout: int = 10,
    ) -> bool: ...


@dataclass
class FakeMarketplaceClient:
    """Deterministic in-memory marketplace used for demos and contract tests."""

    product_id: int = 1
    price: float = 0.36
    name: str = 'Demo product'
    currency: str = 'RUB'
    stock: int = 1
    status: str = 'active'

    def check_api_access(self, timeout: int = 10) -> bool:
        del timeout
        return True

    def get_product(self, product_id: int, timeout: int = 10) -> Product | None:
        del timeout
        if int(product_id) != int(self.product_id):
            return None
        return Product(
            id=self.product_id,
            name=self.name,
            price=float(self.price),
            currency=self.currency,
            stock=self.stock,
            status=self.status,
        )

    def get_my_price(self, product_id: int, timeout: int = 10) -> float | None:
        del timeout
        if int(product_id) != int(self.product_id):
            return None
        return float(self.price)

    def update_price(
        self,
        product_id: int,
        new_price: float,
        timeout: int = 10,
    ) -> bool:
        del timeout
        if int(product_id) != int(self.product_id):
            return False
        self.price = round(float(new_price), 4)
        return True
