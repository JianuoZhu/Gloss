from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        from .selftest import run

        return run(sys.argv[2])
    from .app import App

    return App().run()


if __name__ == "__main__":
    sys.exit(main())
