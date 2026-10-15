from __future__ import annotations

from types import SimpleNamespace

from src.__main__ import _install_runtime_overrides
from src.modular_telegram_bot import ModularTelegramBot
from src.modular_telegram_routed_bot import ModularTelegramRoutedBot
from src.modular_telegram_settings_bot import ModularTelegramSettingsBot
from src.modular_telegram_views_bot import ModularTelegramViewsBot
from src.telegram_bot import TelegramBot
from src.telegram_rendering import (
    DiagnosticsView,
    StatusView,
    render_diagnostics,
    render_status,
)


def test_status_renderer_preserves_message_contract():
    text = render_status(
        StatusView(
            profile_name='GGSEL',
            product_label='Fortnite V-Bucks',
            active_product_slot='1/2',
            runtime_source='товарные',
            tracked_count=2,
            display_price_label='💰 Моя цена',
            display_price='0.3500',
            target_price_label='🎯 Цена по стратегии',
            target_price='0.3400',
            competitor_price='0.3600',
            competitor_url='https://example.test/product',
            parse_method='fixture',
            parse_at='2026-10-15 12:00:00',
            monitor_mode='АКТИВЕН (2 URL)',
            pair_active_label='Да',
            chat_block='\n💬 Авто-инструкции: ВЫКЛ',
            auto_enabled=True,
            mode_label='Демпинг',
            update_at='2026-10-15 11:59',
            check_interval=60,
        )
    )

    assert text.startswith('📊 Статус\n\n🧭 Площадка: GGSEL')
    assert '🆔 Активный товар: Fortnite V-Bucks (1/2)' in text
    assert '💰 Моя цена: 0.3500₽' in text
    assert '🎯 Цена по стратегии: 0.3400₽' in text
    assert '\n💬 Авто-инструкции: ВЫКЛ\n\n🔔 Авто: ВКЛ' in text
    assert text.endswith('⏲️ Интервал: 60s\n')


def test_diagnostics_renderer_preserves_optional_lines_and_error_limit():
    text = render_diagnostics(
        DiagnosticsView(
            profile_name='DIGISELLER',
            api_ok=True,
            product_ok=False,
            product_price='N/A',
            config_valid=False,
            heartbeat_seconds=17,
            auto_enabled=False,
            competitor_count=3,
            last_parser_error='timeout',
            last_block_reason='http_429',
            extra_lines=(
                'Token perms: OK (read/write)',
                'Chat autoreply: ON (sent=4)',
            ),
            errors=('e1', 'e2', 'e3', 'e4'),
        )
    )

    assert text.splitlines()[:4] == [
        '🩺 Диагностика',
        '',
        'Профиль: DIGISELLER',
        'API: OK',
    ]
    assert 'Product: FAIL (N/A₽)' in text
    assert 'Config: INVALID' in text
    assert 'Token perms: OK (read/write)' in text
    assert 'Chat autoreply: ON (sent=4)' in text
    assert text.endswith('Errors: e1; e2; e3')
    assert 'e4' not in text


def test_production_bootstrap_installs_latest_modular_telegram_facade():
    app_main = SimpleNamespace(TelegramBot=TelegramBot)

    result = _install_runtime_overrides(app_main)

    assert result is app_main
    assert app_main.TelegramBot is ModularTelegramRoutedBot
    assert issubclass(ModularTelegramRoutedBot, ModularTelegramSettingsBot)
    assert issubclass(ModularTelegramSettingsBot, ModularTelegramViewsBot)
    assert issubclass(ModularTelegramViewsBot, ModularTelegramBot)
    assert issubclass(ModularTelegramRoutedBot, TelegramBot)
    assert ModularTelegramBot.send_status is not TelegramBot.send_status
    assert ModularTelegramBot.send_diagnostics is not TelegramBot.send_diagnostics
