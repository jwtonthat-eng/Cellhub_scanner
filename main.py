"""
Cellhub Scanner — entry point.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _add_project_root() -> None:
    """Ensure the project root is on sys.path when run directly."""
    root = Path(__file__).parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_add_project_root()


def main() -> None:
    from ui.app_window import AppWindow
    app = AppWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
