"""OpenTofu Menu Builder for OpenTongchi"""

from typing import Dict, Optional
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog, QTextEdit, QDialog, QVBoxLayout, QPushButton
from PySide6.QtCore import QObject, Signal
from app.clients.opentofu import OpenTofuClient, HCPTerraformClient
from app.async_menu import AsyncMenu
from app.dialogs import JsonEditorDialog


class OpenTofuMenuBuilder(QObject):
    notification = Signal(str, str)
    
    def __init__(self, settings, process_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        self._local_client: Optional[OpenTofuClient] = None
        self._hcp_client: Optional[HCPTerraformClient] = None
    
    @property
    def local_client(self) -> OpenTofuClient:
        if self._local_client is None:
            self._local_client = OpenTofuClient(self.settings.opentofu)
        return self._local_client
    
    @property
    def hcp_client(self) -> HCPTerraformClient:
        if self._hcp_client is None:
            self._hcp_client = HCPTerraformClient(self.settings.opentofu)
        return self._hcp_client
    
    def build_menu(self) -> QMenu:
        menu = QMenu("🏗️ OpenTofu")
        
        local_menu = self._create_local_menu()
        menu.addMenu(local_menu)
        menu.addSeparator()
        
        hcp_menu = self._create_hcp_menu()
        menu.addMenu(hcp_menu)
        
        return menu
    
    def _create_local_menu(self) -> QMenu:
        menu = AsyncMenu("📁 Local Workspaces", self._load_local_workspaces)
        menu.set_submenu_factory(self._create_workspace_submenu)
        return menu
    
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
    
    def _create_hcp_menu(self) -> QMenu:
        menu = QMenu("☁️ HCP Terraform")
        if not self.settings.opentofu.hcp_token:
            not_configured = menu.addAction("⚠️ Not Configured")
            not_configured.setEnabled(False)
            return menu
        
        orgs_menu = AsyncMenu("🏢 Organizations", self._load_hcp_orgs)
        orgs_menu.set_submenu_factory(self._create_hcp_org_submenu)
        menu.addMenu(orgs_menu)
        return menu
    
    def _load_hcp_orgs(self) -> list:
        response = self.hcp_client.list_organizations()
        if not response.ok:
            raise Exception(response.error or "Failed to list organizations")
        data = response.data or {}
        orgs = data.get('data', [])
        return [{'text': f"🏢 {o.get('attributes', {}).get('name', o.get('id', ''))}", 
                 'data': o, 'is_submenu': True} for o in orgs]
    
    def _create_hcp_org_submenu(self, title: str, data: Dict) -> QMenu:
        org_name = data.get('attributes', {}).get('name', data.get('id', ''))
        menu = AsyncMenu(title, lambda: self._load_hcp_workspaces(org_name))
        menu.set_submenu_factory(lambda t, d: self._create_hcp_ws_submenu(t, d))
        return menu
    
    def _load_hcp_workspaces(self, org_name: str) -> list:
        response = self.hcp_client.list_workspaces(org_name)
        if not response.ok:
            raise Exception(response.error or "Failed to list workspaces")
        data = response.data or {}
        workspaces = data.get('data', [])
        items = []
        for ws in workspaces:
            attrs = ws.get('attributes', {})
            name = attrs.get('name', 'unknown')
            locked = attrs.get('locked', False)
            emoji = self.hcp_client.get_workspace_status_emoji(ws)
            lock = '🔒' if locked else ''
            items.append({'text': f"{emoji} {lock} {name}", 'data': ws, 'is_submenu': True})
        return items
    
    def _create_hcp_ws_submenu(self, title: str, data: Dict) -> QMenu:
        ws_id = data.get('id', '')
        menu = QMenu(title)
        
        info = menu.addAction("ℹ️ Details")
        info.triggered.connect(lambda: self._show_hcp_workspace(ws_id))
        
        runs_menu = AsyncMenu("🚀 Runs", lambda: self._load_hcp_runs(ws_id))
        menu.addMenu(runs_menu)
        
        new_run = menu.addAction("▶️ Start Run")
        new_run.triggered.connect(lambda: self._start_hcp_run(ws_id))
        
        return menu
    
    def _load_hcp_runs(self, ws_id: str) -> list:
        response = self.hcp_client.list_runs(ws_id)
        if not response.ok:
            raise Exception(response.error or "Failed to list runs")
        data = response.data or {}
        runs = data.get('data', [])
        items = []
        for run in runs[:10]:
            attrs = run.get('attributes', {})
            status = attrs.get('status', 'unknown')
            emoji = self.hcp_client.get_run_status_emoji(status)
            items.append((f"{emoji} {status}", run))
        return items
    
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
    
    def _show_hcp_workspace(self, ws_id: str):
        response = self.hcp_client.get_workspace_by_id(ws_id)
        if response.ok:
            dialog = JsonEditorDialog("Workspace", response.data, readonly=True)
            dialog.exec()
    
    def _start_hcp_run(self, ws_id: str):
        response = self.hcp_client.create_run(ws_id)
        if response.ok:
            self.notification.emit("Run Started", "Plan/Apply run started")
