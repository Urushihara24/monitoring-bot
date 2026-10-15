"""Runtime scheduler with extracted parser coordination.

``Scheduler`` remains the compatibility base while post-v1 decomposition is
performed in small, behaviour-preserving slices. Runtime construction should
prefer ``ModularScheduler`` so extracted components become the active path
without forcing one large rewrite of the legacy scheduler module.
"""

from __future__ import annotations

from typing import Any

from .parser_coordinator import ParserCoordinator
from .rsc_parser import ParseResult
from .scheduler import Scheduler


class ModularScheduler(Scheduler):
    """Scheduler runtime that delegates competitor parsing to a component."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._parser_coordinator = ParserCoordinator(
            profile_id=self.profile_id,
            profile_name=self.profile_name,
            runtime_loader=self._runtime,
            sync_cookies_from_env=self._sync_cookies_from_env,
            reload_cookies_from_backup=self._reload_cookies_from_backup,
        )

    async def _parse_competitor_price(
        self,
        url: str,
        runtime,
        timeout: int = 15,
    ) -> ParseResult:
        return await self._parser_coordinator.parse_competitor_price(
            url,
            runtime=runtime,
            timeout=timeout,
        )
