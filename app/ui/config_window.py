"""角色对话系统 — 配置窗口。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.config import settings as app_settings
from app.core.config import Settings
from app.character.manager import CharacterManager
from app.character.models import Character
from app.llm.client import LLMClient

# ── 暗色主题 ──
STYLE_DARK = """
QWidget {
    background: #1e1e2e;
    color: #cdd6f4;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 6px;
    background: #1e1e2e;
}
QTabBar::tab {
    background: #313244;
    color: #a6adc8;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #45475a;
    color: #cdd6f4;
}
QTabBar::tab:hover:!selected {
    background: #3a3b4e;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 18px;
    font-weight: bold;
    color: #cdd6f4;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLineEdit, QTextEdit, QComboBox {
    background: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px 10px;
    color: #cdd6f4;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #89b4fa;
}
QComboBox::drop-down {
    border: none;
    background: #45475a;
    width: 20px;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}
QComboBox QAbstractItemView {
    background: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
}
QPushButton {
    background: #45475a;
    border: none;
    border-radius: 4px;
    padding: 8px 20px;
    color: #cdd6f4;
    font-weight: 600;
}
QPushButton:hover {
    background: #585b70;
}
QPushButton:pressed {
    background: #313244;
}
QPushButton#primary {
    background: #89b4fa;
    color: #1e1e2e;
}
QPushButton#primary:hover {
    background: #74c7ec;
}
QPushButton#danger {
    background: #f38ba8;
    color: #1e1e2e;
}
QPushButton#danger:hover {
    background: #eba0ac;
}
QListWidget {
    background: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
}
QListWidget::item:selected {
    background: #45475a;
}
QLabel#section-title {
    font-size: 15px;
    font-weight: bold;
    color: #89b4fa;
    margin-bottom: 4px;
}
"""


class ConfigWindow(QWidget):
    """CharacterSay 配置窗口。"""

    def __init__(
        self,
        project_root: str | Path = "",
        character_manager: CharacterManager | None = None,
    ) -> None:
        super().__init__()
        self._project_root = Path(project_root) if project_root else Path.cwd()
        self._char_mgr = character_manager or CharacterManager()
        self._force_close = False
        self._editing_char_id: str = ""

        self._setup_ui()
        self._load_settings()

        # 定时刷新
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(5000)

    # ── UI 构建 ──

    def _setup_ui(self) -> None:
        self.setWindowTitle("CharacterSay — 配置")
        self.resize(680, 580)
        self.setMinimumSize(560, 440)
        self.setStyleSheet(STYLE_DARK)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        title = QLabel("CharacterSay — 角色对话扮演")
        title.setObjectName("section-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # 当前角色状态
        self.char_status_label = QLabel("当前角色: 未选择")
        self.char_status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        self.char_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.char_status_label)

        # 标签页
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_llm_tab(), "LLM 配置")
        self.tabs.addTab(self._build_character_tab(), "角色管理")
        self.tabs.addTab(self._build_audio_tab(), "音频模型")
        self.tabs.addTab(self._build_test_tab(), "模型测试")
        self.tabs.addTab(self._build_history_tab(), "对话记录")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs, stretch=1)

        # 底部按钮
        row = QHBoxLayout()
        row.addStretch()
        save_btn = QPushButton("保存配置")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_config)
        row.addWidget(save_btn)
        row.addStretch()
        main_layout.addLayout(row)

    # ── Tab 1: LLM 配置 ──

    def _build_llm_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        layout.addWidget(QLabel("API Base URL"))
        self.llm_base_url_edit = QLineEdit()
        self.llm_base_url_edit.setPlaceholderText("https://ark.cn-beijing.volces.com/api/v3")
        layout.addWidget(self.llm_base_url_edit)

        layout.addWidget(QLabel("API Key"))
        self.llm_api_key_edit = QLineEdit()
        self.llm_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_api_key_edit.setPlaceholderText("sk-... 或 ark-...")
        layout.addWidget(self.llm_api_key_edit)

        show_cb = QCheckBox("显示密钥")
        show_cb.toggled.connect(
            lambda checked: self.llm_api_key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        layout.addWidget(show_cb)

        layout.addWidget(QLabel("Model"))
        self.llm_model_edit = QLineEdit()
        self.llm_model_edit.setPlaceholderText("doubao-seed-character-260628")
        layout.addWidget(self.llm_model_edit)

        layout.addStretch()
        return w

    # ── Tab 2: 角色管理 ──

    def _build_character_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        # 角色列表
        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("角色列表："))
        list_header.addStretch()

        add_btn = QPushButton("+ 新建角色")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._char_show_add_form)
        list_header.addWidget(add_btn)

        import_btn = QPushButton("导入")
        import_btn.clicked.connect(self._char_import)
        list_header.addWidget(import_btn)

        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self._char_export)
        list_header.addWidget(export_btn)

        layout.addLayout(list_header)

        self.char_list = QListWidget()
        self.char_list.setMinimumHeight(100)
        self.char_list.setMaximumHeight(150)
        self.char_list.currentItemChanged.connect(self._char_on_selected)
        layout.addWidget(self.char_list)

        # 激活按钮
        activate_row = QHBoxLayout()
        self.activate_btn = QPushButton("设为当前角色")
        self.activate_btn.setObjectName("primary")
        self.activate_btn.clicked.connect(self._char_activate)
        self.activate_btn.setEnabled(False)
        activate_row.addWidget(self.activate_btn)

        del_btn = QPushButton("删除角色")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._char_delete)
        activate_row.addWidget(del_btn)
        activate_row.addStretch()
        layout.addLayout(activate_row)

        # 编辑表单
        layout.addWidget(QLabel("— 角色详情 —"))

        layout.addWidget(QLabel("角色名称："))
        self.char_name_edit = QLineEdit()
        self.char_name_edit.setPlaceholderText("如：诸葛亮、猫娘、霸道总裁...")
        layout.addWidget(self.char_name_edit)

        layout.addWidget(QLabel("头像表情："))
        self.char_emoji_edit = QLineEdit()
        self.char_emoji_edit.setPlaceholderText("(可选标识)")
        self.char_emoji_edit.setMaximumWidth(80)
        layout.addWidget(self.char_emoji_edit)

        layout.addWidget(QLabel("性格描述："))
        self.char_persona_edit = QTextEdit()
        self.char_persona_edit.setPlaceholderText("描述角色的核心性格特点...")
        self.char_persona_edit.setMaximumHeight(60)
        layout.addWidget(self.char_persona_edit)

        layout.addWidget(QLabel("背景故事："))
        self.char_backstory_edit = QTextEdit()
        self.char_backstory_edit.setPlaceholderText("角色的背景故事、经历...")
        self.char_backstory_edit.setMaximumHeight(60)
        layout.addWidget(self.char_backstory_edit)

        layout.addWidget(QLabel("说话风格："))
        self.char_style_edit = QTextEdit()
        self.char_style_edit.setPlaceholderText("语气、口头禅、常用表达...")
        self.char_style_edit.setMaximumHeight(60)
        layout.addWidget(self.char_style_edit)

        layout.addWidget(QLabel("招呼语："))
        self.char_greeting_edit = QLineEdit()
        self.char_greeting_edit.setPlaceholderText("你好！很高兴和你聊天。")
        layout.addWidget(self.char_greeting_edit)

        layout.addWidget(QLabel("TTS 音色 ID（可选，未来使用）："))
        self.char_voice_edit = QLineEdit()
        self.char_voice_edit.setPlaceholderText("留空使用默认音色")
        layout.addWidget(self.char_voice_edit)

        # 保存/取消
        form_row = QHBoxLayout()
        form_row.addStretch()
        self.char_cancel_btn = QPushButton("取消")
        self.char_cancel_btn.clicked.connect(self._char_cancel_edit)
        form_row.addWidget(self.char_cancel_btn)
        self.char_save_btn = QPushButton("保存角色")
        self.char_save_btn.setObjectName("primary")
        self.char_save_btn.clicked.connect(self._char_save)
        form_row.addWidget(self.char_save_btn)
        layout.addLayout(form_row)

        return w

    # ── Tab 3: 音频模型 ──

    def _build_audio_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        layout.addWidget(QLabel("音频模型 (TTS 语音合成)"))
        layout.addWidget(QLabel(""))

        status = QLabel("当前状态：未配置（占位模型）")
        status.setStyleSheet("color: #f9e2af; font-size: 14px; font-weight: bold;")
        layout.addWidget(status)

        hint = QLabel(
            "音频模型用于将角色的文字回复转换为语音输出。\n\n"
            "接入方式：\n"
            "1. 实现 app.audio.model.AudioModel 抽象类\n"
            "2. 在启动时将实例注入 controller.audio_model\n\n"
            "示例提供者（待开发）：\n"
            "- 火山引擎 TTS\n"
            "- Azure Speech Services\n"
            "- OpenAI TTS\n"
            "- 本地 VITS 模型"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #a6adc8; font-size: 12px; line-height: 1.6;")
        layout.addWidget(hint)

        layout.addStretch()
        return w

    # ── Tab 4: 模型测试 ──

    def _build_test_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        layout.addWidget(QLabel("测试消息："))
        self.test_input = QTextEdit()
        self.test_input.setPlaceholderText("输入一条消息来测试对话效果...")
        self.test_input.setMaximumHeight(80)
        layout.addWidget(self.test_input)

        send_row = QHBoxLayout()
        send_row.addStretch()
        self.test_send_btn = QPushButton("发送测试")
        self.test_send_btn.setObjectName("primary")
        self.test_send_btn.clicked.connect(self._test_chat)
        send_row.addWidget(self.test_send_btn)
        layout.addLayout(send_row)

        layout.addWidget(QLabel("模型回复："))
        self.test_output = QTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setPlaceholderText("模型回复将显示在这里...")
        layout.addWidget(self.test_output, stretch=1)

        return w

    # ── Tab 5: 对话记录 ──

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(QLabel("对话记录："))
        header.addStretch()
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_history)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setPlaceholderText("开始对话后，记录将自动出现在这里...")
        layout.addWidget(self.history_text, stretch=1)

        self.history_count_label = QLabel("共 0 轮对话")
        self.history_count_label.setStyleSheet("color: #6c7086; font-size: 12px;")
        layout.addWidget(self.history_count_label)

        self._history_count = 0
        return w

    # ── 对话记录回调 ──

    def add_history(self, user_text: str, response_text: str) -> None:
        self._history_count += 1
        entry = (
            f"--- 第 {self._history_count} 轮 ---\n"
            f"[用户]: {user_text}\n"
            f"[角色]: {response_text}\n"
        )
        self.history_text.append(entry)
        self.history_count_label.setText(f"共 {self._history_count} 轮对话")

    def _clear_history(self) -> None:
        self.history_text.clear()
        self._history_count = 0
        self.history_count_label.setText("共 0 轮对话")

    # ── 加载/保存 ──

    def _load_settings(self) -> None:
        self.llm_base_url_edit.setText(app_settings.llm_base_url)
        self.llm_api_key_edit.setText(app_settings.llm_api_key)
        self.llm_model_edit.setText(app_settings.llm_model)
        self._refresh_char_list()
        self._update_char_status()

    def _save_config(self) -> None:
        updates = {
            "LLM_BASE_URL": self.llm_base_url_edit.text().strip(),
            "LLM_API_KEY": self.llm_api_key_edit.text().strip(),
            "LLM_MODEL": self.llm_model_edit.text().strip(),
        }
        try:
            Settings.save_to_env(updates)
            app_settings.llm_base_url = updates["LLM_BASE_URL"]
            app_settings.llm_api_key = updates["LLM_API_KEY"]
            app_settings.llm_model = updates["LLM_MODEL"]
            QMessageBox.information(self, "保存成功", "配置已保存到 .env 文件。")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    # ── 角色 CRUD ──

    def _refresh_char_list(self) -> None:
        self.char_list.clear()
        for c in self._char_mgr.list_all():
            active_mark = " *" if (self._char_mgr.active and self._char_mgr.active.char_id == c.char_id) else ""
            item = QListWidgetItem(f"{c.name}{active_mark}")
            item.setData(Qt.ItemDataRole.UserRole, c.char_id)
            item.setToolTip(f"性格: {c.persona[:100]}\n说话风格: {c.speaking_style[:100]}")
            self.char_list.addItem(item)
        self._update_char_status()

    def _update_char_status(self) -> None:
        if self._char_mgr.active:
            c = self._char_mgr.active
            self.char_status_label.setText(f"当前角色: {c.name}")
        else:
            self.char_status_label.setText("当前角色: 未选择")

    def _char_on_selected(self, current, previous) -> None:
        if not current:
            self.activate_btn.setEnabled(False)
            self._clear_char_form()
            return

        char_id = current.data(Qt.ItemDataRole.UserRole)
        char = self._char_mgr.get(char_id)
        if not char:
            return

        self._editing_char_id = char_id
        self.activate_btn.setEnabled(True)
        self._fill_char_form(char)

    def _fill_char_form(self, c: Character) -> None:
        self.char_name_edit.setText(c.name)
        self.char_emoji_edit.setText(c.avatar_emoji)
        self.char_persona_edit.setPlainText(c.persona)
        self.char_backstory_edit.setPlainText(c.backstory)
        self.char_style_edit.setPlainText(c.speaking_style)
        self.char_greeting_edit.setText(c.greeting)
        self.char_voice_edit.setText(c.voice_id)

    def _clear_char_form(self) -> None:
        self._editing_char_id = ""
        self.char_name_edit.clear()
        self.char_emoji_edit.clear()
        self.char_persona_edit.clear()
        self.char_backstory_edit.clear()
        self.char_style_edit.clear()
        self.char_greeting_edit.clear()
        self.char_voice_edit.clear()

    def _char_show_add_form(self) -> None:
        self._clear_char_form()
        self.char_emoji_edit.setText("")
        self.char_greeting_edit.setText("你好！很高兴和你聊天。")
        self.char_save_btn.setText("创建角色")

    def _char_cancel_edit(self) -> None:
        self._clear_char_form()
        self.char_save_btn.setText("保存角色")
        self.char_list.clearSelection()

    def _char_save(self) -> None:
        name = self.char_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入角色名称。")
            return

        persona = self.char_persona_edit.toPlainText().strip()
        backstory = self.char_backstory_edit.toPlainText().strip()
        speaking_style = self.char_style_edit.toPlainText().strip()
        greeting = self.char_greeting_edit.text().strip()
        avatar_emoji = self.char_emoji_edit.text().strip() or ""
        voice_id = self.char_voice_edit.text().strip()

        if self._editing_char_id:
            # 更新
            existing = self._char_mgr.get(self._editing_char_id)
            if existing:
                existing.name = name
                existing.persona = persona
                existing.backstory = backstory
                existing.speaking_style = speaking_style
                existing.greeting = greeting
                existing.avatar_emoji = avatar_emoji
                existing.voice_id = voice_id
                self._char_mgr.update(existing)
        else:
            # 新建
            char = Character(
                name=name,
                persona=persona,
                backstory=backstory,
                speaking_style=speaking_style,
                greeting=greeting,
                avatar_emoji=avatar_emoji,
                voice_id=voice_id,
            )
            self._char_mgr.add(char)

        self._char_mgr.store.flush()
        self._editing_char_id = ""
        self.char_save_btn.setText("保存角色")
        self._refresh_char_list()

    def _char_activate(self) -> None:
        if not self._editing_char_id:
            return
        char = self._char_mgr.set_active(self._editing_char_id)

        # 更新 .env
        try:
            Settings.save_to_env({"ACTIVE_CHARACTER": char.name})
        except Exception:
            pass

        self._refresh_char_list()
        QMessageBox.information(self, "角色已切换", f"当前角色: {char.name}")

    def _char_delete(self) -> None:
        if not self._editing_char_id:
            return
        char = self._char_mgr.get(self._editing_char_id)
        if not char:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除角色「{char.name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._char_mgr.delete(self._editing_char_id)
        self._char_mgr.store.flush()
        self._clear_char_form()
        self._refresh_char_list()

    def _char_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入角色 JSON", "", "JSON 文件 (*.json);;所有文件 (*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            count = self._char_mgr.import_from_json(path)
            self._refresh_char_list()
            QMessageBox.information(self, "导入完成", f"成功导入 {count} 个角色。")
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))

    def _char_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出角色 JSON", "characters_export.json", "JSON 文件 (*.json)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        count = self._char_mgr.export_to_file(path)
        QMessageBox.information(self, "导出完成", f"已导出 {count} 个角色。")

    # ── 模型测试 ──

    def _test_chat(self) -> None:
        text = self.test_input.toPlainText().strip()
        if not text:
            return
        api_key = self.llm_api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "提示", "请先填写 API Key。")
            return

        self.test_send_btn.setEnabled(False)
        self.test_send_btn.setText("等待回复...")

        # 用当前激活角色或通用角色
        if self._char_mgr.active:
            system_prompt = self._char_mgr.build_system_prompt()
            char_name = self._char_mgr.active.name
        else:
            system_prompt = "你是一个友好的对话助手。"
            char_name = "助手"

        QTimer.singleShot(100, lambda: self._do_test_chat(api_key, text, system_prompt, char_name))

    def _do_test_chat(self, api_key: str, text: str, system_prompt: str, char_name: str) -> None:
        async def _run():
            client = LLMClient()
            client.update_config(
                api_key=api_key,
                base_url=self.llm_base_url_edit.text().strip(),
                model=self.llm_model_edit.text().strip(),
            )
            try:
                # 流式显示
                self.test_output.setPlainText(f"[{char_name}]: 正在生成...")
                accumulated = ""
                async for token in client.chat_stream(
                    user_message=text,
                    system_prompt=system_prompt,
                ):
                    accumulated += token
                    self.test_output.setPlainText(f"[{char_name}]: {accumulated}")
            except Exception as exc:
                self.test_output.setPlainText(f"调用失败: {exc}")
            finally:
                self.test_send_btn.setEnabled(True)
                self.test_send_btn.setText("发送测试")

        loop = asyncio.get_event_loop()
        loop.create_task(_run())

    # ── 自动刷新 ──

    def _auto_refresh(self) -> None:
        if not self.isVisible():
            return
        idx = self.tabs.currentIndex()
        if self.tabs.tabText(idx) == "角色管理":
            self._refresh_char_list()

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index) == "角色管理":
            self._refresh_char_list()

    # ── 窗口关闭 ──

    def closeEvent(self, event) -> None:
        if self._force_close:
            event.accept()
            return
        event.ignore()
        self.hide()

    def force_close(self) -> None:
        self._force_close = True
        self.close()
