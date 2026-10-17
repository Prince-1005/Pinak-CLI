"""Pinak Media Lifecycle: Session coordinator, CLI locking, and close affordance hit-testing."""

from .close_affordances import ClickableRegion, CloseAffordanceManager
from .session_coordinator import MediaSessionCoordinator

__all__ = [
    "MediaSessionCoordinator",
    "CloseAffordanceManager",
    "ClickableRegion",
]
