# Marketplace client contract

`src.marketplace.MarketplaceClient` defines the minimum shared surface used by pricing orchestration and contributor tooling.

Required operations:

```python
check_api_access(timeout=10) -> bool
get_product(product_id, timeout=10) -> Product | None
get_my_price(product_id, timeout=10) -> float | None
update_price(product_id, new_price, timeout=10) -> bool
```

The protocol is deliberately smaller than either production client. GGSEL and DigiSeller keep marketplace-specific helpers for token refresh, display/public price handling, chats and order data.

## Contract rules

- read methods must not mutate seller state;
- `update_price` returns `True` only when the client accepted the write request according to its API contract;
- callers must not infer that a `True` return value proves the storefront price changed — the scheduler verifies the resulting price separately;
- implementations must accept a finite timeout for network operations;
- credentials and authorization material must never be emitted to logs;
- tests and demos should use `FakeMarketplaceClient` when no network behaviour is required.

This seam is intended to make future extraction of scheduler orchestration possible without coupling tests to a concrete marketplace SDK implementation.
