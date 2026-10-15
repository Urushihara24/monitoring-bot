# Storefront parser fixtures

These are synthetic, hand-reduced GGSEL-style HTML fragments, not downloaded
pages. They contain no account data, credentials, cookies, tokens, or live IDs.

- `visible_product_price.html`: the `data-testid="product-price"` selector
  contains a decimal-comma price split across nested spans; expect 149.90.
- `partial_product_price.html`: the same selector has a currency symbol but no
  amount; expect failure with no price or offers. The unrelated stock count
  must not become a price.

The tests call `RSCParser._parse_html()` directly and block the HTTP helper.
Run them with `pytest -q tests/test_rsc_parser_fixtures.py` from the repository
root. No marketplace access or environment credentials are required.
