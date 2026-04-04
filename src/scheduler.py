"""
Scheduler - циклический обработчик auto-pricing.
Поддерживает профильный режим (GGSEL / DigiSeller).
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from dotenv import dotenv_values

from .config import config
from .logic import calculate_price
from .rsc_parser import ParseResult, rsc_parser
from .storage import DEFAULT_PROFILE, storage
from .validator import validate_runtime_config

if TYPE_CHECKING:
    from .api_client import GGSELClient
    from .telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

_MODE_ALREADY = 'already'
_MODE_ADD = 'add'

_ALREADY_KEYWORDS = (
    'уже в друзьях',
    'уже друг',
    'already friend',
    'already in friend',
    'already added',
)
_ADD_KEYWORDS = (
    'добавит',
    'добавлю',
    'добавить в друзья',
    'не в друзьях',
    'add me',
    'will add',
    'not friend',
)


class Scheduler:
    """
    Планировщик задач auto-pricing.

    Цикл:
    1. Парсим цены конкурентов
    2. Получаем текущую цену товара
    3. Рассчитываем целевую цену
    4. Обновляем цену через API (или skip)
    5. Сохраняем state/историю
    6. Отправляем уведомления
    """

    def __init__(
        self,
        api_client: 'GGSELClient',
        telegram_bot: 'TelegramBot',
        *,
        profile_id: str = DEFAULT_PROFILE,
        profile_name: str = 'GGSEL',
        product_id: Optional[int] = None,
        competitor_urls: Optional[list] = None,
    ):
        self.api_client = api_client
        self.telegram_bot = telegram_bot
        self.profile_id = (profile_id or DEFAULT_PROFILE).strip().lower()
        self.profile_name = profile_name
        self.product_id = int(product_id or 0)
        self.default_competitor_urls = competitor_urls or []
        self._running = False
        self._env_cookies_signature: Optional[tuple[str, int, int]] = None
        self._env_cookies_cached_value: Optional[str] = None

    def _runtime(self):
        return storage.get_runtime_config(
            config,
            profile_id=self.profile_id,
            default_urls=self.default_competitor_urls,
        )

    def _state(self):
        return storage.get_state(profile_id=self.profile_id)

    def _tag(self, message: str) -> str:
        return f'[{self.profile_name}] {message}'

    def _normalize_cookies_value(self, value: Optional[str]) -> str:
        """
        Нормализует строку cookies из .env.
        Docker Compose использует '$$' для экранирования '$' в значениях.
        """
        raw = (value or '').strip()
        if not raw:
            return ''
        return raw.replace('$$', '$')

    async def _notify_error_throttled(
        self,
        key: str,
        message: str,
        cooldown_seconds: int = 300,
    ):
        if storage.should_send_alert(
            key=key,
            cooldown_seconds=cooldown_seconds,
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_error(self._tag(message))
        else:
            logger.info(
                '[%s] Уведомление подавлено throttling: key=%s',
                self.profile_name,
                key,
            )

    async def _notify_skip_throttled(
        self,
        runtime,
        current_price: float,
        target_price: float,
        competitor_price: float,
        reason: str,
    ):
        if not getattr(runtime, 'NOTIFY_SKIP', False):
            return
        if storage.should_send_alert(
            key='skip_notification',
            cooldown_seconds=getattr(runtime, 'NOTIFY_SKIP_COOLDOWN_SECONDS', 300),
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_skip(
                current_price=current_price,
                target_price=target_price,
                competitor_price=competitor_price,
                reason=reason,
                profile_name=self.profile_name,
            )
        else:
            logger.info('[%s] Skip-уведомление подавлено', self.profile_name)

    async def _notify_competitor_change_if_needed(
        self,
        runtime,
        old_price: Optional[float],
        new_price: float,
        rank: Optional[int],
        url: Optional[str],
    ):
        if not getattr(runtime, 'NOTIFY_COMPETITOR_CHANGE', True):
            return
        if old_price is None:
            return
        delta = abs(new_price - old_price)
        if delta < getattr(runtime, 'COMPETITOR_CHANGE_DELTA', 0.0001):
            return
        if storage.should_send_alert(
            key='competitor_price_change',
            cooldown_seconds=getattr(
                runtime,
                'COMPETITOR_CHANGE_COOLDOWN_SECONDS',
                60,
            ),
            profile_id=self.profile_id,
        ):
            await self.telegram_bot.notify_competitor_price_changed(
                old_price=old_price,
                new_price=new_price,
                delta=delta,
                rank=rank,
                url=url,
                profile_name=self.profile_name,
            )

    async def _notify_parser_issue_if_needed(
        self,
        runtime,
        url: str,
        result: ParseResult,
    ):
        if not getattr(runtime, 'NOTIFY_PARSER_ISSUES', True):
            return
        reason = (
            result.block_reason
            or (f'http_{result.status_code}' if result.status_code else None)
            or 'parse_failed'
        )
        key = f'parser_issue:{reason}'
        if not storage.should_send_alert(
            key=key,
            cooldown_seconds=getattr(
                runtime,
                'PARSER_ISSUE_COOLDOWN_SECONDS',
                300,
            ),
            profile_id=self.profile_id,
        ):
            return
        await self.telegram_bot.notify_parser_issue(
            url=url,
            method=result.method,
            reason=reason,
            error=result.error or 'unknown',
            status_code=result.status_code,
            profile_name=self.profile_name,
        )

    async def _sync_cookies_from_env(self, force_reload: bool = False) -> bool:
        """
        Подтягивает COMPETITOR_COOKIES из .env в runtime settings.

        Args:
            force_reload: Принудительно перечитать .env, игнорируя кеш
                сигнатуры файла.
        """
        env_path = Path(config.ENV_FILE_PATH).expanduser()
        if not env_path.is_absolute():
            env_path = Path.cwd() / env_path
        if not env_path.exists():
            self._env_cookies_signature = None
            self._env_cookies_cached_value = None
            return False
        try:
            stat = env_path.stat()
            signature = (
                str(env_path.resolve()),
                int(stat.st_mtime_ns),
                int(stat.st_size),
            )
            if signature == self._env_cookies_signature and not force_reload:
                env_cookies = self._env_cookies_cached_value or ''
            else:
                env_data = dotenv_values(str(env_path))
                env_cookies = ''
                cookie_keys = {
                    'ggsel': (
                        'GGSEL_COMPETITOR_COOKIES',
                        'COMPETITOR_COOKIES',
                    ),
                    'digiseller': (
                        'DIGISELLER_COMPETITOR_COOKIES',
                        'COMPETITOR_COOKIES',
                    ),
                }.get(self.profile_id, ('COMPETITOR_COOKIES',))

                for key in cookie_keys:
                    candidate = self._normalize_cookies_value(
                        str(env_data.get(key) or '')
                    )
                    if candidate:
                        env_cookies = candidate
                        break

                self._env_cookies_signature = signature
                self._env_cookies_cached_value = env_cookies or None

            if not env_cookies:
                return False
            current = storage.get_runtime_setting(
                'COMPETITOR_COOKIES',
                profile_id=self.profile_id,
            )
            if current != env_cookies:
                storage.set_runtime_setting(
                    'COMPETITOR_COOKIES',
                    env_cookies,
                    source='env_sync',
                    profile_id=self.profile_id,
                )
                logger.info(
                    '[%s] Cookies синхронизированы из .env (%s символов)',
                    self.profile_name,
                    len(env_cookies),
                )
            return True
        except Exception as e:
            logger.error(
                '[%s] Ошибка синхронизации cookies из .env: %s',
                self.profile_name,
                e,
            )
            return False

    async def _reload_cookies_from_backup(self) -> bool:
        cookies_backup_path = Path(config.COMPETITOR_COOKIES_BACKUP_PATH)
        if not cookies_backup_path.exists():
            return False
        try:
            import json

            with open(cookies_backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cookies_list = data.get('cookies', [])
            cookie_parts = []
            for cookie in cookies_list:
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                if name and value:
                    cookie_parts.append(f'{name}={value}')
            if not cookie_parts:
                return False
            cookie_string = '; '.join(cookie_parts)
            current = storage.get_runtime_setting(
                'COMPETITOR_COOKIES',
                profile_id=self.profile_id,
            )
            if current != cookie_string:
                storage.set_runtime_setting(
                    'COMPETITOR_COOKIES',
                    cookie_string,
                    source='backup_sync',
                    profile_id=self.profile_id,
                )
                logger.info(
                    '[%s] Cookies перезагружены из backup в runtime (%s cookies)',
                    self.profile_name,
                    len(cookie_parts),
                )
            else:
                logger.debug(
                    '[%s] Cookies из backup уже актуальны',
                    self.profile_name,
                )
            return True
        except Exception as e:
            logger.error(
                '[%s] Ошибка перезагрузки cookies: %s',
                self.profile_name,
                e,
            )
            return False

    async def _parse_competitor_price(
        self,
        url: str,
        runtime,
        timeout: int = 15,
    ) -> ParseResult:
        """Каскадный парсинг: только stealth_requests."""
        logger.info('[%s] 🔍 Парсинг цены: %s', self.profile_name, url)
        # Используем cookies только из runtime (БД/env-sync),
        # без fallback на config, чтобы не возвращать протухшие значения
        # из process env после авто-очистки runtime cookies.
        cookies = runtime.COMPETITOR_COOKIES or None

        result = await asyncio.to_thread(
            rsc_parser.parse_url,
            url,
            timeout=timeout,
            cookies=cookies,
        )
        if result.success:
            return result

        # Если cookies протухли, сначала принудительно подтягиваем
        # обновлённые cookies (если внешний скрипт уже записал их в .env /
        # backup), и только потом делаем fallback без cookies.
        if result.cookies_expired and cookies:
            logger.warning(
                '[%s] Cookies протухли для %s, пробую обновить cookies...',
                self.profile_name,
                url,
            )
            synced_from_env = await self._sync_cookies_from_env(
                force_reload=True,
            )
            if not synced_from_env:
                await self._reload_cookies_from_backup()

            refreshed_runtime = self._runtime()
            refreshed_cookies = refreshed_runtime.COMPETITOR_COOKIES or None
            if refreshed_cookies and refreshed_cookies != cookies:
                logger.info(
                    '[%s] Использую обновлённые cookies из runtime '
                    'и повторяю парсинг',
                    self.profile_name,
                )
                refreshed_result = await asyncio.to_thread(
                    rsc_parser.parse_url,
                    url,
                    timeout=timeout,
                    cookies=refreshed_cookies,
                )
                if refreshed_result.success:
                    return refreshed_result
                result = refreshed_result

            logger.warning(
                '[%s] Повторяю парсинг без cookies для %s...',
                self.profile_name,
                url,
            )
            retry_result = await asyncio.to_thread(
                rsc_parser.parse_url,
                url,
                timeout=timeout,
                cookies=None,
            )
            if retry_result.success:
                if (
                    cookies
                    and (
                        not refreshed_cookies
                        or refreshed_cookies == cookies
                    )
                ):
                    storage.set_runtime_setting(
                        'COMPETITOR_COOKIES',
                        '',
                        source='auto_clear_expired',
                        profile_id=self.profile_id,
                    )
                    logger.info(
                        '[%s] Очистил протухшие runtime cookies после '
                        'успешного парсинга без cookies',
                        self.profile_name,
                    )
                return retry_result
            if (
                cookies
                and (
                    not refreshed_cookies
                    or refreshed_cookies == cookies
                )
            ):
                storage.set_runtime_setting(
                    'COMPETITOR_COOKIES',
                    '',
                    source='auto_clear_expired_failed',
                    profile_id=self.profile_id,
                )
                logger.info(
                    '[%s] Очистил протухшие runtime cookies после '
                    'неуспешного retry без cookies',
                    self.profile_name,
                )
            result = retry_result

        return result

    def _chat_autoreply_enabled(self) -> bool:
        if self.profile_id != 'digiseller':
            return False
        return bool(getattr(config, 'DIGISELLER_CHAT_AUTOREPLY_ENABLED', False))

    def _iter_text_values(self, payload: Any):
        queue = [payload]
        while queue:
            current = queue.pop(0)
            if isinstance(current, str):
                normalized = current.strip()
                if normalized:
                    yield normalized
                continue
            if isinstance(current, dict):
                queue.extend(current.values())
                continue
            if isinstance(current, list):
                queue.extend(current)

    def _extract_numeric_field(self, payload: Any, keys: tuple[str, ...]) -> int:
        if isinstance(payload, dict):
            for key in keys:
                if key not in payload:
                    continue
                try:
                    value = int(float(payload.get(key) or 0))
                except (TypeError, ValueError):
                    value = 0
                if value > 0:
                    return value
            for nested in payload.values():
                value = self._extract_numeric_field(nested, keys)
                if value > 0:
                    return value
        if isinstance(payload, list):
            for item in payload:
                value = self._extract_numeric_field(item, keys)
                if value > 0:
                    return value
        return 0

    def _extract_locale(self, payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ('locale', 'lang', 'language', 'site_lang'):
                if key not in payload:
                    continue
                value = str(payload.get(key) or '').strip().lower()
                if 'en' in value:
                    return 'en'
                if 'ru' in value:
                    return 'ru'
            for nested in payload.values():
                locale = self._extract_locale(nested)
                if locale:
                    return locale
        if isinstance(payload, list):
            for item in payload:
                locale = self._extract_locale(item)
                if locale:
                    return locale
        return ''

    def _detect_friend_mode(self, payload: Any) -> str:
        if isinstance(payload, dict):
            options = payload.get('options')
            if isinstance(options, list):
                for option in options:
                    if not isinstance(option, dict):
                        continue
                    selected = (
                        option.get('value')
                        or option.get('selected')
                        or option.get('answer')
                        or option.get('selection')
                    )
                    selected_text = str(selected or '').strip().lower()
                    if not selected_text:
                        continue
                    if any(k in selected_text for k in _ALREADY_KEYWORDS):
                        return _MODE_ALREADY
                    if any(k in selected_text for k in _ADD_KEYWORDS):
                        return _MODE_ADD

        all_text = ' '.join(self._iter_text_values(payload)).lower()
        has_already = any(k in all_text for k in _ALREADY_KEYWORDS)
        has_add = any(k in all_text for k in _ADD_KEYWORDS)
        if has_already and not has_add:
            return _MODE_ALREADY
        if has_add and not has_already:
            return _MODE_ADD
        return _MODE_ALREADY

    def _sanitize_message(self, raw: Any) -> str:
        text = str(raw or '').strip()
        if not text:
            return ''
        text = re.sub(r'<\s*br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'[ \t\f\v]+', ' ', text)
        text = re.sub(r' *\n *', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _resolve_chat_template(self, locale: str, mode: str) -> str:
        locale_tag = 'EN' if locale == 'en' else 'RU'
        mode_tag = 'ALREADY' if mode == _MODE_ALREADY else 'ADD'
        key = f'DIGISELLER_CHAT_TEMPLATE_{locale_tag}_{mode_tag}'
        return self._sanitize_message(getattr(config, key, ''))

    def _pick_instruction_text(
        self,
        product_info: dict[str, Any],
        mode: str,
    ) -> str:
        if mode == _MODE_ADD:
            keys = (
                'add_info',
                'instruction_add',
                'instruction_extra',
                'instruction',
                'info',
            )
        else:
            keys = (
                'info',
                'instruction',
                'instruction_main',
                'add_info',
            )
        for key in keys:
            if key not in product_info:
                continue
            text = self._sanitize_message(product_info.get(key))
            if text:
                return text
        return ''

    def _autoreply_key(self, order_id: int) -> str:
        return f'CHAT_AUTOREPLY_SENT:{order_id}'

    def _is_autoreply_sent(self, order_id: int) -> bool:
        raw = storage.get_runtime_setting(
            self._autoreply_key(order_id),
            profile_id=self.profile_id,
        )
        return bool((raw or '').strip())

    def _mark_autoreply_sent(self, order_id: int):
        storage.set_runtime_setting(
            self._autoreply_key(order_id),
            datetime.now().isoformat(),
            source='chat_autoreply',
            profile_id=self.profile_id,
        )

    def _chat_autoreply_product_ids(self) -> list[int]:
        ids = []
        for value in getattr(
            config,
            'DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS',
            [],
        ):
            try:
                normalized = int(float(value))
            except (TypeError, ValueError):
                continue
            if normalized > 0 and normalized not in ids:
                ids.append(normalized)
        if self.product_id > 0 and self.product_id not in ids:
            ids.append(self.product_id)
        return ids

    def _chat_meta_get(self, key: str) -> Optional[str]:
        return storage.get_runtime_setting(
            key,
            profile_id=self.profile_id,
        )

    def _chat_meta_set(self, key: str, value: str):
        storage.set_runtime_setting(
            key,
            value,
            source='chat_autoreply',
            profile_id=self.profile_id,
        )

    def _chat_meta_inc(self, key: str, delta: int = 1):
        raw = self._chat_meta_get(key)
        current = 0
        if raw is not None:
            try:
                current = int(float(raw))
            except (TypeError, ValueError):
                current = 0
        self._chat_meta_set(key, str(max(0, current + int(delta))))

    def _normalize_compare_text(self, raw: Any) -> str:
        text = self._sanitize_message(raw).lower()
        return re.sub(r'\s+', ' ', text).strip()

    def _is_message_already_sent(self, order_id: int, message: str) -> bool:
        if not bool(
            getattr(
                config,
                'DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES',
                True,
            )
        ):
            return False
        if not hasattr(self.api_client, 'list_messages'):
            return False
        lookback = max(
            1,
            min(
                200,
                int(
                    getattr(
                        config,
                        'DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES',
                        30,
                    )
                ),
            ),
        )
        try:
            messages = self.api_client.list_messages(
                order_id,
                count=lookback,
                timeout=10,
            )
        except Exception:
            return False
        if not isinstance(messages, list) or not messages:
            return False
        expected = self._normalize_compare_text(message)
        if not expected:
            return False
        for item in messages:
            if not isinstance(item, dict):
                continue
            candidate = (
                item.get('message')
                or item.get('text')
                or item.get('body')
                or item.get('content')
            )
            if self._normalize_compare_text(candidate) == expected:
                return True
        return False

    async def _run_digiseller_chat_autoreply(self):
        if not self._chat_autoreply_enabled():
            return
        if not (
            hasattr(self.api_client, 'list_chats')
            and hasattr(self.api_client, 'send_chat_message')
            and hasattr(self.api_client, 'get_order_info')
            and hasattr(self.api_client, 'get_product_info')
        ):
            return

        started_at = datetime.now()
        self._chat_meta_set(
            'CHAT_AUTOREPLY_LAST_RUN_AT',
            started_at.isoformat(),
        )
        try:
            target_products = self._chat_autoreply_product_ids()
            page_size = max(
                1,
                min(
                    100,
                    int(
                        getattr(
                            config,
                            'DIGISELLER_CHAT_AUTOREPLY_PAGE_SIZE',
                            50,
                        )
                    ),
                ),
            )
            max_pages = max(
                1,
                min(
                    10,
                    int(
                        getattr(
                            config,
                            'DIGISELLER_CHAT_AUTOREPLY_MAX_PAGES',
                            2,
                        )
                    ),
                ),
            )
            sent_count = 0
            processed_orders: set[int] = set()
            product_info_cache: Dict[tuple[int, str], dict[str, Any]] = {}
            for page in range(1, max_pages + 1):
                chats = self.api_client.list_chats(
                    filter_new=1,
                    page_size=page_size,
                    page=page,
                    timeout=10,
                )
                if not chats:
                    break

                for chat in chats:
                    if not isinstance(chat, dict):
                        continue
                    order_id = self._extract_numeric_field(
                        chat,
                        (
                            'id_i',
                            'invoice_id',
                            'order_id',
                            'purchase_id',
                        ),
                    )
                    if order_id <= 0:
                        continue
                    if order_id in processed_orders:
                        continue
                    processed_orders.add(order_id)
                    if self._is_autoreply_sent(order_id):
                        continue

                    chat_product = self._extract_numeric_field(
                        chat,
                        (
                            'id_d',
                            'id_goods',
                            'product_id',
                            'content_id',
                        ),
                    )
                    order_info = self.api_client.get_order_info(
                        order_id,
                        locale='ru',
                        timeout=10,
                    ) or {}
                    order_product = self._extract_numeric_field(
                        order_info,
                        (
                            'id_d',
                            'id_goods',
                            'product_id',
                            'content_id',
                        ),
                    )
                    product_id = order_product or chat_product or self.product_id
                    if target_products and product_id not in target_products:
                        continue

                    locale = (
                        self._extract_locale(order_info)
                        or self._extract_locale(chat)
                        or 'ru'
                    )
                    mode = self._detect_friend_mode(
                        {
                            'order': order_info,
                            'chat': chat,
                        }
                    ) or _MODE_ALREADY

                    template = self._resolve_chat_template(
                        locale=locale,
                        mode=mode,
                    )
                    if template:
                        message = template
                    else:
                        info_lang = 'en-US' if locale == 'en' else 'ru-RU'
                        cache_key = (int(product_id), info_lang)
                        product_info = product_info_cache.get(cache_key)
                        if product_info is None:
                            product_info = self.api_client.get_product_info(
                                product_id,
                                timeout=10,
                                lang=info_lang,
                            ) or {}
                            product_info_cache[cache_key] = product_info
                        message = self._pick_instruction_text(
                            product_info,
                            mode=mode,
                        )

                    if not message:
                        logger.warning(
                            '[%s] Нет текста инструкции для order_id=%s '
                            '(product_id=%s, locale=%s, mode=%s)',
                            self.profile_name,
                            order_id,
                            product_id,
                            locale,
                            mode,
                        )
                        continue

                    if self._is_message_already_sent(order_id, message):
                        self._mark_autoreply_sent(order_id)
                        self._chat_meta_inc(
                            'CHAT_AUTOREPLY_DUPLICATE_COUNT',
                            delta=1,
                        )
                        logger.info(
                            '[%s] Пропуск отправки: инструкция уже есть в '
                            'чате order_id=%s',
                            self.profile_name,
                            order_id,
                        )
                        continue

                    sent = self.api_client.send_chat_message(
                        order_id,
                        message,
                        timeout=10,
                    )
                    if not sent:
                        logger.warning(
                            '[%s] Не удалось отправить инструкцию в чат '
                            'order_id=%s',
                            self.profile_name,
                            order_id,
                        )
                        continue

                    self._mark_autoreply_sent(order_id)
                    sent_count += 1
                    logger.info(
                        '[%s] Инструкция отправлена: order_id=%s '
                        '(product_id=%s, locale=%s, mode=%s)',
                        self.profile_name,
                        order_id,
                        product_id,
                        locale,
                        mode,
                    )

            if sent_count > 0:
                self._chat_meta_set(
                    'CHAT_AUTOREPLY_LAST_SENT_AT',
                    datetime.now().isoformat(),
                )
                self._chat_meta_inc(
                    'CHAT_AUTOREPLY_SENT_COUNT',
                    delta=sent_count,
                )
                await self.telegram_bot.notify(
                    (
                        f'💬 *Инструкции отправлены*\n\n'
                        f'Профиль: `{self.profile_name}`\n'
                        f'Отправлено: `{sent_count}`'
                    )
                )
            self._chat_meta_set('CHAT_AUTOREPLY_LAST_ERROR', '')
        except Exception as e:
            self._chat_meta_set('CHAT_AUTOREPLY_LAST_ERROR', str(e))
            logger.error(
                '[%s] Ошибка авто-отправки инструкций: %s',
                self.profile_name,
                e,
                exc_info=True,
            )

    async def run_cycle(self):
        logger.info('[%s] 🔄 Запуск цикла pricing...', self.profile_name)
        try:
            storage.update_state(
                profile_id=self.profile_id,
                last_cycle=datetime.now(),
            )
            # На каждом цикле подтягиваем свежие cookies из .env,
            # чтобы не требовать перезапуска процесса после обновления.
            synced_from_env = await self._sync_cookies_from_env()
            if not synced_from_env:
                await self._reload_cookies_from_backup()
            runtime = self._runtime()
            state = self._state()

            await self._run_digiseller_chat_autoreply()

            is_valid, errors = validate_runtime_config(runtime)
            if not is_valid:
                message = 'Некорректные runtime-настройки: ' + '; '.join(errors[:5])
                logger.error('[%s] %s', self.profile_name, message)
                await self._notify_error_throttled(
                    key='invalid_runtime_config',
                    message=message,
                    cooldown_seconds=180,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return

            logger.info(
                '[%s] Парсинг %s конкурентов...',
                self.profile_name,
                len(runtime.COMPETITOR_URLS),
            )
            if not runtime.COMPETITOR_URLS:
                logger.info(
                    '[%s] Конкуренты не заданы, цикл мониторинга пропущен',
                    self.profile_name,
                )
                storage.update_state(
                    profile_id=self.profile_id,
                    last_competitor_error='no_competitor_urls',
                    last_competitor_block_reason=None,
                    last_competitor_status_code=None,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return
            if self.product_id <= 0:
                message = (
                    'Некорректный product_id для профиля '
                    f'{self.profile_name}: {self.product_id}'
                )
                logger.error('[%s] %s', self.profile_name, message)
                await self._notify_error_throttled(
                    key='invalid_product_id',
                    message=message,
                    cooldown_seconds=300,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return
            competitor_results = await asyncio.gather(*[
                self._parse_competitor_price(url, runtime=runtime, timeout=15)
                for url in runtime.COMPETITOR_URLS
            ])

            for idx, parsed in enumerate(competitor_results):
                if parsed.success:
                    continue
                source_url = (
                    runtime.COMPETITOR_URLS[idx]
                    if idx < len(runtime.COMPETITOR_URLS) else parsed.url
                )
                await self._notify_parser_issue_if_needed(
                    runtime=runtime,
                    url=source_url,
                    result=parsed,
                )

            valid_competitors = [
                (runtime.COMPETITOR_URLS[i], r)
                for i, r in enumerate(competitor_results)
                if r.success and r.price is not None
            ]

            state = self._state()
            auto_mode = state.get('auto_mode', True)
            if not auto_mode:
                if valid_competitors:
                    _, best = min(valid_competitors, key=lambda item: item[1].price)
                    storage.update_state(
                        profile_id=self.profile_id,
                        last_competitor_price=best.price,
                        last_competitor_min=best.price,
                        last_competitor_rank=best.rank,
                        last_competitor_url=best.url,
                        last_competitor_parse_at=datetime.now(),
                        last_competitor_method=best.method,
                        last_competitor_error=None,
                        last_competitor_block_reason=None,
                        last_competitor_status_code=best.status_code,
                    )
                storage.increment_skip_count(profile_id=self.profile_id)
                return

            if not valid_competitors:
                first_error = next(
                    (r for r in competitor_results if not r.success),
                    None,
                )
                storage.update_state(
                    profile_id=self.profile_id,
                    last_competitor_error=first_error.error if first_error else None,
                    last_competitor_block_reason=(
                        first_error.block_reason if first_error else None
                    ),
                    last_competitor_status_code=(
                        first_error.status_code if first_error else None
                    ),
                )
                await self._notify_error_throttled(
                    key='no_competitor_prices',
                    message='Не удалось получить цены конкурентов',
                    cooldown_seconds=3600,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return

            considered = valid_competitors
            force_weak_mode = False
            if runtime.POSITION_FILTER_ENABLED:
                strong = [
                    item for item in valid_competitors
                    if item[1].rank is None
                    or item[1].rank <= runtime.WEAK_POSITION_THRESHOLD
                ]
                if strong:
                    considered = strong
                else:
                    considered = valid_competitors
                    force_weak_mode = True

            selected_url, selected = min(considered, key=lambda item: item[1].price)
            min_price = selected.price
            selected_rank = selected.rank
            competitor_prices = [item[1].price for item in considered]

            previous_min = state.get('last_competitor_min')
            competitor_changed = (
                previous_min is None
                or abs(min_price - previous_min) >= getattr(
                    runtime,
                    'COMPETITOR_CHANGE_DELTA',
                    0.0001,
                )
            )
            competitor_rebound = (
                previous_min is not None
                and (min_price - previous_min) >= getattr(
                    runtime,
                    'FAST_REBOUND_DELTA',
                    0.01,
                )
            )

            await self._notify_competitor_change_if_needed(
                runtime=runtime,
                old_price=previous_min,
                new_price=min_price,
                rank=selected_rank,
                url=selected_url,
            )
            storage.update_state(
                profile_id=self.profile_id,
                last_competitor_price=min_price,
                last_competitor_min=min_price,
                last_competitor_rank=selected_rank,
                last_competitor_url=selected_url,
                last_competitor_parse_at=datetime.now(),
                last_competitor_method=selected.method,
                last_competitor_error=None,
                last_competitor_block_reason=None,
                last_competitor_status_code=selected.status_code,
            )

            try:
                current_price = self.api_client.get_my_price(self.product_id)
            except Exception as e:
                logger.error(
                    '[%s] Ошибка получения текущей цены по API: %s',
                    self.profile_name,
                    e,
                )
                current_price = None
            if current_price is None:
                current_price = state.get('last_price')
            if current_price is not None:
                try:
                    current_price = float(current_price)
                except Exception as e:
                    logger.error(
                        '[%s] Некорректное значение текущей цены: %r (%s)',
                        self.profile_name,
                        current_price,
                        e,
                    )
                    current_price = None
            if current_price is None:
                await self._notify_error_throttled(
                    key='no_current_price',
                    message='Не удалось получить текущую цену',
                    cooldown_seconds=180,
                )
                storage.increment_skip_count(profile_id=self.profile_id)
                return
            # Синхронизируем last_price с фактической ценой из API,
            # чтобы status/дрейф-логика не опирались на устаревшее значение.
            state_last_price_raw = state.get('last_price')
            state_last_price = None
            if state_last_price_raw is not None:
                try:
                    state_last_price = float(state_last_price_raw)
                except Exception:
                    state_last_price = None
            ignore_delta = getattr(runtime, 'IGNORE_DELTA', 0.001)
            if (
                state_last_price is None
                or abs(current_price - state_last_price) >= ignore_delta
            ):
                storage.update_state(
                    profile_id=self.profile_id,
                    last_price=current_price,
                )
                state['last_price'] = current_price

            decision = calculate_price(
                competitor_prices=competitor_prices,
                current_price=current_price,
                last_update=state.get('last_update'),
                config=runtime,
                target_competitor_rank=selected_rank,
                force_weak_mode=force_weak_mode,
                allow_fast_rebound=(
                    competitor_rebound
                    and getattr(
                        runtime,
                        'FAST_REBOUND_BYPASS_COOLDOWN',
                        True,
                    )
                ),
            )

            if (
                getattr(runtime, 'UPDATE_ONLY_ON_COMPETITOR_CHANGE', True)
                and not competitor_changed
            ):
                ignore_delta = getattr(runtime, 'IGNORE_DELTA', 0.001)
                change_delta = getattr(runtime, 'COMPETITOR_CHANGE_DELTA', 0.0001)
                if decision.action != 'update' or decision.price is None:
                    logger.info(
                        '[%s] Цена конкурента не изменилась (%.4f), '
                        'обновление не требуется',
                        self.profile_name,
                        min_price,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

                last_target_price = state.get('last_target_price')
                last_target_comp = state.get('last_target_competitor_min')
                if (
                    last_target_price is not None
                    and last_target_comp is not None
                    and abs(decision.price - last_target_price) < ignore_delta
                    and abs(min_price - last_target_comp) < change_delta
                ):
                    logger.info(
                        '[%s] Цена конкурента не изменилась (%.4f), '
                        'целевая цена %.4f уже применена',
                        self.profile_name,
                        min_price,
                        decision.price,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

                last_requested = state.get('last_price')
                if (
                    last_requested is not None
                    and abs(decision.price - last_requested) < ignore_delta
                ):
                    logger.info(
                        '[%s] Цена конкурента не изменилась (%.4f), '
                        'целевая цена %.4f уже была выставлена ранее',
                        self.profile_name,
                        min_price,
                        decision.price,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

                drift = abs(decision.price - current_price)
                if drift < ignore_delta:
                    logger.info(
                        '[%s] Цена конкурента не изменилась (%.4f), '
                        'текущая цена уже целевая (drift=%.4f)',
                        self.profile_name,
                        min_price,
                        drift,
                    )
                    storage.increment_skip_count(profile_id=self.profile_id)
                    return

                decision.reason = f'reconcile_{decision.reason}'
                logger.info(
                    '[%s] Цена конкурента не изменилась, '
                    'но есть дрейф %.4f -> синхронизирую цену',
                    self.profile_name,
                    drift,
                )

            logger.info(
                '[%s] Итоговое решение: %s (%s)',
                self.profile_name,
                decision.action,
                decision.reason,
            )

            if decision.action == 'update' and decision.price is not None:
                ignore_delta = getattr(runtime, 'IGNORE_DELTA', 0.001)
                last_target_raw = state.get('last_target_price')
                last_update_at = state.get('last_update')
                if (
                    last_target_raw is not None
                    and isinstance(last_update_at, datetime)
                ):
                    try:
                        last_target_price = float(last_target_raw)
                    except Exception:
                        last_target_price = None
                    if last_target_price is not None and (
                        abs(decision.price - last_target_price) < ignore_delta
                    ):
                        recent_window_seconds = max(
                            int(getattr(runtime, 'CHECK_INTERVAL', 60)) * 2,
                            60,
                        )
                        age_seconds = (
                            datetime.now() - last_update_at
                        ).total_seconds()
                        if age_seconds < recent_window_seconds:
                            logger.info(
                                '[%s] Пропуск повторного update: '
                                'целевая %.4f уже выставлялась %.1fs назад',
                                self.profile_name,
                                decision.price,
                                age_seconds,
                            )
                            storage.increment_skip_count(
                                profile_id=self.profile_id,
                            )
                            return
                success = await self._update_price(decision.price, decision)
                if success:
                    applied_price = decision.price
                    try:
                        api_price = self.api_client.get_my_price(self.product_id)
                        if api_price is not None:
                            applied_price = round(float(api_price), 4)
                    except Exception as e:
                        logger.warning(
                            '[%s] Не удалось перечитать цену после update: %s',
                            self.profile_name,
                            e,
                        )

                    storage.increment_update_count(profile_id=self.profile_id)
                    storage.update_state(
                        profile_id=self.profile_id,
                        last_price=applied_price,
                        last_update=datetime.now(),
                        last_target_price=decision.price,
                        last_target_competitor_min=decision.competitor_price,
                    )
                    storage.add_price_history(
                        old_price=decision.old_price,
                        new_price=applied_price,
                        competitor_price=decision.competitor_price,
                        reason=decision.reason,
                        profile_id=self.profile_id,
                    )
                    await self.telegram_bot.notify_price_updated(
                        old_price=decision.old_price,
                        new_price=applied_price,
                        competitor_price=decision.competitor_price,
                        reason=decision.reason,
                        profile_name=self.profile_name,
                    )
                else:
                    storage.increment_skip_count(profile_id=self.profile_id)
                    await self._notify_error_throttled(
                        key='update_price_failed',
                        message='Ошибка обновления цены через API',
                        cooldown_seconds=180,
                    )
                return

            storage.increment_skip_count(profile_id=self.profile_id)
            await self._notify_skip_throttled(
                runtime=runtime,
                current_price=decision.old_price or current_price,
                target_price=decision.price or current_price,
                competitor_price=decision.competitor_price or min_price,
                reason=decision.reason,
            )
        except Exception as e:
            logger.error(
                '[%s] Ошибка в цикле: %s',
                self.profile_name,
                e,
                exc_info=True,
            )
            storage.update_state(
                profile_id=self.profile_id,
                last_cycle=datetime.now(),
            )
            await self._notify_error_throttled(
                key='scheduler_cycle_exception',
                message=f'Ошибка в цикле: {e}',
                cooldown_seconds=120,
            )

    async def _update_price(self, new_price: float, decision) -> bool:
        logger.info(
            '[%s] Обновление цены: %s -> %s',
            self.profile_name,
            decision.old_price,
            new_price,
        )
        return self.api_client.update_price(
            product_id=self.product_id,
            new_price=new_price,
        )

    async def run(self):
        self._running = True
        runtime = self._runtime()
        logger.info(
            '[%s] Планировщик запущен (интервал: %ss)',
            self.profile_name,
            runtime.CHECK_INTERVAL,
        )
        while self._running:
            try:
                await self.run_cycle()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(
                    '[%s] Критическая ошибка планировщика: %s',
                    self.profile_name,
                    e,
                    exc_info=True,
                )
            runtime = self._runtime()
            await asyncio.sleep(runtime.CHECK_INTERVAL)
        self._running = False
        logger.info('[%s] Планировщик остановлен', self.profile_name)

    def stop(self):
        self._running = False


scheduler: Optional[Scheduler] = None
