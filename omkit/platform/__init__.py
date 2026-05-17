"""omkit.platform — re-exports platform primitives.

Settings + sync notification helpers. Additive grouping; flat imports
still work.
"""

from omkit.config import BaseServiceSettings
from omkit.settings import SettingsManager
from omkit.sync_notifier import SyncNotifier

__all__ = [
    "BaseServiceSettings",
    "SettingsManager",
    "SyncNotifier",
]
