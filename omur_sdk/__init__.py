"""packages/omur-sdk/omur_sdk/__init__.py — Public surface of the Omur Python SDK.

Internal helpers (encryption primitives) are available via
``omur_sdk.internal.crypto``; they are intentionally NOT re-exported here.

exports: none
used_by: none
rules:   The module must maintain backward compatibility with all existing API endpoints and data structures, as breaking changes will affect multiple downstream services that depend on this SDK. All public interfaces must be thread-safe and support concurrent access without external synchronization. The SDK cannot introduce any external dependencies beyond those already declared in the project's requirements.txt, and all imports must be absolute within the omur_sdk package namespace.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
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
