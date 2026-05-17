# omkit

Multi-tenant SaaS scaffolding for Python services. Pooled Postgres with RLS, Valkey eventbus, BYOK secrets, LLM provider abstraction, FastAPI observability middleware, and tenant-scoped session/job primitives.

```
pip install git+https://github.com/omurlabs/omkit-python@v0.0.1
```

```python
from omkit.dbpool import create_pool
from omkit.eventbus import EventBus
from omkit.settings import SettingsManager
```

Status: v0.0.1 — initial extraction. API is pre-stable; expect renames before v0.1.

License: Apache-2.0 (planned).
