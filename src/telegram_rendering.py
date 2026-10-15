"""Pure Telegram status/diagnostics rendering.

The functions in this module deliberately contain no Telegram, storage or
marketplace I/O. Runtime collectors can evolve independently while the user-
visible message contract remains easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StatusView:
    profile_name: str
    product_label: str
    active_product_slot: str
    runtime_source: str
    tracked_count: int
    display_price_label: str
    display_price: str
    target_price_label: str
    target_price: str
    competitor_price: str
    competitor_url: str
    parse_method: str
    parse_at: str
    monitor_mode: str
    pair_active_label: str
    chat_block: str
    auto_enabled: bool
    mode_label: str
    update_at: str
    check_interval: int


@dataclass(frozen=True)
class DiagnosticsView:
    profile_name: str
    api_ok: bool
    product_ok: bool
    product_price: str
    config_valid: bool
    heartbeat_seconds: int
    auto_enabled: bool
    competitor_count: int
    last_parser_error: str
    last_block_reason: str
    extra_lines: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)


def render_status(view: StatusView) -> str:
    """Render the existing status message contract from collected values."""
    return f"""📊 Статус

🧭 Площадка: {view.profile_name}
🆔 Активный товар: {view.product_label} ({view.active_product_slot})
🧷 Источник параметров: {view.runtime_source}
📦 Товаров в мониторинге: {view.tracked_count}
{view.display_price_label}: {view.display_price}₽
{view.target_price_label}: {view.target_price}₽
📈 Цена конкурента: {view.competitor_price}₽
🔗 URL: {view.competitor_url}
🧪 Метод парсинга: {view.parse_method}
🕓 Последний парс: {view.parse_at}
📡 Мониторинг: {view.monitor_mode}
🛡️ Пара активна: {view.pair_active_label}
{view.chat_block}

🔔 Авто: {'ВКЛ' if view.auto_enabled else 'ВЫКЛ'}
🎯 Режим: {view.mode_label}
🕐 Обновление: {view.update_at}
⏲️ Интервал: {view.check_interval}s
"""


def render_diagnostics(view: DiagnosticsView) -> str:
    """Render diagnostics without performing runtime or API reads."""
    lines = [
        '🩺 Диагностика',
        '',
        f'Профиль: {view.profile_name}',
        f'API: {"OK" if view.api_ok else "FAIL"}',
        (
            f'Product: {"OK" if view.product_ok else "FAIL"} '
            f'({view.product_price}₽)'
        ),
        f'Config: {"OK" if view.config_valid else "INVALID"}',
        f'Heartbeat: {view.heartbeat_seconds}s',
        f'Auto: {"ON" if view.auto_enabled else "OFF"}',
        f'Competitors: {view.competitor_count}',
        f'Last parser error: {view.last_parser_error}',
        f'Last block reason: {view.last_block_reason}',
    ]
    lines.extend(view.extra_lines)
    if view.errors:
        lines.append('Errors: ' + '; '.join(view.errors[:3]))
    return '\n'.join(lines)
