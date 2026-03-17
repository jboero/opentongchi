"""Boundary Menu Builder for OpenTongchi"""

from typing import Dict, Optional, List
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog
from PySide6.QtCore import QObject, Signal
from app.clients.boundary import BoundaryClient
from app.async_menu import AsyncMenu
from app.dialogs import JsonEditorDialog


class BoundaryMenuBuilder(QObject):
    notification = Signal(str, str)
    
    def __init__(self, settings, process_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        self._client: Optional[BoundaryClient] = None
    
    @property
    def client(self) -> BoundaryClient:
        if self._client is None:
            self._client = BoundaryClient(self.settings.boundary)
        return self._client
    
    def refresh_client(self):
        """Force recreation of client with fresh settings."""
        self._client = None
    
    def build_menu(self) -> QMenu:
        # Always refresh client to pick up any settings changes
        self.refresh_client()
        
        menu = QMenu("🚪 Boundary")
        
        if not self.settings.boundary.address:
            not_configured = menu.addAction("⚠️ Not Configured")
            not_configured.setEnabled(False)
            return menu
        
        self._add_status_menu(menu)
        menu.addSeparator()
        
        # === Main Navigation (matching web UI) ===
        
        # Orgs (scope tree)
        orgs_menu = self._create_orgs_menu()
        menu.addMenu(orgs_menu)
        
        # Aliases
        aliases_menu = self._create_aliases_menu()
        menu.addMenu(aliases_menu)
        
        # Workers
        workers_menu = self._create_workers_menu()
        menu.addMenu(workers_menu)
        
        menu.addSeparator()
        
        # === Global IAM ===
        iam_menu = self._create_global_iam_menu()
        menu.addMenu(iam_menu)
        
        menu.addSeparator()
        
        # === Quick Access ===
        
        # All Targets (recursive, across all scopes)
        targets_menu = self._create_all_targets_menu()
        menu.addMenu(targets_menu)
        
        # Sessions (recursive)
        sessions_menu = self._create_sessions_menu()
        menu.addMenu(sessions_menu)
        
        # Active Connections (local proxy processes)
        connections_menu = self._create_connections_menu()
        menu.addMenu(connections_menu)
        
        return menu
    
    def _add_status_menu(self, menu: QMenu):
        try:
            # This will trigger authentication if needed
            healthy = self.client.is_healthy()
            
            if healthy:
                status = menu.addAction("🟢 Connected")
                status.setEnabled(False)
                
                if self.client.token:
                    auth_info = menu.addAction(f"🔑 Authenticated")
                    auth_info.setEnabled(False)
            else:
                # Check if there's an auth error
                auth_error = self.client.get_auth_error()
                if auth_error:
                    status = menu.addAction("🔴 Auth Failed")
                    status.setEnabled(False)
                    
                    # Show error details (truncated)
                    error_text = auth_error[:50] + "..." if len(auth_error) > 50 else auth_error
                    error_action = menu.addAction(f"⚠️ {error_text}")
                    error_action.setEnabled(False)
                    
                    # Add retry option
                    retry = menu.addAction("🔄 Retry Authentication")
                    retry.triggered.connect(self._retry_auth)
                else:
                    status = menu.addAction("🔴 Disconnected")
                    status.setEnabled(False)
        except Exception as e:
            status = menu.addAction(f"⚪ Error: {str(e)[:30]}")
            status.setEnabled(False)
    
    def _retry_auth(self):
        """Reset auth state and retry."""
        self.client.reset_auth()
        self.refresh_client()
        self.notification.emit("Retrying", "Attempting to authenticate...")
    
    # ==================== Organization/Scope Tree ====================
    
    def _create_orgs_menu(self) -> QMenu:
        """Create the main org/scope hierarchy menu."""
        menu = AsyncMenu("🏢 Organizations", self._load_orgs)
        menu.set_submenu_factory(self._create_org_submenu)
        return menu
    
    def _load_orgs(self) -> list:
        """Load organizations (scopes under global) with New option."""
        items = [{'text': "➕ New Organization...", 'data': {'_action': 'new_org'}, 'is_submenu': False}]
        
        result = self.client.scope_list(scope_id='global')
        if result.get('success'):
            data = result.get('data') or {}
            scopes = data.get('items') or []
            
            for scope in scopes:
                scope_id = scope.get('id', '')
                name = scope.get('name', scope_id)
                scope_type = scope.get('type', '')
                
                # Orgs have type 'org'
                emoji = '🏢' if scope_type == 'org' else '📂'
                
                items.append({
                    'text': f"{emoji} {name}",
                    'data': scope,
                    'is_submenu': True
                })
        
        if len(items) == 1:
            items.append({
                'text': "(No organizations yet)",
                'data': None,
                'is_submenu': False,
                'enabled': False
            })
        
        return items
    
    def _create_org_submenu(self, title: str, data: Dict) -> QMenu:
        """Create submenu for an organization showing its projects."""
        if data is None:
            menu = QMenu(title)
            menu.setEnabled(False)
            return menu
        
        # Handle "New Organization" action
        if data.get('_action') == 'new_org':
            self._create_new_org()
            menu = QMenu(title)
            return menu
        
        org_id = data.get('id', '')
        org_name = data.get('name', org_id)
        menu = QMenu(title)
        
        # Org details
        info = menu.addAction("ℹ️ Organization Details")
        info.triggered.connect(lambda: self._show_scope_details(data))
        
        menu.addSeparator()
        
        # Projects submenu (scopes under this org)
        projects_menu = AsyncMenu("📁 Projects", lambda: self._load_projects_with_new(org_id))
        projects_menu.set_submenu_factory(lambda t, d: self._create_project_submenu(t, d, org_id))
        menu.addMenu(projects_menu)
        
        # Targets in this org (recursive)
        targets_menu = AsyncMenu("🎯 All Targets", lambda: self._load_targets(org_id))
        targets_menu.set_submenu_factory(self._create_target_submenu)
        menu.addMenu(targets_menu)
        
        # Sessions in this org
        sessions_menu = AsyncMenu("📋 All Sessions", lambda: self._load_sessions(org_id))
        sessions_menu.set_submenu_factory(self._create_session_submenu)
        menu.addMenu(sessions_menu)
        
        menu.addSeparator()
        
        # Users in this org
        users_menu = AsyncMenu("👥 Users", lambda: self._load_users_with_new(org_id))
        users_menu.set_item_callback(self._on_user_item_clicked)
        menu.addMenu(users_menu)
        
        # Groups in this org
        groups_menu = AsyncMenu("👪 Groups", lambda: self._load_groups_with_new(org_id))
        groups_menu.set_item_callback(self._on_group_item_clicked)
        menu.addMenu(groups_menu)
        
        # Roles in this org
        roles_menu = AsyncMenu("🔐 Roles", lambda: self._load_roles_with_new(org_id))
        roles_menu.set_item_callback(self._on_role_item_clicked)
        menu.addMenu(roles_menu)
        
        return menu
    
    def _load_projects_with_new(self, org_id: str) -> list:
        """Load projects (scopes under an org) with New option."""
        items = [{'text': "➕ New Project...", 'data': {'_action': 'new_project', 'org_id': org_id}, 'is_submenu': False}]
        
        result = self.client.scope_list(scope_id=org_id)
        if result.get('success'):
            data = result.get('data') or {}
            scopes = data.get('items') or []
            
            for scope in scopes:
                scope_id = scope.get('id', '')
                name = scope.get('name', scope_id)
                
                items.append({
                    'text': f"📁 {name}",
                    'data': scope,
                    'is_submenu': True
                })
        
        if len(items) == 1:
            items.append({
                'text': "(No projects yet)",
                'data': None,
                'is_submenu': False,
                'enabled': False
            })
        
        return items
    
    def _load_projects(self, org_id: str) -> list:
        """Load projects (scopes under an org)."""
        result = self.client.scope_list(scope_id=org_id)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list projects'))
        
        data = result.get('data') or {}
        scopes = data.get('items') or []
        items = []
        
        for scope in scopes:
            scope_id = scope.get('id', '')
            name = scope.get('name', scope_id)
            
            items.append({
                'text': f"📁 {name}",
                'data': scope,
                'is_submenu': True
            })
        
        if not items:
            items.append({
                'text': "(No projects)",
                'data': None,
                'is_submenu': False,
                'enabled': False
            })
        
        return items
    
    def _create_project_submenu(self, title: str, data: Dict, org_id: str = None) -> QMenu:
        """Create submenu for a project showing its targets, sessions, etc."""
        if data is None:
            menu = QMenu(title)
            menu.setEnabled(False)
            return menu
        
        # Handle "New Project" action
        if data.get('_action') == 'new_project':
            self._create_new_project(data.get('org_id', 'global'))
            menu = QMenu(title)
            return menu
        
        project_id = data.get('id', '')
        menu = QMenu(title)
        
        # Project details
        info = menu.addAction("ℹ️ Project Details")
        info.triggered.connect(lambda: self._show_scope_details(data))
        
        menu.addSeparator()
        
        # Targets in this project
        targets_menu = AsyncMenu("🎯 Targets", lambda: self._load_targets(project_id))
        targets_menu.set_submenu_factory(self._create_target_submenu)
        menu.addMenu(targets_menu)
        
        # Sessions in this project
        sessions_menu = AsyncMenu("📋 Sessions", lambda: self._load_sessions(project_id))
        sessions_menu.set_submenu_factory(self._create_session_submenu)
        menu.addMenu(sessions_menu)
        
        menu.addSeparator()
        
        # Host Catalogs
        host_catalogs_menu = AsyncMenu("🖥️ Host Catalogs", lambda: self._load_host_catalogs(project_id))
        host_catalogs_menu.set_submenu_factory(self._create_host_catalog_submenu)
        menu.addMenu(host_catalogs_menu)
        
        # Credential Stores
        cred_stores_menu = AsyncMenu("🔐 Credential Stores", lambda: self._load_credential_stores(project_id))
        cred_stores_menu.set_item_callback(self._show_credential_store_details)
        menu.addMenu(cred_stores_menu)
        
        return menu
    
    # ==================== Targets ====================
    
    def _create_all_targets_menu(self) -> QMenu:
        """All targets across all scopes."""
        menu = AsyncMenu("🎯 All Targets", lambda: self._load_targets(None))
        menu.set_submenu_factory(self._create_target_submenu)
        return menu
    
    def _load_targets(self, scope_id: str = None) -> list:
        result = self.client.target_list(scope_id=scope_id, recursive=True)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list targets'))
        
        data = result.get('data', {})
        targets = data.get('items', []) if isinstance(data, dict) else []
        data = result.get('data') or {}
        targets = data.get('items') or []
        items = []
        
        for target in targets:
            target_id = target.get('id', '')
            name = target.get('name', 'unnamed')
            target_type = target.get('type', '')
            scope_info = target.get('scope') or {}
            scope_name = scope_info.get('name', '')
            
            # Check if connected
            connected = self.client.is_connected(target_id)
            emoji = '🟢' if connected else '⚪'
            lock = '🔓' if connected else '🔒'
            
            display = f"{emoji} {lock} {name}"
            if scope_name:
                display += f" [{scope_name}]"
            if target_type:
                display += f" ({target_type})"
            
            items.append({
                'text': display,
                'data': target,
                'is_submenu': True
            })
        
        if not items:
            items.append({
                'text': "(No targets)",
                'data': None,
                'is_submenu': False,
                'enabled': False
            })
        
        return items
    
    def _create_target_submenu(self, title: str, data: Dict) -> QMenu:
        if data is None:
            menu = QMenu(title)
            menu.setEnabled(False)
            return menu
        
        target_id = data.get('id', '')
        menu = QMenu(title)
        
        # Info
        info = menu.addAction("ℹ️ Target Details")
        info.triggered.connect(lambda: self._show_target(target_id))
        
        menu.addSeparator()
        
        # Connection actions
        if self.client.is_connected(target_id):
            disconnect = menu.addAction("🔌 Disconnect")
            disconnect.triggered.connect(lambda: self._disconnect_target(target_id))
        else:
            connect = menu.addAction("🔗 Connect")
            connect.triggered.connect(lambda: self._connect_target(target_id))
        
        # Connect with custom port
        connect_port = menu.addAction("🔗 Connect (Custom Port)...")
        connect_port.triggered.connect(lambda: self._connect_target_custom_port(target_id))
        
        return menu
    
    # ==================== Sessions ====================
    
    def _create_sessions_menu(self) -> QMenu:
        menu = AsyncMenu("📋 Sessions", lambda: self._load_sessions(None))
        menu.set_submenu_factory(self._create_session_submenu)
        return menu
    
    def _load_sessions(self, scope_id: str = None) -> list:
        result = self.client.session_list(scope_id=scope_id, recursive=True)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list sessions'))
        
        data = result.get('data') or {}
        sessions = data.get('items') or []
        items = []
        
        for session in sessions:
            session_id = session.get('id', '')
            status = session.get('status', '')
            target_id = session.get('target_id', '')[:8] if session.get('target_id') else ''
            
            emoji = {'active': '🟢', 'pending': '🟡', 'canceling': '🟠'}.get(status, '⚪')
            
            items.append({
                'text': f"{emoji} {session_id[:12]}... → {target_id}... ({status})",
                'data': session,
                'is_submenu': True
            })
        
        if not items:
            items.append({
                'text': "(No active sessions)",
                'data': None,
                'is_submenu': False,
                'enabled': False
            })
        
        return items
    
    def _create_session_submenu(self, title: str, data: Dict) -> QMenu:
        if data is None:
            menu = QMenu(title)
            menu.setEnabled(False)
            return menu
        
        session_id = data.get('id', '')
        menu = QMenu(title)
        
        info = menu.addAction("ℹ️ Session Details")
        info.triggered.connect(lambda: self._show_session(session_id))
        
        menu.addSeparator()
        
        cancel = menu.addAction("🚫 Cancel Session")
        cancel.triggered.connect(lambda: self._cancel_session(session_id))
        
        return menu
    
    # ==================== Connections ====================
    
    def _create_connections_menu(self) -> QMenu:
        menu = QMenu("🔌 Active Connections")
        
        active = self.client.get_active_connections()
        
        if not active:
            no_conn = menu.addAction("(No active connections)")
            no_conn.setEnabled(False)
        else:
            for target_id in active:
                action = menu.addAction(f"🟢 {target_id[:16]}...")
                action.triggered.connect(lambda checked, tid=target_id: self._disconnect_target(tid))
        
        menu.addSeparator()
        
        disconnect_all = menu.addAction("🔌 Disconnect All")
        disconnect_all.triggered.connect(self._disconnect_all)
        disconnect_all.setEnabled(len(active) > 0)
        
        return menu
    
    # ==================== Aliases ====================
    
    def _create_aliases_menu(self) -> QMenu:
        menu = AsyncMenu("🔗 Aliases", self._load_aliases_with_new)
        menu.set_item_callback(self._on_alias_item_clicked)
        return menu
    
    def _load_aliases_with_new(self) -> list:
        items = [("➕ New Alias...", {'_action': 'new_alias'})]
        
        result = self.client.alias_list(scope_id='global')
        if result.get('success'):
            data = result.get('data') or {}
            aliases = data.get('items') or []
            
            for alias in aliases:
                alias_id = alias.get('id', '')
                value = alias.get('value', alias_id)
                alias_type = alias.get('type', '')
                dest_id = alias.get('destination_id', '')[:8] if alias.get('destination_id') else ''
                
                display = f"🔗 {value}"
                if dest_id:
                    display += f" → {dest_id}..."
                if alias_type:
                    display += f" ({alias_type})"
                
                items.append((display, alias))
        
        if len(items) == 1:
            items.append(("(No aliases yet)", None))
        
        return items
    
    def _on_alias_item_clicked(self, data: Dict):
        if data is None:
            return
        if data.get('_action') == 'new_alias':
            self._create_new_alias()
        else:
            self._show_alias_details(data)
    
    def _show_alias_details(self, alias: Dict):
        if alias is None:
            return
        value = alias.get('value', alias.get('id', 'unknown'))
        dialog = JsonEditorDialog(f"Alias: {value}", alias, readonly=True)
        dialog.exec()
    
    # ==================== Workers ====================
    
    def _create_workers_menu(self) -> QMenu:
        menu = AsyncMenu("⚙️ Workers", self._load_workers)
        menu.set_submenu_factory(self._create_worker_submenu)
        return menu
    
    def _load_workers(self) -> list:
        result = self.client.worker_list(scope_id='global')
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list workers'))
        
        data = result.get('data', {})
        workers = data.get('items', []) if isinstance(data, dict) else []
        
        items = []
        for worker in workers:
            worker_id = worker.get('id', '')
            name = worker.get('name', worker_id)
            worker_type = worker.get('type', '')
            address = worker.get('address', '')
            
            # Check worker status
            last_status = worker.get('last_status_time', '')
            active_conn_count = worker.get('active_connection_count', 0)
            
            # Status emoji based on connection count or status
            if active_conn_count > 0:
                emoji = '🟢'
            elif last_status:
                emoji = '🟡'
            else:
                emoji = '⚪'
            
            display = f"{emoji} {name}"
            if worker_type:
                display += f" ({worker_type})"
            if address:
                display += f" @ {address}"
            
            items.append({
                'text': display,
                'data': worker,
                'is_submenu': True
            })
        
        if not items:
            items.append({
                'text': "(No workers)",
                'data': None,
                'is_submenu': False,
                'enabled': False
            })
        
        return items
    
    def _create_worker_submenu(self, title: str, data: Dict) -> QMenu:
        if data is None:
            menu = QMenu(title)
            menu.setEnabled(False)
            return menu
        
        worker_id = data.get('id', '')
        menu = QMenu(title)
        
        # Worker details
        info = menu.addAction("ℹ️ Worker Details")
        info.triggered.connect(lambda: self._show_worker_details(data))
        
        menu.addSeparator()
        
        # Show some quick info
        address = data.get('address', 'N/A')
        addr_action = menu.addAction(f"📍 Address: {address}")
        addr_action.setEnabled(False)
        
        conn_count = data.get('active_connection_count', 0)
        conn_action = menu.addAction(f"🔌 Active Connections: {conn_count}")
        conn_action.setEnabled(False)
        
        return menu
    
    def _show_worker_details(self, worker: Dict):
        if worker is None:
            return
        name = worker.get('name', worker.get('id', 'unknown'))
        dialog = JsonEditorDialog(f"Worker: {name}", worker, readonly=True)
        dialog.exec()
    
    # ==================== Global IAM ====================
    
    def _create_global_iam_menu(self) -> QMenu:
        """Create Global IAM menu matching web UI structure."""
        menu = QMenu("🛡️ Global IAM")
        
        # Users
        users_menu = AsyncMenu("👥 Users", lambda: self._load_users_with_new('global'))
        users_menu.set_item_callback(self._on_user_item_clicked)
        menu.addMenu(users_menu)
        
        # Groups
        groups_menu = AsyncMenu("👪 Groups", lambda: self._load_groups_with_new('global'))
        groups_menu.set_item_callback(self._on_group_item_clicked)
        menu.addMenu(groups_menu)
        
        # Roles
        roles_menu = AsyncMenu("🔐 Roles", lambda: self._load_roles_with_new('global'))
        roles_menu.set_item_callback(self._on_role_item_clicked)
        menu.addMenu(roles_menu)
        
        menu.addSeparator()
        
        # Auth Methods
        auth_menu = AsyncMenu("🔑 Auth Methods", self._load_auth_methods)
        auth_menu.set_item_callback(self._show_auth_method_details)
        menu.addMenu(auth_menu)
        
        return menu
    
    # ==================== Auth Methods ====================
    
    def _load_auth_methods(self) -> list:
        result = self.client.auth_method_list(scope_id='global')
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list auth methods'))
        
        data = result.get('data', {})
        methods = data.get('items', []) if isinstance(data, dict) else []
        
        items = []
        for method in methods:
            method_id = method.get('id', '')
            name = method.get('name', method_id)
            method_type = method.get('type', '')
            
            emoji = {'password': '🔑', 'oidc': '🌐', 'ldap': '📁'}.get(method_type, '🔐')
            items.append((f"{emoji} {name} ({method_type})", method))
        
        return items if items else [("(No auth methods)", None)]
    
    # ==================== Users, Groups, Roles ====================
    
    def _load_users(self, scope_id: str = 'global') -> list:
        result = self.client.user_list(scope_id=scope_id)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list users'))
        
        data = result.get('data') or {}
        users = data.get('items') or []
        
        items = [(f"👤 {u.get('name', u.get('id', 'unknown'))}", u) for u in users]
        return items if items else [("(No users)", None)]
    
    def _load_users_with_new(self, scope_id: str = 'global') -> list:
        """Load users with a New User option at the top."""
        items = [("➕ New User...", {'_action': 'new_user', 'scope_id': scope_id})]
        
        result = self.client.user_list(scope_id=scope_id)
        if result.get('success'):
            data = result.get('data') or {}
            users = data.get('items') or []
            for u in users:
                items.append((f"👤 {u.get('name', u.get('id', 'unknown'))}", u))
        
        if len(items) == 1:
            items.append(("(No users yet)", None))
        
        return items
    
    def _on_user_item_clicked(self, data: Dict):
        if data is None:
            return
        if data.get('_action') == 'new_user':
            self._create_new_user(data.get('scope_id', 'global'))
        else:
            self._show_user_details(data)
    
    def _load_groups(self, scope_id: str = 'global') -> list:
        result = self.client.group_list(scope_id=scope_id)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list groups'))
        
        data = result.get('data') or {}
        groups = data.get('items') or []
        
        items = [(f"👪 {g.get('name', g.get('id', 'unknown'))}", g) for g in groups]
        return items if items else [("(No groups)", None)]
    
    def _load_groups_with_new(self, scope_id: str = 'global') -> list:
        """Load groups with a New Group option at the top."""
        items = [("➕ New Group...", {'_action': 'new_group', 'scope_id': scope_id})]
        
        result = self.client.group_list(scope_id=scope_id)
        if result.get('success'):
            data = result.get('data') or {}
            groups = data.get('items') or []
            for g in groups:
                items.append((f"👪 {g.get('name', g.get('id', 'unknown'))}", g))
        
        if len(items) == 1:
            items.append(("(No groups yet)", None))
        
        return items
    
    def _on_group_item_clicked(self, data: Dict):
        if data is None:
            return
        if data.get('_action') == 'new_group':
            self._create_new_group(data.get('scope_id', 'global'))
        else:
            self._show_group_details(data)
    
    def _load_roles(self, scope_id: str = 'global') -> list:
        result = self.client.role_list(scope_id=scope_id)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list roles'))
        
        data = result.get('data') or {}
        roles = data.get('items') or []
        
        items = [(f"🔐 {r.get('name', r.get('id', 'unknown'))}", r) for r in roles]
        return items if items else [("(No roles)", None)]
    
    def _load_roles_with_new(self, scope_id: str = 'global') -> list:
        """Load roles with a New Role option at the top."""
        items = [("➕ New Role...", {'_action': 'new_role', 'scope_id': scope_id})]
        
        result = self.client.role_list(scope_id=scope_id)
        if result.get('success'):
            data = result.get('data') or {}
            roles = data.get('items') or []
            for r in roles:
                items.append((f"🔐 {r.get('name', r.get('id', 'unknown'))}", r))
        
        if len(items) == 1:
            items.append(("(No roles yet)", None))
        
        return items
    
    def _on_role_item_clicked(self, data: Dict):
        if data is None:
            return
        if data.get('_action') == 'new_role':
            self._create_new_role(data.get('scope_id', 'global'))
        else:
            self._show_role_details(data)
    
    # ==================== Host Catalogs ====================
    
    def _load_host_catalogs(self, scope_id: str) -> list:
        result = self.client.host_catalog_list(scope_id=scope_id)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list host catalogs'))
        
        data = result.get('data', {})
        catalogs = data.get('items', []) if isinstance(data, dict) else []
        items = []
        
        for catalog in catalogs:
            catalog_id = catalog.get('id', '')
            name = catalog.get('name', catalog_id)
            catalog_type = catalog.get('type', '')
            
            items.append({
                'text': f"🖥️ {name} ({catalog_type})",
                'data': catalog,
                'is_submenu': True
            })
        
        return items if items else [{'text': "(No host catalogs)", 'data': None, 'is_submenu': False, 'enabled': False}]
    
    def _create_host_catalog_submenu(self, title: str, data: Dict) -> QMenu:
        if data is None:
            menu = QMenu(title)
            menu.setEnabled(False)
            return menu
        
        catalog_id = data.get('id', '')
        menu = QMenu(title)
        
        info = menu.addAction("ℹ️ Catalog Details")
        info.triggered.connect(lambda: self._show_json_dialog("Host Catalog", data))
        
        menu.addSeparator()
        
        # Host Sets
        host_sets_menu = AsyncMenu("📦 Host Sets", lambda: self._load_host_sets(catalog_id))
        host_sets_menu.set_item_callback(lambda d: self._show_json_dialog("Host Set", d))
        menu.addMenu(host_sets_menu)
        
        # Hosts
        hosts_menu = AsyncMenu("🖥️ Hosts", lambda: self._load_hosts(catalog_id))
        hosts_menu.set_item_callback(lambda d: self._show_json_dialog("Host", d))
        menu.addMenu(hosts_menu)
        
        return menu
    
    def _load_host_sets(self, catalog_id: str) -> list:
        result = self.client.host_set_list(catalog_id)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list host sets'))
        
        data = result.get('data', {})
        sets = data.get('items', []) if isinstance(data, dict) else []
        
        return [(f"📦 {s.get('name', s.get('id', 'unknown'))}", s) for s in sets] or [("(No host sets)", None)]
    
    def _load_hosts(self, catalog_id: str) -> list:
        result = self.client.host_list(catalog_id)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list hosts'))
        
        data = result.get('data', {})
        hosts = data.get('items', []) if isinstance(data, dict) else []
        
        return [(f"🖥️ {h.get('name', h.get('address', h.get('id', 'unknown')))}", h) for h in hosts] or [("(No hosts)", None)]
    
    # ==================== Credential Stores ====================
    
    def _load_credential_stores(self, scope_id: str) -> list:
        result = self.client.credential_store_list(scope_id=scope_id)
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list credential stores'))
        
        data = result.get('data', {})
        stores = data.get('items', []) if isinstance(data, dict) else []
        
        return [(f"🔐 {s.get('name', s.get('id', 'unknown'))}", s) for s in stores] or [("(No credential stores)", None)]
    
    # ==================== Action handlers ====================
    
    def _show_target(self, target_id: str):
        result = self.client.target_read(target_id)
        if result.get('success'):
            dialog = JsonEditorDialog(f"Target: {target_id[:16]}...", result.get('data'), readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", result.get('error', 'Failed to read target'))
    
    def _connect_target(self, target_id: str):
        try:
            process = self.client.connect(target_id)
            
            # Register with process manager so it shows up in global process list
            self.process_manager.register_external_process(
                name=f"Boundary: {target_id[:12]}...",
                description=f"Connection to target {target_id}",
                process=process,
                on_cancel=lambda tid=target_id: self._disconnect_target(tid)
            )
            
            self.notification.emit("Connecting", f"Establishing connection to {target_id[:16]}...")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to connect: {e}")
    
    def _connect_target_custom_port(self, target_id: str):
        port, ok = QInputDialog.getInt(None, "Custom Port", "Listen port:", 0, 0, 65535)
        if ok:
            try:
                process = self.client.connect(target_id, listen_port=port if port > 0 else None)
                
                # Register with process manager
                self.process_manager.register_external_process(
                    name=f"Boundary: {target_id[:12]}... (port {port})",
                    description=f"Connection to target {target_id} on port {port}",
                    process=process,
                    on_cancel=lambda tid=target_id: self._disconnect_target(tid)
                )
                
                self.notification.emit("Connected", f"Connected on port {port}")
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to connect: {e}")
    
    def _disconnect_target(self, target_id: str):
        if self.client.disconnect(target_id):
            self.notification.emit("Disconnected", f"Disconnected from {target_id[:16]}...")
    
    def _disconnect_all(self):
        active = self.client.get_active_connections()
        for target_id in active:
            self.client.disconnect(target_id)
        self.notification.emit("Disconnected", f"Disconnected {len(active)} connections")
    
    def _show_session(self, session_id: str):
        result = self.client.session_read(session_id)
        if result.get('success'):
            dialog = JsonEditorDialog(f"Session: {session_id[:16]}...", result.get('data'), readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", result.get('error', 'Failed to read session'))
    
    def _cancel_session(self, session_id: str):
        result = self.client.session_cancel(session_id)
        if result.get('success'):
            self.notification.emit("Session Cancelled", f"Session {session_id[:12]}... cancelled")
        else:
            QMessageBox.warning(None, "Error", result.get('error', 'Failed to cancel session'))
    
    def _show_scope_details(self, scope: Dict):
        name = scope.get('name', scope.get('id', 'unknown'))
        dialog = JsonEditorDialog(f"Scope: {name}", scope, readonly=True)
        dialog.exec()
    
    def _show_user_details(self, user: Dict):
        if user is None:
            return
        name = user.get('name', user.get('id', 'unknown'))
        dialog = JsonEditorDialog(f"User: {name}", user, readonly=True)
        dialog.exec()
    
    def _show_group_details(self, group: Dict):
        if group is None:
            return
        name = group.get('name', group.get('id', 'unknown'))
        dialog = JsonEditorDialog(f"Group: {name}", group, readonly=True)
        dialog.exec()
    
    def _show_role_details(self, role: Dict):
        if role is None:
            return
        name = role.get('name', role.get('id', 'unknown'))
        dialog = JsonEditorDialog(f"Role: {name}", role, readonly=True)
        dialog.exec()
    
    def _show_auth_method_details(self, method: Dict):
        if method is None:
            return
        name = method.get('name', method.get('id', 'unknown'))
        dialog = JsonEditorDialog(f"Auth Method: {name}", method, readonly=True)
        dialog.exec()
    
    def _show_credential_store_details(self, store: Dict):
        if store is None:
            return
        name = store.get('name', store.get('id', 'unknown'))
        dialog = JsonEditorDialog(f"Credential Store: {name}", store, readonly=True)
        dialog.exec()
    
    def _show_json_dialog(self, title: str, data: Dict):
        if data is None:
            return
        dialog = JsonEditorDialog(title, data, readonly=True)
        dialog.exec()
    
    # ==================== Create Actions ====================
    
    def _create_new_org(self):
        """Create a new organization."""
        name, ok = QInputDialog.getText(None, "New Organization", "Organization name:")
        if ok and name:
            desc, _ = QInputDialog.getText(None, "New Organization", "Description (optional):")
            result = self.client.scope_create('global', name, desc if desc else None)
            if result.get('success'):
                self.notification.emit("Created", f"Organization '{name}' created")
            else:
                QMessageBox.warning(None, "Error", result.get('error', 'Failed to create organization'))
    
    def _create_new_project(self, org_id: str):
        """Create a new project under an organization."""
        name, ok = QInputDialog.getText(None, "New Project", "Project name:")
        if ok and name:
            desc, _ = QInputDialog.getText(None, "New Project", "Description (optional):")
            result = self.client.scope_create(org_id, name, desc if desc else None)
            if result.get('success'):
                self.notification.emit("Created", f"Project '{name}' created")
            else:
                QMessageBox.warning(None, "Error", result.get('error', 'Failed to create project'))
    
    def _create_new_user(self, scope_id: str = 'global'):
        """Create a new user."""
        name, ok = QInputDialog.getText(None, "New User", "User name:")
        if ok and name:
            desc, _ = QInputDialog.getText(None, "New User", "Description (optional):")
            result = self.client.user_create(scope_id, name, desc if desc else None)
            if result.get('success'):
                self.notification.emit("Created", f"User '{name}' created")
            else:
                QMessageBox.warning(None, "Error", result.get('error', 'Failed to create user'))
    
    def _create_new_group(self, scope_id: str = 'global'):
        """Create a new group."""
        name, ok = QInputDialog.getText(None, "New Group", "Group name:")
        if ok and name:
            desc, _ = QInputDialog.getText(None, "New Group", "Description (optional):")
            result = self.client.group_create(scope_id, name, desc if desc else None)
            if result.get('success'):
                self.notification.emit("Created", f"Group '{name}' created")
            else:
                QMessageBox.warning(None, "Error", result.get('error', 'Failed to create group'))
    
    def _create_new_role(self, scope_id: str = 'global'):
        """Create a new role."""
        name, ok = QInputDialog.getText(None, "New Role", "Role name:")
        if ok and name:
            desc, _ = QInputDialog.getText(None, "New Role", "Description (optional):")
            result = self.client.role_create(scope_id, name, desc if desc else None)
            if result.get('success'):
                self.notification.emit("Created", f"Role '{name}' created")
            else:
                QMessageBox.warning(None, "Error", result.get('error', 'Failed to create role'))
    
    def _create_new_alias(self):
        """Create a new alias."""
        value, ok = QInputDialog.getText(None, "New Alias", "Alias value (e.g., 'myserver'):")
        if ok and value:
            dest_id, ok2 = QInputDialog.getText(None, "New Alias", "Destination target ID:")
            if ok2 and dest_id:
                result = self.client.alias_create('global', value, dest_id)
                if result.get('success'):
                    self.notification.emit("Created", f"Alias '{value}' created")
                else:
                    QMessageBox.warning(None, "Error", result.get('error', 'Failed to create alias'))
