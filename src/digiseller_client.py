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
from typing import Any, Dict, Optional

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
        default_product_id: int = 0,
    ):
        super().__init__(
            api_key=api_key,
            seller_id=seller_id,
            base_url=base_url,
            lang=lang,
            access_token=access_token,
        )
        self.default_product_id = int(default_product_id or 0)

    def get_product_info(
        self,
        product_id: int,
        timeout: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Получение информации о товаре:
        GET /api/products/{product_id}/data
        """
        url = f'{self.base_url}/products/{product_id}/data'
        response = self._authorized_request(
            'GET',
            url,
            params={'seller_id': self.seller_id, 'lang': self.lang},
            timeout=timeout,
        )
        if response is None:
            return None

        try:
            data = response.json()
        except Exception as e:
            logger.error('Ошибка парсинга DigiSeller JSON: %s', e)
            return None

        if data.get('retval') != 0:
            logger.error('DigiSeller get_product_info error: %s', data)
            return None

        product = data.get('product')
        if isinstance(product, dict):
            return product

        content = data.get('content')
        if isinstance(content, dict):
            # В ряде ответов продукт находится в content.product
            if isinstance(content.get('product'), dict):
                return content['product']
            return content

        logger.error('Неожиданный формат product/data: %s', data)
        return None

    def _extract_price(self, product_info: Dict[str, Any]) -> float:
        """Извлечение цены из различных форматов ответа DigiSeller."""
        if 'price' in product_info:
            try:
                return float(product_info.get('price', 0) or 0)
            except Exception:
                pass

        prices = product_info.get('prices')
        if isinstance(prices, dict):
            default = prices.get('default')
            if isinstance(default, dict):
                try:
                    return float(default.get('price', 0) or 0)
                except Exception:
                    pass

            initial = prices.get('initial')
            if isinstance(initial, dict):
                try:
                    return float(initial.get('price', 0) or 0)
                except Exception:
                    pass

        # fallback по валютным полям
        for key in ('price_rub', 'price_usd', 'price_eur', 'price_uah'):
            if key in product_info:
                try:
                    return float(product_info.get(key, 0) or 0)
                except Exception:
                    continue

        return 0.0

    def get_product(self, product_id: int, timeout: int = 10) -> Optional[Product]:
        product_info = self.get_product_info(product_id, timeout=timeout)
        if not product_info:
            return None

        name = (
            product_info.get('name')
            or product_info.get('title')
            or ''
        )

        currency = (
            product_info.get('currency')
            or product_info.get('base_currency')
            or (
                (product_info.get('prices') or {})
                .get('default', {})
                .get('currency')
            )
            or 'RUB'
        )

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
            except Exception:
                pass

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
        # Базовая проверка прав токена.
        perms_url = f'{self.base_url}/token/perms'
        response = self._authorized_request(
            'GET',
            perms_url,
            timeout=8,
            max_retries=2,
        )
        if response is None:
            logger.error('DigiSeller API недоступен (token/perms)')
            return False

        if response.status_code in (401, 403):
            logger.error('DigiSeller API: доступ запрещён (%s)', response.status_code)
            return False

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

        logger.info('DigiSeller API доступен')
        return True
