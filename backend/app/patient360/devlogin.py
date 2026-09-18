"""Dev-login map: the only place in the backend where a name exists.

login -> opaque user_id. Roles come from identity.users, never from here; the
self patient key comes from the vault, never from here. In production this is
replaced by an IdP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DevPersona:
    login: str
    user_id: str
    display: str


class DevLoginMap:
    def __init__(self, personas: list[DevPersona]) -> None:
        self._by_login = {p.login: p for p in personas}
        self._by_user = {p.user_id: p for p in personas}

    @classmethod
    def load(cls, path: Path) -> DevLoginMap:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        personas = [DevPersona(p["login"], p["user_id"], p["display"]) for p in data["personas"]]
        return cls(personas)

    def resolve(self, login: str) -> DevPersona | None:
        return self._by_login.get(login.strip().lower())

    def display_for(self, user_id: str) -> str | None:
        p = self._by_user.get(user_id)
        return p.display if p else None

    def personas(self) -> list[DevPersona]:
        return list(self._by_login.values())
