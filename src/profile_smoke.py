"""
Утилиты smoke-проверки профиля API.

Сценарий:
1. Проверка API-доступа.
2. Чтение текущей цены товара.
3. Тестовый update (noop или mutate).
4. Rollback (только для mutate).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def _round4(value: float) -> float:
    return round(float(value), 4)


@dataclass
class SmokeResult:
    api_access: bool
    product_read_ok: bool
    current_price: Optional[float]
    write_probe_ok: bool
    rollback_ok: Optional[bool]
    mutated: bool
    probe_price: Optional[float]
    verify_price: Optional[float]
    token_perms_ok: Optional[bool]
    token_perms_desc: Optional[str]
    error: Optional[str]
    token_refresh_ok: Optional[bool] = None
    token_refresh_desc: Optional[str] = None


def run_profile_smoke(
    client,
    product_id: int,
    *,
    mutate: bool = False,
    delta: float = 0.0001,
    verify_read: bool = False,
) -> SmokeResult:
    """
    Запускает smoke-проверку для API клиента профиля.

    mutate=False: write probe выполняется текущей ценой (без изменения).
    mutate=True: выполняется небольшое изменение цены и rollback.
    """
    try:
        token_perms_ok: Optional[bool] = None
        token_perms_desc: Optional[str] = None
        token_refresh_ok: Optional[bool] = None
        token_refresh_desc: Optional[str] = None

        if not client:
            return SmokeResult(
                api_access=False,
                product_read_ok=False,
                current_price=None,
                write_probe_ok=False,
                rollback_ok=None,
                mutated=False,
                probe_price=None,
                verify_price=None,
                token_perms_ok=token_perms_ok,
                token_perms_desc=token_perms_desc,
                error='api_client_missing',
                token_refresh_ok=token_refresh_ok,
                token_refresh_desc=token_refresh_desc,
            )

        if not int(product_id or 0):
            return SmokeResult(
                api_access=False,
                product_read_ok=False,
                current_price=None,
                write_probe_ok=False,
                rollback_ok=None,
                mutated=False,
                probe_price=None,
                verify_price=None,
                token_perms_ok=token_perms_ok,
                token_perms_desc=token_perms_desc,
                error='product_id_missing',
                token_refresh_ok=token_refresh_ok,
                token_refresh_desc=token_refresh_desc,
            )

        if hasattr(client, 'can_refresh_access_token'):
            try:
                token_refresh_ok = bool(client.can_refresh_access_token())
                token_refresh_desc = (
                    'available'
                    if token_refresh_ok
                    else 'api_secret_missing'
                )
            except Exception as exc:
                token_refresh_ok = False
                token_refresh_desc = f'exception:{exc}'

        if hasattr(client, 'get_token_perms_status'):
            try:
                raw_ok, raw_desc = client.get_token_perms_status()
                token_perms_ok = bool(raw_ok)
                token_perms_desc = str(raw_desc)
            except Exception as exc:
                token_perms_ok = False
                token_perms_desc = f'exception:{exc}'

        api_access = bool(client.check_api_access())
        if not api_access:
            return SmokeResult(
                api_access=False,
                product_read_ok=False,
                current_price=None,
                write_probe_ok=False,
                rollback_ok=None,
                mutated=False,
                probe_price=None,
                verify_price=None,
                token_perms_ok=token_perms_ok,
                token_perms_desc=token_perms_desc,
                error='api_access_failed',
                token_refresh_ok=token_refresh_ok,
                token_refresh_desc=token_refresh_desc,
            )

        current_price = client.get_my_price(int(product_id))
        if current_price is None:
            return SmokeResult(
                api_access=True,
                product_read_ok=False,
                current_price=None,
                write_probe_ok=False,
                rollback_ok=None,
                mutated=False,
                probe_price=None,
                verify_price=None,
                token_perms_ok=token_perms_ok,
                token_perms_desc=token_perms_desc,
                error='price_read_failed',
                token_refresh_ok=token_refresh_ok,
                token_refresh_desc=token_refresh_desc,
            )
        current_price = _round4(current_price)

        probe_price = current_price
        mutated = bool(mutate)
        if mutated:
            step = _round4(delta)
            if step <= 0:
                step = 0.0001
            probe_price = _round4(current_price + step)
            if probe_price == current_price:
                probe_price = _round4(current_price + 0.0001)

        write_ok = bool(client.update_price(int(product_id), float(probe_price)))
        if not write_ok:
            return SmokeResult(
                api_access=True,
                product_read_ok=True,
                current_price=current_price,
                write_probe_ok=False,
                rollback_ok=None,
                mutated=mutated,
                probe_price=probe_price,
                verify_price=None,
                token_perms_ok=token_perms_ok,
                token_perms_desc=token_perms_desc,
                error='write_probe_failed',
                token_refresh_ok=token_refresh_ok,
                token_refresh_desc=token_refresh_desc,
            )

        rollback_ok: Optional[bool] = None
        if mutated:
            rollback_ok = bool(
                client.update_price(int(product_id), float(current_price))
            )

        verify_price = None
        if verify_read:
            verify_value = client.get_my_price(int(product_id))
            verify_price = (
                _round4(verify_value)
                if verify_value is not None
                else None
            )

        return SmokeResult(
            api_access=True,
            product_read_ok=True,
            current_price=current_price,
            write_probe_ok=True,
            rollback_ok=rollback_ok,
            mutated=mutated,
            probe_price=probe_price,
            verify_price=verify_price,
            token_perms_ok=token_perms_ok,
            token_perms_desc=token_perms_desc,
            error=None,
            token_refresh_ok=token_refresh_ok,
            token_refresh_desc=token_refresh_desc,
        )
    except Exception as exc:
        return SmokeResult(
            api_access=False,
            product_read_ok=False,
            current_price=None,
            write_probe_ok=False,
            rollback_ok=None,
            mutated=bool(mutate),
            probe_price=None,
            verify_price=None,
            token_perms_ok=None,
            token_perms_desc=None,
            error=f'exception:{exc}',
            token_refresh_ok=None,
            token_refresh_desc=None,
        )
