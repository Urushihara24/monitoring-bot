"""Telegram keyboard/view builders without runtime or storage access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


@dataclass(frozen=True)
class RuleButtonView:
    index: int
    label: str
    enabled: bool


@dataclass(frozen=True)
class ProductButtonView:
    product_id: int
    label: str
    active: bool


def build_main_keyboard(
    *,
    status: str,
    products: str,
    previous_product: str,
    next_product: str,
    profile: str,
    settings: str,
) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [status, products],
            [previous_product, next_product],
            [profile, settings],
        ],
        resize_keyboard=True,
    )


def build_settings_keyboard(
    *,
    auto_on: str,
    auto_off: str,
    auto_enabled: bool,
    price: str,
    mode: str,
    price_guard: str,
    product_remove: str,
    back: str,
    chat_supported: bool,
    chat_on: str,
    chat_off: str,
    chat_enabled: bool,
    empty_only_on: str,
    empty_only_off: str,
    empty_only_enabled: bool,
    smart_non_empty_on: str,
    smart_non_empty_off: str,
    smart_non_empty_enabled: bool,
    chat_policy: str,
    chat_rules: str,
) -> ReplyKeyboardMarkup:
    auto_toggle = auto_off if auto_enabled else auto_on
    rows: list[list[str]] = [
        [auto_toggle],
        [price, mode],
        [price_guard],
        [product_remove],
    ]
    if chat_supported:
        chat_toggle = chat_off if chat_enabled else chat_on
        empty_toggle = empty_only_off if empty_only_enabled else empty_only_on
        smart_toggle = (
            smart_non_empty_off
            if smart_non_empty_enabled
            else smart_non_empty_on
        )
        rows.append([chat_toggle, empty_toggle])
        rows.append([smart_toggle])
        rows.append([chat_policy, chat_rules])
    rows.append([back])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_profile_keyboard(
    profile_buttons: Sequence[str],
    *,
    back: str,
) -> ReplyKeyboardMarkup:
    rows = [[button] for button in profile_buttons]
    rows.append([back])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_price_guard_keyboard(
    *,
    min_label: str,
    max_label: str,
    undercut_label: str,
    raise_label: str,
    rounding_label: str,
    rebound_enabled: bool,
) -> InlineKeyboardMarkup:
    rebound_label = (
        '🔁 Отскок: ВКЛ' if rebound_enabled else '🔁 Отскок: ВЫКЛ'
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(min_label, callback_data='pc:min'),
                InlineKeyboardButton(max_label, callback_data='pc:max'),
            ],
            [
                InlineKeyboardButton(undercut_label, callback_data='pc:under'),
                InlineKeyboardButton(raise_label, callback_data='pc:raise'),
            ],
            [
                InlineKeyboardButton(rounding_label, callback_data='pc:round'),
            ],
            [
                InlineKeyboardButton(rebound_label, callback_data='pc:rebound'),
            ],
            [
                InlineKeyboardButton('✅ Готово', callback_data='pc:done'),
            ],
        ]
    )


def build_chat_rules_keyboard(
    entries: Sequence[RuleButtonView],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        status = '✅' if entry.enabled else '🚫'
        rows.append(
            [
                InlineKeyboardButton(
                    text=f'{entry.index}. {status} {entry.label}',
                    callback_data=f'cr:t:{entry.index}',
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton('🔄 Обновить', callback_data='cr:r'),
            InlineKeyboardButton('♻️ Сброс', callback_data='cr:x'),
            InlineKeyboardButton('✅ Готово', callback_data='cr:d'),
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_products_keyboard(
    entries: Sequence[ProductButtonView],
    *,
    confirm: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        prefix = '✅' if entry.active else '📦'
        rows.append(
            [
                InlineKeyboardButton(
                    text=f'{prefix} {entry.label}',
                    callback_data=f'pm:s:{entry.product_id}',
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton('➕ Товар', callback_data='pm:a'),
            InlineKeyboardButton('🔗 Конкурент', callback_data='pm:u'),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton('✏️ Переименовать', callback_data='pm:n'),
            InlineKeyboardButton('♻️ Сбросить имя', callback_data='pm:c'),
        ]
    )

    if confirm == 'active':
        rows.append(
            [
                InlineKeyboardButton('✅ Да, удалить', callback_data='pm:y:active'),
                InlineKeyboardButton('↩️ Отмена', callback_data='pm:r'),
            ]
        )
    elif confirm == 'all':
        rows.append(
            [
                InlineKeyboardButton('✅ Да, удалить всё', callback_data='pm:y:all'),
                InlineKeyboardButton('↩️ Отмена', callback_data='pm:r'),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton('🗑 Удалить активный', callback_data='pm:rd'),
                InlineKeyboardButton('🧹 Удалить все', callback_data='pm:ra'),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton('🔄 Обновить', callback_data='pm:r'),
            InlineKeyboardButton('✅ Готово', callback_data='pm:d'),
        ]
    )
    return InlineKeyboardMarkup(rows)
