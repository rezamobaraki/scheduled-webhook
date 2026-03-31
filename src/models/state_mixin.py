from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from src.core.errors import StateTransitionError


class StateMixin:
    _state_field: ClassVar[str]
    _allowed_transitions: ClassVar[dict[StrEnum, set[StrEnum]]]

    @property
    def current_state(self) -> StrEnum:
        return getattr(self, self._state_field)

    def can_transition_to(self, target: StrEnum) -> bool:
        allowed = self._allowed_transitions.get(self.current_state, set())
        return target in allowed

    def transition_to(self, target: StrEnum) -> None:
        if not self.can_transition_to(target):
            raise StateTransitionError(
                model=self.__class__.__name__,
                current=self.current_state,
                target=target,
            )
        setattr(self, self._state_field, target)
