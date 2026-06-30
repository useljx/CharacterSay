"""CharacterSay 主入口。"""

from __future__ import annotations

import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from app.ui.tray_app import TrayApp


def main() -> int:
    print("main: creating QApplication")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    print("main: creating qasync loop")
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    print("main: creating TrayApp")
    tray = TrayApp()
    app._tray_app = tray
    print("main: TrayApp created")

    with loop:
        print("main: entering event loop")
        loop.run_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
