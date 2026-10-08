"""Service settings. Jev is off unless DECIDE_JEV_ENABLED says otherwise. No secret is read here."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    jev_enabled: bool = False
    daily_token_cap: int = 1_000_000
    min_confidence: float = 0.8
    owner_users: frozenset[str] = frozenset({"gab"})
    engine_user: str = "uc-engine"
    database_url: str = ""

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = os.environ if env is None else env
        owners = frozenset(u.strip() for u in (env.get("DECIDE_OWNER_USERS") or "gab").split(",") if u.strip())
        return cls(
            jev_enabled=_flag(env.get("DECIDE_JEV_ENABLED")),
            daily_token_cap=int(env.get("DECIDE_DAILY_TOKEN_CAP") or 1_000_000),
            min_confidence=float(env.get("DECIDE_MIN_CONFIDENCE") or 0.8),
            owner_users=owners or frozenset({"gab"}),
            database_url=env.get("DECIDE_DATABASE_URL") or "",
        )

    def __repr__(self) -> str:
        # the database URL can carry a password: never print it
        return (f"Settings(jev_enabled={self.jev_enabled}, daily_token_cap={self.daily_token_cap}, "
                f"min_confidence={self.min_confidence}, owner_users={sorted(self.owner_users)}, "
                f"engine_user={self.engine_user!r})")
