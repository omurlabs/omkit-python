"""omkit.platform — re-exports platform primitives.

Settings + sync notification + lazy model lifecycle helpers. Additive
grouping; flat imports still work.
"""

from omkit.config import BaseServiceSettings
from omkit.model_lifecycle import ModelLifecycle, ModelRegistry
from omkit.settings import SettingsManager
from omkit.syncnotifier import SyncNotifier

__all__ = [
    "BaseServiceSettings",
    "ModelLifecycle",
    "ModelRegistry",
    "SettingsManager",
    "SyncNotifier",
]
