from __future__ import annotations

from src.telegram_views import (
    ProductButtonView,
    RuleButtonView,
    build_chat_rules_keyboard,
    build_main_keyboard,
    build_price_guard_keyboard,
    build_products_keyboard,
    build_profile_keyboard,
    build_settings_keyboard,
)


def _reply_rows(markup):
    return [[button.text for button in row] for row in markup.keyboard]


def _inline_rows(markup):
    return [
        [(button.text, button.callback_data) for button in row]
        for row in markup.inline_keyboard
    ]


def test_main_and_profile_keyboard_layouts_are_stable():
    main = build_main_keyboard(
        status='status',
        products='products',
        previous_product='prev',
        next_product='next',
        profile='profile',
        settings='settings',
    )
    profiles = build_profile_keyboard(['GGSEL', 'DIGI'], back='back')

    assert _reply_rows(main) == [
        ['status', 'products'],
        ['prev', 'next'],
        ['profile', 'settings'],
    ]
    assert _reply_rows(profiles) == [['GGSEL'], ['DIGI'], ['back']]


def test_settings_keyboard_preserves_toggle_semantics():
    markup = build_settings_keyboard(
        auto_on='auto on',
        auto_off='auto off',
        auto_enabled=True,
        price='price',
        mode='mode',
        price_guard='guard',
        product_remove='remove',
        back='back',
        chat_supported=True,
        chat_on='chat on',
        chat_off='chat off',
        chat_enabled=False,
        empty_only_on='empty on',
        empty_only_off='empty off',
        empty_only_enabled=True,
        smart_non_empty_on='smart on',
        smart_non_empty_off='smart off',
        smart_non_empty_enabled=False,
        chat_policy='policy',
        chat_rules='rules',
    )

    assert _reply_rows(markup) == [
        ['auto off'],
        ['price', 'mode'],
        ['guard'],
        ['remove'],
        ['chat on', 'empty off'],
        ['smart on'],
        ['policy', 'rules'],
        ['back'],
    ]


def test_price_guard_callbacks_match_existing_contract():
    markup = build_price_guard_keyboard(
        min_label='min',
        max_label='max',
        undercut_label='under',
        raise_label='raise',
        rounding_label='round',
        rebound_enabled=True,
    )

    assert _inline_rows(markup) == [
        [('min', 'pc:min'), ('max', 'pc:max')],
        [('under', 'pc:under'), ('raise', 'pc:raise')],
        [('round', 'pc:round')],
        [('🔁 Отскок: ВКЛ', 'pc:rebound')],
        [('✅ Готово', 'pc:done')],
    ]


def test_chat_rules_keyboard_preserves_indices_and_actions():
    markup = build_chat_rules_keyboard(
        [
            RuleButtonView(index=1, label='Variant A', enabled=True),
            RuleButtonView(index=2, label='Variant B', enabled=False),
        ]
    )

    assert _inline_rows(markup) == [
        [('1. ✅ Variant A', 'cr:t:1')],
        [('2. 🚫 Variant B', 'cr:t:2')],
        [
            ('🔄 Обновить', 'cr:r'),
            ('♻️ Сброс', 'cr:x'),
            ('✅ Готово', 'cr:d'),
        ],
    ]


def test_products_keyboard_preserves_selection_and_confirmation_actions():
    entries = [
        ProductButtonView(product_id=10, label='Primary', active=True),
        ProductButtonView(product_id=20, label='Secondary', active=False),
    ]
    markup = build_products_keyboard(entries, confirm='active')
    rows = _inline_rows(markup)

    assert rows[0] == [('✅ Primary', 'pm:s:10')]
    assert rows[1] == [('📦 Secondary', 'pm:s:20')]
    assert rows[2] == [('➕ Товар', 'pm:a'), ('🔗 Конкурент', 'pm:u')]
    assert rows[3] == [
        ('✏️ Переименовать', 'pm:n'),
        ('♻️ Сбросить имя', 'pm:c'),
    ]
    assert rows[4] == [
        ('✅ Да, удалить', 'pm:y:active'),
        ('↩️ Отмена', 'pm:r'),
    ]
    assert rows[-1] == [('🔄 Обновить', 'pm:r'), ('✅ Готово', 'pm:d')]
