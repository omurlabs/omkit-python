"""packages/omur-sdk/omur_sdk/platform/__init__.py — re-exports Omur-internal platform primitives.

Settings, model lifecycle, cerebellum client, sync notification.
Additive grouping; flat imports still work.

exports: none
used_by: none
rules:   The platform module must maintain backward compatibility across all supported Python versions (3.8+) and cannot introduce breaking changes to its public API surface. All platform-specific implementations must be isolated behind a consistent interface that allows for easy swapping of underlying platform handlers without affecting client code. The module cannot have any runtime dependencies on external packages beyond the standard library and explicitly declared optional dependencies.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
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
