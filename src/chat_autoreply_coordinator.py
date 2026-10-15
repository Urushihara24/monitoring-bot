"""Marketplace chat auto-reply orchestration for scheduler runtimes.

The coordinator owns the long-running chat scan/send flow while deliberately
reusing the already-tested parsing, policy, rule-resolution and persistence
helpers on the scheduler host. This keeps the extraction behaviour-preserving
and separates orchestration before lower-level chat helpers are decomposed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from . import chat_autoreply as chat_keys

logger = logging.getLogger(__name__)

_CHAT_POLICY_ON_ORDER = 'ON_ORDER'
_MODE_ALREADY = 'already'


class ChatAutoreplyCoordinator:
    """Coordinate marketplace chat discovery, filtering and safe sends."""

    def __init__(self, host: Any) -> None:
        self._host = host

    def __getattr__(self, name: str) -> Any:
        # During the staged decomposition, rule parsing, chat metadata helpers
        # and API access still live on the scheduler compatibility host.
        return getattr(self._host, name)

    async def run(self) -> None:
        if not self._chat_autoreply_enabled():
            return
        if not self._chat_autoreply_supported():
            return
        if not self._should_run_chat_autoreply_now():
            return

        started_at = datetime.now()
        self._chat_meta_set(
            chat_keys.KEY_LAST_RUN_AT,
            started_at.isoformat(),
        )
        try:
            require_rules = self._chat_autoreply_require_rules()
            allow_custom_text = self._chat_autoreply_allow_custom_text()
            allow_template_fallback = (
                self._chat_autoreply_allow_template_fallback()
            )
            if hasattr(self.api_client, 'get_chat_perms_status'):
                perms_ok, perms_desc = self._chat_perms_status_cached()
                if not perms_ok:
                    perms_lower = (perms_desc or '').lower()
                    is_transient = 'no_response' in perms_lower
                    is_rate_limited = 'http_429' in perms_lower
                    if is_rate_limited:
                        message = (
                            'Rate limit chat API для авто-инструкций: '
                            f'{perms_desc}'
                        )
                        alert_key = 'chat_autoreply_api_rate_limited'
                        cooldown_seconds = 900
                    elif is_transient:
                        message = (
                            'Временная недоступность chat API для '
                            f'авто-инструкций: {perms_desc}'
                        )
                        alert_key = 'chat_autoreply_api_unavailable'
                        cooldown_seconds = 300
                    else:
                        message = (
                            'Недостаточно прав chat API для авто-инструкций: '
                            f'{perms_desc}'
                        )
                        alert_key = 'chat_autoreply_perms'
                        cooldown_seconds = 900
                    self._chat_meta_set(
                        chat_keys.KEY_LAST_ERROR,
                        message,
                    )
                    self._log_warning_throttled(
                        key=alert_key,
                        message=message,
                        cooldown_seconds=cooldown_seconds,
                    )
                    await self._notify_error_throttled(
                        key=alert_key,
                        message=message,
                        cooldown_seconds=cooldown_seconds,
                    )
                    return

            self._cleanup_autoreply_marks_if_due()
            target_products = self._chat_autoreply_product_ids()
            page_size = max(
                1,
                min(
                    100,
                    int(
                        self._chat_cfg(
                            'PAGE_SIZE',
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
                        self._chat_cfg(
                            'MAX_PAGES',
                            2,
                        )
                    ),
                ),
            )
            sent_count = 0
            skipped_non_empty_chat_count = 0
            processed_orders: set[int] = set()
            product_info_cache: Dict[tuple[int, str], dict[str, Any]] = {}
            product_rules_cache: Dict[int, dict[str, dict[str, Any]]] = {}
            chats_product_filter = target_products or None
            recent_minutes = max(
                1,
                min(
                    240,
                    int(
                        self._chat_cfg(
                            'RECENT_LOOKBACK_MINUTES',
                            20,
                        )
                    ),
                ),
            )
            recent_cutoff = datetime.now() - timedelta(minutes=recent_minutes)
            query_plan = [(1, max_pages, 'new')]
            if bool(self._chat_cfg('ENABLE_RECENT_FALLBACK', True)):
                query_plan.append((None, 1, 'recent'))
            for filter_new, plan_max_pages, plan_name in query_plan:
                for page in range(1, plan_max_pages + 1):
                    chats = self.api_client.list_chats(
                        filter_new=filter_new,
                        product_ids=chats_product_filter,
                        page_size=page_size,
                        page=page,
                        timeout=10,
                    )
                    if not chats:
                        break

                    for chat in chats:
                        if not isinstance(chat, dict):
                            continue
                        if plan_name == 'recent':
                            activity_at = self._extract_chat_activity_at(chat)
                            if (
                                activity_at is not None
                                and activity_at < recent_cutoff
                            ):
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

                        lookback_messages = max(
                            1,
                            min(
                                200,
                                int(
                                    self._chat_cfg(
                                        'LOOKBACK_MESSAGES',
                                        30,
                                    )
                                ),
                            ),
                        )
                        cached_messages: Optional[list[dict[str, Any]]] = None

                        chat_product = self._extract_product_id(
                            chat,
                            exclude_ids={order_id},
                        )
                        locale_hint = self._extract_locale(chat) or 'ru'
                        order_info: dict[str, Any] = {}
                        for order_locale in self._order_locales_to_try(locale_hint):
                            order_info = self.api_client.get_order_info(
                                order_id,
                                locale=order_locale,
                                timeout=10,
                            ) or {}
                            if order_info:
                                break
                        order_product = self._extract_product_id(
                            order_info,
                            exclude_ids={order_id},
                        )
                        candidate_product_ids = []
                        for candidate in (chat_product, order_product):
                            if candidate > 0 and candidate not in candidate_product_ids:
                                candidate_product_ids.append(candidate)
                        known_product_id = order_product or chat_product
                        if target_products:
                            matched_product_id = next(
                                (
                                    candidate for candidate in candidate_product_ids
                                    if candidate in target_products
                                ),
                                0,
                            )
                            if matched_product_id > 0:
                                known_product_id = matched_product_id
                            elif not candidate_product_ids:
                                logger.info(
                                    '[%s] Пропуск order_id=%s: не удалось определить '
                                    'product_id для фильтра target товаров',
                                    self.profile_name,
                                    order_id,
                                )
                                continue
                            else:
                                logger.info(
                                    '[%s] Пропуск order_id=%s: product_id не в '
                                    'target (candidates=%s, targets=%s)',
                                    self.profile_name,
                                    order_id,
                                    candidate_product_ids,
                                    target_products,
                                )
                                continue

                        product_id = known_product_id or self.product_id
                        chat_policy = self._chat_autoreply_policy(product_id)

                        need_messages_for_policy = (
                            chat_policy != _CHAT_POLICY_ON_ORDER
                        )
                        need_messages_for_empty_guard = (
                            self._chat_autoreply_only_empty_chat()
                        )
                        if (
                            need_messages_for_policy
                            or need_messages_for_empty_guard
                        ):
                            cached_messages = self._list_recent_messages(
                                order_id,
                                lookback=lookback_messages,
                            )
                            if cached_messages is None:
                                logger.warning(
                                    '[%s] Пропуск order_id=%s: не удалось '
                                    'получить сообщения чата '
                                    '(policy=%s, only_empty=%s)',
                                    self.profile_name,
                                    order_id,
                                    chat_policy,
                                    need_messages_for_empty_guard,
                                )
                                continue

                        if (
                            need_messages_for_empty_guard
                            and cached_messages
                        ):
                            if self._chat_autoreply_smart_non_empty():
                                (
                                    allow_non_empty,
                                    allow_reason,
                                ) = self._allow_non_empty_chat_autoreply(
                                    cached_messages
                                )
                                if not allow_non_empty:
                                    skipped_non_empty_chat_count += 1
                                    continue
                                logger.info(
                                    '[%s] order_id=%s: непустой чат '
                                    'допущен smart-mode (%s)',
                                    self.profile_name,
                                    order_id,
                                    allow_reason,
                                )
                            else:
                                skipped_non_empty_chat_count += 1
                                continue

                        if need_messages_for_policy:
                            policy_ok, policy_reason = self._chat_policy_allows_send(
                                policy=chat_policy,
                                messages=cached_messages or [],
                            )
                            if not policy_ok:
                                logger.info(
                                    '[%s] Пропуск order_id=%s: policy=%s '
                                    '(%s, product_id=%s)',
                                    self.profile_name,
                                    order_id,
                                    chat_policy,
                                    policy_reason,
                                    product_id,
                                )
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

                        message = ''
                        message_source = ''
                        rules = product_rules_cache.get(product_id)
                        if rules is None:
                            rules = self._chat_rules_get(product_id)
                            product_rules_cache[product_id] = rules

                        selected_options_payload = {
                            'order': order_info,
                            'chat': chat,
                        }
                        if rules:
                            require_id_match = self._rules_require_id_match(rules)
                            matched_rule = None
                            matched_context: Optional[dict[str, Any]] = None
                            for context in self._iter_selected_option_contexts(
                                selected_options_payload
                            ):
                                context_keys = list(context.get('keys') or [])
                                if require_id_match:
                                    context_keys = [
                                        key for key in context_keys
                                        if chat_keys.is_option_variant_rule_key(key)
                                    ]
                                for key in context_keys:
                                    rule = rules.get(key)
                                    if rule is None:
                                        continue
                                    matched_rule = rule
                                    matched_context = dict(context)
                                    matched_context['matched_key'] = key
                                    break
                                if matched_rule is not None:
                                    break

                            if matched_rule is None or matched_context is None:
                                logger.info(
                                    '[%s] Пропуск order_id=%s: нет совпадения по '
                                    'настроенным правилам параметров '
                                    '(product_id=%s)',
                                    self.profile_name,
                                    order_id,
                                    product_id,
                                )
                                continue

                            if not bool(matched_rule.get('enabled', True)):
                                logger.info(
                                    '[%s] Пропуск order_id=%s: правило отключено '
                                    '(product_id=%s, option=%s, value=%s)',
                                    self.profile_name,
                                    order_id,
                                    product_id,
                                    matched_context.get('option_name'),
                                    matched_context.get('selected_value'),
                                )
                                continue

                            custom_message = ''
                            if allow_custom_text:
                                custom_message = self._sanitize_message(
                                    matched_rule.get('text') or ''
                                )
                            if custom_message:
                                message = custom_message
                                message_source = 'rule_custom'
                            else:
                                message = self._pick_instruction_for_option(
                                    matched_context['option'],
                                    mode=mode,
                                    locale=locale,
                                )
                                if message:
                                    message_source = 'rule_option'
                                else:
                                    for info_lang in self._product_info_locales_to_try(
                                        locale
                                    ):
                                        cache_key = (int(product_id), info_lang)
                                        product_info = product_info_cache.get(
                                            cache_key
                                        )
                                        if product_info is None:
                                            product_info = self.api_client.get_product_info(
                                                product_id,
                                                timeout=10,
                                                lang=info_lang,
                                            ) or {}
                                            product_info_cache[
                                                cache_key
                                            ] = product_info
                                        info_locale = (
                                            'en'
                                            if info_lang.lower().startswith('en')
                                            else 'ru'
                                        )
                                        message = self._pick_instruction_for_rule_key(
                                            product_info,
                                            rule_key=matched_context.get(
                                                'matched_key'
                                            )
                                            or matched_context['key'],
                                            mode=mode,
                                            locale=info_locale,
                                        )
                                        if message:
                                            message_source = (
                                                f'rule_product_option[{info_lang}]'
                                            )
                                            break
                                    if not message:
                                        logger.info(
                                            '[%s] Пропуск order_id=%s: по выбранному '
                                            'параметру нет текста инструкции '
                                            '(product_id=%s, option=%s, value=%s)',
                                            self.profile_name,
                                            order_id,
                                            product_id,
                                            matched_context.get('option_name'),
                                            matched_context.get('selected_value'),
                                        )
                                        continue
                        else:
                            if require_rules:
                                # Safety-first: without explicit per-product rules,
                                # send only the explicit configured template.
                                if allow_template_fallback:
                                    template = self._resolve_chat_template(
                                        locale=locale,
                                        mode=mode,
                                    )
                                    message = self._sanitize_message(template)
                                    message_source = 'template'
                                if not message:
                                    logger.info(
                                        '[%s] Пропуск order_id=%s: включен '
                                        'REQUIRE_RULES и нет правил/шаблона '
                                        '(product_id=%s)',
                                        self.profile_name,
                                        order_id,
                                        product_id,
                                    )
                                    continue
                            else:
                                if allow_template_fallback:
                                    template = self._resolve_chat_template(
                                        locale=locale,
                                        mode=mode,
                                    )
                                    message = self._sanitize_message(template)
                                    message_source = 'template'
                                if not message:
                                    message = self._pick_selected_option_instruction(
                                        selected_options_payload,
                                        mode=mode,
                                        locale=locale,
                                    )
                                    if message:
                                        message_source = 'order_selected_option'
                                if not message:
                                    message = self._pick_instruction_text(
                                        order_info,
                                        mode=mode,
                                        locale=locale,
                                    )
                                    if message:
                                        message_source = 'order_info'
                                if not message:
                                    for info_lang in (
                                        self._product_info_locales_to_try(locale)
                                    ):
                                        cache_key = (int(product_id), info_lang)
                                        product_info = product_info_cache.get(
                                            cache_key
                                        )
                                        if product_info is None:
                                            product_info = self.api_client.get_product_info(
                                                product_id,
                                                timeout=10,
                                                lang=info_lang,
                                            ) or {}
                                            product_info_cache[cache_key] = (
                                                product_info
                                            )
                                        info_locale = (
                                            'en'
                                            if info_lang.lower().startswith('en')
                                            else 'ru'
                                        )
                                        message = self._pick_selected_option_instruction(
                                            product_info,
                                            mode=mode,
                                            locale=info_locale,
                                        )
                                        if message:
                                            message_source = (
                                                f'product_selected_option[{info_lang}]'
                                            )
                                            break
                                        message = self._pick_instruction_text(
                                            product_info,
                                            mode=mode,
                                            locale=info_locale,
                                        )
                                        if message:
                                            message_source = (
                                                f'product_info[{info_lang}]'
                                            )
                                            break

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

                        if self._is_forbidden_outbound_chat_message(message):
                            logger.error(
                                '[%s] Блокирована отправка потенциально '
                                'служебного текста в order_id=%s '
                                '(product_id=%s, source=%s)',
                                self.profile_name,
                                order_id,
                                product_id,
                                message_source or 'unknown',
                            )
                            continue

                        if self._is_message_already_sent(
                            order_id,
                            message,
                            preloaded_messages=cached_messages,
                        ):
                            self._mark_autoreply_sent(order_id)
                            self._chat_meta_inc(
                                chat_keys.KEY_DUPLICATE_COUNT,
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
                            '(product_id=%s, locale=%s, mode=%s, '
                            'policy=%s, source=%s)',
                            self.profile_name,
                            order_id,
                            product_id,
                            locale,
                            mode,
                            chat_policy,
                            message_source,
                        )

            if skipped_non_empty_chat_count > 0:
                logger.info(
                    '[%s] Авто-инструкции: пропущено, чат не пуст: %s',
                    self.profile_name,
                    skipped_non_empty_chat_count,
                )

            if sent_count > 0:
                self._chat_meta_set(
                    chat_keys.KEY_LAST_SENT_AT,
                    datetime.now().isoformat(),
                )
                self._chat_meta_inc(
                    chat_keys.KEY_SENT_COUNT,
                    delta=sent_count,
                )
                await self.telegram_bot.notify(
                    (
                        f'💬 *Инструкции отправлены*\n\n'
                        f'Профиль: `{self.profile_name}`\n'
                        f'Отправлено: `{sent_count}`'
                    )
                )
            self._chat_meta_set(chat_keys.KEY_LAST_ERROR, '')
        except Exception as e:
            self._chat_meta_set(chat_keys.KEY_LAST_ERROR, str(e))
            logger.error(
                '[%s] Ошибка авто-отправки инструкций: %s',
                self.profile_name,
                e,
                exc_info=True,
            )
