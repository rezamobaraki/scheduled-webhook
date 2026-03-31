"""Reusable model mixins."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from src.core.errors import StateTransitionError


class StateMixin:
    """Lightweight state-machine guard for SQLAlchemy models.

    Subclasses declare *which* column holds the state and *which*
    transitions are legal.  The mixin adds a single ``transition_to``
    method that validates the move before mutating the column.

    Usage::

        class Timer(StateMixin, BaseModel):
            _state_field = "status"
            _allowed_transitions = {
                TimerStatus.PENDING: {TimerStatus.EXECUTED, TimerStatus.FAILED},
            }
    """

    _state_field: ClassVar[str]
    _allowed_transitions: ClassVar[dict[StrEnum, set[StrEnum]]]

    @property
    def current_state(self) -> StrEnum:
        return getattr(self, self._state_field)

    def can_transition_to(self, target: StrEnum) -> bool:
        allowed = self._allowed_transitions.get(self.current_state, set())
        return target in allowed

    def transition_to(self, target: StrEnum) -> None:
        """Move to *target* state or raise ``StateTransitionError``."""
        if not self.can_transition_to(target):
            raise StateTransitionError(
                model=self.__class__.__name__,
                current=self.current_state,
                target=target,
            )
        setattr(self, self._state_field, target)
