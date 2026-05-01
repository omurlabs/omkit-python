"""packages/omur-sdk/omur_sdk/__init__.py — Public surface of the Omur Python SDK.

Internal helpers (encryption primitives) are available via
``omur_sdk.internal.crypto``; they are intentionally NOT re-exported here.

exports: none
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from omur_sdk.cerebellum_client import CerebellumClient
from omur_sdk.http import build_tenant_client
from omur_sdk.metrics import mount_metrics
from omur_sdk.model_lifecycle import ModelLifecycle, ModelRegistry
from omur_sdk.settings import SettingsManager
from omur_sdk import tenant
from omur_sdk.tracing import instrument_fastapi

__all__ = [
    "CerebellumClient",
    "build_tenant_client",
    "mount_metrics",
    "ModelLifecycle",
    "ModelRegistry",
    "SettingsManager",
    "tenant",
    "instrument_fastapi",
]
