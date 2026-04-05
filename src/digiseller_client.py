"""
Клиент DigiSeller API.

Документация:
- ApiLogin: /api/apilogin
- Product description: /api/products/{product_id}/data
- Bulk update prices: /api/product/edit/prices
- Update task status: /api/product/edit/UpdateProductsTaskStatus
"""

from __future__ import annotations

import logging
import random
import re
from collections import deque
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .api_client import GGSELClient, Product

logger = logging.getLogger(__name__)


class DigiSellerClient(GGSELClient):
    """Клиент DigiSeller с адаптацией ответа product/data."""

    def __init__(
        self,
        api_key: str,
        seller_id: int,
        base_url: str,
        lang: str = 'ru-RU',
        access_token: str = '',
        api_secret: str = '',
        default_product_id: int = 0,
    ):
        super().__init__(
            api_key=api_key,
            seller_id=seller_id,
            base_url=base_url,
            lang=lang,
            access_token=access_token,
            api_secret=api_secret,
        )
        self.default_product_id = int(default_product_id or 0)

    def _to_float(self, value: Any) -> Optional[float]:
        """Преобразует число/строку в float (поддержка 0,1234)."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip().replace(',', '.')
            if not normalized:
                return None
            try:
                return float(normalized)
            except Exception:
                return None
        return None

    def _extract_product_payload(
        self,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        product = payload.get('product')
        if isinstance(product, dict):
            return product
        if isinstance(product, list) and product:
            first = product[0]
            if isinstance(first, dict):
                return first

        content = payload.get('content')
        if isinstance(content, dict):
            nested_product = content.get('product')
            if isinstance(nested_product, dict):
                return nested_product
            if isinstance(nested_product, list) and nested_product:
                first = nested_product[0]
                if isinstance(first, dict):
                    return first

            for key in ('goods', 'items', 'data'):
                nested = content.get(key)
                if isinstance(nested, dict):
                    return nested
                if isinstance(nested, list) and nested:
                    first = nested[0]
                    if isinstance(first, dict):
                        return first
            return content

        return None

    def _extract_permissions(self, payload: Dict[str, Any]) -> list[str]:
        """
        Пытается вытащить список прав из произвольного JSON token/perms.
        """
        result: list[str] = []
        seen: set[str] = set()
        queue: deque[Any] = deque([payload])
        keys_of_interest = {'permissions', 'perms', 'scopes', 'scope', 'access'}

        while queue:
            current = queue.popleft()
            if isinstance(current, dict):
                for key, value in current.items():
                    if key.lower() in keys_of_interest:
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, str):
                                    normalized = item.strip()
                                    if normalized and normalized not in seen:
                                        seen.add(normalized)
                                        result.append(normalized)
                        elif isinstance(value, str):
                            normalized = value.strip()
                            if normalized and normalized not in seen:
                                seen.add(normalized)
                                result.append(normalized)
                    if isinstance(value, (dict, list)):
                        queue.append(value)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        queue.append(item)
        return result

    def get_token_perms_status(self, timeout: int = 8) -> tuple[bool, str]:
        """
        Проверяет endpoint /token/perms и возвращает:
        (is_ok, короткое описание).
        """
        perms_url = f'{self.base_url}/token/perms'
        response = self._authorized_request(
            'GET',
            perms_url,
            timeout=timeout,
            max_retries=2,
        )
        if response is None:
            return False, 'no_response'
        if response.status_code in (401, 403):
            return False, f'http_{response.status_code}'
        if response.status_code >= 400:
            return False, f'http_{response.status_code}'

        try:
            data = response.json()
        except Exception:
            return bool(response.ok), 'non_json'

        if not isinstance(data, dict):
            return bool(response.ok), 'ok'

        retval = self._response_retval(data)
        if retval is not None and retval != 0:
            return False, f'retval_{retval}'

        permissions = self._extract_permissions(data)
        if permissions:
            preview = ', '.join(permissions[:4])
            return True, preview
        return True, 'ok'

    def get_product_info(
        self,
        product_id: int,
        timeout: int = 10,
        lang: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Получение информации о товаре:
        GET /api/products/{product_id}/data
        """
        url = f'{self.base_url}/products/{product_id}/data'
        response = self._authorized_request(
            'GET',
            url,
            params={'seller_id': self.seller_id, 'lang': lang or self.lang},
            timeout=timeout,
        )
        if response is None:
            return None

        try:
            data = response.json()
        except Exception as e:
            logger.error('Ошибка парсинга DigiSeller JSON: %s', e)
            return None

        retval = self._response_retval(data)
        if retval is not None and retval != 0:
            logger.error('DigiSeller get_product_info error: %s', data)
            return None

        product_payload = self._extract_product_payload(data)
        if isinstance(product_payload, dict):
            return product_payload

        logger.error('Неожиданный формат product/data: %s', data)
        return None

    def _extract_price(self, product_info: Dict[str, Any]) -> float:
        """Извлечение цены из различных форматов ответа DigiSeller."""
        if 'price' in product_info:
            parsed = self._to_float(product_info.get('price'))
            if parsed is not None:
                return parsed

        prices = product_info.get('prices')
        if isinstance(prices, dict):
            default = prices.get('default')
            if isinstance(default, dict):
                parsed = self._to_float(default.get('price'))
                if parsed is not None:
                    return parsed

            if isinstance(default, list) and default:
                for item in default:
                    if not isinstance(item, dict):
                        continue
                    parsed = self._to_float(item.get('price'))
                    if parsed is not None:
                        return parsed

            initial = prices.get('initial')
            if isinstance(initial, dict):
                parsed = self._to_float(initial.get('price'))
                if parsed is not None:
                    return parsed

        if isinstance(prices, list):
            for item in prices:
                if not isinstance(item, dict):
                    continue
                price = self._to_float(item.get('price'))
                if price and price > 0:
                    return price

        # fallback по валютным полям
        for key in (
            'price_rub',
            'price_usd',
            'price_eur',
            'price_uah',
            'cost',
            'amount',
        ):
            if key in product_info:
                parsed = self._to_float(product_info.get(key))
                if parsed is not None:
                    return parsed

        return 0.0

    def _extract_plati_product_id(self, card_url: str) -> Optional[int]:
        path = (urlparse(card_url).path or '').strip('/')
        if not path:
            return None
        match = re.search(r'(\d+)(?:[/?#]|$)', path)
        if not match:
            return None
        try:
            product_id = int(match.group(1))
        except Exception:
            return None
        return product_id if product_id > 0 else None

    def _extract_unit_cnt_min(self, product_info: Dict[str, Any]) -> Optional[int]:
        prices_unit = product_info.get('prices_unit')
        if not isinstance(prices_unit, dict):
            return None
        for key in ('unit_cnt_min', 'unit_cnt'):
            raw = prices_unit.get(key)
            parsed = self._to_float(raw)
            if parsed is None:
                continue
            value = int(parsed)
            if value > 0:
                return value
        return None

    def _fetch_plati_unit_price_rub(
        self,
        *,
        public_product_id: int,
        qty: int,
        timeout: int,
    ) -> Optional[float]:
        if public_product_id <= 0 or qty <= 0:
            return None
        url = (
            'https://plati.market/asp/price_options.asp'
            f'?p={public_product_id}&n={qty}&c=RUB&e=&d=false&x='
            f'&rnd={random.random()}'
        )
        response = self._request_with_retry(
            'GET',
            url,
            timeout=timeout,
            max_retries=2,
            headers={
                'Accept': 'application/json,text/plain,*/*',
                'X-Requested-With': 'XMLHttpRequest',
            },
        )
        if response is None or response.status_code != 200:
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        err_code = str(payload.get('err', '0')).strip()
        if err_code not in ('0', ''):
            return None

        # endpoint возвращает unit-цену в поле price.
        price = self._to_float(payload.get('price'))
        if price is not None and price > 0:
            return round(price, 4)

        # fallback: amount/cnt -> unit price.
        amount = self._to_float(payload.get('amount'))
        cnt = self._to_float(payload.get('cnt'))
        if amount is None or cnt is None or cnt <= 0:
            return None
        return round(amount / cnt, 4)

    def get_public_price(self, product_id: int, timeout: int = 10) -> Optional[float]:
        """
        Публичная цена DigiSeller/Plati в RUB за 1 единицу.
        """
        product_info = self.get_product_info(product_id, timeout=timeout)
        if not isinstance(product_info, dict):
            return None

        card_url = str(product_info.get('card_url') or '').strip()
        public_product_id = self._extract_plati_product_id(card_url) or int(
            product_id or 0
        )
        unit_cnt_min = self._extract_unit_cnt_min(product_info) or 1
        public_price = self._fetch_plati_unit_price_rub(
            public_product_id=public_product_id,
            qty=unit_cnt_min,
            timeout=timeout,
        )
        if public_price is not None:
            logger.info(
                'DigiSeller публичная unit-цена товара %s: %s RUB',
                product_id,
                public_price,
            )
            return public_price

        # fallback по payload (может быть уже unit-цена в RUB).
        prices_unit = product_info.get('prices_unit')
        if isinstance(prices_unit, dict):
            for key in ('unit_amount', 'unit_amount_min'):
                parsed = self._to_float(prices_unit.get(key))
                if parsed is not None and parsed > 0:
                    return round(parsed, 4)

        return None

    def get_product(self, product_id: int, timeout: int = 10) -> Optional[Product]:
        product_info = self.get_product_info(product_id, timeout=timeout)
        if not product_info:
            return None

        name = (
            product_info.get('name')
            or product_info.get('title')
            or ''
        )

        currency = product_info.get('currency') or product_info.get('base_currency')
        prices = product_info.get('prices')
        if not currency and isinstance(prices, dict):
            default_price = prices.get('default')
            if isinstance(default_price, dict):
                currency = default_price.get('currency')
            elif isinstance(default_price, list):
                for item in default_price:
                    if isinstance(item, dict) and item.get('currency'):
                        currency = item.get('currency')
                        break
        if not currency and isinstance(prices, list):
            for item in prices:
                if isinstance(item, dict) and item.get('currency'):
                    currency = item.get('currency')
                    break
        if not currency:
            currency = 'RUB'

        stock = 0
        for stock_key in ('num_in_stock', 'in_stock', 'stock'):
            if stock_key in product_info:
                try:
                    stock = int(product_info.get(stock_key, 0) or 0)
                    break
                except Exception:
                    continue

        visible = product_info.get('visible')
        status = 'active'
        if visible is not None:
            try:
                status = 'active' if int(visible) == 1 else 'hidden'
            except (TypeError, ValueError):
                status = 'active'

        return Product(
            id=int(product_id),
            name=str(name),
            price=self._extract_price(product_info),
            currency=str(currency or 'RUB'),
            stock=stock,
            status=status,
        )

    def get_my_price(self, product_id: int, timeout: int = 10) -> Optional[float]:
        product = self.get_product(product_id, timeout=timeout)
        if not product:
            return None
        return product.price

    def _build_update_price_payload(
        self,
        product_id: int,
        price_4dp: str,
    ) -> list[dict[str, Any]]:
        """
        Для DigiSeller отправляем float-цену в bulk payload.
        """
        return [
            {
                'product_id': product_id,
                'price': float(price_4dp),
                'variants': [],
            }
        ]

    def _is_async_task_success(
        self,
        *,
        status: int,
        success_count: int,
        error_count: int,
        total_count: int,
    ) -> bool:
        """
        DigiSeller async semantics:
        2 = Error, 3 = Done.
        """
        return (
            status == 3
            and error_count == 0
            and (success_count > 0 or total_count == 0)
        )

    def _is_async_task_error(self, *, status: int) -> bool:
        return status == 2

    def check_api_access(self) -> bool:
        """
        Проверка доступа к DigiSeller API.
        """
        logger.info('Проверка доступа к DigiSeller API...')
        perms_ok, perms_desc = self.get_token_perms_status(timeout=8)
        if not perms_ok:
            logger.warning(
                'DigiSeller token/perms недоступен (%s), '
                'перехожу к проверке чтения товара',
                perms_desc,
            )
        else:
            logger.info('DigiSeller token/perms: %s', perms_desc)

        # Дополнительная проверка чтения товара (если ID задан).
        if self.default_product_id > 0:
            product = self.get_product(self.default_product_id, timeout=10)
            if product is None:
                logger.error(
                    'DigiSeller API: не удалось прочитать товар %s',
                    self.default_product_id,
                )
                return False
            logger.info(
                'DigiSeller API доступен, товар %s прочитан',
                self.default_product_id,
            )
            return True

        if perms_ok:
            logger.info('DigiSeller API доступен')
            return True

        logger.error(
            'DigiSeller API недоступен: нет default_product_id и token/perms fail'
        )
        return False
