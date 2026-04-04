"""
GGSEL API клиент
Обновлённая версия с retry logic и обработкой ошибок
"""

import logging
import time
import hashlib
import base64
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Optional, Dict, Any
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

    def __init__(
        self,
        api_key: str,
        seller_id: int,
        base_url: str,
        lang: str = "ru-RU",
        access_token: str = "",
    ):
        """
        Args:
            api_key: API ключ (или access token для legacy-конфига)
            seller_id: ID продавца
            base_url: Базовый URL API
            lang: Язык (по умолчанию ru-RU)
            access_token: Access token (если не задан, может быть
                получен из api_key для legacy-конфига)
        """
        self.api_key = api_key
        self.seller_id = seller_id
        self.base_url = (base_url or "").rstrip("/")
        self.lang = lang
        self.access_token = self._normalize_access_token(access_token)
        self.token_valid_thru: Optional[datetime] = None
        # Если access_token не задан, но api_key похож на JWT,
        # используем его как токен (legacy-конфиг)
        if not self.access_token and self._is_probably_jwt(self.api_key):
            self.access_token = self.api_key
            self.token_valid_thru = self._extract_jwt_exp(self.access_token)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        # Параметры ожидания асинхронного обновления цены
        self.task_poll_interval = 1.5
        self.task_poll_timeout = 30.0

    def _normalize_access_token(self, token: Optional[str]) -> str:
        """Нормализует access token (обрезает пробелы, если не None)"""
        return token.strip() if token else ""

    def _response_retval(self, payload: Dict[str, Any]) -> Optional[int]:
        """
        Возвращает retval из разных форматов API ответа.

        Поддерживаются: retval / retVal / ret_val.
        """
        if not isinstance(payload, dict):
            return None
        for key in ("retval", "retVal", "ret_val"):
            if key not in payload:
                continue
            try:
                return int(payload.get(key))
            except Exception:
                return None
        return None

    def _is_probably_jwt(self, value: str) -> bool:
        """Грубая эвристика: похоже ли значение на JWT access token"""
        if not value:
            return False
        parts = value.split(".")
        return len(parts) == 3 and all(parts)

    def _extract_jwt_exp(self, token: str) -> Optional[datetime]:
        """Извлекает exp из JWT (если есть)"""
        if not self._is_probably_jwt(token):
            return None
        try:
            payload_part = token.split(".")[1]
            padded = payload_part + "=" * (-len(payload_part) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
            payload = json.loads(decoded.decode("utf-8"))
            exp = payload.get("exp")
            if exp is None:
                return None
            return datetime.fromtimestamp(int(exp), tz=timezone.utc)
        except Exception:
            return None

    def _parse_valid_thru(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _is_cached_token_valid(self) -> bool:
        if not self.access_token:
            return False
        if self.token_valid_thru is None:
            return True
        # Обновляем токен заранее за 60 секунд до истечения.
        now = datetime.now(timezone.utc)
        remaining = (self.token_valid_thru - now).total_seconds()
        return remaining > 60

    def _refresh_access_token(self, timeout: int = 10) -> bool:
        """
        Получение access token через ApiLogin:
        sign = sha256(api_key + timestamp)
        """
        if not self.api_key:
            logger.error("ApiLogin невозможен: GGSEL_API_KEY пуст")
            return False

        timestamp = str(int(time.time()))
        sign_input = (self.api_key + timestamp).encode("utf-8")
        sign = hashlib.sha256(sign_input).hexdigest()
        payload = {
            "seller_id": self.seller_id,
            "timestamp": timestamp,
            "sign": sign,
        }
        url = f"{self.base_url}/apilogin"

        response = self._request_with_retry(
            "POST",
            url,
            json=payload,
            timeout=timeout,
            max_retries=2,
        )
        if response is None:
            logger.error("ApiLogin не вернул ответ")
            return False

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Ошибка парсинга JSON ApiLogin: {e}")
            return False

        retval = self._response_retval(data)
        if data.get("token") and retval in (None, 0):
            self.access_token = str(data.get("token"))
            valid_thru = data.get("valid_thru")
            self.token_valid_thru = self._parse_valid_thru(valid_thru)
            logger.info("Access token успешно получен через ApiLogin")
            return True

        logger.error(f"ApiLogin error: {data}")
        return False

    def _get_access_token(
        self, force_refresh: bool = False, timeout: int = 10
    ) -> Optional[str]:
        if force_refresh:
            self.token_valid_thru = None
            self.access_token = ""

        if self._is_cached_token_valid():
            return self.access_token

        if self._refresh_access_token(timeout=timeout):
            return self.access_token
        return None

    def _authorized_request(
        self,
        method: str,
        url: str,
        *,
        timeout: int = 10,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        **kwargs,
    ) -> Optional[requests.Response]:
        token = self._get_access_token(timeout=timeout)
        if not token:
            logger.error("Не удалось получить access token")
            return None

        req_params = dict(params or {})
        # Пробуем оба способа авторизации:
        # 1. Query param (основной по документации GGSEL)
        # 2. Authorization header (для совместимости)
        req_params["token"] = token
        
        # Добавляем Authorization header для случаев, когда API требует Bearer token
        req_headers = dict(headers or {})
        if token and self._is_probably_jwt(token):
            req_headers["Authorization"] = f"Bearer {token}"

        response = self._request_with_retry(
            method,
            url,
            params=req_params,
            headers=req_headers,
            timeout=timeout,
            max_retries=max_retries,
            **kwargs,
        )

        # Если токен протух/отозван — пробуем получить новый и повторить 1 раз.
        if response is not None and response.status_code == 401:
            logger.warning(
                "Получен 401, пробуем обновить access token и " "повторить запрос"
            )
            token = self._get_access_token(force_refresh=True, timeout=timeout)
            if not token:
                return response
            req_params["token"] = token
            if self._is_probably_jwt(token):
                req_headers["Authorization"] = f"Bearer {token}"
            response = self._request_with_retry(
                method,
                url,
                params=req_params,
                headers=req_headers,
                timeout=timeout,
                max_retries=max_retries,
                **kwargs,
            )

        return response

    def _lang_headers(self) -> Dict[str, str]:
        """Заголовки c локалью для endpoints, где это требуется"""
        return {"lang": self.lang}

    def _request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        timeout: int = 10,
        **kwargs,
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
                    logger.error(f"API endpoint не найден (404): {url}")
                    return response

                # 401/403 retry-им с задержкой
                if response.status_code in (401, 403):
                    req_id = response.headers.get("x-request-id")
                    auth_hdr = response.headers.get("www-authenticate")
                    logger.warning(
                        f"Доступ запрещён ({response.status_code}), "
                        f"попытка {attempt + 1}/{max_retries}, "
                        f"x-request-id={req_id}, www-authenticate={auth_hdr}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2**attempt)
                        continue

                # 5xx retry-им
                if response.status_code >= 500:
                    logger.warning(
                        f"Server error ({response.status_code}), "
                        f"попытка {attempt + 1}/{max_retries}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2**attempt)
                        continue

                return response

            except requests.Timeout:
                last_error = f"Timeout ({timeout}s)"
                logger.warning(f"{last_error}, попытка {attempt + 1}/{max_retries}")

            except requests.RequestException as e:
                last_error = str(e)
                logger.error(f"Ошибка запроса: {e}")

            # Экспоненциальная задержка перед следующей попыткой
            if attempt < max_retries - 1:
                time.sleep(2**attempt)

        logger.error(f"Все попытки исчерпаны: {last_error}")
        return None

    def get_product(self, product_id: int, timeout: int = 10) -> Optional[Product]:
        """
        Получение товара по ID
        """
        product_info = self.get_product_info(product_id, timeout=timeout)
        if not product_info:
            logger.warning(f"Товар {product_id} не найден")
            return None

        return Product(
            id=product_id,
            name=str(product_info.get("name", "") or ""),
            price=float(product_info.get("price", 0) or 0),
            currency=str(product_info.get("currency", "RUB") or "RUB"),
            stock=int(product_info.get("num_in_stock", 0) or 0),
            status=(
                "active"
                if int(product_info.get("is_available", 1) or 0) == 1
                else "hidden"
            ),
        )

    def get_product_info(
        self, product_id: int, timeout: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Получение детальной информации о товаре

        GET /api_sellers/api/products/{product_id}/data
        """
        url = f"{self.base_url}/products/{product_id}/data"
        response = self._authorized_request(
            "GET",
            url,
            timeout=timeout,
        )

        if response is None:
            return None

        try:
            data = response.json()
        except Exception as e:
            logger.error(f"Ошибка парсинга JSON get_product_info: {e}")
            return None

        retval = self._response_retval(data)
        if retval in (None, 0) and isinstance(data.get("product"), dict):
            return data["product"]

        logger.error(f"GGSEL get_product_info error: {data}")
        return None

    def get_my_price(self, product_id: int, timeout: int = 10) -> Optional[float]:
        """
        Получение текущей цены товара
        """
        product_info = self.get_product_info(product_id, timeout=timeout)

        if product_info:
            price = float(product_info.get("price", 0) or 0)
            currency = str(product_info.get("currency", "RUB") or "RUB")
            logger.info(f"Текущая цена товара {product_id}: {price} {currency}")
            return price

        logger.warning(f"Не удалось получить цену товара {product_id}")
        return None

    def _coerce_price(self, value: Any) -> Optional[float]:
        """Безопасно преобразует цену к float с 4 знаками."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                price = float(value)
            except Exception:
                return None
            return round(price, 4) if price > 0 else None
        if isinstance(value, str):
            cleaned = value.strip().replace(",", ".")
            try:
                price = float(cleaned)
            except Exception:
                return None
            return round(price, 4) if price > 0 else None
        return None

    def get_public_price(self, product_id: int, timeout: int = 10) -> Optional[float]:
        """
        Получение цены с публичной витрины GGSEL (api4).

        Для ряда товаров витрина и seller endpoint могут различаться
        из-за внутренних округлений/надбавок; для статуса используем
        именно витринную цену.
        """
        url = f"https://api4.ggsel.com/goods/{int(product_id)}"
        response = self._request_with_retry(
            "GET",
            url,
            timeout=timeout,
            max_retries=2,
            headers={"Accept": "application/json"},
        )
        if response is None or response.status_code != 200:
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return None

        prices_unit = data.get("prices_unit") or {}
        if isinstance(prices_unit, dict):
            price = self._coerce_price(prices_unit.get("unit_amount"))
            if price is not None:
                logger.info(
                    "Публичная цена товара %s: %s RUB",
                    product_id,
                    price,
                )
                return price

        price = self._coerce_price(data.get("price"))
        if price is not None:
            logger.info("Публичная цена товара %s: %s RUB", product_id, price)
        return price

    def get_display_price(self, product_id: int, timeout: int = 10) -> Optional[float]:
        """
        Цена для отображения в статусе.
        Приоритет: публичная витрина -> seller API.
        """
        public_price = self.get_public_price(product_id, timeout=timeout)
        if public_price is not None:
            return public_price
        return self.get_my_price(product_id, timeout=timeout)

    def get_update_task_status(
        self, task_id: str, timeout: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Получение статуса async-задачи обновления цен

        GET /api_sellers/api/product/edit/UpdateProductsTaskStatus
        """
        url = f"{self.base_url}/product/edit/UpdateProductsTaskStatus"
        response = self._authorized_request(
            "GET",
            url,
            params={
                "taskId": task_id,
            },
            timeout=timeout,
        )
        if response is None:
            return None

        try:
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка парсинга JSON task status: {e}")
            return None

    def _format_price_4dp(self, price: float) -> str:
        """Строгое форматирование цены в 4 знака после запятой."""
        normalized = Decimal(str(price)).quantize(
            Decimal("0.0001"),
            rounding=ROUND_HALF_UP,
        )
        return format(normalized, "f")

    def _build_update_price_payload(
        self,
        product_id: int,
        price_4dp: str,
    ) -> list[dict[str, Any]]:
        """
        Формирует payload для bulk-обновления цен.
        """
        return [
            {
                "product_id": product_id,
                # Для GGSEL отправляем строку с фиксированной точностью.
                "price": price_4dp,
                "variants": [],
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
        Правило успешного завершения async-задачи.
        GGSEL: 2 = done, 3 = error.
        """
        return (
            status == 2
            and error_count == 0
            and (success_count > 0 or total_count == 0)
        )

    def _is_async_task_error(self, *, status: int) -> bool:
        """
        Правило завершения async-задачи с ошибкой.
        """
        return status == 3

    def _extract_task_id_from_response(
        self,
        response: requests.Response,
        result: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Извлекает taskId из JSON или plain-text ответа.

        Некоторые API возвращают taskId в JSON, другие — просто UUID строкой.
        """
        if isinstance(result, dict):
            task_id = result.get("taskId") or result.get("TaskId")
            if task_id:
                return str(task_id)

        body = ""
        try:
            body = (response.text or "").strip()
        except Exception:
            body = ""
        if not body:
            return None

        if re.fullmatch(r"[0-9a-fA-F-]{32,64}", body):
            return body
        return None

    def update_price(
        self, product_id: int, new_price: float, timeout: int = 10
    ) -> bool:
        """
        Обновление цены товара

        POST /api_sellers/api/product/edit/prices
        """
        url = f"{self.base_url}/product/edit/prices"
        price_4dp = self._format_price_4dp(new_price)
        data = self._build_update_price_payload(
            product_id=product_id,
            price_4dp=price_4dp,
        )

        logger.info(
            "Обновление цены: product=%s, price=%s",
            product_id,
            price_4dp,
        )

        response = self._authorized_request(
            "POST",
            url,
            json=data,
            timeout=timeout,
            max_retries=3,
        )

        if response is None:
            logger.error("Не удалось обновить цену (все попытки исчерпаны)")
            return False

        if response.status_code == 404:
            logger.error("GGSEL API endpoint не найден (404)")
            return False

        result: Dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                result = parsed
        except Exception as e:
            logger.warning(
                "Ответ update_price не JSON (%s), пытаюсь прочитать taskId из текста",
                e,
            )

        task_id = self._extract_task_id_from_response(response, result)

        # Для async-обновления важно дождаться финального статуса задачи
        if task_id:
            logger.info(
                "Получен taskId=%s, ожидаем завершение обновления цены...",
                task_id,
            )
            started_at = time.time()

            while time.time() - started_at <= self.task_poll_timeout:
                status_result = self.get_update_task_status(task_id, timeout=timeout)
                if status_result is None:
                    time.sleep(self.task_poll_interval)
                    continue

                status = int(status_result.get("Status", 0) or 0)
                success_count = int(status_result.get("SuccessCount", 0) or 0)
                error_count = int(status_result.get("ErrorCount", 0) or 0)
                total_count = int(status_result.get("TotalCount", 0) or 0)

                if self._is_async_task_success(
                    status=status,
                    success_count=success_count,
                    error_count=error_count,
                    total_count=total_count,
                ):
                    logger.info(
                        f"✅ Цена обновлена: {price_4dp} (taskId={task_id})"
                    )
                    return True

                if self._is_async_task_error(status=status):
                    logger.error(
                        "Задача обновления завершилась ошибкой: %s",
                        status_result,
                    )
                    return False

                time.sleep(self.task_poll_interval)

            logger.error(
                "Таймаут ожидания taskId=%s (%ss)",
                task_id,
                self.task_poll_timeout,
            )
            return False

        # Фоллбек: API вернул синхронный успешный ответ
        # (иногда обновление применяется без асинхронной задачи).
        retval = self._response_retval(result) if result else None
        if response.ok and retval in (None, 0) and result:
            logger.info(f"✅ Цена обновлена: {price_4dp}")
            return True

        if result:
            logger.error(f"GGSEL API update error: {result}")
        else:
            logger.error(
                "GGSEL API update error: status=%s, body=%r",
                response.status_code,
                (response.text or "")[:300],
            )
        return False

    def list_chats(
        self,
        *,
        filter_new: Optional[int] = None,
        email: Optional[str] = None,
        product_ids: Optional[list[int]] = None,
        page_size: int = 50,
        page: int = 1,
        timeout: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Возвращает список чатов продавца.
        GET /api_sellers/api/debates/v2/chats
        """
        url = f"{self.base_url}/debates/v2/chats"
        params: Dict[str, Any] = {
            "pagesize": page_size,
            "page": page,
        }
        if filter_new is not None:
            params["filter_new"] = int(filter_new)
        if email:
            params["email"] = email
        if product_ids:
            params["id_ds"] = ",".join(str(int(x)) for x in product_ids)

        response = self._authorized_request(
            "GET",
            url,
            params=params,
            timeout=timeout,
            max_retries=2,
        )
        if response is None or response.status_code >= 400:
            return []
        try:
            payload = response.json()
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        return items if isinstance(items, list) else []

    def list_messages(
        self,
        order_id: int,
        *,
        id_from: Optional[int] = None,
        id_to: Optional[int] = None,
        newer: Optional[int] = None,
        count: int = 100,
        timeout: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Возвращает сообщения по заказу.
        GET /api_sellers/api/debates/v2
        """
        url = f"{self.base_url}/debates/v2"
        params: Dict[str, Any] = {
            "id_i": int(order_id),
            "count": int(count),
        }
        if id_from is not None:
            params["id_from"] = int(id_from)
        if id_to is not None:
            params["id_to"] = int(id_to)
        if newer is not None:
            params["newer"] = int(newer)

        response = self._authorized_request(
            "GET",
            url,
            params=params,
            timeout=timeout,
            max_retries=2,
        )
        if response is None or response.status_code >= 400:
            return []
        try:
            payload = response.json()
        except Exception:
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload["items"]
        return []

    def send_chat_message(
        self,
        order_id: int,
        message: str,
        timeout: int = 10,
    ) -> bool:
        """
        Отправляет сообщение в чат заказа.
        POST /api_sellers/api/debates/v2
        """
        if not message.strip():
            return False
        url = f"{self.base_url}/debates/v2"
        response = self._authorized_request(
            "POST",
            url,
            params={"id_i": int(order_id)},
            json={"message": message},
            timeout=timeout,
            max_retries=2,
        )
        if response is None or response.status_code >= 400:
            return False
        try:
            payload = response.json()
            if isinstance(payload, dict):
                retval = self._response_retval(payload)
                return retval in (None, 0)
        except Exception:
            # На некоторых инсталляциях endpoint может вернуть пустой body.
            return response.ok
        return response.ok

    def get_order_info(
        self,
        invoice_id: int,
        *,
        locale: str = "ru",
        timeout: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Возвращает данные заказа.
        GET /api_sellers/api/purchase/info/{invoice_id}
        """
        url = f"{self.base_url}/purchase/info/{int(invoice_id)}"
        response = self._authorized_request(
            "GET",
            url,
            headers={"locale": locale},
            timeout=timeout,
            max_retries=2,
        )
        if response is None or response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        retval = self._response_retval(payload)
        if retval not in (None, 0):
            return None
        content = payload.get("content")
        if isinstance(content, dict):
            return content
        return payload

    def check_api_access(self) -> bool:
        """
        Проверка доступа к API

        Returns:
            True если API доступен
        """
        logger.info("Проверка доступа к GGSEL API...")

        response = self._authorized_request(
            "GET",
            f"{self.base_url}/products/list",
            params={"page": 1, "count": 1},
            headers=self._lang_headers(),
            timeout=5,
        )

        if response is None:
            logger.error("API недоступен")
            return False

        if response.status_code == 404:
            logger.error("API endpoint не найден (404)")
            logger.error("Требуется активация Seller API в личном кабинете GGSEL")
            return False

        if response.status_code in (401, 403):
            logger.error(f"Доступ запрещён ({response.status_code})")
            logger.error("Проверьте API ключ")
            return False

        logger.info("API доступен")
        return True
