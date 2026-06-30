"""系统托盘应用。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from app.character.manager import CharacterManager
from app.runtime.controller import AppController
from app.ui.config_window import ConfigWindow
from app.ui.overlay_window import OverlayWindow

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TrayApp:
    def __init__(self) -> None:
        print("tray: init start")

        # ── 角色管理器 ──
        self.char_mgr = CharacterManager()
        self.char_mgr.auto_activate()

        # ── 悬浮窗 ──
        self.overlay = OverlayWindow()
        self.overlay.show()

        if self.char_mgr.active:
            c = self.char_mgr.active
            self.overlay.set_character_info(c.name, c.avatar_emoji)
            self.overlay.set_status(f"[{c.name}] — 已就绪")
        else:
            self.overlay.set_status("请创建角色 — 打开配置窗口")

        print("tray: overlay shown =", self.overlay.isVisible())

        # ── 配置窗口 ──
        self.config_window = ConfigWindow(
            project_root=_PROJECT_ROOT,
            character_manager=self.char_mgr,
        )

        # ── 控制器 ──
        self.controller = AppController(character_manager=self.char_mgr)
        self.controller.status_changed.connect(self.overlay.set_status)
        self.controller.partial_changed.connect(self.overlay.set_partial_text)
        self.controller.utterance_changed.connect(self.overlay.set_user_text)
        self.controller.response_changed.connect(self.overlay.set_response)
        self.controller.error_changed.connect(
            lambda text: self.overlay.set_status(f"错误: {text}")
        )
        self.controller.history_changed.connect(self.config_window.add_history)

        # ── 系统托盘 ──
        tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        print("tray: system tray available =", tray_available)

        if not tray_available:
            print("tray: system tray unavailable")
            self.overlay.set_status("错误: 系统托盘不可用")
            self.tray = None
            self.config_window.show()
            return

        self.tray = QSystemTrayIcon(self.config_window)
        self.tray.setToolTip("CharacterSay")

        icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.tray.setIcon(icon)

        # ── 菜单 ──
        self.menu = QMenu(self.config_window)

        self.settings_action = QAction("打开配置", self.menu)
        self.menu.addAction(self.settings_action)

        self.menu.addSeparator()

        self.start_action = QAction("开始对话", self.menu)
        self.stop_action = QAction("停止对话", self.menu)
        self.toggle_action = QAction("显示/隐藏字幕", self.menu)

        self.start_action.triggered.connect(self._start_controller)
        self.stop_action.triggered.connect(self._stop_controller)
        self.toggle_action.triggered.connect(self._toggle_overlay)

        self.menu.addAction(self.start_action)
        self.menu.addAction(self.stop_action)
        self.menu.addAction(self.toggle_action)

        self.menu.addSeparator()

        self.quit_action = QAction("退出", self.menu)
        self.quit_action.triggered.connect(self._quit_app)
        self.menu.addAction(self.quit_action)

        # ── 信号 ──
        self.settings_action.triggered.connect(self._show_config)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        # 启动时显示配置窗口
        self.config_window.show()

        print("tray: init done")

    def _show_config(self) -> None:
        self.config_window.show()
        self.config_window.raise_()
        self.config_window.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_config()

    def _toggle_overlay(self) -> None:
        new_visible = not self.overlay.isVisible()
        self.overlay.setVisible(new_visible)

    def _start_controller(self) -> None:
        print("tray: start clicked")
        asyncio.create_task(self._do_start())

    async def _do_start(self) -> None:
        char = self.char_mgr.active
        if char:
            self.overlay.set_character_info(char.name, char.avatar_emoji)
        await self.controller.start()

    def _stop_controller(self) -> None:
        print("tray: stop clicked")
        asyncio.create_task(self.controller.stop())

    def _quit_app(self) -> None:
        print("tray: quit clicked")
        asyncio.create_task(self._quit())

    async def _quit(self) -> None:
        print("tray: quitting")
        await self.controller.stop()
        self.config_window.force_close()
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()
