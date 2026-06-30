"""角色对话悬浮窗 —— 透明置顶窗口，显示角色回复。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget


class OverlayWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._drag_offset: QPoint | None = None
        self._dragging = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # 比面试版稍宽，角色回复可能较长
        self.resize(600, 200)

        self.container = QWidget(self)
        self.container.setObjectName("container")

        self.status_label = QLabel("已停止")
        self.user_label = QLabel("")
        self.response_label = QLabel("")

        for label in (self.status_label, self.user_label, self.response_label):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            label.installEventFilter(self)

        self.container.installEventFilter(self)

        # 文字阴影
        for target in (self.user_label, self.response_label):
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(6)
            shadow.setOffset(0, 1)
            shadow.setColor(Qt.GlobalColor.black)
            target.setGraphicsEffect(shadow)

        self.status_label.setObjectName("status")
        self.user_label.setObjectName("user")
        self.response_label.setObjectName("response")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(8, 6, 8, 6)
        container_layout.setSpacing(4)
        container_layout.addWidget(self.status_label)
        container_layout.addWidget(self.user_label)
        container_layout.addWidget(self.response_label)

        layout.addWidget(self.container)

        self.setStyleSheet("""
            QWidget#container {
                background: transparent;
                border: none;
            }
            QLabel {
                background: transparent;
                border: none;
            }
            QLabel#status {
                color: rgba(255, 255, 255, 0.45);
                font-size: 10px;
            }
            QLabel#user {
                color: #a6e3a1;
                font-size: 13px;
                font-weight: 700;
                padding: 2px 0;
            }
            QLabel#response {
                color: rgba(255, 255, 255, 0.92);
                font-size: 15px;
                font-weight: 500;
            }
        """)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.container.resize(self.size())

    # ── 公开接口 ──

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_user_text(self, text: str) -> None:
        """显示用户说的话（ASR 最终结果或完整话语）。"""
        if len(text) > 500:
            text = text[:500] + "…"
        self.user_label.setText(f"你说：{text}")

    def set_partial_text(self, text: str) -> None:
        """显示 ASR 中间结果（用户正在说）。"""
        if len(text) > 200:
            text = text[:200] + "…"
        self.user_label.setText(f"（正在说）{text}")

    def set_response(self, text: str) -> None:
        """显示角色回复（流式更新）。"""
        if len(text) > 2000:
            text = text[:2000] + "…"
        self.response_label.setText(text)

    def set_character_info(self, name: str, emoji: str = "") -> None:
        """更新当前角色展示信息。"""
        self.set_status(f"[{name}]")

    # ── 拖拽 ──

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            self._handle_mouse_press(event)
            return True
        if event.type() == QEvent.Type.MouseMove:
            self._handle_mouse_move(event)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease:
            self._handle_mouse_release(event)
            return True
        return super().eventFilter(obj, event)

    def _handle_mouse_press(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _handle_mouse_move(self, event: QMouseEvent) -> None:
        if self._dragging and self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def _handle_mouse_release(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_offset = None
            event.accept()
