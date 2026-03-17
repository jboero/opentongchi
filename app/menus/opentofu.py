"""OpenTofu Menu Builder for OpenTongchi"""

from typing import Dict, Optional
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog, QTextEdit, QDialog, QVBoxLayout, QPushButton
from PySide6.QtCore import QObject, Signal
from app.clients.opentofu import OpenTofuClient, HCPTerraformClient
from app.async_menu import AsyncMenu
from app.dialogs import JsonEditorDialog, CrudDialog


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
    
    def refresh_clients(self):
        """Reset clients to pick up new settings."""
        self._local_client = None
        self._hcp_client = None
    
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
        org_id = data.get('id', '')
        menu = QMenu(title)
        
        # Organization Info/Settings
        info = menu.addAction("ℹ️ Organization Info")
        info.triggered.connect(lambda: self._show_hcp_org(org_name))
        
        settings = menu.addAction("⚙️ Organization Settings")
        settings.triggered.connect(lambda: self._show_hcp_org_settings(org_name))
        
        menu.addSeparator()
        
        # Workspaces submenu
        ws_menu = AsyncMenu("📁 Workspaces", lambda: self._load_hcp_workspaces(org_name))
        ws_menu.set_submenu_factory(self._create_hcp_ws_submenu)
        ws_menu.set_new_item_callback(lambda: self._create_hcp_workspace(org_name), "➕ New Workspace...")
        menu.addMenu(ws_menu)
        
        # Variable Sets submenu
        varsets_menu = AsyncMenu("📦 Variable Sets", lambda: self._load_hcp_varsets(org_name))
        varsets_menu.set_submenu_factory(self._create_hcp_varset_submenu)
        varsets_menu.set_new_item_callback(lambda: self._create_hcp_varset(org_name), "➕ New Variable Set...")
        menu.addMenu(varsets_menu)
        
        menu.addSeparator()
        
        # Teams submenu
        teams_menu = AsyncMenu("👥 Teams", lambda: self._load_hcp_teams(org_name))
        teams_menu.set_item_callback(self._show_hcp_team)
        menu.addMenu(teams_menu)
        
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
        attrs = data.get('attributes', {})
        ws_name = attrs.get('name', '')
        locked = attrs.get('locked', False)
        menu = QMenu(title)
        
        # Info
        info = menu.addAction("ℹ️ Workspace Details")
        info.triggered.connect(lambda: self._show_hcp_workspace(ws_id))
        
        menu.addSeparator()
        
        # Lock/Unlock
        if locked:
            unlock = menu.addAction("🔓 Unlock")
            unlock.triggered.connect(lambda: self._unlock_hcp_workspace(ws_id))
        else:
            lock = menu.addAction("🔒 Lock")
            lock.triggered.connect(lambda: self._lock_hcp_workspace(ws_id))
        
        menu.addSeparator()
        
        # Variables submenu
        vars_menu = AsyncMenu("🔐 Variables", lambda: self._load_hcp_ws_variables(ws_id))
        vars_menu.set_item_callback(lambda d: self._show_hcp_variable(d))
        vars_menu.set_new_item_callback(lambda: self._create_hcp_ws_variable(ws_id), "➕ New Variable...")
        menu.addMenu(vars_menu)
        
        # Runs submenu
        runs_menu = AsyncMenu("🚀 Runs", lambda: self._load_hcp_runs(ws_id))
        runs_menu.set_item_callback(lambda d: self._show_hcp_run(d.get('id', '')))
        menu.addMenu(runs_menu)
        
        # State versions
        state_menu = AsyncMenu("📊 State Versions", lambda: self._load_hcp_state_versions(ws_id))
        menu.addMenu(state_menu)
        
        menu.addSeparator()
        
        # Actions
        new_run = menu.addAction("▶️ Start Run")
        new_run.triggered.connect(lambda: self._start_hcp_run(ws_id))
        
        destroy_run = menu.addAction("💥 Start Destroy Run")
        destroy_run.triggered.connect(lambda: self._start_hcp_destroy_run(ws_id))
        
        menu.addSeparator()
        
        delete_ws = menu.addAction("🗑️ Delete Workspace")
        delete_ws.triggered.connect(lambda: self._delete_hcp_workspace(ws_id, ws_name))
        
        return menu
    
    def _load_hcp_varsets(self, org_name: str) -> list:
        response = self.hcp_client.list_variable_sets(org_name)
        if not response.ok:
            raise Exception(response.error or "Failed to list variable sets")
        data = response.data or {}
        varsets = data.get('data', [])
        items = []
        for vs in varsets:
            attrs = vs.get('attributes', {})
            name = attrs.get('name', 'unknown')
            is_global = attrs.get('global', False)
            icon = '🌐' if is_global else '📦'
            items.append({'text': f"{icon} {name}", 'data': vs, 'is_submenu': True})
        return items
    
    def _create_hcp_varset_submenu(self, title: str, data: Dict) -> QMenu:
        varset_id = data.get('id', '')
        attrs = data.get('attributes', {})
        varset_name = attrs.get('name', '')
        menu = QMenu(title)
        
        # Info
        info = menu.addAction("ℹ️ Variable Set Details")
        info.triggered.connect(lambda: self._show_hcp_varset(varset_id))
        
        menu.addSeparator()
        
        # Variables in this set
        vars_menu = AsyncMenu("🔐 Variables", lambda: self._load_hcp_varset_variables(varset_id))
        vars_menu.set_item_callback(lambda d: self._show_hcp_variable(d))
        vars_menu.set_new_item_callback(lambda: self._create_hcp_varset_variable(varset_id), "➕ New Variable...")
        menu.addMenu(vars_menu)
        
        # Workspaces using this set
        ws_menu = AsyncMenu("📁 Applied Workspaces", lambda: self._load_hcp_varset_workspaces(varset_id))
        menu.addMenu(ws_menu)
        
        menu.addSeparator()
        
        # Edit
        edit = menu.addAction("✏️ Edit Variable Set")
        edit.triggered.connect(lambda: self._edit_hcp_varset(varset_id, varset_name))
        
        delete = menu.addAction("🗑️ Delete Variable Set")
        delete.triggered.connect(lambda: self._delete_hcp_varset(varset_id, varset_name))
        
        return menu
    
    def _load_hcp_teams(self, org_name: str) -> list:
        response = self.hcp_client.list_teams(org_name)
        if not response.ok:
            raise Exception(response.error or "Failed to list teams")
        data = response.data or {}
        teams = data.get('data', [])
        return [(f"👥 {t.get('attributes', {}).get('name', 'unknown')}", t) for t in teams]
    
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
    
    def _load_hcp_ws_variables(self, ws_id: str) -> list:
        response = self.hcp_client.list_variables(ws_id)
        if not response.ok:
            raise Exception(response.error or "Failed to list variables")
        data = response.data or {}
        variables = data.get('data', [])
        items = []
        for var in variables:
            attrs = var.get('attributes', {})
            key = attrs.get('key', 'unknown')
            sensitive = attrs.get('sensitive', False)
            category = attrs.get('category', 'terraform')
            icon = '🔒' if sensitive else '🔓'
            cat_icon = '🌍' if category == 'env' else '📝'
            items.append((f"{icon} {cat_icon} {key}", var))
        return items
    
    def _load_hcp_varset_variables(self, varset_id: str) -> list:
        response = self.hcp_client.list_varset_variables(varset_id)
        if not response.ok:
            raise Exception(response.error or "Failed to list variables")
        data = response.data or {}
        variables = data.get('data', [])
        items = []
        for var in variables:
            attrs = var.get('attributes', {})
            key = attrs.get('key', 'unknown')
            sensitive = attrs.get('sensitive', False)
            icon = '🔒' if sensitive else '🔓'
            items.append((f"{icon} {key}", var))
        return items
    
    def _load_hcp_varset_workspaces(self, varset_id: str) -> list:
        response = self.hcp_client.list_varset_workspaces(varset_id)
        if not response.ok:
            raise Exception(response.error or "Failed to list workspaces")
        data = response.data or {}
        workspaces = data.get('data', [])
        return [(f"📁 {ws.get('attributes', {}).get('name', ws.get('id', ''))}", ws) for ws in workspaces]
    
    def _load_hcp_state_versions(self, ws_id: str) -> list:
        response = self.hcp_client.list_state_versions(ws_id)
        if not response.ok:
            raise Exception(response.error or "Failed to list state versions")
        data = response.data or {}
        versions = data.get('data', [])
        items = []
        for v in versions[:10]:
            attrs = v.get('attributes', {})
            serial = attrs.get('serial', 0)
            created = attrs.get('created-at', '')[:10]
            items.append((f"📊 v{serial} ({created})", v))
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
        message, ok = QInputDialog.getText(None, "Start Run", "Run message (optional):")
        if ok:
            response = self.hcp_client.create_run(ws_id, message=message if message else None)
            if response.ok:
                self.notification.emit("Run Started", "Plan/Apply run started")
            else:
                QMessageBox.warning(None, "Error", f"Failed to start run: {response.error}")
    
    def _start_hcp_destroy_run(self, ws_id: str):
        reply = QMessageBox.warning(
            None, "Destroy Run",
            "⚠️ Start a DESTROY run? This will destroy all resources!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            response = self.hcp_client.create_run(ws_id, is_destroy=True)
            if response.ok:
                self.notification.emit("Destroy Run Started", "Destroy run started")
    
    def _show_hcp_run(self, run_id: str):
        response = self.hcp_client.get_run(run_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Run: {run_id[:8]}...", response.data, readonly=True)
            dialog.exec()
    
    def _lock_hcp_workspace(self, ws_id: str):
        reason, ok = QInputDialog.getText(None, "Lock Workspace", "Lock reason:")
        if ok:
            response = self.hcp_client.lock_workspace(ws_id, reason)
            if response.ok:
                self.notification.emit("Workspace Locked", "Workspace locked")
    
    def _unlock_hcp_workspace(self, ws_id: str):
        response = self.hcp_client.unlock_workspace(ws_id)
        if response.ok:
            self.notification.emit("Workspace Unlocked", "Workspace unlocked")
    
    def _create_hcp_workspace(self, org_name: str):
        name, ok = QInputDialog.getText(None, "New Workspace", "Workspace name:")
        if ok and name:
            dialog = CrudDialog("New Workspace", {
                'name': name,
                'description': '',
                'auto_apply': False
            })
            if dialog.exec():
                data = dialog.data
                response = self.hcp_client.create_workspace(
                    name=data.get('name', name),
                    org_name=org_name,
                    description=data.get('description'),
                    auto_apply=data.get('auto_apply', False)
                )
                if response.ok:
                    self.notification.emit("Workspace Created", f"Workspace {name} created")
                else:
                    QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _delete_hcp_workspace(self, ws_id: str, ws_name: str):
        reply = QMessageBox.warning(
            None, "Delete Workspace",
            f"⚠️ Delete workspace '{ws_name}'?\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Get org name from workspace first
            ws_response = self.hcp_client.get_workspace_by_id(ws_id)
            if ws_response.ok:
                org_name = ws_response.data.get('data', {}).get('relationships', {}).get(
                    'organization', {}).get('data', {}).get('id', '')
                response = self.hcp_client.delete_workspace(ws_name, org_name)
                if response.ok:
                    self.notification.emit("Workspace Deleted", f"Workspace {ws_name} deleted")
    
    def _show_hcp_org(self, org_name: str):
        response = self.hcp_client.get_organization(org_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Organization: {org_name}", response.data, readonly=True)
            dialog.exec()
    
    def _show_hcp_org_settings(self, org_name: str):
        response = self.hcp_client.get_organization(org_name)
        if response.ok:
            attrs = response.data.get('data', {}).get('attributes', {})
            dialog = CrudDialog(f"Organization Settings: {org_name}", {
                'name': attrs.get('name', ''),
                'email': attrs.get('email', ''),
                'collaborator_auth_policy': attrs.get('collaborator-auth-policy', 'password'),
                'cost_estimation_enabled': attrs.get('cost-estimation-enabled', False),
                'two_factor_conformant': attrs.get('two-factor-conformant', False),
            })
            if dialog.exec():
                data = dialog.data
                update_response = self.hcp_client.update_organization(
                    org_name,
                    email=data.get('email'),
                    collaborator_auth_policy=data.get('collaborator_auth_policy')
                )
                if update_response.ok:
                    self.notification.emit("Settings Updated", "Organization settings updated")
    
    def _show_hcp_team(self, team: Dict):
        team_id = team.get('id', '')
        response = self.hcp_client.get_team(team_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Team", response.data, readonly=True)
            dialog.exec()
    
    # Variable Set handlers
    def _show_hcp_varset(self, varset_id: str):
        response = self.hcp_client.get_variable_set(varset_id)
        if response.ok:
            dialog = JsonEditorDialog("Variable Set", response.data, readonly=True)
            dialog.exec()
    
    def _create_hcp_varset(self, org_name: str):
        name, ok = QInputDialog.getText(None, "New Variable Set", "Variable set name:")
        if ok and name:
            dialog = CrudDialog("New Variable Set", {
                'name': name,
                'description': '',
                'global': False
            })
            if dialog.exec():
                data = dialog.data
                response = self.hcp_client.create_variable_set(
                    name=data.get('name', name),
                    org_name=org_name,
                    description=data.get('description'),
                    global_set=data.get('global', False)
                )
                if response.ok:
                    self.notification.emit("Variable Set Created", f"Variable set {name} created")
                else:
                    QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _edit_hcp_varset(self, varset_id: str, varset_name: str):
        response = self.hcp_client.get_variable_set(varset_id)
        if response.ok:
            attrs = response.data.get('data', {}).get('attributes', {})
            dialog = CrudDialog(f"Edit Variable Set: {varset_name}", {
                'name': attrs.get('name', ''),
                'description': attrs.get('description', ''),
                'global': attrs.get('global', False)
            })
            if dialog.exec():
                data = dialog.data
                update_response = self.hcp_client.update_variable_set(
                    varset_id,
                    name=data.get('name'),
                    description=data.get('description'),
                    global_set=data.get('global')
                )
                if update_response.ok:
                    self.notification.emit("Variable Set Updated", f"Variable set updated")
    
    def _delete_hcp_varset(self, varset_id: str, varset_name: str):
        reply = QMessageBox.warning(
            None, "Delete Variable Set",
            f"Delete variable set '{varset_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            response = self.hcp_client.delete_variable_set(varset_id)
            if response.ok:
                self.notification.emit("Variable Set Deleted", f"Variable set deleted")
    
    # Variable handlers
    def _show_hcp_variable(self, var: Dict):
        attrs = var.get('attributes', {})
        key = attrs.get('key', 'unknown')
        sensitive = attrs.get('sensitive', False)
        
        display_data = {
            'key': key,
            'value': '(sensitive)' if sensitive else attrs.get('value', ''),
            'category': attrs.get('category', 'terraform'),
            'sensitive': sensitive,
            'hcl': attrs.get('hcl', False),
            'description': attrs.get('description', '')
        }
        
        dialog = JsonEditorDialog(f"Variable: {key}", display_data, readonly=True)
        dialog.exec()
    
    def _create_hcp_ws_variable(self, ws_id: str):
        dialog = CrudDialog("New Variable", {
            'key': '',
            'value': '',
            'category': 'terraform',
            'sensitive': False,
            'hcl': False
        })
        if dialog.exec():
            data = dialog.data
            response = self.hcp_client.create_variable(
                ws_id,
                key=data.get('key', ''),
                value=data.get('value', ''),
                category=data.get('category', 'terraform'),
                sensitive=data.get('sensitive', False),
                hcl=data.get('hcl', False)
            )
            if response.ok:
                self.notification.emit("Variable Created", f"Variable {data.get('key')} created")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _create_hcp_varset_variable(self, varset_id: str):
        dialog = CrudDialog("New Variable", {
            'key': '',
            'value': '',
            'category': 'terraform',
            'sensitive': False,
            'hcl': False
        })
        if dialog.exec():
            data = dialog.data
            response = self.hcp_client.create_varset_variable(
                varset_id,
                key=data.get('key', ''),
                value=data.get('value', ''),
                category=data.get('category', 'terraform'),
                sensitive=data.get('sensitive', False),
                hcl=data.get('hcl', False)
            )
            if response.ok:
                self.notification.emit("Variable Created", f"Variable {data.get('key')} created")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
