"""packages/omur-sdk/omur_sdk/platform/__init__.py — re-exports Omur-internal platform primitives.

Settings, model lifecycle, cerebellum client, sync notification.
Additive grouping; flat imports still work.

exports: none
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
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
