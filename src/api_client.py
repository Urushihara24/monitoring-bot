"""
GGSEL API клиент
Обновлённая версия с retry logic и обработкой ошибок
"""

import logging
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class Product:
    """Товар GGSEL"""
    id: int
    name: str
    price: float
    currency: str
    stock: int
    status: str


class GGSELClient:
    """Клиент для GGSEL Seller API"""

    def __init__(self, api_key: str, seller_id: int, base_url: str, lang: str = 'ru-RU'):
        self.api_key = api_key
        self.seller_id = seller_id
        self.base_url = base_url
        self.lang = lang
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })
        # Параметры ожидания асинхронного обновления цены
        self.task_poll_interval = 1.5
        self.task_poll_timeout = 30.0

    def _lang_headers(self) -> Dict[str, str]:
        """Заголовки c локалью для endpoints, где это требуется"""
        return {'lang': self.lang}

    def _request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        timeout: int = 10,
        **kwargs
    ) -> Optional[requests.Response]:
        """
        HTTP запрос с retry logic

        Args:
            method: HTTP метод
            url: URL
            max_retries: Количество попыток
            timeout: Таймаут
            **kwargs: Аргументы для requests

        Returns:
            Response или None
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, timeout=timeout, **kwargs)

                # 404 не retry-им
                if response.status_code == 404:
                    logger.error(f'API endpoint не найден (404): {url}')
                    return response

                # 401/403 retry-им с задержкой
                if response.status_code in (401, 403):
                    logger.warning(f'Доступ запрещён ({response.status_code}), попытка {attempt + 1}/{max_retries}')
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue

                # 5xx retry-им
                if response.status_code >= 500:
                    logger.warning(f'Server error ({response.status_code}), попытка {attempt + 1}/{max_retries}')
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue

                return response

            except requests.Timeout:
                last_error = f'Timeout ({timeout}s)'
                logger.warning(f'{last_error}, попытка {attempt + 1}/{max_retries}')

            except requests.RequestException as e:
                last_error = str(e)
                logger.error(f'Ошибка запроса: {e}')

            # Экспоненциальная задержка перед следующей попыткой
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

        logger.error(f'Все попытки исчерпаны: {last_error}')
        return None

    def get_products(self, page: int = 1, count: int = 10, timeout: int = 10) -> List[Product]:
        """
        Получение списка товаров

        GET /api_sellers/api/products/list
        """
        url = f'{self.base_url}/products/list'
        params = {
            'page': page,
            'count': count,
            'token': self.api_key,
        }

        logger.debug(f'Запрос товаров: page={page}, count={count}')

        response = self._request_with_retry(
            'GET',
            url,
            params=params,
            headers=self._lang_headers(),
            timeout=timeout,
        )

        if response is None:
            return []

        if response.status_code == 404:
            logger.error('GGSEL API endpoint не найден (404)')
            logger.error('Возможно API требует активации в личном кабинете')
            return []

        try:
            data = response.json()
        except Exception as e:
            logger.error(f'Ошибка парсинга JSON: {e}')
            return []

        if data.get('retval') == 0 and 'rows' in data:
            products = []
            for p in data['rows']:
                products.append(
                    Product(
                        id=int(p.get('id_goods', p.get('id', 0)) or 0),
                        name=str(p.get('name_goods', p.get('name', '')) or ''),
                        price=float(p.get('price', 0) or 0),
                        currency=str(p.get('currency', 'RUB') or 'RUB'),
                        stock=int(p.get('num_in_stock', p.get('in_stock', 0)) or 0),
                        status='active' if int(p.get('visible', 1) or 0) == 1 else 'hidden',
                    )
                )
            logger.info(f'Получено товаров: {len(products)}')
            return products

        logger.error(f'GGSEL API error: {data}')
        return []

    def get_product(self, product_id: int, timeout: int = 10) -> Optional[Product]:
        """
        Получение товара по ID
        """
        product_info = self.get_product_info(product_id, timeout=timeout)
        if not product_info:
            logger.warning(f'Товар {product_id} не найден')
            return None

        return Product(
            id=product_id,
            name=str(product_info.get('name', '') or ''),
            price=float(product_info.get('price', 0) or 0),
            currency=str(product_info.get('currency', 'RUB') or 'RUB'),
            stock=int(product_info.get('num_in_stock', 0) or 0),
            status='active' if int(product_info.get('is_available', 1) or 0) == 1 else 'hidden',
        )

    def get_product_info(self, product_id: int, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Получение детальной информации о товаре

        GET /api_sellers/api/products/{product_id}/data
        """
        url = f'{self.base_url}/products/{product_id}/data'
        response = self._request_with_retry(
            'GET',
            url,
            params={'token': self.api_key},
            timeout=timeout,
        )

        if response is None:
            return None

        try:
            data = response.json()
        except Exception as e:
            logger.error(f'Ошибка парсинга JSON get_product_info: {e}')
            return None

        if data.get('retval') == 0 and isinstance(data.get('product'), dict):
            return data['product']

        logger.error(f'GGSEL get_product_info error: {data}')
        return None

    def get_my_price(self, product_id: int, timeout: int = 10) -> Optional[float]:
        """
        Получение текущей цены товара
        """
        product_info = self.get_product_info(product_id, timeout=timeout)

        if product_info:
            price = float(product_info.get('price', 0) or 0)
            currency = str(product_info.get('currency', 'RUB') or 'RUB')
            logger.info(f'Текущая цена товара {product_id}: {price} {currency}')
            return price

        logger.warning(f'Не удалось получить цену товара {product_id}')
        return None

    def get_update_task_status(self, task_id: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Получение статуса async-задачи обновления цен

        GET /api_sellers/api/product/edit/UpdateProductsTaskStatus
        """
        url = f'{self.base_url}/product/edit/UpdateProductsTaskStatus'
        response = self._request_with_retry(
            'GET',
            url,
            params={
                'token': self.api_key,
                'taskId': task_id,
            },
            timeout=timeout,
        )
        if response is None:
            return None

        try:
            return response.json()
        except Exception as e:
            logger.error(f'Ошибка парсинга JSON task status: {e}')
            return None

    def update_price(self, product_id: int, new_price: float, timeout: int = 10) -> bool:
        """
        Обновление цены товара

        POST /api_sellers/api/product/edit/prices
        """
        url = f'{self.base_url}/product/edit/prices'
        params = {'token': self.api_key}
        data = [
            {
                'product_id': product_id,
                'price': new_price,
                'variants': [],
            }
        ]

        logger.info(f'Обновление цены: product={product_id}, price={new_price}')

        response = self._request_with_retry(
            'POST',
            url,
            params=params,
            json=data,
            timeout=timeout,
            max_retries=3,
        )

        if response is None:
            logger.error('Не удалось обновить цену (все попытки исчерпаны)')
            return False

        if response.status_code == 404:
            logger.error('GGSEL API endpoint не найден (404)')
            return False

        try:
            result = response.json()
        except Exception as e:
            logger.error(f'Ошибка парсинга JSON ответа: {e}')
            return response.ok

        task_id = result.get('taskId') or result.get('TaskId')

        # Для async-обновления важно дождаться финального статуса задачи
        if task_id:
            logger.info(f'Получен taskId={task_id}, ожидаем завершение обновления цены...')
            started_at = time.time()

            while time.time() - started_at <= self.task_poll_timeout:
                status_result = self.get_update_task_status(task_id, timeout=timeout)
                if status_result is None:
                    time.sleep(self.task_poll_interval)
                    continue

                status = int(status_result.get('Status', 0) or 0)
                success_count = int(status_result.get('SuccessCount', 0) or 0)
                error_count = int(status_result.get('ErrorCount', 0) or 0)
                total_count = int(status_result.get('TotalCount', 0) or 0)

                # По документации Status: 1/2/3, где 2/3 - финальные
                if status == 2:
                    if error_count == 0 and (success_count > 0 or total_count == 0):
                        logger.info(f'✅ Цена обновлена: {new_price} (taskId={task_id})')
                        return True
                    logger.error(f'Задача завершена с ошибками: {status_result}')
                    return False

                if status == 3:
                    logger.error(f'Задача обновления завершилась ошибкой: {status_result}')
                    return False

                time.sleep(self.task_poll_interval)

            logger.error(f'Таймаут ожидания taskId={task_id} ({self.task_poll_timeout}s)')
            return False

        # Фоллбек: если API вернул синхронный успешный ответ
        if response.ok and result.get('retval') in (None, 0):
            logger.info(f'✅ Цена обновлена: {new_price}')
            return True

        logger.error(f'GGSEL API update error: {result}')
        return False

    def check_api_access(self) -> bool:
        """
        Проверка доступа к API

        Returns:
            True если API доступен
        """
        logger.info('Проверка доступа к GGSEL API...')

        response = self._request_with_retry(
            'GET',
            f'{self.base_url}/products/list',
            params={'page': 1, 'count': 1, 'token': self.api_key},
            headers=self._lang_headers(),
            timeout=5,
        )

        if response is None:
            logger.error('API недоступен')
            return False

        if response.status_code == 404:
            logger.error('API endpoint не найден (404)')
            logger.error('Требуется активация Seller API в личном кабинете GGSEL')
            return False

        if response.status_code in (401, 403):
            logger.error(f'Доступ запрещён ({response.status_code})')
            logger.error('Проверьте API ключ')
            return False

        logger.info('API доступен')
        return True


# Глобальный экземпляр (создаётся в main)
api_client: Optional[GGSELClient] = None
