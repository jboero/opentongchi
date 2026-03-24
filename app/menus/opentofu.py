"""OpenTofu Menu Builder for OpenTongchi — Local workspaces only."""

import subprocess
from typing import Dict, Optional
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog, QTextEdit, QDialog, QVBoxLayout, QPushButton
from PySide6.QtCore import QObject, Signal
from app.clients.opentofu import OpenTofuClient
from app.async_menu import AsyncMenu
from app.dialogs import JsonEditorDialog, CrudDialog


class OpenTofuMenuBuilder(QObject):
    notification = Signal(str, str)

    def __init__(self, settings, process_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        self._local_client: Optional[OpenTofuClient] = None

    @property
    def local_client(self) -> OpenTofuClient:
        if self._local_client is None:
            self._local_client = OpenTofuClient(self.settings.opentofu)
        return self._local_client

    def refresh_clients(self):
        """Reset clients to pick up new settings."""
        self._local_client = None

    def build_menu(self) -> AsyncMenu:
        menu = AsyncMenu("🏗️ OpenTofu", self._load_local_workspaces)
        menu.set_submenu_factory(self._create_workspace_submenu)
        def _tofu_footer(m):
            m.addAction("📂 Open Directory...").triggered.connect(self._open_directory)
        menu.set_footer_builder(_tofu_footer)
        return menu

    def _open_directory(self):
        path = str(self.local_client.home_dir)
        subprocess.Popen(['xdg-open', path])

    def _load_local_workspaces(self) -> list:
        workspaces = self.local_client.list_workspaces()
        items = []
        for ws in workspaces:
            name = ws.get('name', 'unknown')
            status = ws.get('status', 'unknown')
            emoji = self.local_client.get_workspace_status_emoji(status)
            items.append({'text': f"{emoji} {name}", 'data': ws, 'is_submenu': True})
        return items

    def _create_workspace_submenu(self, title: str, data: Dict) -> QMenu:
        ws_name = data.get('name', '')
        menu = QMenu(title)

        status = data.get('status', 'unknown')
        status_action = menu.addAction(f"Status: {status}")
        status_action.setEnabled(False)
        menu.addSeparator()

        init = menu.addAction("📥 Initialize")
        init.triggered.connect(lambda: self._init_workspace(ws_name))

        plan = menu.addAction("📋 Plan")
        plan.triggered.connect(lambda: self._plan_workspace(ws_name))

        apply = menu.addAction("✅ Apply")
        apply.triggered.connect(lambda: self._apply_workspace(ws_name))

        refresh = menu.addAction("🔄 Refresh")
        refresh.triggered.connect(lambda: self._refresh_workspace(ws_name))

        destroy = menu.addAction("💥 Destroy")
        destroy.triggered.connect(lambda: self._destroy_workspace(ws_name))

        menu.addSeparator()

        outputs = menu.addAction("📤 Outputs")
        outputs.triggered.connect(lambda: self._show_outputs(ws_name))

        logs_menu = AsyncMenu("📜 Logs", lambda: self._load_logs(ws_name))
        logs_menu.set_item_callback(lambda d: self._show_log(ws_name, d.get('name', '')))
        menu.addMenu(logs_menu)

        return menu

    def _load_logs(self, ws_name: str) -> list:
        logs = self.local_client.list_logs(ws_name)
        return [{'text': f"📄 {log['name']}", 'data': log} for log in logs]

    def _init_workspace(self, ws_name: str):
        def do_init():
            return self.local_client.init(ws_name)
        self.process_manager.start_process(f"Init {ws_name}", f"Initializing {ws_name}", do_init)
        self.notification.emit("Initialize Started", f"Initializing {ws_name}")

    def _plan_workspace(self, ws_name: str):
        def do_plan():
            return self.local_client.plan(ws_name)
        self.process_manager.start_process(f"Plan {ws_name}", f"Planning {ws_name}", do_plan)
        self.notification.emit("Plan Started", f"Planning {ws_name}")

    def _refresh_workspace(self, ws_name: str):
        def do_refresh():
            return self.local_client.refresh(ws_name)
        self.process_manager.start_process(f"Refresh {ws_name}", f"Refreshing {ws_name}", do_refresh)
        self.notification.emit("Refresh Started", f"Refreshing {ws_name}")

    def _apply_workspace(self, ws_name: str):
        reply = QMessageBox.question(None, "Apply", f"Apply changes to {ws_name}?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        def do_apply():
            return self.local_client.apply(ws_name, auto_approve=True)
        self.process_manager.start_process(f"Apply {ws_name}", f"Applying {ws_name}", do_apply)
        self.notification.emit("Apply Started", f"Applying {ws_name}")

    def _destroy_workspace(self, ws_name: str):
        reply = QMessageBox.warning(None, "Destroy", f"⚠️ DESTROY {ws_name}?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        def do_destroy():
            return self.local_client.destroy(ws_name, auto_approve=True)
        self.process_manager.start_process(f"Destroy {ws_name}", f"Destroying {ws_name}", do_destroy)
        self.notification.emit("Destroy Started", f"Destroying {ws_name}")

    def _show_outputs(self, ws_name: str):
        result = self.local_client.output(ws_name)
        if result.get('success'):
            dialog = JsonEditorDialog(f"Outputs: {ws_name}", result.get('data', {}), readonly=True)
            dialog.exec()

    def _show_log(self, ws_name: str, log_name: str):
        content = self.local_client.read_log(ws_name, log_name)
        dialog = QDialog()
        dialog.setWindowTitle(f"Log: {log_name}")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setPlainText(content)
        text.setReadOnly(True)
        layout.addWidget(text)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()
