#!/usr/bin/env python3
"""Servidor MCP leve do CEW ("cew-mcp") por stdio. Implementacao em cew/mcp_server.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cew.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
