"""Platform facade — re-exports Omur-internal platform primitives.

Settings, model lifecycle, cerebellum client, sync notification.
Additive grouping; flat imports still work.
"""

from omur_sdk.cerebellum_client import CerebellumClient
from omur_sdk.config import BaseServiceSettings
from omur_sdk.model_lifecycle import ModelLifecycle, ModelRegistry
from omur_sdk.settings import SettingsManager
from omur_sdk.sync_notifier import SyncNotifier

__all__ = [
    "BaseServiceSettings",
    "SettingsManager",
    "ModelLifecycle",
    "ModelRegistry",
    "CerebellumClient",
    "SyncNotifier",
]
