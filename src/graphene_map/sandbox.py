"""Token Factory Sandboxes (ConTree), behind one module of ours: the SDK is in beta."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def sandbox_configured() -> bool:
    """ConTree is set up on this machine: its SDK imports, and a token or a profile is configured
    (CONTREE_TOKEN, or ~/.config/contree/auth.ini). That the file exists is all that is asked; it is
    never read. `graphene init` offers the sandbox placement when this is true."""
    if not all(importlib.util.find_spec(name) for name in ("contree_sdk", "contree_client")):
        return False
    return bool(os.environ.get("CONTREE_TOKEN")) or (Path.home() / ".config/contree/auth.ini").exists()
