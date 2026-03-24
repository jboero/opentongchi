"""
OpenBao Menu Builder for OpenTongchi
Builds dynamic menus for OpenBao/Vault operations using OpenAPI schema.
"""

import json
import base64
from typing import Dict, Any, Optional, Callable
from pathlib import Path
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog, QLineEdit, QFileDialog
from PySide6.QtCore import QObject, Signal

from app.clients.openbao import OpenBaoClient
from app.async_menu import AsyncMenu, LazySubmenu, create_status_prefix
from app.dialogs import SecretDialog, JsonEditorDialog, CrudDialog


class OpenBaoMenuBuilder(QObject):
    """Builds menus for OpenBao operations."""
    
    notification = Signal(str, str)  # title, message
    
    def __init__(self, settings, process_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        self._client: Optional[OpenBaoClient] = None
        self._schema_cache: Optional[Dict] = None
    
    @property
    def client(self) -> OpenBaoClient:
        if self._client is None:
            self._client = OpenBaoClient(self.settings.openbao)
        return self._client
    
    def refresh_client(self):
        self._client = None
        self._schema_cache = None
    
    def build_menu(self) -> QMenu:
        menu = QMenu("🔐 OpenBao")
        
        if not self.settings.openbao.address:
            not_configured = menu.addAction("⚠️ Not Configured")
            not_configured.setEnabled(False)
            return menu
        
        self._add_status_menu(menu)
        menu.addSeparator()
        
        secrets_menu = self._create_secrets_menu()
        menu.addMenu(secrets_menu)
        
        auth_menu = self._create_auth_menu()
        menu.addMenu(auth_menu)
        
        identity_menu = self._create_identity_menu()
        menu.addMenu(identity_menu)
        
        policies_menu = self._create_policies_menu()
        menu.addMenu(policies_menu)
        
        namespaces_menu = self._create_namespaces_menu()
        menu.addMenu(namespaces_menu)
        
        sys_menu = self._create_system_menu()
        menu.addMenu(sys_menu)
        
        tools_menu = self._create_tools_menu()
        menu.addMenu(tools_menu)
        
        menu.addSeparator()
        
        token_menu = self._create_token_menu()
        menu.addMenu(token_menu)
        
        menu.addSeparator()
        refresh_schema = menu.addAction("🔄 Refresh Schema")
        refresh_schema.triggered.connect(self._refresh_schema)
        
        return menu
    
    def _add_status_menu(self, menu: QMenu):
        try:
            if self.client.is_healthy():
                status = menu.addAction("🟢 Connected")
            else:
                status = menu.addAction("🔴 Disconnected")
        except Exception:
            status = menu.addAction("⚪ Unknown")
        status.setEnabled(False)
    
    def _create_secrets_menu(self) -> QMenu:
        menu = AsyncMenu("🗝️ Secrets", self._load_mounts)
        menu.set_submenu_factory(self._create_mount_submenu)
        menu.set_new_item_callback(self._enable_secrets_engine, "➕ Enable Engine...")
        return menu
    
    def _load_mounts(self) -> list:
        response = self.client.list_mounts()
        if not response.ok:
            raise Exception(response.error or "Failed to list mounts")
        
        mounts = response.data.get('data', response.data) if response.data else {}
        items = []
        
        for path, info in mounts.items():
            # Skip sys/ — it has its own dedicated System menu
            if path.rstrip('/') == 'sys':
                continue
            engine_type = info.get('type', 'unknown')
            icon = {'kv': '📦', 'transit': '🔒', 'pki': '📜', 'aws': '☁️',
                    'database': '🗄️', 'ssh': '🔑', 'totp': '⏱️', 'cubbyhole': '🧊'}.get(engine_type, '📁')
            
            items.append({
                'text': f"{icon} {path.rstrip('/')} ({engine_type})",
                'data': {'path': path, 'type': engine_type, 'info': info},
                'is_submenu': True
            })
        return items
    
    def _create_mount_submenu(self, title: str, data: Dict) -> QMenu:
        mount_path = data['path'].rstrip('/')
        engine_type = data['type']
        
        if engine_type == 'kv':
            return self._create_kv_menu(title, mount_path)
        else:
            return self._create_generic_engine_menu(title, mount_path, engine_type)
    
    def _create_kv_menu(self, title: str, mount_path: str) -> QMenu:
        is_v2 = self.client.is_kv_v2(mount_path)
        
        def load_secrets(path: str = ""):
            if is_v2:
                response = self.client.kv2_list(mount_path, path)
            else:
                response = self.client.kv1_list(mount_path, path)
            
            if not response.ok:
                if response.status_code == 404:
                    return []
                raise Exception(response.error or "Failed to list secrets")
            
            keys = response.data.get('data', {}).get('keys', []) if response.data else []
            items = []
            
            for key in keys:
                full_path = f"{path}/{key}" if path else key
                is_folder = key.endswith('/')
                
                if is_folder:
                    items.append({
                        'text': f"📁 {key}",
                        'data': {'path': full_path.rstrip('/'), 'is_folder': True},
                        'is_submenu': True
                    })
                else:
                    items.append({
                        'text': f"🔑 {key}",
                        'data': {'path': full_path, 'is_folder': False},
                        'callback': lambda d: self._show_secret(mount_path, d['path'], is_v2)
                    })
            return items
        
        menu = AsyncMenu(title, lambda: load_secrets(""))
        menu.set_new_item_callback(lambda: self._create_secret(mount_path, "", is_v2), "➕ New Secret...")
        
        def create_folder_submenu(folder_title: str, data: Dict) -> QMenu:
            folder_path = data['path']
            submenu = AsyncMenu(folder_title, lambda: load_secrets(folder_path))
            submenu.set_new_item_callback(lambda: self._create_secret(mount_path, folder_path, is_v2), "➕ New Secret...")
            submenu.set_submenu_factory(create_folder_submenu)
            return submenu
        
        menu.set_submenu_factory(create_folder_submenu)
        return menu
    
    def _create_generic_engine_menu(self, title: str, mount_path: str, engine_type: str) -> QMenu:
        menu = QMenu(title)
        
        info_action = menu.addAction("ℹ️ Engine Info")
        info_action.triggered.connect(lambda: self._show_engine_info(mount_path))
        
        menu.addSeparator()
        
        if engine_type == 'transit':
            self._build_transit_menu(menu, mount_path)
        elif engine_type == 'pki':
            self._build_pki_menu(menu, mount_path)
        elif engine_type == 'database':
            self._build_database_menu(menu, mount_path)
        elif engine_type == 'aws':
            self._build_aws_menu(menu, mount_path)
        elif engine_type == 'ssh':
            self._build_ssh_menu(menu, mount_path)
        elif engine_type == 'totp':
            self._build_totp_menu(menu, mount_path)
        elif engine_type == 'cubbyhole':
            self._build_cubbyhole_menu(menu, mount_path)
        elif engine_type in ('gcp', 'azure', 'alicloud', 'oracle', 'digitalocean'):
            self._build_cloud_secrets_menu(menu, mount_path, engine_type)
        else:
            # Generic secrets engine - provide basic CRUD
            self._build_generic_secrets_menu(menu, mount_path, engine_type)
        
        return menu
    
    def _build_generic_secrets_menu(self, menu: QMenu, mount_path: str, engine_type: str):
        """Build a generic secrets menu with basic CRUD for any engine type."""
        # Secrets listing with CRUD
        secrets_menu = AsyncMenu("🔑 Secrets", lambda: self._load_generic_secrets(mount_path, ""))
        secrets_menu.set_submenu_factory(lambda t, d: self._create_generic_secret_submenu(mount_path, t, d))
        secrets_menu.set_new_item_callback(lambda: self._create_generic_secret(mount_path, ""), "➕ New Secret...")
        menu.addMenu(secrets_menu)
        
        menu.addSeparator()
        
        # Quick create
        create_action = menu.addAction("➕ Create Secret")
        create_action.triggered.connect(lambda: self._create_generic_secret(mount_path, ""))
        
        # Raw API access for advanced users
        raw_read = menu.addAction("📖 Read Path...")
        raw_read.triggered.connect(lambda: self._raw_read_path(mount_path))
        
        raw_write = menu.addAction("✏️ Write Path...")
        raw_write.triggered.connect(lambda: self._raw_write_path(mount_path))
        
        raw_list = menu.addAction("📋 List Path...")
        raw_list.triggered.connect(lambda: self._raw_list_path(mount_path))
        
        raw_delete = menu.addAction("🗑️ Delete Path...")
        raw_delete.triggered.connect(lambda: self._raw_delete_path(mount_path))
    
    def _load_generic_secrets(self, mount_path: str, subpath: str) -> list:
        """Load secrets from a generic engine path."""
        full_path = f"{mount_path}/{subpath}".rstrip('/')
        response = self.client.api_list(full_path)
        
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list secrets")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        items = []
        
        for key in keys:
            full_key_path = f"{subpath}/{key}".lstrip('/') if subpath else key
            is_folder = key.endswith('/')
            
            if is_folder:
                items.append({
                    'text': f"📁 {key}",
                    'data': {'path': full_key_path.rstrip('/'), 'is_folder': True},
                    'is_submenu': True
                })
            else:
                items.append({
                    'text': f"🔑 {key}",
                    'data': {'path': full_key_path, 'is_folder': False},
                    'is_submenu': True
                })
        return items
    
    def _create_generic_secret_submenu(self, mount_path: str, title: str, data: Dict) -> QMenu:
        """Create submenu for a generic secret or folder."""
        path = data.get('path', '')
        is_folder = data.get('is_folder', False)
        
        if is_folder:
            # It's a folder - recurse
            submenu = AsyncMenu(title, lambda: self._load_generic_secrets(mount_path, path))
            submenu.set_submenu_factory(lambda t, d: self._create_generic_secret_submenu(mount_path, t, d))
            submenu.set_new_item_callback(lambda: self._create_generic_secret(mount_path, path), "➕ New Secret...")
            return submenu
        else:
            # It's a secret - show actions
            menu = QMenu(title)
            
            view = menu.addAction("👁️ View Secret")
            view.triggered.connect(lambda: self._view_generic_secret(mount_path, path))
            
            edit = menu.addAction("✏️ Edit Secret")
            edit.triggered.connect(lambda: self._edit_generic_secret(mount_path, path))
            
            menu.addSeparator()
            
            delete = menu.addAction("🗑️ Delete Secret")
            delete.triggered.connect(lambda: self._delete_generic_secret(mount_path, path))
            
            return menu
    
    def _view_generic_secret(self, mount_path: str, path: str):
        """View a generic secret."""
        full_path = f"{mount_path}/{path}"
        response = self.client.api_read(full_path)
        if response.ok:
            dialog = JsonEditorDialog(f"Secret: {path}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to read: {response.error}")
    
    def _edit_generic_secret(self, mount_path: str, path: str):
        """Edit a generic secret."""
        full_path = f"{mount_path}/{path}"
        response = self.client.api_read(full_path)
        if response.ok:
            current_data = response.data.get('data', {}) if response.data else {}
            dialog = SecretDialog(path, current_data)
            dialog.saved.connect(lambda p, d: self._save_generic_secret(mount_path, p, d))
            dialog.deleted.connect(lambda p: self._delete_generic_secret(mount_path, p))
            dialog.exec()
    
    def _create_generic_secret(self, mount_path: str, folder_path: str):
        """Create a new generic secret."""
        name, ok = QInputDialog.getText(None, "New Secret", "Secret name/path:")
        if ok and name:
            full_path = f"{folder_path}/{name}".lstrip('/') if folder_path else name
            dialog = SecretDialog(full_path, {}, is_new=True)
            dialog.saved.connect(lambda p, d: self._save_generic_secret(mount_path, p, d))
            dialog.exec()
    
    def _save_generic_secret(self, mount_path: str, path: str, data: Dict):
        """Save a generic secret."""
        full_path = f"{mount_path}/{path}"
        response = self.client.api_write(full_path, data)
        if response.ok:
            self.notification.emit("Secret Saved", f"Secret at {path} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save: {response.error}")
    
    def _delete_generic_secret(self, mount_path: str, path: str):
        """Delete a generic secret."""
        reply = QMessageBox.question(None, "Delete Secret", f"Delete secret at '{path}'?")
        if reply == QMessageBox.StandardButton.Yes:
            full_path = f"{mount_path}/{path}"
            response = self.client.api_delete(full_path)
            if response.ok:
                self.notification.emit("Secret Deleted", f"Secret at {path} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed to delete: {response.error}")
    
    def _raw_read_path(self, mount_path: str):
        """Raw read from any path under mount."""
        path, ok = QInputDialog.getText(None, "Read Path", f"Path under {mount_path}/:")
        if ok and path:
            full_path = f"{mount_path}/{path}"
            response = self.client.api_read(full_path)
            if response.ok:
                dialog = JsonEditorDialog(f"Read: {full_path}", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _raw_write_path(self, mount_path: str):
        """Raw write to any path under mount."""
        path, ok = QInputDialog.getText(None, "Write Path", f"Path under {mount_path}/:")
        if ok and path:
            full_path = f"{mount_path}/{path}"
            dialog = SecretDialog(path, {}, is_new=True)
            dialog.saved.connect(lambda p, d: self._do_raw_write(full_path, d))
            dialog.exec()
    
    def _do_raw_write(self, full_path: str, data: Dict):
        response = self.client.api_write(full_path, data)
        if response.ok:
            self.notification.emit("Written", f"Data written to {full_path}")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _raw_list_path(self, mount_path: str):
        """Raw list from any path under mount."""
        path, ok = QInputDialog.getText(None, "List Path", f"Path under {mount_path}/ (empty for root):")
        if ok:
            full_path = f"{mount_path}/{path}".rstrip('/')
            response = self.client.api_list(full_path)
            if response.ok:
                dialog = JsonEditorDialog(f"List: {full_path}", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _raw_delete_path(self, mount_path: str):
        """Raw delete at any path under mount."""
        path, ok = QInputDialog.getText(None, "Delete Path", f"Path under {mount_path}/:")
        if ok and path:
            reply = QMessageBox.warning(None, "Delete", f"Delete {mount_path}/{path}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                full_path = f"{mount_path}/{path}"
                response = self.client.api_delete(full_path)
                if response.ok:
                    self.notification.emit("Deleted", f"Deleted {full_path}")
                else:
                    QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _build_database_menu(self, menu: QMenu, mount_path: str):
        """Build database secrets engine menu."""
        # Connections submenu with CRUD
        config_menu = AsyncMenu("⚙️ Connections", lambda: self._load_database_connections(mount_path))
        config_menu.set_submenu_factory(lambda t, d: self._create_db_connection_submenu(mount_path, d))
        config_menu.set_new_item_callback(lambda: self._create_database_connection(mount_path), "➕ New Connection...")
        menu.addMenu(config_menu)
        
        # Dynamic roles submenu with CRUD and per-role credential generation
        roles_menu = AsyncMenu("👤 Dynamic Roles", lambda: self._load_database_roles(mount_path))
        roles_menu.set_submenu_factory(lambda t, d: self._create_db_role_submenu(mount_path, d, is_static=False))
        roles_menu.set_new_item_callback(lambda: self._create_database_role(mount_path), "➕ New Role...")
        menu.addMenu(roles_menu)
        
        # Static roles submenu
        static_roles_menu = AsyncMenu("📌 Static Roles", lambda: self._load_database_static_roles(mount_path))
        static_roles_menu.set_submenu_factory(lambda t, d: self._create_db_role_submenu(mount_path, d, is_static=True))
        static_roles_menu.set_new_item_callback(lambda: self._create_database_static_role(mount_path), "➕ New Static Role...")
        menu.addMenu(static_roles_menu)
    
    def _load_database_connections(self, mount_path: str) -> list:
        """Load database connections."""
        response = self.client.database_list_connections(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list connections")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"🔌 {k}", k) for k in keys]
    
    def _load_database_roles(self, mount_path: str) -> list:
        """Load database dynamic roles."""
        response = self.client.database_list_roles(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"👤 {k}", k) for k in keys]
    
    def _load_database_static_roles(self, mount_path: str) -> list:
        """Load database static roles."""
        response = self.client.database_list_static_roles(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list static roles")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"📌 {k}", k) for k in keys]
    
    def _create_db_connection_submenu(self, mount_path: str, name: str) -> QMenu:
        """Create submenu for a database connection."""
        menu = QMenu(name)
        
        view = menu.addAction("👁️ View Configuration")
        view.triggered.connect(lambda: self._show_database_config(mount_path, name))
        
        edit = menu.addAction("✏️ Edit Connection")
        edit.triggered.connect(lambda: self._edit_database_connection(mount_path, name))
        
        menu.addSeparator()
        
        reset = menu.addAction("🔄 Reset Connection")
        reset.triggered.connect(lambda: self._reset_database_connection(mount_path, name))
        
        rotate = menu.addAction("🔑 Rotate Root Credentials")
        rotate.triggered.connect(lambda: self._rotate_database_root(mount_path, name))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Connection")
        delete.triggered.connect(lambda: self._delete_database_connection(mount_path, name))
        
        return menu
    
    def _create_db_role_submenu(self, mount_path: str, name: str, is_static: bool = False) -> QMenu:
        """Create submenu for a database role."""
        menu = QMenu(name)
        
        # Generate credentials - the main feature!
        creds = menu.addAction("🔑 Generate Credentials")
        if is_static:
            creds.triggered.connect(lambda: self._get_database_static_creds(mount_path, name))
        else:
            creds.triggered.connect(lambda: self._generate_database_creds(mount_path, name))
        
        menu.addSeparator()
        
        view = menu.addAction("👁️ View Role")
        if is_static:
            view.triggered.connect(lambda: self._show_database_static_role(mount_path, name))
        else:
            view.triggered.connect(lambda: self._show_database_role(mount_path, name))
        
        edit = menu.addAction("✏️ Edit Role")
        if is_static:
            edit.triggered.connect(lambda: self._edit_database_static_role(mount_path, name))
        else:
            edit.triggered.connect(lambda: self._edit_database_role(mount_path, name))
        
        if is_static:
            menu.addSeparator()
            rotate = menu.addAction("🔄 Rotate Credentials Now")
            rotate.triggered.connect(lambda: self._rotate_database_static_role(mount_path, name))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Role")
        if is_static:
            delete.triggered.connect(lambda: self._delete_database_static_role(mount_path, name))
        else:
            delete.triggered.connect(lambda: self._delete_database_role(mount_path, name))
        
        return menu
    
    def _build_aws_menu(self, menu: QMenu, mount_path: str):
        """Build AWS secrets engine menu."""
        # Root config
        config_menu = QMenu("⚙️ Configuration")
        
        view_config = config_menu.addAction("👁️ View Root Config")
        view_config.triggered.connect(lambda: self._show_aws_config(mount_path))
        
        edit_config = config_menu.addAction("✏️ Configure Root Credentials")
        edit_config.triggered.connect(lambda: self._edit_aws_config(mount_path))
        
        rotate_root = config_menu.addAction("🔄 Rotate Root Credentials")
        rotate_root.triggered.connect(lambda: self._rotate_aws_root(mount_path))
        
        menu.addMenu(config_menu)
        
        # Roles with full CRUD
        roles_menu = AsyncMenu("👤 Roles", lambda: self._load_aws_roles(mount_path))
        roles_menu.set_submenu_factory(lambda t, d: self._create_aws_role_submenu(mount_path, d))
        roles_menu.set_new_item_callback(lambda: self._create_aws_role(mount_path), "➕ New Role...")
        menu.addMenu(roles_menu)
        
        # STS Roles (for assumed_role credential types)
        sts_menu = AsyncMenu("🎫 STS Roles", lambda: self._load_generic_list(mount_path, 'sts'))
        sts_menu.set_submenu_factory(lambda t, d: self._create_aws_sts_role_submenu(mount_path, d))
        menu.addMenu(sts_menu)
        
        menu.addSeparator()
        
        # Lease config
        lease_config = menu.addAction("⏱️ Lease Configuration")
        lease_config.triggered.connect(lambda: self._show_aws_lease_config(mount_path))
    
    def _load_aws_roles(self, mount_path: str) -> list:
        """Load AWS roles."""
        response = self.client.api_list(f"{mount_path}/roles")
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"👤 {k}", k) for k in keys]
    
    def _create_aws_role_submenu(self, mount_path: str, name: str) -> QMenu:
        """Create submenu for an AWS role."""
        menu = QMenu(name)
        
        # Generate credentials - main feature
        creds = menu.addAction("🔑 Generate Credentials")
        creds.triggered.connect(lambda: self._generate_aws_creds_for_role(mount_path, name))
        
        sts = menu.addAction("🎫 Generate STS Credentials")
        sts.triggered.connect(lambda: self._generate_aws_sts_for_role(mount_path, name))
        
        menu.addSeparator()
        
        view = menu.addAction("👁️ View Role")
        view.triggered.connect(lambda: self._show_aws_role(mount_path, name))
        
        edit = menu.addAction("✏️ Edit Role")
        edit.triggered.connect(lambda: self._edit_aws_role(mount_path, name))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Role")
        delete.triggered.connect(lambda: self._delete_aws_role(mount_path, name))
        
        return menu
    
    def _create_aws_sts_role_submenu(self, mount_path: str, name: str) -> QMenu:
        """Create submenu for an AWS STS role."""
        menu = QMenu(name)
        
        creds = menu.addAction("🎫 Generate STS Credentials")
        creds.triggered.connect(lambda: self._generate_aws_sts_for_role(mount_path, name))
        
        view = menu.addAction("👁️ View Role")
        view.triggered.connect(lambda: self._show_aws_sts_role(mount_path, name))
        
        return menu
    
    def _show_aws_config(self, mount_path: str):
        """View AWS root configuration."""
        response = self.client.api_read(f"{mount_path}/config/root")
        if response.ok:
            dialog = JsonEditorDialog("AWS Root Config", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.information(None, "Info", "No root configuration found")
    
    def _edit_aws_config(self, mount_path: str):
        """Edit AWS root configuration."""
        template = {
            'access_key': '',
            'secret_key': '',
            'region': 'us-east-1',
            'iam_endpoint': '',
            'sts_endpoint': '',
            'max_retries': -1,
        }
        response = self.client.api_read(f"{mount_path}/config/root")
        if response.ok:
            data = response.data.get('data', response.data)
            template.update(data)
        
        dialog = JsonEditorDialog("AWS Root Config", template, readonly=False)
        dialog.saved.connect(lambda d: self._save_aws_config(mount_path, d))
        dialog.exec()
    
    def _save_aws_config(self, mount_path: str, data: Dict):
        """Save AWS root configuration."""
        response = self.client.api_write(f"{mount_path}/config/root", data)
        if response.ok:
            self.notification.emit("Config Saved", "AWS root configuration saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _rotate_aws_root(self, mount_path: str):
        """Rotate AWS root credentials."""
        reply = QMessageBox.question(None, "Rotate Root",
                                     "Rotate AWS root credentials?\nThis will create new access keys.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.api_write(f"{mount_path}/config/rotate-root", {})
            if response.ok:
                self.notification.emit("Root Rotated", "AWS root credentials rotated")
                # Show the new access key
                dialog = JsonEditorDialog("New Root Credentials", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_aws_role(self, mount_path: str, name: str):
        """View AWS role."""
        response = self.client.api_read(f"{mount_path}/roles/{name}")
        if response.ok:
            dialog = JsonEditorDialog(f"AWS Role: {name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _edit_aws_role(self, mount_path: str, name: str):
        """Edit AWS role."""
        from app.dialogs import AWSRoleDialog
        response = self.client.api_read(f"{mount_path}/roles/{name}")
        if response.ok:
            data = response.data.get('data', response.data)
            dialog = AWSRoleDialog(name=name, config=data, is_new=False)
            dialog.saved.connect(lambda n, d: self._save_aws_role(mount_path, n, d))
            dialog.exec()
    
    def _create_aws_role(self, mount_path: str):
        """Create a new AWS role."""
        from app.dialogs import AWSRoleDialog
        dialog = AWSRoleDialog(is_new=True)
        dialog.saved.connect(lambda name, d: self._save_aws_role(mount_path, name, d))
        dialog.exec()
    
    def _save_aws_role(self, mount_path: str, name: str, data: Dict):
        """Save AWS role."""
        response = self.client.api_write(f"{mount_path}/roles/{name}", data)
        if response.ok:
            self.notification.emit("Role Saved", f"AWS role {name} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save role: {response.error}")
    
    def _delete_aws_role(self, mount_path: str, name: str):
        """Delete AWS role."""
        reply = QMessageBox.question(None, "Delete Role",
                                     f"Delete AWS role '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.api_delete(f"{mount_path}/roles/{name}")
            if response.ok:
                self.notification.emit("Role Deleted", f"AWS role {name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_aws_sts_role(self, mount_path: str, name: str):
        """View AWS STS role."""
        response = self.client.api_read(f"{mount_path}/sts/{name}")
        if response.ok:
            dialog = JsonEditorDialog(f"AWS STS Role: {name}", response.data, readonly=True)
            dialog.exec()
    
    def _generate_aws_creds_for_role(self, mount_path: str, role_name: str):
        """Generate AWS credentials for a specific role."""
        response = self.client.api_read(f"{mount_path}/creds/{role_name}")
        if response.ok:
            creds_data = response.data.get('data', response.data)
            lease_info = {
                'lease_id': response.data.get('lease_id', ''),
                'lease_duration': response.data.get('lease_duration', 0),
                **creds_data
            }
            dialog = JsonEditorDialog(f"AWS Credentials: {role_name}", lease_info, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to generate credentials: {response.error}")
    
    def _generate_aws_sts_for_role(self, mount_path: str, role_name: str):
        """Generate AWS STS credentials for a specific role."""
        response = self.client.api_read(f"{mount_path}/sts/{role_name}")
        if response.ok:
            creds_data = response.data.get('data', response.data)
            lease_info = {
                'lease_id': response.data.get('lease_id', ''),
                'lease_duration': response.data.get('lease_duration', 0),
                **creds_data
            }
            dialog = JsonEditorDialog(f"AWS STS Credentials: {role_name}", lease_info, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to generate STS credentials: {response.error}")
    
    def _show_aws_lease_config(self, mount_path: str):
        """View and edit AWS lease configuration."""
        response = self.client.api_read(f"{mount_path}/config/lease")
        if response.ok:
            data = response.data.get('data', response.data)
        else:
            data = {'lease': '30m', 'lease_max': '24h'}
        
        dialog = JsonEditorDialog("AWS Lease Config", data, readonly=False)
        dialog.saved.connect(lambda d: self._save_aws_lease_config(mount_path, d))
        dialog.exec()
    
    def _save_aws_lease_config(self, mount_path: str, data: Dict):
        """Save AWS lease configuration."""
        response = self.client.api_write(f"{mount_path}/config/lease", data)
        if response.ok:
            self.notification.emit("Config Saved", "AWS lease configuration saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    # ==================== Generic Cloud Secrets Engine ====================
    
    # Cloud provider configurations
    CLOUD_PROVIDERS = {
        'gcp': {
            'name': 'Google Cloud',
            'icon': '☁️',
            'config_fields': {
                'credentials': {'type': 'text', 'label': 'Service Account JSON', 'required': True},
                'ttl': {'type': 'duration', 'label': 'Default TTL', 'default': '1h'},
                'max_ttl': {'type': 'duration', 'label': 'Max TTL', 'default': '24h'},
            },
            'role_types': ['access_token', 'service_account_key'],
            'creds_endpoint': 'token',
        },
        'azure': {
            'name': 'Microsoft Azure',
            'icon': '🔷',
            'config_fields': {
                'subscription_id': {'type': 'string', 'label': 'Subscription ID', 'required': True},
                'tenant_id': {'type': 'string', 'label': 'Tenant ID', 'required': True},
                'client_id': {'type': 'string', 'label': 'Client ID'},
                'client_secret': {'type': 'password', 'label': 'Client Secret'},
                'environment': {'type': 'string', 'label': 'Environment', 'default': 'AzurePublicCloud'},
            },
            'role_types': ['azure_role'],
            'creds_endpoint': 'creds',
        },
        'alicloud': {
            'name': 'Alibaba Cloud',
            'icon': '🌏',
            'config_fields': {
                'access_key': {'type': 'string', 'label': 'Access Key', 'required': True},
                'secret_key': {'type': 'password', 'label': 'Secret Key', 'required': True},
                'region': {'type': 'string', 'label': 'Region'},
            },
            'role_types': ['ram_role', 'assume_role'],
            'creds_endpoint': 'creds',
        },
        'oracle': {
            'name': 'Oracle Cloud',
            'icon': '🔴',
            'config_fields': {
                'user_ocid': {'type': 'string', 'label': 'User OCID', 'required': True},
                'tenancy_ocid': {'type': 'string', 'label': 'Tenancy OCID', 'required': True},
                'fingerprint': {'type': 'string', 'label': 'Fingerprint', 'required': True},
                'private_key': {'type': 'text', 'label': 'Private Key', 'required': True},
                'region': {'type': 'string', 'label': 'Region'},
            },
            'role_types': ['api_key'],
            'creds_endpoint': 'creds',
        },
        'digitalocean': {
            'name': 'DigitalOcean',
            'icon': '🌊',
            'config_fields': {
                'token': {'type': 'password', 'label': 'API Token', 'required': True},
            },
            'role_types': ['personal_access_token'],
            'creds_endpoint': 'creds',
        },
    }
    
    def _build_cloud_secrets_menu(self, menu: QMenu, mount_path: str, cloud_type: str):
        """Build a generic cloud secrets engine menu (GCP, Azure, AliCloud, Oracle, DigitalOcean)."""
        provider = self.CLOUD_PROVIDERS.get(cloud_type, {})
        provider_name = provider.get('name', cloud_type.upper())
        icon = provider.get('icon', '☁️')
        
        # Root config
        config_menu = QMenu(f"⚙️ Configuration")
        
        view_config = config_menu.addAction("👁️ View Config")
        view_config.triggered.connect(lambda: self._show_cloud_config(mount_path, cloud_type))
        
        edit_config = config_menu.addAction("✏️ Configure Credentials")
        edit_config.triggered.connect(lambda: self._edit_cloud_config(mount_path, cloud_type))
        
        if cloud_type in ('gcp', 'azure'):
            rotate_root = config_menu.addAction("🔄 Rotate Root Credentials")
            rotate_root.triggered.connect(lambda: self._rotate_cloud_root(mount_path, cloud_type))
        
        menu.addMenu(config_menu)
        
        # Roles with full CRUD
        roles_menu = AsyncMenu("👤 Roles", lambda: self._load_cloud_roles(mount_path))
        roles_menu.set_submenu_factory(lambda t, d: self._create_cloud_role_submenu(mount_path, d, cloud_type))
        roles_menu.set_new_item_callback(lambda: self._create_cloud_role(mount_path, cloud_type), "➕ New Role...")
        menu.addMenu(roles_menu)
        
        # Rolesets (GCP specific)
        if cloud_type == 'gcp':
            rolesets_menu = AsyncMenu("📋 Rolesets", lambda: self._load_cloud_rolesets(mount_path))
            rolesets_menu.set_submenu_factory(lambda t, d: self._create_cloud_roleset_submenu(mount_path, d))
            rolesets_menu.set_new_item_callback(lambda: self._create_cloud_roleset(mount_path), "➕ New Roleset...")
            menu.addMenu(rolesets_menu)
        
        menu.addSeparator()
        
        # Quick generate credentials
        quick_creds = menu.addAction(f"{icon} Generate Credentials...")
        quick_creds.triggered.connect(lambda: self._generate_cloud_creds_prompt(mount_path, cloud_type))
    
    def _load_cloud_roles(self, mount_path: str) -> list:
        """Load cloud roles."""
        response = self.client.api_list(f"{mount_path}/roles")
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"👤 {k}", k) for k in keys]
    
    def _load_cloud_rolesets(self, mount_path: str) -> list:
        """Load cloud rolesets (GCP)."""
        response = self.client.api_list(f"{mount_path}/rolesets")
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list rolesets")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"📋 {k}", k) for k in keys]
    
    def _create_cloud_role_submenu(self, mount_path: str, name: str, cloud_type: str) -> QMenu:
        """Create submenu for a cloud role."""
        menu = QMenu(name)
        provider = self.CLOUD_PROVIDERS.get(cloud_type, {})
        creds_endpoint = provider.get('creds_endpoint', 'creds')
        
        # Generate credentials - main feature
        creds = menu.addAction("🔑 Generate Credentials")
        creds.triggered.connect(lambda: self._generate_cloud_creds(mount_path, name, cloud_type, creds_endpoint))
        
        menu.addSeparator()
        
        view = menu.addAction("👁️ View Role")
        view.triggered.connect(lambda: self._show_cloud_role(mount_path, name))
        
        edit = menu.addAction("✏️ Edit Role")
        edit.triggered.connect(lambda: self._edit_cloud_role(mount_path, name, cloud_type))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Role")
        delete.triggered.connect(lambda: self._delete_cloud_role(mount_path, name))
        
        return menu
    
    def _create_cloud_roleset_submenu(self, mount_path: str, name: str) -> QMenu:
        """Create submenu for a GCP roleset."""
        menu = QMenu(name)
        
        # Generate access token
        token = menu.addAction("🔑 Generate Access Token")
        token.triggered.connect(lambda: self._generate_cloud_creds(mount_path, name, 'gcp', 'token'))
        
        # Generate service account key
        key = menu.addAction("🔐 Generate Service Account Key")
        key.triggered.connect(lambda: self._generate_cloud_creds(mount_path, name, 'gcp', 'key'))
        
        menu.addSeparator()
        
        view = menu.addAction("👁️ View Roleset")
        view.triggered.connect(lambda: self._show_cloud_roleset(mount_path, name))
        
        edit = menu.addAction("✏️ Edit Roleset")
        edit.triggered.connect(lambda: self._edit_cloud_roleset(mount_path, name))
        
        menu.addSeparator()
        
        rotate = menu.addAction("🔄 Rotate Service Account")
        rotate.triggered.connect(lambda: self._rotate_cloud_roleset(mount_path, name))
        
        rotate_key = menu.addAction("🔄 Rotate Service Account Key")
        rotate_key.triggered.connect(lambda: self._rotate_cloud_roleset_key(mount_path, name))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Roleset")
        delete.triggered.connect(lambda: self._delete_cloud_roleset(mount_path, name))
        
        return menu
    
    def _show_cloud_config(self, mount_path: str, cloud_type: str):
        """View cloud configuration."""
        response = self.client.api_read(f"{mount_path}/config")
        if response.ok:
            dialog = JsonEditorDialog(f"{cloud_type.upper()} Config", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.information(None, "Info", "No configuration found")
    
    def _edit_cloud_config(self, mount_path: str, cloud_type: str):
        """Edit cloud configuration."""
        provider = self.CLOUD_PROVIDERS.get(cloud_type, {})
        config_fields = provider.get('config_fields', {})
        
        # Build template from provider config
        template = {}
        for field, info in config_fields.items():
            template[field] = info.get('default', '')
        
        # Try to load current config
        response = self.client.api_read(f"{mount_path}/config")
        if response.ok:
            data = response.data.get('data', response.data)
            template.update(data)
        
        dialog = JsonEditorDialog(f"{cloud_type.upper()} Config", template, readonly=False)
        dialog.saved.connect(lambda d: self._save_cloud_config(mount_path, d))
        dialog.exec()
    
    def _save_cloud_config(self, mount_path: str, data: Dict):
        """Save cloud configuration."""
        response = self.client.api_write(f"{mount_path}/config", data)
        if response.ok:
            self.notification.emit("Config Saved", "Cloud configuration saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _rotate_cloud_root(self, mount_path: str, cloud_type: str):
        """Rotate cloud root credentials."""
        reply = QMessageBox.question(None, "Rotate Root",
                                     f"Rotate {cloud_type.upper()} root credentials?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.api_write(f"{mount_path}/config/rotate-root", {})
            if response.ok:
                self.notification.emit("Root Rotated", f"{cloud_type.upper()} root credentials rotated")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_cloud_role(self, mount_path: str, name: str):
        """View cloud role."""
        response = self.client.api_read(f"{mount_path}/roles/{name}")
        if response.ok:
            dialog = JsonEditorDialog(f"Cloud Role: {name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _edit_cloud_role(self, mount_path: str, name: str, cloud_type: str):
        """Edit cloud role."""
        response = self.client.api_read(f"{mount_path}/roles/{name}")
        if response.ok:
            data = response.data.get('data', response.data)
            dialog = JsonEditorDialog(f"Edit Cloud Role: {name}", data, readonly=False)
            dialog.saved.connect(lambda d: self._save_cloud_role(mount_path, name, d))
            dialog.exec()
    
    def _create_cloud_role(self, mount_path: str, cloud_type: str):
        """Create a new cloud role."""
        from app.dialogs import CloudRoleDialog
        dialog = CloudRoleDialog(cloud_type=cloud_type, is_new=True)
        dialog.saved.connect(lambda name, d: self._save_cloud_role(mount_path, name, d))
        dialog.exec()
    
    def _save_cloud_role(self, mount_path: str, name: str, data: Dict):
        """Save cloud role."""
        response = self.client.api_write(f"{mount_path}/roles/{name}", data)
        if response.ok:
            self.notification.emit("Role Saved", f"Cloud role {name} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save role: {response.error}")
    
    def _delete_cloud_role(self, mount_path: str, name: str):
        """Delete cloud role."""
        reply = QMessageBox.question(None, "Delete Role",
                                     f"Delete cloud role '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.api_delete(f"{mount_path}/roles/{name}")
            if response.ok:
                self.notification.emit("Role Deleted", f"Cloud role {name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_cloud_roleset(self, mount_path: str, name: str):
        """View GCP roleset."""
        response = self.client.api_read(f"{mount_path}/rolesets/{name}")
        if response.ok:
            dialog = JsonEditorDialog(f"GCP Roleset: {name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _edit_cloud_roleset(self, mount_path: str, name: str):
        """Edit GCP roleset."""
        response = self.client.api_read(f"{mount_path}/rolesets/{name}")
        if response.ok:
            data = response.data.get('data', response.data)
            dialog = JsonEditorDialog(f"Edit GCP Roleset: {name}", data, readonly=False)
            dialog.saved.connect(lambda d: self._save_cloud_roleset(mount_path, name, d))
            dialog.exec()
    
    def _create_cloud_roleset(self, mount_path: str):
        """Create a new GCP roleset."""
        name, ok = QInputDialog.getText(None, "New GCP Roleset", "Roleset name:")
        if not ok or not name:
            return
        
        template = {
            'project': '',
            'secret_type': 'access_token',  # or 'service_account_key'
            'bindings': '# IAM bindings in HCL format\nresource "//cloudresourcemanager.googleapis.com/projects/PROJECT_ID" {\n  roles = ["roles/viewer"]\n}',
            'token_scopes': ['https://www.googleapis.com/auth/cloud-platform'],
        }
        
        dialog = JsonEditorDialog(f"New GCP Roleset: {name}", template, readonly=False)
        dialog.saved.connect(lambda d: self._save_cloud_roleset(mount_path, name, d))
        dialog.exec()
    
    def _save_cloud_roleset(self, mount_path: str, name: str, data: Dict):
        """Save GCP roleset."""
        response = self.client.api_write(f"{mount_path}/rolesets/{name}", data)
        if response.ok:
            self.notification.emit("Roleset Saved", f"GCP roleset {name} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save roleset: {response.error}")
    
    def _delete_cloud_roleset(self, mount_path: str, name: str):
        """Delete GCP roleset."""
        reply = QMessageBox.question(None, "Delete Roleset",
                                     f"Delete GCP roleset '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.api_delete(f"{mount_path}/rolesets/{name}")
            if response.ok:
                self.notification.emit("Roleset Deleted", f"GCP roleset {name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _rotate_cloud_roleset(self, mount_path: str, name: str):
        """Rotate GCP roleset service account."""
        reply = QMessageBox.question(None, "Rotate Service Account",
                                     f"Rotate service account for roleset '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.api_write(f"{mount_path}/rolesets/{name}/rotate", {})
            if response.ok:
                self.notification.emit("Rotated", f"Service account rotated for {name}")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _rotate_cloud_roleset_key(self, mount_path: str, name: str):
        """Rotate GCP roleset service account key."""
        reply = QMessageBox.question(None, "Rotate Key",
                                     f"Rotate service account key for roleset '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.api_write(f"{mount_path}/rolesets/{name}/rotate-key", {})
            if response.ok:
                self.notification.emit("Key Rotated", f"Service account key rotated for {name}")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _generate_cloud_creds(self, mount_path: str, role_name: str, cloud_type: str, endpoint: str):
        """Generate credentials for a cloud role/roleset."""
        # Determine the correct path
        if endpoint in ('token', 'key'):
            # GCP roleset endpoints
            path = f"{mount_path}/{endpoint}/{role_name}"
        else:
            path = f"{mount_path}/{endpoint}/{role_name}"
        
        response = self.client.api_read(path)
        if response.ok:
            creds_data = response.data.get('data', response.data)
            lease_info = {
                'lease_id': response.data.get('lease_id', ''),
                'lease_duration': response.data.get('lease_duration', 0),
                **creds_data
            }
            dialog = JsonEditorDialog(f"{cloud_type.upper()} Credentials: {role_name}", lease_info, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to generate credentials: {response.error}")
    
    def _generate_cloud_creds_prompt(self, mount_path: str, cloud_type: str):
        """Prompt for role/roleset and generate credentials."""
        # List available roles
        roles = []
        response = self.client.api_list(f"{mount_path}/roles")
        if response.ok:
            roles.extend(response.data.get('data', {}).get('keys', []))
        
        if cloud_type == 'gcp':
            response = self.client.api_list(f"{mount_path}/rolesets")
            if response.ok:
                rolesets = response.data.get('data', {}).get('keys', [])
                roles.extend([f"roleset:{r}" for r in rolesets])
        
        if not roles:
            QMessageBox.warning(None, "No Roles", "No roles or rolesets configured")
            return
        
        role, ok = QInputDialog.getItem(None, "Generate Credentials", "Select role:", roles, 0, False)
        if ok and role:
            if role.startswith('roleset:'):
                roleset_name = role.replace('roleset:', '')
                self._generate_cloud_creds(mount_path, roleset_name, cloud_type, 'token')
            else:
                provider = self.CLOUD_PROVIDERS.get(cloud_type, {})
                endpoint = provider.get('creds_endpoint', 'creds')
                self._generate_cloud_creds(mount_path, role, cloud_type, endpoint)

    def _build_ssh_menu(self, menu: QMenu, mount_path: str):
        """Build SSH secrets engine menu."""
        # CA Configuration
        ca_menu = QMenu("🔐 CA Configuration")
        
        view_ca = ca_menu.addAction("👁️ View Public Key")
        view_ca.triggered.connect(lambda: self._show_ssh_ca(mount_path))
        
        configure_ca = ca_menu.addAction("⚙️ Configure CA")
        configure_ca.triggered.connect(lambda: self._configure_ssh_ca(mount_path))
        
        delete_ca = ca_menu.addAction("🗑️ Delete CA")
        delete_ca.triggered.connect(lambda: self._delete_ssh_ca(mount_path))
        
        menu.addMenu(ca_menu)
        
        # Roles submenu with CRUD and per-role operations
        roles_menu = AsyncMenu("👤 Roles", lambda: self._load_ssh_roles(mount_path))
        roles_menu.set_submenu_factory(lambda t, d: self._create_ssh_role_submenu(mount_path, d))
        roles_menu.set_new_item_callback(lambda: self._create_ssh_role(mount_path), "➕ New Role...")
        menu.addMenu(roles_menu)
        
        # Zero-address config
        menu.addSeparator()
        zeroaddr = menu.addAction("🌐 Zero-Address Config")
        zeroaddr.triggered.connect(lambda: self._show_ssh_zeroaddress(mount_path))
    
    def _load_ssh_roles(self, mount_path: str) -> list:
        """Load SSH roles."""
        response = self.client.ssh_list_roles(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"🔑 {k}", k) for k in keys]
    
    def _create_ssh_role_submenu(self, mount_path: str, name: str) -> QMenu:
        """Create submenu for an SSH role."""
        menu = QMenu(name)
        
        # Sign key - main feature
        sign = menu.addAction("✍️ Sign SSH Key")
        sign.triggered.connect(lambda: self._sign_ssh_key_for_role(mount_path, name))
        
        # Issue credentials
        issue = menu.addAction("🔑 Issue Credentials")
        issue.triggered.connect(lambda: self._issue_ssh_creds_for_role(mount_path, name))
        
        menu.addSeparator()
        
        view = menu.addAction("👁️ View Role")
        view.triggered.connect(lambda: self._show_ssh_role(mount_path, name))
        
        edit = menu.addAction("✏️ Edit Role")
        edit.triggered.connect(lambda: self._edit_ssh_role(mount_path, name))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Role")
        delete.triggered.connect(lambda: self._delete_ssh_role(mount_path, name))
        
        return menu
    
    def _build_totp_menu(self, menu: QMenu, mount_path: str):
        """Build TOTP secrets engine menu."""
        keys_menu = AsyncMenu("🔑 Keys", lambda: self._load_generic_list(mount_path, 'keys'))
        keys_menu.set_item_callback(lambda d: self._show_totp_key(mount_path, d))
        menu.addMenu(keys_menu)
        
        menu.addSeparator()
        
        create = menu.addAction("➕ Create Key")
        create.triggered.connect(lambda: self._create_totp_key(mount_path))
        
        code = menu.addAction("🔢 Generate Code")
        code.triggered.connect(lambda: self._generate_totp_code(mount_path))
    
    def _build_cubbyhole_menu(self, menu: QMenu, mount_path: str):
        """Build cubbyhole secrets menu - simple personal secrets."""
        secrets_menu = AsyncMenu("🔑 My Secrets", lambda: self._load_generic_secrets(mount_path, ""))
        secrets_menu.set_submenu_factory(lambda t, d: self._create_generic_secret_submenu(mount_path, t, d))
        secrets_menu.set_new_item_callback(lambda: self._create_generic_secret(mount_path, ""), "➕ New Secret...")
        menu.addMenu(secrets_menu)
    
    # ==================== Database Engine Helpers ====================
    
    def _show_database_config(self, mount_path: str, name: str):
        """View database connection configuration."""
        response = self.client.database_read_connection(mount_path, name)
        if response.ok:
            dialog = JsonEditorDialog(f"DB Connection: {name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to read connection: {response.error}")
    
    def _edit_database_connection(self, mount_path: str, name: str):
        """Edit database connection configuration."""
        from app.dialogs import DatabaseConnectionDialog
        response = self.client.database_read_connection(mount_path, name)
        if response.ok:
            data = response.data.get('data', response.data)
            dialog = DatabaseConnectionDialog(name=name, config=data, is_new=False)
            dialog.saved.connect(lambda n, d: self._save_database_connection(mount_path, n, d))
            dialog.exec()
    
    def _create_database_connection(self, mount_path: str):
        """Create a new database connection."""
        from app.dialogs import DatabaseConnectionDialog
        dialog = DatabaseConnectionDialog(is_new=True)
        dialog.saved.connect(lambda name, d: self._save_database_connection(mount_path, name, d))
        dialog.exec()
    
    def _save_database_connection(self, mount_path: str, name: str, data: Dict):
        """Save database connection."""
        response = self.client.api_write(f"{mount_path}/config/{name}", data)
        if response.ok:
            self.notification.emit("Connection Saved", f"Database connection {name} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save connection: {response.error}")
    
    def _delete_database_connection(self, mount_path: str, name: str):
        """Delete database connection."""
        reply = QMessageBox.question(None, "Delete Connection",
                                     f"Delete database connection '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.database_delete_connection(mount_path, name)
            if response.ok:
                self.notification.emit("Connection Deleted", f"Database connection {name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _reset_database_connection(self, mount_path: str, name: str):
        """Reset (close and reopen) database connection."""
        response = self.client.database_reset_connection(mount_path, name)
        if response.ok:
            self.notification.emit("Connection Reset", f"Database connection {name} reset")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _rotate_database_root(self, mount_path: str, name: str):
        """Rotate root credentials for database connection."""
        reply = QMessageBox.question(None, "Rotate Root",
                                     f"Rotate root credentials for '{name}'?\nThis cannot be undone.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.database_rotate_root(mount_path, name)
            if response.ok:
                self.notification.emit("Root Rotated", f"Root credentials rotated for {name}")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_database_role(self, mount_path: str, name: str):
        """View database role."""
        response = self.client.database_read_role(mount_path, name)
        if response.ok:
            dialog = JsonEditorDialog(f"DB Role: {name}", response.data, readonly=True)
            dialog.exec()
    
    def _edit_database_role(self, mount_path: str, name: str):
        """Edit database role."""
        from app.dialogs import DatabaseRoleDialog
        response = self.client.database_read_role(mount_path, name)
        if response.ok:
            data = response.data.get('data', response.data)
            # Get list of connections for the dropdown
            conn_response = self.client.database_list_connections(mount_path)
            connections = conn_response.data.get('data', {}).get('keys', []) if conn_response.ok else []
            
            dialog = DatabaseRoleDialog(name=name, config=data, connections=connections, 
                                        is_static=False, is_new=False)
            dialog.saved.connect(lambda n, d: self._save_database_role(mount_path, n, d))
            dialog.exec()
    
    def _create_database_role(self, mount_path: str):
        """Create a new database role."""
        from app.dialogs import DatabaseRoleDialog
        # Get list of connections for the dropdown
        conn_response = self.client.database_list_connections(mount_path)
        connections = conn_response.data.get('data', {}).get('keys', []) if conn_response.ok else []
        
        if not connections:
            QMessageBox.warning(None, "No Connections", 
                               "Please create a database connection first before creating roles.")
            return
        
        dialog = DatabaseRoleDialog(connections=connections, is_static=False, is_new=True)
        dialog.saved.connect(lambda name, d: self._save_database_role(mount_path, name, d))
        dialog.exec()
    
    def _save_database_role(self, mount_path: str, name: str, data: Dict):
        """Save database role."""
        response = self.client.api_write(f"{mount_path}/roles/{name}", data)
        if response.ok:
            self.notification.emit("Role Saved", f"Database role {name} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save role: {response.error}")
    
    def _delete_database_role(self, mount_path: str, name: str):
        """Delete database role."""
        reply = QMessageBox.question(None, "Delete Role",
                                     f"Delete database role '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.database_delete_role(mount_path, name)
            if response.ok:
                self.notification.emit("Role Deleted", f"Database role {name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _generate_database_creds(self, mount_path: str, role_name: str):
        """Generate credentials for a database role."""
        response = self.client.database_generate_creds(mount_path, role_name)
        if response.ok:
            # Show the credentials with lease info
            creds_data = response.data.get('data', response.data)
            lease_info = {
                'lease_id': response.data.get('lease_id', ''),
                'lease_duration': response.data.get('lease_duration', 0),
                **creds_data
            }
            dialog = JsonEditorDialog(f"DB Credentials: {role_name}", lease_info, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to generate credentials: {response.error}")
    
    def _show_database_static_role(self, mount_path: str, name: str):
        """View static database role."""
        response = self.client.database_read_static_role(mount_path, name)
        if response.ok:
            dialog = JsonEditorDialog(f"Static DB Role: {name}", response.data, readonly=True)
            dialog.exec()
    
    def _edit_database_static_role(self, mount_path: str, name: str):
        """Edit static database role."""
        from app.dialogs import DatabaseRoleDialog
        response = self.client.database_read_static_role(mount_path, name)
        if response.ok:
            data = response.data.get('data', response.data)
            # Get list of connections for the dropdown
            conn_response = self.client.database_list_connections(mount_path)
            connections = conn_response.data.get('data', {}).get('keys', []) if conn_response.ok else []
            
            dialog = DatabaseRoleDialog(name=name, config=data, connections=connections, 
                                        is_static=True, is_new=False)
            dialog.saved.connect(lambda n, d: self._save_database_static_role(mount_path, n, d))
            dialog.exec()
    
    def _create_database_static_role(self, mount_path: str):
        """Create a new static database role."""
        from app.dialogs import DatabaseRoleDialog
        # Get list of connections for the dropdown
        conn_response = self.client.database_list_connections(mount_path)
        connections = conn_response.data.get('data', {}).get('keys', []) if conn_response.ok else []
        
        if not connections:
            QMessageBox.warning(None, "No Connections", 
                               "Please create a database connection first before creating roles.")
            return
        
        dialog = DatabaseRoleDialog(connections=connections, is_static=True, is_new=True)
        dialog.saved.connect(lambda name, d: self._save_database_static_role(mount_path, name, d))
        dialog.exec()
    
    def _save_database_static_role(self, mount_path: str, name: str, data: Dict):
        """Save static database role."""
        response = self.client.api_write(f"{mount_path}/static-roles/{name}", data)
        if response.ok:
            self.notification.emit("Static Role Saved", f"Static database role {name} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save static role: {response.error}")
    
    def _delete_database_static_role(self, mount_path: str, name: str):
        """Delete static database role."""
        reply = QMessageBox.question(None, "Delete Static Role",
                                     f"Delete static database role '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.database_delete_static_role(mount_path, name)
            if response.ok:
                self.notification.emit("Static Role Deleted", f"Static database role {name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _get_database_static_creds(self, mount_path: str, role_name: str):
        """Get current credentials for a static database role."""
        response = self.client.database_get_static_creds(mount_path, role_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Static DB Credentials: {role_name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to get credentials: {response.error}")
    
    def _rotate_database_static_role(self, mount_path: str, role_name: str):
        """Rotate credentials for a static database role."""
        response = self.client.database_rotate_static_role(mount_path, role_name)
        if response.ok:
            self.notification.emit("Credentials Rotated", f"Static role {role_name} credentials rotated")
            # Show the new credentials
            self._get_database_static_creds(mount_path, role_name)
        else:
            QMessageBox.warning(None, "Error", f"Failed to rotate: {response.error}")
    
    # ==================== SSH Engine Helpers ====================
    
    def _show_ssh_ca(self, mount_path: str):
        """View SSH CA public key."""
        response = self.client.ssh_read_ca_config(mount_path)
        if response.ok:
            dialog = JsonEditorDialog("SSH CA Public Key", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to read CA: {response.error}")
    
    def _configure_ssh_ca(self, mount_path: str):
        """Configure SSH CA."""
        template = {
            'generate_signing_key': True,
            'key_type': 'ssh-rsa',
            'key_bits': 4096,
        }
        
        dialog = JsonEditorDialog("Configure SSH CA", template, readonly=False)
        if dialog.exec():
            data = dialog.data
            response = self.client.api_write(f"{mount_path}/config/ca", data)
            if response.ok:
                self.notification.emit("CA Configured", "SSH CA has been configured")
                # Show the public key
                self._show_ssh_ca(mount_path)
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _delete_ssh_ca(self, mount_path: str):
        """Delete SSH CA configuration."""
        reply = QMessageBox.question(None, "Delete CA",
                                     "Delete SSH CA configuration?\nThis will invalidate all signed certificates.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.ssh_delete_ca(mount_path)
            if response.ok:
                self.notification.emit("CA Deleted", "SSH CA has been deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_ssh_zeroaddress(self, mount_path: str):
        """View SSH zero-address configuration."""
        response = self.client.ssh_read_zeroaddress(mount_path)
        if response.ok:
            dialog = JsonEditorDialog("SSH Zero-Address Config", response.data, readonly=False)
            dialog.saved.connect(lambda d: self._save_ssh_zeroaddress(mount_path, d))
            dialog.exec()
        else:
            # Show template if not configured
            template = {'roles': []}
            dialog = JsonEditorDialog("SSH Zero-Address Config", template, readonly=False)
            dialog.saved.connect(lambda d: self._save_ssh_zeroaddress(mount_path, d))
            dialog.exec()
    
    def _save_ssh_zeroaddress(self, mount_path: str, data: Dict):
        """Save SSH zero-address configuration."""
        response = self.client.api_write(f"{mount_path}/config/zeroaddress", data)
        if response.ok:
            self.notification.emit("Config Saved", "Zero-address configuration saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_ssh_role(self, mount_path: str, name: str):
        """View SSH role."""
        response = self.client.ssh_read_role(mount_path, name)
        if response.ok:
            dialog = JsonEditorDialog(f"SSH Role: {name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _edit_ssh_role(self, mount_path: str, name: str):
        """Edit SSH role."""
        from app.dialogs import SSHRoleDialog
        response = self.client.ssh_read_role(mount_path, name)
        if response.ok:
            data = response.data.get('data', response.data)
            dialog = SSHRoleDialog(name=name, config=data, is_new=False)
            dialog.saved.connect(lambda n, d: self._save_ssh_role(mount_path, n, d))
            dialog.exec()
    
    def _create_ssh_role(self, mount_path: str):
        """Create a new SSH role."""
        from app.dialogs import SSHRoleDialog
        dialog = SSHRoleDialog(is_new=True)
        dialog.saved.connect(lambda name, d: self._save_ssh_role(mount_path, name, d))
        dialog.exec()
    
    def _save_ssh_role(self, mount_path: str, name: str, data: Dict):
        """Save SSH role."""
        response = self.client.api_write(f"{mount_path}/roles/{name}", data)
        if response.ok:
            self.notification.emit("Role Saved", f"SSH role {name} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save role: {response.error}")
    
    def _delete_ssh_role(self, mount_path: str, name: str):
        """Delete SSH role."""
        reply = QMessageBox.question(None, "Delete Role",
                                     f"Delete SSH role '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.ssh_delete_role(mount_path, name)
            if response.ok:
                self.notification.emit("Role Deleted", f"SSH role {name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _sign_ssh_key_for_role(self, mount_path: str, role_name: str):
        """Sign an SSH public key using a specific role."""
        # Allow file selection or paste
        file_path, _ = QFileDialog.getOpenFileName(None, "Select Public Key", "", 
                                                   "Public Keys (*.pub);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    public_key = f.read().strip()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to read file: {e}")
                return
        else:
            public_key, ok = QInputDialog.getMultiLineText(None, "Sign SSH Key", "Paste public key:")
            if not ok or not public_key:
                return
        
        # Optional: get valid principals
        principals, ok = QInputDialog.getText(None, "Valid Principals (optional)", 
                                              "Comma-separated list of valid principals:")
        
        data = {'public_key': public_key}
        if ok and principals:
            data['valid_principals'] = principals
        
        response = self.client.api_write(f"{mount_path}/sign/{role_name}", data)
        if response.ok:
            signed_data = response.data.get('data', response.data)
            dialog = JsonEditorDialog(f"Signed SSH Certificate", signed_data, readonly=True)
            dialog.exec()
            
            # Offer to save the signed certificate
            if 'signed_key' in signed_data:
                reply = QMessageBox.question(None, "Save Certificate",
                                            "Save the signed certificate to a file?",
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    save_path, _ = QFileDialog.getSaveFileName(None, "Save Certificate", 
                                                               "id_rsa-cert.pub", 
                                                               "Certificate (*.pub);;All Files (*)")
                    if save_path:
                        with open(save_path, 'w') as f:
                            f.write(signed_data['signed_key'])
                        self.notification.emit("Certificate Saved", f"Saved to {save_path}")
        else:
            QMessageBox.warning(None, "Error", f"Failed to sign key: {response.error}")
    
    def _issue_ssh_creds_for_role(self, mount_path: str, role_name: str):
        """Issue SSH credentials (key pair + certificate) for a role."""
        response = self.client.ssh_issue_credential(mount_path, role_name)
        if response.ok:
            creds_data = response.data.get('data', response.data)
            dialog = JsonEditorDialog(f"SSH Credentials: {role_name}", creds_data, readonly=True)
            dialog.exec()
            
            # Offer to save the credentials
            if 'private_key' in creds_data:
                reply = QMessageBox.question(None, "Save Credentials",
                                            "Save the SSH credentials to files?",
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    base_path, _ = QFileDialog.getSaveFileName(None, "Save Private Key", 
                                                               "id_rsa_vault", 
                                                               "Key Files (*);;All Files (*)")
                    if base_path:
                        # Save private key
                        with open(base_path, 'w') as f:
                            f.write(creds_data['private_key'])
                        os.chmod(base_path, 0o600)
                        
                        # Save public key if present
                        if 'public_key' in creds_data:
                            with open(f"{base_path}.pub", 'w') as f:
                                f.write(creds_data['public_key'])
                        
                        # Save certificate if present
                        if 'signed_key' in creds_data:
                            with open(f"{base_path}-cert.pub", 'w') as f:
                                f.write(creds_data['signed_key'])
                        
                        self.notification.emit("Credentials Saved", f"Saved to {base_path}")
        else:
            QMessageBox.warning(None, "Error", f"Failed to issue credentials: {response.error}")
    
    # Legacy methods for backwards compatibility
    def _sign_ssh_key(self, mount_path: str):
        """Sign SSH key - legacy method that asks for role."""
        role, ok = QInputDialog.getText(None, "Sign SSH Key", "Role name:")
        if ok and role:
            self._sign_ssh_key_for_role(mount_path, role)
    
    def _issue_ssh_creds(self, mount_path: str):
        """Issue SSH credentials - legacy method that asks for role."""
        role, ok = QInputDialog.getText(None, "Issue SSH Credentials", "Role name:")
        if ok and role:
            self._issue_ssh_creds_for_role(mount_path, role)
    
    # ==================== Other Engine Helpers ====================
    
    def _show_aws_role(self, mount_path: str, name: str):
        response = self.client.api_read(f"{mount_path}/roles/{name}")
        if response.ok:
            dialog = JsonEditorDialog(f"AWS Role: {name}", response.data, readonly=True)
            dialog.exec()
    
    def _generate_aws_creds(self, mount_path: str):
        role, ok = QInputDialog.getText(None, "Generate AWS Credentials", "Role name:")
        if ok and role:
            response = self.client.api_read(f"{mount_path}/creds/{role}")
            if response.ok:
                dialog = JsonEditorDialog("AWS Credentials", response.data, readonly=True)
                dialog.exec()
    
    def _generate_aws_sts(self, mount_path: str):
        role, ok = QInputDialog.getText(None, "Generate STS Credentials", "Role name:")
        if ok and role:
            response = self.client.api_read(f"{mount_path}/sts/{role}")
            if response.ok:
                dialog = JsonEditorDialog("AWS STS Credentials", response.data, readonly=True)
                dialog.exec()
    
    def _show_totp_key(self, mount_path: str, name: str):
        response = self.client.api_read(f"{mount_path}/keys/{name}")
        if response.ok:
            dialog = JsonEditorDialog(f"TOTP Key: {name}", response.data, readonly=True)
            dialog.exec()
    
    def _create_totp_key(self, mount_path: str):
        name, ok = QInputDialog.getText(None, "Create TOTP Key", "Key name:")
        if ok and name:
            dialog = CrudDialog("TOTP Key", {
                'issuer': '',
                'account_name': '',
                'generate': True
            })
            if dialog.exec():
                data = dialog.data
                response = self.client.api_write(f"{mount_path}/keys/{name}", data)
                if response.ok:
                    self.notification.emit("TOTP Key Created", f"Key {name} created")
                    result_dialog = JsonEditorDialog("TOTP Key", response.data, readonly=True)
                    result_dialog.exec()
    
    def _generate_totp_code(self, mount_path: str):
        name, ok = QInputDialog.getText(None, "Generate TOTP Code", "Key name:")
        if ok and name:
            response = self.client.api_read(f"{mount_path}/code/{name}")
            if response.ok:
                code = response.data.get('data', {}).get('code', '')
                QMessageBox.information(None, "TOTP Code", f"Code: {code}")
    
    def _build_transit_menu(self, menu: QMenu, mount_path: str):
        """Build Transit engine menu."""
        # Keys submenu
        keys_menu = AsyncMenu("🔑 Keys", lambda: self._load_transit_keys(mount_path))
        keys_menu.set_submenu_factory(lambda t, d: self._create_transit_key_submenu(mount_path, t, d))
        keys_menu.set_new_item_callback(lambda: self._create_transit_key(mount_path), "➕ New Key...")
        menu.addMenu(keys_menu)
        
        menu.addSeparator()
        
        # Quick actions
        encrypt_action = menu.addAction("🔒 Encrypt Data")
        encrypt_action.triggered.connect(lambda: self._transit_encrypt_dialog(mount_path))
        
        decrypt_action = menu.addAction("🔓 Decrypt Data")
        decrypt_action.triggered.connect(lambda: self._transit_decrypt_dialog(mount_path))
        
        menu.addSeparator()
        
        sign_action = menu.addAction("✍️ Sign Data")
        sign_action.triggered.connect(lambda: self._transit_sign_dialog(mount_path))
        
        verify_action = menu.addAction("✅ Verify Signature")
        verify_action.triggered.connect(lambda: self._transit_verify_dialog(mount_path))
        
        menu.addSeparator()
        
        hmac_action = menu.addAction("#️⃣ Generate HMAC")
        hmac_action.triggered.connect(lambda: self._transit_hmac_dialog(mount_path))
        
        datakey_action = menu.addAction("🎲 Generate Data Key")
        datakey_action.triggered.connect(lambda: self._transit_datakey_dialog(mount_path))
    
    def _load_transit_keys(self, mount_path: str) -> list:
        response = self.client.transit_list_keys(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list keys")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [{'text': f"🔑 {k}", 'data': k, 'is_submenu': True} for k in keys]
    
    def _create_transit_key_submenu(self, mount_path: str, title: str, key_name: str) -> QMenu:
        menu = QMenu(title)
        
        info = menu.addAction("ℹ️ Key Info")
        info.triggered.connect(lambda: self._show_transit_key_info(mount_path, key_name))
        
        menu.addSeparator()
        
        # Key operations
        encrypt = menu.addAction("🔒 Encrypt")
        encrypt.triggered.connect(lambda: self._transit_encrypt_with_key(mount_path, key_name))
        
        decrypt = menu.addAction("🔓 Decrypt")
        decrypt.triggered.connect(lambda: self._transit_decrypt_with_key(mount_path, key_name))
        
        rewrap = menu.addAction("🔄 Rewrap")
        rewrap.triggered.connect(lambda: self._transit_rewrap_with_key(mount_path, key_name))
        
        menu.addSeparator()
        
        sign = menu.addAction("✍️ Sign")
        sign.triggered.connect(lambda: self._transit_sign_with_key(mount_path, key_name))
        
        verify = menu.addAction("✅ Verify")
        verify.triggered.connect(lambda: self._transit_verify_with_key(mount_path, key_name))
        
        hmac = menu.addAction("#️⃣ HMAC")
        hmac.triggered.connect(lambda: self._transit_hmac_with_key(mount_path, key_name))
        
        menu.addSeparator()
        
        rotate = menu.addAction("🔄 Rotate Key")
        rotate.triggered.connect(lambda: self._rotate_transit_key(mount_path, key_name))
        
        export = menu.addAction("📤 Export Key")
        export.triggered.connect(lambda: self._export_transit_key(mount_path, key_name))
        
        menu.addSeparator()
        
        config = menu.addAction("⚙️ Configure Key")
        config.triggered.connect(lambda: self._configure_transit_key(mount_path, key_name))
        
        delete = menu.addAction("🗑️ Delete Key")
        delete.triggered.connect(lambda: self._delete_transit_key(mount_path, key_name))
        
        return menu
    
    def _build_pki_menu(self, menu: QMenu, mount_path: str):
        """Build PKI engine menu."""
        # CA Certificate
        ca_menu = QMenu("📜 CA Certificate")
        
        view_ca = ca_menu.addAction("👁️ View CA Cert")
        view_ca.triggered.connect(lambda: self._show_pki_ca(mount_path))
        
        view_crl = ca_menu.addAction("📋 View CRL")
        view_crl.triggered.connect(lambda: self._show_pki_crl(mount_path))
        
        ca_menu.addSeparator()
        
        gen_root = ca_menu.addAction("🔐 Generate Root CA")
        gen_root.triggered.connect(lambda: self._generate_pki_root(mount_path))
        
        gen_inter = ca_menu.addAction("📄 Generate Intermediate CSR")
        gen_inter.triggered.connect(lambda: self._generate_pki_intermediate(mount_path))
        
        set_signed = ca_menu.addAction("📥 Set Signed Intermediate")
        set_signed.triggered.connect(lambda: self._set_pki_signed_intermediate(mount_path))
        
        menu.addMenu(ca_menu)
        
        menu.addSeparator()
        
        # Roles
        roles_menu = AsyncMenu("👤 Roles", lambda: self._load_pki_roles(mount_path))
        roles_menu.set_submenu_factory(lambda t, d: self._create_pki_role_submenu(mount_path, t, d))
        roles_menu.set_new_item_callback(lambda: self._create_pki_role(mount_path), "➕ New Role...")
        menu.addMenu(roles_menu)
        
        # Issuers
        issuers_menu = AsyncMenu("🏛️ Issuers", lambda: self._load_pki_issuers(mount_path))
        issuers_menu.set_item_callback(lambda d: self._show_pki_issuer(mount_path, d))
        menu.addMenu(issuers_menu)
        
        # Certificates
        certs_menu = AsyncMenu("📜 Certificates", lambda: self._load_pki_certs(mount_path))
        certs_menu.set_submenu_factory(lambda t, d: self._create_pki_cert_submenu(mount_path, t, d))
        menu.addMenu(certs_menu)
        
        menu.addSeparator()
        
        # Quick actions
        issue_cert = menu.addAction("📝 Issue Certificate")
        issue_cert.triggered.connect(lambda: self._issue_pki_cert_dialog(mount_path))
        
        sign_csr = menu.addAction("✍️ Sign CSR")
        sign_csr.triggered.connect(lambda: self._sign_pki_csr_dialog(mount_path))
        
        menu.addSeparator()
        
        tidy = menu.addAction("🧹 Tidy Cert Store")
        tidy.triggered.connect(lambda: self._tidy_pki(mount_path))
    
    def _load_pki_roles(self, mount_path: str) -> list:
        response = self.client.pki_list_roles(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [{'text': f"👤 {k}", 'data': k, 'is_submenu': True} for k in keys]
    
    def _create_pki_role_submenu(self, mount_path: str, title: str, role_name: str) -> QMenu:
        menu = QMenu(title)
        
        info = menu.addAction("ℹ️ Role Info")
        info.triggered.connect(lambda: self._show_pki_role_info(mount_path, role_name))
        
        menu.addSeparator()
        
        issue = menu.addAction("📝 Issue Certificate")
        issue.triggered.connect(lambda: self._issue_cert_for_role(mount_path, role_name))
        
        sign = menu.addAction("✍️ Sign CSR")
        sign.triggered.connect(lambda: self._sign_csr_for_role(mount_path, role_name))
        
        menu.addSeparator()
        
        edit = menu.addAction("✏️ Edit Role")
        edit.triggered.connect(lambda: self._edit_pki_role(mount_path, role_name))
        
        delete = menu.addAction("🗑️ Delete Role")
        delete.triggered.connect(lambda: self._delete_pki_role(mount_path, role_name))
        
        return menu
    
    def _load_pki_issuers(self, mount_path: str) -> list:
        response = self.client.pki_list_issuers(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list issuers")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"🏛️ {k[:16]}...", k) for k in keys]
    
    def _load_pki_certs(self, mount_path: str) -> list:
        response = self.client.pki_list_certs(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list certificates")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [{'text': f"📜 {k[:20]}...", 'data': k, 'is_submenu': True} for k in keys[:50]]  # Limit display
    
    def _create_pki_cert_submenu(self, mount_path: str, title: str, serial: str) -> QMenu:
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Certificate")
        view.triggered.connect(lambda: self._show_pki_cert(mount_path, serial))
        
        menu.addSeparator()
        
        revoke = menu.addAction("🚫 Revoke Certificate")
        revoke.triggered.connect(lambda: self._revoke_pki_cert(mount_path, serial))
        
        return menu
    
    def _create_auth_menu(self) -> QMenu:
        menu = AsyncMenu("🔓 Auth Methods", self._load_auth_methods)
        menu.set_submenu_factory(self._create_auth_method_submenu)
        menu.set_new_item_callback(self._enable_auth_method, "➕ Enable Method...")
        return menu
    
    def _load_auth_methods(self) -> list:
        response = self.client.list_auth_methods()
        if not response.ok:
            raise Exception(response.error or "Failed to list auth methods")
        
        methods = response.data.get('data', response.data) if response.data else {}
        items = []
        
        for path, info in methods.items():
            method_type = info.get('type', 'unknown')
            icon = {'token': '🎫', 'userpass': '👤', 'ldap': '📒', 'approle': '🤖',
                    'aws': '☁️', 'kubernetes': '☸️', 'oidc': '🔐', 'jwt': '🎟️'}.get(method_type, '🔑')
            
            items.append({
                'text': f"{icon} {path.rstrip('/')} ({method_type})",
                'data': {'path': path.rstrip('/'), 'type': method_type, 'info': info},
                'is_submenu': True
            })
        return items
    
    def _create_auth_method_submenu(self, title: str, data: Dict) -> QMenu:
        """Create submenu for an auth method based on its type."""
        path = data.get('path', '')
        method_type = data.get('type', 'unknown')
        info = data.get('info', {})
        
        menu = QMenu(title)
        
        # Common actions for all auth methods
        view_config = menu.addAction("ℹ️ View Configuration")
        view_config.triggered.connect(lambda: self._view_auth_config(path, info))
        
        tune = menu.addAction("🔧 Tune Settings")
        tune.triggered.connect(lambda: self._tune_auth_method(path))
        
        menu.addSeparator()
        
        # Type-specific menus
        if method_type == 'userpass':
            self._build_userpass_menu(menu, path)
        elif method_type == 'approle':
            self._build_approle_menu(menu, path)
        elif method_type == 'token':
            self._build_token_auth_menu(menu)
        elif method_type == 'ldap':
            self._build_ldap_menu(menu, path)
        elif method_type in ('oidc', 'jwt'):
            self._build_oidc_menu(menu, path, method_type)
        elif method_type == 'kubernetes':
            self._build_kubernetes_menu(menu, path)
        else:
            # Generic auth method
            self._build_generic_auth_menu(menu, path)
        
        menu.addSeparator()
        
        disable = menu.addAction("🗑️ Disable Auth Method")
        disable.triggered.connect(lambda: self._disable_auth(path))
        
        return menu
    
    def _view_auth_config(self, path: str, info: Dict):
        """View auth method configuration."""
        # Combine sys/auth info with any method-specific config
        config_data = {'mount_info': info}
        
        # Try to get method-specific config
        response = self.client.read_auth_method(path)
        if response.ok and response.data:
            config_data['tune'] = response.data.get('data', response.data)
        
        dialog = JsonEditorDialog(f"Auth: {path}", config_data, readonly=True)
        dialog.exec()
    
    def _tune_auth_method(self, path: str):
        """Tune an auth method's settings."""
        # Get current config
        response = self.client.read_auth_method(path)
        current = response.data.get('data', {}) if response.ok else {}
        
        dialog = CrudDialog(f"Tune: {path}", {
            'default_lease_ttl': current.get('default_lease_ttl', ''),
            'max_lease_ttl': current.get('max_lease_ttl', ''),
            'description': current.get('description', ''),
            'listing_visibility': current.get('listing_visibility', 'hidden'),
            'token_type': current.get('token_type', 'default')
        })
        
        if dialog.exec():
            data = dialog.data
            response = self.client.tune_auth_method(
                path,
                default_lease_ttl=data.get('default_lease_ttl') or None,
                max_lease_ttl=data.get('max_lease_ttl') or None,
                description=data.get('description') or None,
                listing_visibility=data.get('listing_visibility') or None,
                token_type=data.get('token_type') or None
            )
            if response.ok:
                self.notification.emit("Auth Tuned", f"Auth method {path} updated")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _disable_auth(self, path: str):
        """Disable an auth method."""
        reply = QMessageBox.warning(
            None, "Disable Auth Method",
            f"⚠️ Disable auth method '{path}'?\n\nThis will revoke all tokens issued by this method!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.disable_auth_method(path)
            if response.ok:
                self.notification.emit("Auth Disabled", f"Auth method {path} disabled")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    # ============ Userpass Auth Menu ============
    
    def _build_userpass_menu(self, menu: QMenu, mount_path: str):
        """Build userpass-specific menu items."""
        users_menu = AsyncMenu("👤 Users", lambda: self._load_userpass_users(mount_path))
        users_menu.set_submenu_factory(lambda t, d: self._create_userpass_user_submenu(mount_path, t, d))
        users_menu.set_new_item_callback(lambda: self._create_userpass_user(mount_path), "➕ New User...")
        menu.addMenu(users_menu)
    
    def _load_userpass_users(self, mount_path: str) -> list:
        """Load userpass users."""
        response = self.client.userpass_list_users(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list users")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [{'text': f"👤 {u}", 'data': {'username': u}, 'is_submenu': True} for u in keys]
    
    def _create_userpass_user_submenu(self, mount_path: str, title: str, data: Dict) -> QMenu:
        """Create submenu for a userpass user."""
        username = data.get('username', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View User")
        view.triggered.connect(lambda: self._view_userpass_user(mount_path, username))
        
        edit = menu.addAction("✏️ Edit User")
        edit.triggered.connect(lambda: self._edit_userpass_user(mount_path, username))
        
        change_pwd = menu.addAction("🔑 Change Password")
        change_pwd.triggered.connect(lambda: self._change_userpass_password(mount_path, username))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete User")
        delete.triggered.connect(lambda: self._delete_userpass_user(mount_path, username))
        
        return menu
    
    def _view_userpass_user(self, mount_path: str, username: str):
        """View userpass user details."""
        response = self.client.userpass_read_user(mount_path, username)
        if response.ok:
            dialog = JsonEditorDialog(f"User: {username}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to read user: {response.error}")
    
    def _create_userpass_user(self, mount_path: str):
        """Create a new userpass user."""
        username, ok = QInputDialog.getText(None, "New User", "Username:")
        if not ok or not username:
            return
        
        password, ok = QInputDialog.getText(None, "Password", "Password:", 
                                            QLineEdit.EchoMode.Password)
        if not ok or not password:
            return
        
        dialog = CrudDialog(f"New User: {username}", {
            'policies': '',
            'ttl': '',
            'max_ttl': ''
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            
            response = self.client.userpass_create_user(
                mount_path, username, password,
                policies=policies if policies else None,
                ttl=data.get('ttl') or None,
                max_ttl=data.get('max_ttl') or None
            )
            if response.ok:
                self.notification.emit("User Created", f"User {username} created")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _edit_userpass_user(self, mount_path: str, username: str):
        """Edit a userpass user."""
        response = self.client.userpass_read_user(mount_path, username)
        if not response.ok:
            QMessageBox.warning(None, "Error", f"Failed to read user: {response.error}")
            return
        
        user_data = response.data.get('data', {})
        policies = ', '.join(user_data.get('policies', []) or user_data.get('token_policies', []))
        
        dialog = CrudDialog(f"Edit User: {username}", {
            'policies': policies,
            'ttl': str(user_data.get('ttl', '') or user_data.get('token_ttl', '')),
            'max_ttl': str(user_data.get('max_ttl', '') or user_data.get('token_max_ttl', ''))
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            
            response = self.client.userpass_update_user(
                mount_path, username,
                policies=policies if policies else None,
                ttl=data.get('ttl') or None,
                max_ttl=data.get('max_ttl') or None
            )
            if response.ok:
                self.notification.emit("User Updated", f"User {username} updated")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _change_userpass_password(self, mount_path: str, username: str):
        """Change a user's password."""
        password, ok = QInputDialog.getText(None, "Change Password", 
                                            f"New password for {username}:",
                                            QLineEdit.EchoMode.Password)
        if ok and password:
            response = self.client.userpass_update_password(mount_path, username, password)
            if response.ok:
                self.notification.emit("Password Changed", f"Password for {username} updated")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _delete_userpass_user(self, mount_path: str, username: str):
        """Delete a userpass user."""
        reply = QMessageBox.question(None, "Delete User", f"Delete user '{username}'?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.userpass_delete_user(mount_path, username)
            if response.ok:
                self.notification.emit("User Deleted", f"User {username} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    # ============ AppRole Auth Menu ============
    
    def _build_approle_menu(self, menu: QMenu, mount_path: str):
        """Build AppRole-specific menu items."""
        roles_menu = AsyncMenu("🤖 Roles", lambda: self._load_approle_roles(mount_path))
        roles_menu.set_submenu_factory(lambda t, d: self._create_approle_role_submenu(mount_path, t, d))
        roles_menu.set_new_item_callback(lambda: self._create_approle_role(mount_path), "➕ New Role...")
        menu.addMenu(roles_menu)
    
    def _load_approle_roles(self, mount_path: str) -> list:
        """Load AppRole roles."""
        response = self.client.approle_list_roles(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [{'text': f"🤖 {r}", 'data': {'role_name': r}, 'is_submenu': True} for r in keys]
    
    def _create_approle_role_submenu(self, mount_path: str, title: str, data: Dict) -> QMenu:
        """Create submenu for an AppRole role."""
        role_name = data.get('role_name', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Role")
        view.triggered.connect(lambda: self._view_approle_role(mount_path, role_name))
        
        edit = menu.addAction("✏️ Edit Role")
        edit.triggered.connect(lambda: self._edit_approle_role(mount_path, role_name))
        
        menu.addSeparator()
        
        get_role_id = menu.addAction("🆔 Get Role ID")
        get_role_id.triggered.connect(lambda: self._get_approle_role_id(mount_path, role_name))
        
        gen_secret = menu.addAction("🔐 Generate Secret ID")
        gen_secret.triggered.connect(lambda: self._generate_approle_secret(mount_path, role_name))
        
        list_secrets = menu.addAction("📋 List Secret IDs")
        list_secrets.triggered.connect(lambda: self._list_approle_secrets(mount_path, role_name))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Role")
        delete.triggered.connect(lambda: self._delete_approle_role(mount_path, role_name))
        
        return menu
    
    def _view_approle_role(self, mount_path: str, role_name: str):
        """View AppRole role details."""
        response = self.client.approle_read_role(mount_path, role_name)
        if response.ok:
            dialog = JsonEditorDialog(f"AppRole: {role_name}", response.data, readonly=True)
            dialog.exec()
    
    def _create_approle_role(self, mount_path: str):
        """Create a new AppRole role."""
        role_name, ok = QInputDialog.getText(None, "New Role", "Role name:")
        if not ok or not role_name:
            return
        
        dialog = CrudDialog(f"New AppRole: {role_name}", {
            'bind_secret_id': True,
            'token_policies': '',
            'token_ttl': '',
            'token_max_ttl': '',
            'secret_id_bound_cidrs': ''
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('token_policies', '').split(',') if p.strip()]
            cidrs = [c.strip() for c in data.get('secret_id_bound_cidrs', '').split(',') if c.strip()]
            
            response = self.client.approle_create_role(
                mount_path, role_name,
                bind_secret_id=data.get('bind_secret_id', True),
                token_policies=policies if policies else None,
                token_ttl=data.get('token_ttl') or None,
                token_max_ttl=data.get('token_max_ttl') or None,
                secret_id_bound_cidrs=cidrs if cidrs else None
            )
            if response.ok:
                self.notification.emit("Role Created", f"AppRole {role_name} created")
    
    def _edit_approle_role(self, mount_path: str, role_name: str):
        """Edit an AppRole role."""
        response = self.client.approle_read_role(mount_path, role_name)
        if not response.ok:
            return
        
        role_data = response.data.get('data', {})
        
        dialog = CrudDialog(f"Edit AppRole: {role_name}", {
            'bind_secret_id': role_data.get('bind_secret_id', True),
            'token_policies': ', '.join(role_data.get('token_policies', [])),
            'token_ttl': str(role_data.get('token_ttl', '')),
            'token_max_ttl': str(role_data.get('token_max_ttl', '')),
            'secret_id_bound_cidrs': ', '.join(role_data.get('secret_id_bound_cidrs', []) or [])
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('token_policies', '').split(',') if p.strip()]
            cidrs = [c.strip() for c in data.get('secret_id_bound_cidrs', '').split(',') if c.strip()]
            
            self.client.approle_create_role(
                mount_path, role_name,
                bind_secret_id=data.get('bind_secret_id', True),
                token_policies=policies if policies else None,
                token_ttl=data.get('token_ttl') or None,
                token_max_ttl=data.get('token_max_ttl') or None,
                secret_id_bound_cidrs=cidrs if cidrs else None
            )
            self.notification.emit("Role Updated", f"AppRole {role_name} updated")
    
    def _get_approle_role_id(self, mount_path: str, role_name: str):
        """Get the Role ID for an AppRole."""
        response = self.client.approle_read_role_id(mount_path, role_name)
        if response.ok:
            role_id = response.data.get('data', {}).get('role_id', '')
            dialog = JsonEditorDialog(f"Role ID: {role_name}", {'role_id': role_id}, readonly=True)
            dialog.exec()
    
    def _generate_approle_secret(self, mount_path: str, role_name: str):
        """Generate a new Secret ID for an AppRole."""
        dialog = CrudDialog(f"Generate Secret ID: {role_name}", {
            'ttl': '',
            'cidr_list': '',
            'metadata': '{}'
        })
        
        if dialog.exec():
            data = dialog.data
            cidrs = [c.strip() for c in data.get('cidr_list', '').split(',') if c.strip()]
            try:
                metadata = json.loads(data.get('metadata', '{}'))
            except:
                metadata = None
            
            response = self.client.approle_generate_secret_id(
                mount_path, role_name,
                ttl=data.get('ttl') or None,
                cidr_list=cidrs if cidrs else None,
                metadata=metadata
            )
            if response.ok:
                secret_data = response.data.get('data', {})
                dialog = JsonEditorDialog("Generated Secret ID", secret_data, readonly=True)
                dialog.exec()
                self.notification.emit("Secret ID Generated", f"New Secret ID for {role_name}")
    
    def _list_approle_secrets(self, mount_path: str, role_name: str):
        """List Secret ID accessors for an AppRole."""
        response = self.client.approle_list_secret_ids(mount_path, role_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Secret IDs: {role_name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.information(None, "No Secrets", "No Secret IDs found for this role")
    
    def _delete_approle_role(self, mount_path: str, role_name: str):
        """Delete an AppRole role."""
        reply = QMessageBox.question(None, "Delete Role", f"Delete AppRole '{role_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.approle_delete_role(mount_path, role_name)
            if response.ok:
                self.notification.emit("Role Deleted", f"AppRole {role_name} deleted")
    
    # ============ Token Auth Menu ============
    
    def _build_token_auth_menu(self, menu: QMenu):
        """Build token auth-specific menu items."""
        roles_menu = AsyncMenu("🎫 Token Roles", self._load_token_roles)
        roles_menu.set_submenu_factory(self._create_token_role_submenu)
        roles_menu.set_new_item_callback(self._create_token_role, "➕ New Role...")
        menu.addMenu(roles_menu)
    
    def _load_token_roles(self) -> list:
        """Load token roles."""
        response = self.client.token_list_roles()
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list token roles")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [{'text': f"🎫 {r}", 'data': {'role_name': r}, 'is_submenu': True} for r in keys]
    
    def _create_token_role_submenu(self, title: str, data: Dict) -> QMenu:
        """Create submenu for a token role."""
        role_name = data.get('role_name', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Role")
        view.triggered.connect(lambda: self._view_token_role(role_name))
        
        edit = menu.addAction("✏️ Edit Role")
        edit.triggered.connect(lambda: self._edit_token_role(role_name))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Role")
        delete.triggered.connect(lambda: self._delete_token_role(role_name))
        
        return menu
    
    def _view_token_role(self, role_name: str):
        """View token role details."""
        response = self.client.token_read_role(role_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Token Role: {role_name}", response.data, readonly=True)
            dialog.exec()
    
    def _create_token_role(self):
        """Create a new token role."""
        role_name, ok = QInputDialog.getText(None, "New Token Role", "Role name:")
        if not ok or not role_name:
            return
        
        dialog = CrudDialog(f"New Token Role: {role_name}", {
            'allowed_policies': '',
            'orphan': False,
            'renewable': True,
            'token_period': '',
            'token_explicit_max_ttl': ''
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('allowed_policies', '').split(',') if p.strip()]
            
            response = self.client.token_create_role(
                role_name,
                allowed_policies=policies if policies else None,
                orphan=data.get('orphan', False),
                renewable=data.get('renewable', True),
                token_period=data.get('token_period') or None,
                token_explicit_max_ttl=data.get('token_explicit_max_ttl') or None
            )
            if response.ok:
                self.notification.emit("Role Created", f"Token role {role_name} created")
    
    def _edit_token_role(self, role_name: str):
        """Edit a token role."""
        response = self.client.token_read_role(role_name)
        if not response.ok:
            return
        
        role_data = response.data.get('data', {})
        
        dialog = CrudDialog(f"Edit Token Role: {role_name}", {
            'allowed_policies': ', '.join(role_data.get('allowed_policies', [])),
            'orphan': role_data.get('orphan', False),
            'renewable': role_data.get('renewable', True),
            'token_period': str(role_data.get('token_period', '')),
            'token_explicit_max_ttl': str(role_data.get('token_explicit_max_ttl', ''))
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('allowed_policies', '').split(',') if p.strip()]
            
            self.client.token_create_role(
                role_name,
                allowed_policies=policies if policies else None,
                orphan=data.get('orphan', False),
                renewable=data.get('renewable', True),
                token_period=data.get('token_period') or None,
                token_explicit_max_ttl=data.get('token_explicit_max_ttl') or None
            )
            self.notification.emit("Role Updated", f"Token role {role_name} updated")
    
    def _delete_token_role(self, role_name: str):
        """Delete a token role."""
        reply = QMessageBox.question(None, "Delete Role", f"Delete token role '{role_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.token_delete_role(role_name)
            if response.ok:
                self.notification.emit("Role Deleted", f"Token role {role_name} deleted")
    
    # ============ LDAP Auth Menu ============
    
    def _build_ldap_menu(self, menu: QMenu, mount_path: str):
        """Build LDAP-specific menu items."""
        config = menu.addAction("⚙️ LDAP Configuration")
        config.triggered.connect(lambda: self._show_ldap_config(mount_path))
        
        menu.addSeparator()
        
        groups_menu = AsyncMenu("👥 Groups", lambda: self._load_ldap_groups(mount_path))
        groups_menu.set_submenu_factory(lambda t, d: self._create_ldap_group_submenu(mount_path, t, d))
        groups_menu.set_new_item_callback(lambda: self._create_ldap_group(mount_path), "➕ New Group...")
        menu.addMenu(groups_menu)
        
        users_menu = AsyncMenu("👤 Users", lambda: self._load_ldap_users(mount_path))
        users_menu.set_submenu_factory(lambda t, d: self._create_ldap_user_submenu(mount_path, t, d))
        users_menu.set_new_item_callback(lambda: self._create_ldap_user(mount_path), "➕ New User...")
        menu.addMenu(users_menu)
    
    def _show_ldap_config(self, mount_path: str):
        """Show LDAP configuration."""
        response = self.client.ldap_read_config(mount_path)
        if response.ok:
            dialog = JsonEditorDialog(f"LDAP Config: {mount_path}", response.data, readonly=True)
            dialog.exec()
    
    def _load_ldap_groups(self, mount_path: str) -> list:
        """Load LDAP groups."""
        response = self.client.ldap_list_groups(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list groups")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [{'text': f"👥 {g}", 'data': {'name': g}, 'is_submenu': True} for g in keys]
    
    def _create_ldap_group_submenu(self, mount_path: str, title: str, data: Dict) -> QMenu:
        """Create submenu for an LDAP group."""
        name = data.get('name', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Group")
        view.triggered.connect(lambda: self._view_ldap_group(mount_path, name))
        
        edit = menu.addAction("✏️ Edit Policies")
        edit.triggered.connect(lambda: self._edit_ldap_group(mount_path, name))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Group")
        delete.triggered.connect(lambda: self._delete_ldap_group(mount_path, name))
        
        return menu
    
    def _view_ldap_group(self, mount_path: str, name: str):
        """View LDAP group details."""
        response = self.client.ldap_read_group(mount_path, name)
        if response.ok:
            dialog = JsonEditorDialog(f"LDAP Group: {name}", response.data, readonly=True)
            dialog.exec()
    
    def _create_ldap_group(self, mount_path: str):
        """Create an LDAP group mapping."""
        name, ok = QInputDialog.getText(None, "New LDAP Group", "Group name:")
        if not ok or not name:
            return
        
        policies, ok = QInputDialog.getText(None, "Policies", "Policies (comma-separated):")
        if ok:
            policy_list = [p.strip() for p in policies.split(',') if p.strip()]
            response = self.client.ldap_write_group(mount_path, name, policy_list)
            if response.ok:
                self.notification.emit("Group Created", f"LDAP group {name} created")
    
    def _edit_ldap_group(self, mount_path: str, name: str):
        """Edit an LDAP group's policies."""
        response = self.client.ldap_read_group(mount_path, name)
        if not response.ok:
            return
        
        current = ', '.join(response.data.get('data', {}).get('policies', []))
        policies, ok = QInputDialog.getText(None, f"Edit {name}", "Policies:", text=current)
        if ok:
            policy_list = [p.strip() for p in policies.split(',') if p.strip()]
            self.client.ldap_write_group(mount_path, name, policy_list)
            self.notification.emit("Group Updated", f"LDAP group {name} updated")
    
    def _delete_ldap_group(self, mount_path: str, name: str):
        """Delete an LDAP group."""
        reply = QMessageBox.question(None, "Delete Group", f"Delete LDAP group '{name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.ldap_delete_group(mount_path, name)
            if response.ok:
                self.notification.emit("Group Deleted", f"LDAP group {name} deleted")
    
    def _load_ldap_users(self, mount_path: str) -> list:
        """Load LDAP users."""
        response = self.client.ldap_list_users(mount_path)
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list users")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [{'text': f"👤 {u}", 'data': {'username': u}, 'is_submenu': True} for u in keys]
    
    def _create_ldap_user_submenu(self, mount_path: str, title: str, data: Dict) -> QMenu:
        """Create submenu for an LDAP user."""
        username = data.get('username', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View User")
        view.triggered.connect(lambda: self._view_ldap_user(mount_path, username))
        
        edit = menu.addAction("✏️ Edit User")
        edit.triggered.connect(lambda: self._edit_ldap_user(mount_path, username))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete User")
        delete.triggered.connect(lambda: self._delete_ldap_user(mount_path, username))
        
        return menu
    
    def _view_ldap_user(self, mount_path: str, username: str):
        """View LDAP user details."""
        response = self.client.ldap_read_user(mount_path, username)
        if response.ok:
            dialog = JsonEditorDialog(f"LDAP User: {username}", response.data, readonly=True)
            dialog.exec()
    
    def _create_ldap_user(self, mount_path: str):
        """Create an LDAP user mapping."""
        username, ok = QInputDialog.getText(None, "New LDAP User", "Username:")
        if not ok or not username:
            return
        
        dialog = CrudDialog(f"New LDAP User: {username}", {
            'policies': '',
            'groups': ''
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            groups = [g.strip() for g in data.get('groups', '').split(',') if g.strip()]
            
            response = self.client.ldap_write_user(
                mount_path, username,
                policies=policies if policies else None,
                groups=groups if groups else None
            )
            if response.ok:
                self.notification.emit("User Created", f"LDAP user {username} created")
    
    def _edit_ldap_user(self, mount_path: str, username: str):
        """Edit an LDAP user."""
        response = self.client.ldap_read_user(mount_path, username)
        if not response.ok:
            return
        
        user_data = response.data.get('data', {})
        
        dialog = CrudDialog(f"Edit LDAP User: {username}", {
            'policies': ', '.join(user_data.get('policies', [])),
            'groups': ', '.join(user_data.get('groups', []))
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            groups = [g.strip() for g in data.get('groups', '').split(',') if g.strip()]
            
            self.client.ldap_write_user(
                mount_path, username,
                policies=policies if policies else None,
                groups=groups if groups else None
            )
            self.notification.emit("User Updated", f"LDAP user {username} updated")
    
    def _delete_ldap_user(self, mount_path: str, username: str):
        """Delete an LDAP user."""
        reply = QMessageBox.question(None, "Delete User", f"Delete LDAP user '{username}'?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.ldap_delete_user(mount_path, username)
            if response.ok:
                self.notification.emit("User Deleted", f"LDAP user {username} deleted")
    
    # ============ OIDC/JWT Auth Menu ============
    
    def _build_oidc_menu(self, menu: QMenu, mount_path: str, method_type: str):
        """Build OIDC/JWT-specific menu items."""
        config = menu.addAction("⚙️ View Configuration")
        config.triggered.connect(lambda: self._show_oidc_config(mount_path))
        
        menu.addSeparator()
        
        roles_menu = AsyncMenu("👤 Roles", lambda: self._load_oidc_roles(mount_path))
        roles_menu.set_item_callback(lambda d: self._view_oidc_role(mount_path, d))
        menu.addMenu(roles_menu)
    
    def _show_oidc_config(self, mount_path: str):
        """Show OIDC configuration."""
        response = self.client.api_read(f"auth/{mount_path}/config")
        if response.ok:
            dialog = JsonEditorDialog(f"OIDC Config: {mount_path}", response.data, readonly=True)
            dialog.exec()
    
    def _load_oidc_roles(self, mount_path: str) -> list:
        """Load OIDC roles."""
        response = self.client.api_list(f"auth/{mount_path}/role")
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"👤 {r}", r) for r in keys]
    
    def _view_oidc_role(self, mount_path: str, role_name: str):
        """View OIDC role details."""
        response = self.client.api_read(f"auth/{mount_path}/role/{role_name}")
        if response.ok:
            dialog = JsonEditorDialog(f"OIDC Role: {role_name}", response.data, readonly=True)
            dialog.exec()
    
    # ============ Kubernetes Auth Menu ============
    
    def _build_kubernetes_menu(self, menu: QMenu, mount_path: str):
        """Build Kubernetes-specific menu items."""
        config = menu.addAction("⚙️ View Configuration")
        config.triggered.connect(lambda: self._show_k8s_config(mount_path))
        
        menu.addSeparator()
        
        roles_menu = AsyncMenu("☸️ Roles", lambda: self._load_k8s_roles(mount_path))
        roles_menu.set_item_callback(lambda d: self._view_k8s_role(mount_path, d))
        menu.addMenu(roles_menu)
    
    def _show_k8s_config(self, mount_path: str):
        """Show Kubernetes configuration."""
        response = self.client.api_read(f"auth/{mount_path}/config")
        if response.ok:
            dialog = JsonEditorDialog(f"K8s Config: {mount_path}", response.data, readonly=True)
            dialog.exec()
    
    def _load_k8s_roles(self, mount_path: str) -> list:
        """Load Kubernetes roles."""
        response = self.client.api_list(f"auth/{mount_path}/role")
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"☸️ {r}", r) for r in keys]
    
    def _view_k8s_role(self, mount_path: str, role_name: str):
        """View Kubernetes role details."""
        response = self.client.api_read(f"auth/{mount_path}/role/{role_name}")
        if response.ok:
            dialog = JsonEditorDialog(f"K8s Role: {role_name}", response.data, readonly=True)
            dialog.exec()
    
    # ============ Generic Auth Menu ============
    
    def _build_generic_auth_menu(self, menu: QMenu, mount_path: str):
        """Build generic auth menu for unknown auth types."""
        # Try to list roles
        roles_menu = AsyncMenu("📋 Roles", lambda: self._load_generic_auth_roles(mount_path))
        roles_menu.set_item_callback(lambda d: self._view_generic_auth_role(mount_path, d))
        menu.addMenu(roles_menu)
    
    def _load_generic_auth_roles(self, mount_path: str) -> list:
        """Load roles for generic auth method."""
        response = self.client.api_list(f"auth/{mount_path}/role")
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list roles")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"📋 {r}", r) for r in keys]
    
    def _view_generic_auth_role(self, mount_path: str, role_name: str):
        """View generic auth role details."""
        response = self.client.api_read(f"auth/{mount_path}/role/{role_name}")
        if response.ok:
            dialog = JsonEditorDialog(f"Role: {role_name}", response.data, readonly=True)
            dialog.exec()
    
    # ============ Identity Menu ============
    
    def _create_identity_menu(self) -> QMenu:
        """Create the Identity menu with Entities, Aliases, and Groups."""
        menu = QMenu("🪪 Identity")
        
        # Entities submenu
        entities_menu = AsyncMenu("👤 Entities", self._load_entities)
        entities_menu.set_submenu_factory(self._create_entity_submenu)
        entities_menu.set_new_item_callback(self._create_entity, "➕ New Entity...")
        menu.addMenu(entities_menu)
        
        # Entity Aliases submenu
        aliases_menu = AsyncMenu("🔗 Entity Aliases", self._load_entity_aliases)
        aliases_menu.set_submenu_factory(self._create_entity_alias_submenu)
        aliases_menu.set_new_item_callback(self._create_entity_alias, "➕ New Alias...")
        menu.addMenu(aliases_menu)
        
        menu.addSeparator()
        
        # Groups submenu
        groups_menu = AsyncMenu("👥 Groups", self._load_groups)
        groups_menu.set_submenu_factory(self._create_group_submenu)
        groups_menu.set_new_item_callback(self._create_group, "➕ New Group...")
        menu.addMenu(groups_menu)
        
        # Group Aliases submenu
        group_aliases_menu = AsyncMenu("🔗 Group Aliases", self._load_group_aliases)
        group_aliases_menu.set_submenu_factory(self._create_group_alias_submenu)
        group_aliases_menu.set_new_item_callback(self._create_group_alias, "➕ New Group Alias...")
        menu.addMenu(group_aliases_menu)
        
        menu.addSeparator()
        
        # Lookup actions
        lookup_entity = menu.addAction("🔍 Lookup Entity")
        lookup_entity.triggered.connect(self._lookup_entity_dialog)
        
        lookup_group = menu.addAction("🔍 Lookup Group")
        lookup_group.triggered.connect(self._lookup_group_dialog)
        
        menu.addSeparator()
        
        merge_entities = menu.addAction("🔀 Merge Entities")
        merge_entities.triggered.connect(self._merge_entities_dialog)
        
        return menu
    
    # ============ Entity Loaders and Menus ============
    
    def _load_entities(self) -> list:
        """Load all entities by name."""
        response = self.client.identity_list_entities_by_name()
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list entities")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        items = []
        for name in keys:
            items.append({
                'text': f"👤 {name}",
                'data': {'name': name},
                'is_submenu': True
            })
        return items
    
    def _create_entity_submenu(self, title: str, data: Dict) -> QMenu:
        """Create submenu for an entity."""
        entity_name = data.get('name', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Entity")
        view.triggered.connect(lambda: self._view_entity_by_name(entity_name))
        
        edit = menu.addAction("✏️ Edit Entity")
        edit.triggered.connect(lambda: self._edit_entity_by_name(entity_name))
        
        menu.addSeparator()
        
        # Entity aliases submenu
        aliases_menu = AsyncMenu("🔗 Aliases", lambda: self._load_entity_aliases_for_entity(entity_name))
        aliases_menu.set_item_callback(lambda d: self._view_entity_alias(d))
        menu.addMenu(aliases_menu)
        
        add_alias = menu.addAction("➕ Add Alias")
        add_alias.triggered.connect(lambda: self._add_alias_to_entity(entity_name))
        
        menu.addSeparator()
        
        # Groups this entity belongs to
        groups_menu = AsyncMenu("👥 Member Of Groups", lambda: self._load_groups_for_entity(entity_name))
        menu.addMenu(groups_menu)
        
        menu.addSeparator()
        
        disable = menu.addAction("🚫 Disable Entity")
        disable.triggered.connect(lambda: self._disable_entity(entity_name))
        
        delete = menu.addAction("🗑️ Delete Entity")
        delete.triggered.connect(lambda: self._delete_entity_by_name(entity_name))
        
        return menu
    
    def _view_entity_by_name(self, name: str):
        """View entity details by name."""
        response = self.client.identity_read_entity_by_name(name)
        if response.ok:
            dialog = JsonEditorDialog(f"Entity: {name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to read entity: {response.error}")
    
    def _edit_entity_by_name(self, name: str):
        """Edit an entity by name."""
        response = self.client.identity_read_entity_by_name(name)
        if not response.ok:
            QMessageBox.warning(None, "Error", f"Failed to read entity: {response.error}")
            return
        
        entity_data = response.data.get('data', {})
        entity_id = entity_data.get('id', '')
        
        dialog = CrudDialog(f"Edit Entity: {name}", {
            'name': entity_data.get('name', ''),
            'policies': ', '.join(entity_data.get('policies', [])),
            'disabled': entity_data.get('disabled', False),
            'metadata': json.dumps(entity_data.get('metadata', {}))
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            try:
                metadata = json.loads(data.get('metadata', '{}'))
            except:
                metadata = {}
            
            update_response = self.client.identity_update_entity(
                entity_id,
                name=data.get('name'),
                policies=policies if policies else None,
                metadata=metadata if metadata else None,
                disabled=data.get('disabled', False)
            )
            if update_response.ok:
                self.notification.emit("Entity Updated", f"Entity {name} updated")
            else:
                QMessageBox.warning(None, "Error", f"Failed to update: {update_response.error}")
    
    def _create_entity(self):
        """Create a new entity."""
        dialog = CrudDialog("New Entity", {
            'name': '',
            'policies': '',
            'metadata': '{}'
        })
        
        if dialog.exec():
            data = dialog.data
            name = data.get('name', '').strip()
            if not name:
                QMessageBox.warning(None, "Error", "Entity name is required")
                return
            
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            try:
                metadata = json.loads(data.get('metadata', '{}'))
            except:
                metadata = {}
            
            response = self.client.identity_create_entity(
                name=name,
                policies=policies if policies else None,
                metadata=metadata if metadata else None
            )
            if response.ok:
                self.notification.emit("Entity Created", f"Entity {name} created")
            else:
                QMessageBox.warning(None, "Error", f"Failed to create entity: {response.error}")
    
    def _delete_entity_by_name(self, name: str):
        """Delete an entity by name."""
        reply = QMessageBox.warning(
            None, "Delete Entity",
            f"⚠️ Delete entity '{name}'?\nThis will also delete all aliases.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.identity_delete_entity_by_name(name)
            if response.ok:
                self.notification.emit("Entity Deleted", f"Entity {name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed to delete: {response.error}")
    
    def _disable_entity(self, name: str):
        """Disable an entity."""
        response = self.client.identity_read_entity_by_name(name)
        if response.ok:
            entity_id = response.data.get('data', {}).get('id', '')
            update_response = self.client.identity_update_entity(entity_id, disabled=True)
            if update_response.ok:
                self.notification.emit("Entity Disabled", f"Entity {name} disabled")
    
    def _load_entity_aliases_for_entity(self, entity_name: str) -> list:
        """Load aliases for a specific entity."""
        response = self.client.identity_read_entity_by_name(entity_name)
        if not response.ok:
            return []
        
        aliases = response.data.get('data', {}).get('aliases', [])
        items = []
        for alias in aliases:
            alias_name = alias.get('name', 'unknown')
            mount_type = alias.get('mount_type', '')
            items.append((f"🔗 {alias_name} ({mount_type})", alias.get('id', '')))
        return items
    
    def _load_groups_for_entity(self, entity_name: str) -> list:
        """Load groups that an entity belongs to."""
        response = self.client.identity_read_entity_by_name(entity_name)
        if not response.ok:
            return []
        
        group_ids = response.data.get('data', {}).get('group_ids', [])
        items = []
        for gid in group_ids:
            g_response = self.client.identity_read_group(gid)
            if g_response.ok:
                g_name = g_response.data.get('data', {}).get('name', gid[:8])
                items.append((f"👥 {g_name}", gid))
            else:
                items.append((f"👥 {gid[:12]}...", gid))
        return items
    
    def _add_alias_to_entity(self, entity_name: str):
        """Add an alias to an entity."""
        response = self.client.identity_read_entity_by_name(entity_name)
        if not response.ok:
            QMessageBox.warning(None, "Error", "Failed to read entity")
            return
        
        entity_id = response.data.get('data', {}).get('id', '')
        
        auth_response = self.client.list_auth_methods()
        if not auth_response.ok:
            QMessageBox.warning(None, "Error", "Failed to list auth methods")
            return
        
        auth_methods = auth_response.data.get('data', auth_response.data) if auth_response.data else {}
        accessors = []
        accessor_map = {}
        for path, info in auth_methods.items():
            accessor = info.get('accessor', '')
            if accessor:
                label = f"{path.rstrip('/')} ({info.get('type', 'unknown')})"
                accessors.append(label)
                accessor_map[label] = accessor
        
        if not accessors:
            QMessageBox.warning(None, "Error", "No auth methods found")
            return
        
        alias_name, ok = QInputDialog.getText(None, "New Alias", "Alias name (e.g. username):")
        if not ok or not alias_name:
            return
        
        accessor_label, ok = QInputDialog.getItem(None, "Select Auth Method", "Mount:", accessors, 0, False)
        if not ok:
            return
        
        mount_accessor = accessor_map.get(accessor_label, '')
        
        response = self.client.identity_create_entity_alias(
            name=alias_name,
            canonical_id=entity_id,
            mount_accessor=mount_accessor
        )
        if response.ok:
            self.notification.emit("Alias Created", f"Alias {alias_name} added to {entity_name}")
        else:
            QMessageBox.warning(None, "Error", f"Failed to create alias: {response.error}")
    
    # ============ Entity Alias Loaders and Menus ============
    
    def _load_entity_aliases(self) -> list:
        """Load all entity aliases."""
        response = self.client.identity_list_entity_aliases()
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list aliases")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        items = []
        for alias_id in keys[:50]:  # Limit to avoid slow loading
            alias_response = self.client.identity_read_entity_alias(alias_id)
            if alias_response.ok:
                alias_data = alias_response.data.get('data', {})
                name = alias_data.get('name', alias_id[:8])
                mount_type = alias_data.get('mount_type', '')
                items.append({
                    'text': f"🔗 {name} ({mount_type})",
                    'data': {'id': alias_id, 'name': name},
                    'is_submenu': True
                })
        return items
    
    def _create_entity_alias_submenu(self, title: str, data: Dict) -> QMenu:
        """Create submenu for an entity alias."""
        alias_id = data.get('id', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Alias")
        view.triggered.connect(lambda: self._view_entity_alias(alias_id))
        
        edit = menu.addAction("✏️ Edit Alias")
        edit.triggered.connect(lambda: self._edit_entity_alias(alias_id))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Alias")
        delete.triggered.connect(lambda: self._delete_entity_alias(alias_id))
        
        return menu
    
    def _view_entity_alias(self, alias_id: str):
        """View entity alias details."""
        response = self.client.identity_read_entity_alias(alias_id)
        if response.ok:
            dialog = JsonEditorDialog("Entity Alias", response.data, readonly=True)
            dialog.exec()
    
    def _edit_entity_alias(self, alias_id: str):
        """Edit an entity alias."""
        response = self.client.identity_read_entity_alias(alias_id)
        if not response.ok:
            QMessageBox.warning(None, "Error", "Failed to read alias")
            return
        
        alias_data = response.data.get('data', {})
        dialog = CrudDialog("Edit Alias", {
            'name': alias_data.get('name', ''),
            'custom_metadata': json.dumps(alias_data.get('custom_metadata', {}))
        })
        
        if dialog.exec():
            data = dialog.data
            try:
                metadata = json.loads(data.get('custom_metadata', '{}'))
            except:
                metadata = {}
            
            update_response = self.client.identity_update_entity_alias(
                alias_id,
                name=data.get('name'),
                custom_metadata=metadata if metadata else None
            )
            if update_response.ok:
                self.notification.emit("Alias Updated", "Entity alias updated")
    
    def _create_entity_alias(self):
        """Create a new entity alias."""
        entities_response = self.client.identity_list_entities_by_name()
        if not entities_response.ok:
            QMessageBox.warning(None, "Error", "Failed to list entities")
            return
        
        entity_names = entities_response.data.get('data', {}).get('keys', [])
        if not entity_names:
            QMessageBox.warning(None, "Error", "No entities found. Create an entity first.")
            return
        
        entity_name, ok = QInputDialog.getItem(None, "Select Entity", "Entity:", entity_names, 0, False)
        if not ok:
            return
        
        entity_response = self.client.identity_read_entity_by_name(entity_name)
        if not entity_response.ok:
            return
        entity_id = entity_response.data.get('data', {}).get('id', '')
        
        auth_response = self.client.list_auth_methods()
        auth_methods = auth_response.data.get('data', auth_response.data) if auth_response.ok and auth_response.data else {}
        accessors = []
        accessor_map = {}
        for path, info in auth_methods.items():
            accessor = info.get('accessor', '')
            if accessor:
                label = f"{path.rstrip('/')} ({info.get('type', 'unknown')})"
                accessors.append(label)
                accessor_map[label] = accessor
        
        if not accessors:
            QMessageBox.warning(None, "Error", "No auth methods found")
            return
        
        alias_name, ok = QInputDialog.getText(None, "Alias Name", "Alias name:")
        if not ok or not alias_name:
            return
        
        accessor_label, ok = QInputDialog.getItem(None, "Auth Method", "Mount:", accessors, 0, False)
        if not ok:
            return
        
        mount_accessor = accessor_map.get(accessor_label, '')
        
        response = self.client.identity_create_entity_alias(
            name=alias_name,
            canonical_id=entity_id,
            mount_accessor=mount_accessor
        )
        if response.ok:
            self.notification.emit("Alias Created", f"Alias {alias_name} created")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _delete_entity_alias(self, alias_id: str):
        """Delete an entity alias."""
        reply = QMessageBox.question(None, "Delete Alias", "Delete this alias?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.identity_delete_entity_alias(alias_id)
            if response.ok:
                self.notification.emit("Alias Deleted", "Entity alias deleted")
    
    # ============ Group Loaders and Menus ============
    
    def _load_groups(self) -> list:
        """Load all groups by name."""
        response = self.client.identity_list_groups_by_name()
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list groups")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        items = []
        for name in keys:
            items.append({
                'text': f"👥 {name}",
                'data': {'name': name},
                'is_submenu': True
            })
        return items
    
    def _create_group_submenu(self, title: str, data: Dict) -> QMenu:
        """Create submenu for a group."""
        group_name = data.get('name', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Group")
        view.triggered.connect(lambda: self._view_group_by_name(group_name))
        
        edit = menu.addAction("✏️ Edit Group")
        edit.triggered.connect(lambda: self._edit_group_by_name(group_name))
        
        menu.addSeparator()
        
        members_menu = AsyncMenu("👤 Members", lambda: self._load_group_members(group_name))
        menu.addMenu(members_menu)
        
        add_member = menu.addAction("➕ Add Member")
        add_member.triggered.connect(lambda: self._add_member_to_group(group_name))
        
        menu.addSeparator()
        
        aliases_menu = AsyncMenu("🔗 Aliases", lambda: self._load_group_aliases_for_group(group_name))
        menu.addMenu(aliases_menu)
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Group")
        delete.triggered.connect(lambda: self._delete_group_by_name(group_name))
        
        return menu
    
    def _view_group_by_name(self, name: str):
        """View group details."""
        response = self.client.identity_read_group_by_name(name)
        if response.ok:
            dialog = JsonEditorDialog(f"Group: {name}", response.data, readonly=True)
            dialog.exec()
    
    def _edit_group_by_name(self, name: str):
        """Edit a group."""
        response = self.client.identity_read_group_by_name(name)
        if not response.ok:
            QMessageBox.warning(None, "Error", "Failed to read group")
            return
        
        group_data = response.data.get('data', {})
        group_id = group_data.get('id', '')
        
        dialog = CrudDialog(f"Edit Group: {name}", {
            'name': group_data.get('name', ''),
            'policies': ', '.join(group_data.get('policies', [])),
            'metadata': json.dumps(group_data.get('metadata', {}))
        })
        
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            try:
                metadata = json.loads(data.get('metadata', '{}'))
            except:
                metadata = {}
            
            update_response = self.client.identity_update_group(
                group_id,
                name=data.get('name'),
                policies=policies if policies else None,
                metadata=metadata if metadata else None
            )
            if update_response.ok:
                self.notification.emit("Group Updated", f"Group {name} updated")
    
    def _create_group(self):
        """Create a new group."""
        dialog = CrudDialog("New Group", {
            'name': '',
            'type': 'internal',
            'policies': '',
            'metadata': '{}'
        })
        
        if dialog.exec():
            data = dialog.data
            name = data.get('name', '').strip()
            if not name:
                QMessageBox.warning(None, "Error", "Group name is required")
                return
            
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            try:
                metadata = json.loads(data.get('metadata', '{}'))
            except:
                metadata = {}
            
            response = self.client.identity_create_group(
                name=name,
                group_type=data.get('type', 'internal'),
                policies=policies if policies else None,
                metadata=metadata if metadata else None
            )
            if response.ok:
                self.notification.emit("Group Created", f"Group {name} created")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _delete_group_by_name(self, name: str):
        """Delete a group."""
        reply = QMessageBox.warning(
            None, "Delete Group",
            f"Delete group '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.identity_delete_group_by_name(name)
            if response.ok:
                self.notification.emit("Group Deleted", f"Group {name} deleted")
    
    def _load_group_members(self, group_name: str) -> list:
        """Load members of a group."""
        response = self.client.identity_read_group_by_name(group_name)
        if not response.ok:
            return []
        
        group_data = response.data.get('data', {})
        member_entity_ids = group_data.get('member_entity_ids', []) or []
        
        items = []
        for eid in member_entity_ids:
            e_response = self.client.identity_read_entity(eid)
            if e_response.ok:
                e_name = e_response.data.get('data', {}).get('name', eid[:8])
                items.append((f"👤 {e_name}", eid))
            else:
                items.append((f"👤 {eid[:12]}...", eid))
        return items
    
    def _add_member_to_group(self, group_name: str):
        """Add a member entity to a group."""
        group_response = self.client.identity_read_group_by_name(group_name)
        if not group_response.ok:
            QMessageBox.warning(None, "Error", "Failed to read group")
            return
        
        group_data = group_response.data.get('data', {})
        group_id = group_data.get('id', '')
        current_members = group_data.get('member_entity_ids', []) or []
        
        entities_response = self.client.identity_list_entities_by_name()
        if not entities_response.ok:
            QMessageBox.warning(None, "Error", "Failed to list entities")
            return
        
        entity_names = entities_response.data.get('data', {}).get('keys', [])
        if not entity_names:
            QMessageBox.warning(None, "Error", "No entities available")
            return
        
        entity_name, ok = QInputDialog.getItem(None, "Add Member", "Select entity:", entity_names, 0, False)
        if not ok:
            return
        
        entity_response = self.client.identity_read_entity_by_name(entity_name)
        if not entity_response.ok:
            return
        entity_id = entity_response.data.get('data', {}).get('id', '')
        
        new_members = list(set(current_members + [entity_id]))
        
        response = self.client.identity_update_group(group_id, member_entity_ids=new_members)
        if response.ok:
            self.notification.emit("Member Added", f"Added {entity_name} to {group_name}")
    
    def _load_group_aliases_for_group(self, group_name: str) -> list:
        """Load aliases for a group."""
        response = self.client.identity_read_group_by_name(group_name)
        if not response.ok:
            return []
        
        alias = response.data.get('data', {}).get('alias', {})
        if alias:
            return [(f"🔗 {alias.get('name', 'unknown')}", alias.get('id', ''))]
        return []
    
    # ============ Group Alias Loaders and Menus ============
    
    def _load_group_aliases(self) -> list:
        """Load all group aliases."""
        response = self.client.identity_list_group_aliases()
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or "Failed to list group aliases")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        items = []
        for alias_id in keys[:50]:
            alias_response = self.client.identity_read_group_alias(alias_id)
            if alias_response.ok:
                alias_data = alias_response.data.get('data', {})
                name = alias_data.get('name', alias_id[:8])
                items.append({
                    'text': f"🔗 {name}",
                    'data': {'id': alias_id, 'name': name},
                    'is_submenu': True
                })
        return items
    
    def _create_group_alias_submenu(self, title: str, data: Dict) -> QMenu:
        """Create submenu for a group alias."""
        alias_id = data.get('id', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Alias")
        view.triggered.connect(lambda: self._view_group_alias(alias_id))
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Alias")
        delete.triggered.connect(lambda: self._delete_group_alias(alias_id))
        
        return menu
    
    def _view_group_alias(self, alias_id: str):
        """View group alias details."""
        response = self.client.identity_read_group_alias(alias_id)
        if response.ok:
            dialog = JsonEditorDialog("Group Alias", response.data, readonly=True)
            dialog.exec()
    
    def _create_group_alias(self):
        """Create a new group alias (for external groups)."""
        groups_response = self.client.identity_list_groups_by_name()
        if not groups_response.ok:
            QMessageBox.warning(None, "Error", "Failed to list groups")
            return
        
        group_names = groups_response.data.get('data', {}).get('keys', [])
        if not group_names:
            QMessageBox.warning(None, "Error", "No groups found")
            return
        
        group_name, ok = QInputDialog.getItem(None, "Select Group", "External group:", group_names, 0, False)
        if not ok:
            return
        
        group_response = self.client.identity_read_group_by_name(group_name)
        if not group_response.ok:
            return
        group_id = group_response.data.get('data', {}).get('id', '')
        
        auth_response = self.client.list_auth_methods()
        auth_methods = auth_response.data.get('data', {}) if auth_response.ok else {}
        accessors = []
        accessor_map = {}
        for path, info in auth_methods.items():
            accessor = info.get('accessor', '')
            if accessor:
                label = f"{path.rstrip('/')} ({info.get('type', 'unknown')})"
                accessors.append(label)
                accessor_map[label] = accessor
        
        if not accessors:
            QMessageBox.warning(None, "Error", "No auth methods found")
            return
        
        alias_name, ok = QInputDialog.getText(None, "Alias Name", "Group alias name:")
        if not ok or not alias_name:
            return
        
        accessor_label, ok = QInputDialog.getItem(None, "Auth Method", "Mount:", accessors, 0, False)
        if not ok:
            return
        
        mount_accessor = accessor_map.get(accessor_label, '')
        
        response = self.client.identity_create_group_alias(
            name=alias_name,
            canonical_id=group_id,
            mount_accessor=mount_accessor
        )
        if response.ok:
            self.notification.emit("Group Alias Created", f"Alias {alias_name} created")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _delete_group_alias(self, alias_id: str):
        """Delete a group alias."""
        reply = QMessageBox.question(None, "Delete Alias", "Delete this group alias?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.identity_delete_group_alias(alias_id)
            if response.ok:
                self.notification.emit("Alias Deleted", "Group alias deleted")
    
    # ============ Lookup and Merge ============
    
    def _lookup_entity_dialog(self):
        """Lookup an entity."""
        search_type, ok = QInputDialog.getItem(
            None, "Lookup Entity", "Search by:",
            ['Name', 'Entity ID', 'Alias Name'], 0, False
        )
        if not ok:
            return
        
        value, ok = QInputDialog.getText(None, "Lookup Entity", f"Enter {search_type.lower()}:")
        if not ok or not value:
            return
        
        if search_type == 'Name':
            response = self.client.identity_lookup_entity(name=value)
        elif search_type == 'Entity ID':
            response = self.client.identity_lookup_entity(entity_id=value)
        else:
            auth_response = self.client.list_auth_methods()
            auth_methods = auth_response.data.get('data', {}) if auth_response.ok else {}
            accessors = []
            accessor_map = {}
            for path, info in auth_methods.items():
                accessor = info.get('accessor', '')
                if accessor:
                    label = f"{path.rstrip('/')} ({info.get('type', 'unknown')})"
                    accessors.append(label)
                    accessor_map[label] = accessor
            
            accessor_label, ok = QInputDialog.getItem(None, "Auth Method", "Mount:", accessors, 0, False)
            if not ok:
                return
            mount_accessor = accessor_map.get(accessor_label, '')
            response = self.client.identity_lookup_entity(alias_name=value, alias_mount_accessor=mount_accessor)
        
        if response.ok:
            dialog = JsonEditorDialog("Entity Lookup Result", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Not Found", f"Entity not found: {response.error}")
    
    def _lookup_group_dialog(self):
        """Lookup a group."""
        search_type, ok = QInputDialog.getItem(
            None, "Lookup Group", "Search by:",
            ['Name', 'Group ID'], 0, False
        )
        if not ok:
            return
        
        value, ok = QInputDialog.getText(None, "Lookup Group", f"Enter {search_type.lower()}:")
        if not ok or not value:
            return
        
        if search_type == 'Name':
            response = self.client.identity_lookup_group(name=value)
        else:
            response = self.client.identity_lookup_group(group_id=value)
        
        if response.ok:
            dialog = JsonEditorDialog("Group Lookup Result", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Not Found", f"Group not found: {response.error}")
    
    def _merge_entities_dialog(self):
        """Merge multiple entities into one."""
        entities_response = self.client.identity_list_entities_by_name()
        if not entities_response.ok:
            QMessageBox.warning(None, "Error", "Failed to list entities")
            return
        
        entity_names = entities_response.data.get('data', {}).get('keys', [])
        if len(entity_names) < 2:
            QMessageBox.warning(None, "Error", "Need at least 2 entities to merge")
            return
        
        target_name, ok = QInputDialog.getItem(None, "Merge Entities", "Target entity (keep):", entity_names, 0, False)
        if not ok:
            return
        
        target_response = self.client.identity_read_entity_by_name(target_name)
        if not target_response.ok:
            return
        target_id = target_response.data.get('data', {}).get('id', '')
        
        remaining = [n for n in entity_names if n != target_name]
        source_name, ok = QInputDialog.getItem(None, "Merge Entities", "Source entity (merge into target):", remaining, 0, False)
        if not ok:
            return
        
        source_response = self.client.identity_read_entity_by_name(source_name)
        if not source_response.ok:
            return
        source_id = source_response.data.get('data', {}).get('id', '')
        
        reply = QMessageBox.warning(
            None, "Confirm Merge",
            f"Merge '{source_name}' into '{target_name}'?\n\nThis will delete {source_name}.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.identity_merge_entities(target_id, [source_id])
            if response.ok:
                self.notification.emit("Entities Merged", f"Merged {source_name} into {target_name}")
            else:
                QMessageBox.warning(None, "Error", f"Merge failed: {response.error}")
    
    def _create_policies_menu(self) -> QMenu:
        menu = AsyncMenu("📜 Policies", self._load_policies)
        menu.set_item_callback(self._show_policy)
        menu.set_new_item_callback(self._create_policy, "➕ New Policy...")
        return menu
    
    def _load_policies(self) -> list:
        response = self.client.list_policies()
        if not response.ok:
            raise Exception(response.error or "Failed to list policies")
        policies = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"📋 {p}", p) for p in policies]
    
    # ============ Namespaces Menu ============
    
    def _create_namespaces_menu(self) -> QMenu:
        """Create the Namespaces menu."""
        menu = QMenu("🏛️ Namespaces")
        
        # Current namespace indicator
        current_ns = self.settings.openbao.namespace or "(root)"
        current = menu.addAction(f"📍 Current: {current_ns}")
        current.setEnabled(False)
        
        menu.addSeparator()
        
        # List namespaces
        ns_list_menu = AsyncMenu("📋 List Namespaces", self._load_namespaces)
        ns_list_menu.set_submenu_factory(self._create_namespace_submenu)
        ns_list_menu.set_new_item_callback(self._create_namespace, "➕ New Namespace...")
        menu.addMenu(ns_list_menu)
        
        menu.addSeparator()
        
        # Switch namespace
        switch = menu.addAction("🔄 Switch Namespace")
        switch.triggered.connect(self._switch_namespace)
        
        # Go to root
        go_root = menu.addAction("🏠 Go to Root Namespace")
        go_root.triggered.connect(self._go_to_root_namespace)
        
        return menu
    
    def _load_namespaces(self) -> list:
        """Load list of namespaces."""
        response = self.client.list_namespaces()
        if not response.ok:
            if response.status_code == 404:
                return []
            # Namespaces might not be available (OSS version)
            if "path is unsupported" in str(response.error).lower():
                return [{'text': '⚠️ Enterprise feature', 'data': None, 'is_submenu': False}]
            raise Exception(response.error or "Failed to list namespaces")
        
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        items = []
        for ns in keys:
            ns_name = ns.rstrip('/')
            items.append({
                'text': f"🏛️ {ns_name}",
                'data': {'name': ns_name},
                'is_submenu': True
            })
        return items
    
    def _create_namespace_submenu(self, title: str, data: Dict) -> QMenu:
        """Create submenu for a namespace."""
        if data is None:
            return QMenu(title)
        
        ns_name = data.get('name', '')
        menu = QMenu(title)
        
        view = menu.addAction("👁️ View Details")
        view.triggered.connect(lambda: self._view_namespace(ns_name))
        
        switch = menu.addAction("🔄 Switch to This Namespace")
        switch.triggered.connect(lambda: self._do_switch_namespace(ns_name))
        
        menu.addSeparator()
        
        # Nested namespaces
        nested_menu = AsyncMenu("📂 Nested Namespaces", lambda: self._load_nested_namespaces(ns_name))
        nested_menu.set_submenu_factory(self._create_namespace_submenu)
        menu.addMenu(nested_menu)
        
        menu.addSeparator()
        
        delete = menu.addAction("🗑️ Delete Namespace")
        delete.triggered.connect(lambda: self._delete_namespace(ns_name))
        
        return menu
    
    def _load_nested_namespaces(self, parent_ns: str) -> list:
        """Load nested namespaces under a parent."""
        # Temporarily switch to parent namespace to list children
        old_ns = self.client.namespace
        self.client.namespace = parent_ns
        
        try:
            response = self.client.list_namespaces()
            if not response.ok:
                return []
            
            keys = response.data.get('data', {}).get('keys', []) if response.data else []
            items = []
            for ns in keys:
                ns_name = ns.rstrip('/')
                full_path = f"{parent_ns}/{ns_name}"
                items.append({
                    'text': f"🏛️ {ns_name}",
                    'data': {'name': full_path},
                    'is_submenu': True
                })
            return items
        finally:
            self.client.namespace = old_ns
    
    def _view_namespace(self, ns_name: str):
        """View namespace details."""
        response = self.client.read_namespace(ns_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Namespace: {ns_name}", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed to read namespace: {response.error}")
    
    def _create_namespace(self):
        """Create a new namespace."""
        name, ok = QInputDialog.getText(None, "New Namespace", "Namespace path:")
        if ok and name:
            response = self.client.create_namespace(name)
            if response.ok:
                self.notification.emit("Namespace Created", f"Namespace {name} created")
            else:
                QMessageBox.warning(None, "Error", f"Failed to create namespace: {response.error}")
    
    def _delete_namespace(self, ns_name: str):
        """Delete a namespace."""
        reply = QMessageBox.warning(
            None, "Delete Namespace",
            f"⚠️ Delete namespace '{ns_name}'?\n\nThis will delete ALL data within this namespace!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Confirm again
            confirm, ok = QInputDialog.getText(
                None, "Confirm Delete",
                f"Type '{ns_name}' to confirm deletion:"
            )
            if ok and confirm == ns_name:
                response = self.client.delete_namespace(ns_name)
                if response.ok:
                    self.notification.emit("Namespace Deleted", f"Namespace {ns_name} deleted")
                else:
                    QMessageBox.warning(None, "Error", f"Failed to delete: {response.error}")
    
    def _switch_namespace(self):
        """Switch to a different namespace."""
        current = self.settings.openbao.namespace or ""
        ns, ok = QInputDialog.getText(
            None, "Switch Namespace",
            "Enter namespace path (empty for root):",
            QLineEdit.EchoMode.Normal,
            current
        )
        if ok:
            self._do_switch_namespace(ns)
    
    def _do_switch_namespace(self, ns_name: str):
        """Actually switch to a namespace."""
        self.settings.openbao.namespace = ns_name if ns_name else ""
        self.client.namespace = ns_name if ns_name else None
        self.refresh_client()
        ns_display = ns_name if ns_name else "(root)"
        self.notification.emit("Namespace Changed", f"Switched to namespace: {ns_display}")
    
    def _go_to_root_namespace(self):
        """Switch to root namespace."""
        self._do_switch_namespace("")
    
    def _create_system_menu(self) -> QMenu:
        menu = QMenu("⚙️ System")
        
        # Status section
        status_menu = QMenu("📊 Status")
        
        health = status_menu.addAction("❤️ Health")
        health.triggered.connect(self._show_health)
        
        seal = status_menu.addAction("🔒 Seal Status")
        seal.triggered.connect(self._show_seal_status)
        
        leader = status_menu.addAction("👑 Leader")
        leader.triggered.connect(self._show_leader)
        
        ha_status = status_menu.addAction("🔄 HA Status")
        ha_status.triggered.connect(self._show_ha_status)
        
        key_status = status_menu.addAction("🔑 Key Status")
        key_status.triggered.connect(self._show_key_status)
        
        init_status = status_menu.addAction("🎬 Init Status")
        init_status.triggered.connect(self._show_init_status)
        
        menu.addMenu(status_menu)
        
        # Mounts management (tune existing engines)
        mounts_menu = QMenu("📦 Mounts")
        
        list_secret_mounts = mounts_menu.addAction("🗝️ List Secret Engines")
        list_secret_mounts.triggered.connect(self._list_secret_mounts)
        
        list_auth_mounts = mounts_menu.addAction("🔐 List Auth Methods")
        list_auth_mounts.triggered.connect(self._list_auth_mounts)
        
        mounts_menu.addSeparator()
        
        tune_mount = mounts_menu.addAction("⚙️ Tune Mount")
        tune_mount.triggered.connect(self._tune_mount)
        
        disable_mount = mounts_menu.addAction("🗑️ Disable Mount")
        disable_mount.triggered.connect(self._disable_mount)
        
        menu.addMenu(mounts_menu)
        
        # Operations section
        ops_menu = QMenu("🔧 Operations")
        
        seal_vault = ops_menu.addAction("🔒 Seal Vault")
        seal_vault.triggered.connect(self._seal_vault)
        
        unseal_vault = ops_menu.addAction("🔓 Unseal Vault")
        unseal_vault.triggered.connect(self._unseal_vault)
        
        step_down = ops_menu.addAction("👇 Step Down")
        step_down.triggered.connect(self._step_down)
        
        rotate_key = ops_menu.addAction("🔄 Rotate Encryption Key")
        rotate_key.triggered.connect(self._rotate_encryption_key)
        
        menu.addMenu(ops_menu)
        
        # Audit section
        audit_menu = AsyncMenu("📝 Audit Devices", self._load_audit_devices)
        audit_menu.set_submenu_factory(self._create_audit_device_submenu)
        audit_menu.set_new_item_callback(self._create_audit_device, "➕ Enable Audit Device...")
        menu.addMenu(audit_menu)
        
        # Leases section
        leases_menu = QMenu("📋 Leases")
        lookup_lease = leases_menu.addAction("🔍 Lookup Lease")
        lookup_lease.triggered.connect(self._lookup_lease)
        renew_lease = leases_menu.addAction("🔄 Renew Lease")
        renew_lease.triggered.connect(self._renew_lease_dialog)
        revoke_lease = leases_menu.addAction("🗑️ Revoke Lease")
        revoke_lease.triggered.connect(self._revoke_lease)
        list_leases = leases_menu.addAction("📋 List Leases")
        list_leases.triggered.connect(self._list_leases)
        revoke_prefix = leases_menu.addAction("⚠️ Revoke Prefix")
        revoke_prefix.triggered.connect(self._revoke_lease_prefix)
        menu.addMenu(leases_menu)
        
        # Plugins section
        plugins_menu = QMenu("🔌 Plugins")
        list_plugins = plugins_menu.addAction("📋 List Catalog")
        list_plugins.triggered.connect(self._show_plugins_catalog)
        reload_plugin = plugins_menu.addAction("🔄 Reload Plugin")
        reload_plugin.triggered.connect(self._reload_plugin)
        reload_mounts = plugins_menu.addAction("🔄 Reload All Mounts")
        reload_mounts.triggered.connect(self._reload_mounts)
        menu.addMenu(plugins_menu)
        
        # Quotas section
        quotas_menu = QMenu("📊 Quotas")
        rate_limits = quotas_menu.addAction("⏱️ Rate Limit Quotas")
        rate_limits.triggered.connect(self._show_rate_limit_quotas)
        lease_counts = quotas_menu.addAction("📈 Lease Count Quotas")
        lease_counts.triggered.connect(self._show_lease_count_quotas)
        quotas_menu.addSeparator()
        create_rate_limit = quotas_menu.addAction("➕ Create Rate Limit")
        create_rate_limit.triggered.connect(self._create_rate_limit_quota)
        menu.addMenu(quotas_menu)
        
        # Storage section (Raft)
        storage_menu = QMenu("💾 Storage (Raft)")
        raft_config = storage_menu.addAction("⚙️ Configuration")
        raft_config.triggered.connect(self._show_raft_config)
        autopilot_state = storage_menu.addAction("🤖 Autopilot State")
        autopilot_state.triggered.connect(self._show_autopilot_state)
        autopilot_config = storage_menu.addAction("⚙️ Autopilot Config")
        autopilot_config.triggered.connect(self._show_autopilot_config)
        storage_menu.addSeparator()
        snapshot = storage_menu.addAction("📥 Download Snapshot")
        snapshot.triggered.connect(self._download_raft_snapshot)
        remove_peer = storage_menu.addAction("🗑️ Remove Peer")
        remove_peer.triggered.connect(self._remove_raft_peer)
        menu.addMenu(storage_menu)
        
        # Replication section
        replication_menu = QMenu("🔄 Replication")
        repl_status = replication_menu.addAction("📊 Status")
        repl_status.triggered.connect(self._show_replication_status)
        menu.addMenu(replication_menu)
        
        menu.addSeparator()
        
        # Counters/Metrics section
        counters_menu = QMenu("📈 Counters & Metrics")
        activity = counters_menu.addAction("📊 Client Activity")
        activity.triggered.connect(self._show_client_activity)
        token_count = counters_menu.addAction("🎫 Token Count")
        token_count.triggered.connect(self._show_token_count)
        entity_count = counters_menu.addAction("👤 Entity Count")
        entity_count.triggered.connect(self._show_entity_count)
        in_flight = counters_menu.addAction("✈️ In-Flight Requests")
        in_flight.triggered.connect(self._show_in_flight_requests)
        counters_menu.addSeparator()
        prometheus = counters_menu.addAction("📊 Prometheus Metrics")
        prometheus.triggered.connect(self._show_prometheus_metrics)
        menu.addMenu(counters_menu)
        
        # Config section
        config_menu = QMenu("⚙️ Configuration")
        cors = config_menu.addAction("🌐 CORS")
        cors.triggered.connect(self._show_cors_config)
        ui_headers = config_menu.addAction("📋 UI Headers")
        ui_headers.triggered.connect(self._show_ui_headers)
        state = config_menu.addAction("📝 Sanitized State")
        state.triggered.connect(self._show_config_state)
        config_menu.addSeparator()
        request_headers = config_menu.addAction("📋 Audited Request Headers")
        request_headers.triggered.connect(self._show_audited_request_headers)
        license_info = config_menu.addAction("📜 License Info")
        license_info.triggered.connect(self._show_license_info)
        menu.addMenu(config_menu)
        
        # Internal UI endpoints
        internal_menu = QMenu("🔍 Internal")
        ui_mounts = internal_menu.addAction("📦 UI Mounts")
        ui_mounts.triggered.connect(self._show_ui_mounts)
        ui_namespaces = internal_menu.addAction("📂 UI Namespaces")
        ui_namespaces.triggered.connect(self._show_ui_namespaces)
        openapi = internal_menu.addAction("📖 OpenAPI Spec")
        openapi.triggered.connect(self._show_openapi_spec)
        menu.addMenu(internal_menu)
        
        # Advanced section
        advanced_menu = QMenu("🔧 Advanced")
        host_info = advanced_menu.addAction("🖥️ Host Info")
        host_info.triggered.connect(self._show_host_info)
        capabilities = advanced_menu.addAction("🔐 Check Capabilities")
        capabilities.triggered.connect(self._check_capabilities)
        capabilities_self = advanced_menu.addAction("🔐 Check My Capabilities")
        capabilities_self.triggered.connect(self._check_capabilities_self)
        remount = advanced_menu.addAction("📦 Remount Engine")
        remount.triggered.connect(self._remount_engine)
        raw_storage = advanced_menu.addAction("💾 Raw Storage (Root)")
        raw_storage.triggered.connect(self._browse_raw_storage)
        advanced_menu.addSeparator()
        pprof = advanced_menu.addAction("📊 pprof Index")
        pprof.triggered.connect(self._show_pprof)
        monitor = advanced_menu.addAction("📋 Monitor Logs")
        monitor.triggered.connect(self._show_monitor_logs)
        menu.addMenu(advanced_menu)
        
        # Root token generation (dangerous operations)
        root_menu = QMenu("⚠️ Root Token")
        gen_status = root_menu.addAction("📊 Generation Status")
        gen_status.triggered.connect(self._show_root_gen_status)
        gen_init = root_menu.addAction("▶️ Start Generation")
        gen_init.triggered.connect(self._init_root_generation)
        gen_cancel = root_menu.addAction("❌ Cancel Generation")
        gen_cancel.triggered.connect(self._cancel_root_generation)
        menu.addMenu(root_menu)
        
        # Rekey section
        rekey_menu = QMenu("🔑 Rekey")
        rekey_status = rekey_menu.addAction("📊 Status")
        rekey_status.triggered.connect(self._show_rekey_status)
        rekey_init = rekey_menu.addAction("▶️ Start Rekey")
        rekey_init.triggered.connect(self._init_rekey)
        rekey_cancel = rekey_menu.addAction("❌ Cancel Rekey")
        rekey_cancel.triggered.connect(self._cancel_rekey)
        menu.addMenu(rekey_menu)
        
        return menu
    
    # ==================== System Menu Helpers ====================
    
    def _show_ha_status(self):
        """Show HA status."""
        response = self.client.sys_ha_status()
        if response.ok:
            dialog = JsonEditorDialog("HA Status", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_key_status(self):
        """Show encryption key status."""
        response = self.client.sys_key_status()
        if response.ok:
            dialog = JsonEditorDialog("Key Status", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_init_status(self):
        """Show initialization status."""
        response = self.client.sys_init_status()
        if response.ok:
            dialog = JsonEditorDialog("Init Status", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _seal_vault(self):
        """Seal the vault."""
        reply = QMessageBox.question(None, "⚠️ Seal Vault",
                                     "Are you sure you want to SEAL the vault?\nThis will require unsealing to access secrets.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.sys_seal()
            if response.ok:
                self.notification.emit("Vault Sealed", "The vault has been sealed")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _unseal_vault(self):
        """Unseal the vault."""
        key, ok = QInputDialog.getText(None, "Unseal Vault", "Enter unseal key:")
        if ok and key:
            response = self.client.sys_unseal(key=key)
            if response.ok:
                data = response.data.get('data', response.data)
                sealed = data.get('sealed', True)
                progress = data.get('progress', 0)
                threshold = data.get('t', 0)
                if sealed:
                    QMessageBox.information(None, "Unseal Progress", 
                                           f"Progress: {progress}/{threshold}")
                else:
                    self.notification.emit("Vault Unsealed", "The vault has been unsealed")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _step_down(self):
        """Force active node to step down."""
        reply = QMessageBox.question(None, "Step Down",
                                     "Force the active node to step down?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.sys_step_down()
            if response.ok:
                self.notification.emit("Step Down", "Active node has stepped down")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _rotate_encryption_key(self):
        """Rotate the encryption key."""
        reply = QMessageBox.question(None, "Rotate Key",
                                     "Rotate the encryption key?\nThis is a safe operation.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.sys_rotate()
            if response.ok:
                self.notification.emit("Key Rotated", "Encryption key has been rotated")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _create_audit_device_submenu(self, title: str, data: str) -> QMenu:
        """Create submenu for an audit device."""
        menu = QMenu(data)
        
        view = menu.addAction("👁️ View")
        view.triggered.connect(lambda: self._show_audit_device(data))
        
        disable = menu.addAction("🗑️ Disable")
        disable.triggered.connect(lambda: self._disable_audit_device(data))
        
        return menu
    
    def _show_audit_device(self, path: str):
        """Show audit device configuration."""
        response = self.client.list_audit_devices()
        if response.ok:
            devices = response.data.get('data', response.data)
            device_key = path.rstrip('/') + '/'
            if device_key in devices:
                dialog = JsonEditorDialog(f"Audit Device: {path}", devices[device_key], readonly=True)
                dialog.exec()
    
    def _create_audit_device(self):
        """Enable a new audit device."""
        path, ok = QInputDialog.getText(None, "Enable Audit Device", "Path (e.g., 'file/'):")
        if not ok or not path:
            return
        
        device_types = ['file', 'syslog', 'socket']
        device_type, ok = QInputDialog.getItem(None, "Audit Device Type", "Select type:",
                                               device_types, 0, False)
        if not ok:
            return
        
        if device_type == 'file':
            template = {
                'type': 'file',
                'options': {
                    'file_path': '/var/log/vault/audit.log',
                    'log_raw': False,
                }
            }
        elif device_type == 'syslog':
            template = {
                'type': 'syslog',
                'options': {
                    'facility': 'AUTH',
                    'tag': 'vault',
                }
            }
        else:
            template = {
                'type': 'socket',
                'options': {
                    'address': 'localhost:9090',
                    'socket_type': 'tcp',
                }
            }
        
        dialog = JsonEditorDialog(f"Enable Audit: {path}", template, readonly=False)
        if dialog.exec():
            data = dialog.data
            response = self.client.enable_audit_device(path, data.get('type', device_type),
                                                       options=data.get('options', {}))
            if response.ok:
                self.notification.emit("Audit Enabled", f"Audit device {path} enabled")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _disable_audit_device(self, path: str):
        """Disable an audit device."""
        reply = QMessageBox.question(None, "Disable Audit",
                                     f"Disable audit device '{path}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.disable_audit_device(path)
            if response.ok:
                self.notification.emit("Audit Disabled", f"Audit device {path} disabled")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _renew_lease_dialog(self):
        """Renew a lease."""
        lease_id, ok = QInputDialog.getText(None, "Renew Lease", "Lease ID:")
        if ok and lease_id:
            increment, ok = QInputDialog.getInt(None, "Renew Lease", "Increment (seconds):", 3600, 0, 86400*30)
            if ok:
                response = self.client.renew_lease(lease_id, increment)
                if response.ok:
                    self.notification.emit("Lease Renewed", f"Lease renewed: {lease_id}")
                else:
                    QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _list_leases(self):
        """List leases by prefix."""
        prefix, ok = QInputDialog.getText(None, "List Leases", "Prefix (e.g., 'database/creds/'):")
        if ok and prefix:
            response = self.client.list_leases(prefix)
            if response.ok:
                dialog = JsonEditorDialog(f"Leases: {prefix}", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_plugins_catalog(self):
        """Show plugins catalog."""
        response = self.client.sys_plugins_catalog_list()
        if response.ok:
            dialog = JsonEditorDialog("Plugins Catalog", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _reload_plugin(self):
        """Reload a plugin."""
        plugin, ok = QInputDialog.getText(None, "Reload Plugin", "Plugin name:")
        if ok and plugin:
            response = self.client.sys_plugins_reload(plugin=plugin)
            if response.ok:
                self.notification.emit("Plugin Reloaded", f"Plugin {plugin} reloaded")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_rate_limit_quotas(self):
        """Show rate limit quotas."""
        response = self.client.sys_quotas_rate_limit_list()
        if response.ok:
            dialog = JsonEditorDialog("Rate Limit Quotas", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_lease_count_quotas(self):
        """Show lease count quotas."""
        response = self.client.sys_quotas_lease_count_list()
        if response.ok:
            dialog = JsonEditorDialog("Lease Count Quotas", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_raft_config(self):
        """Show Raft storage configuration."""
        response = self.client.sys_storage_raft_config()
        if response.ok:
            dialog = JsonEditorDialog("Raft Configuration", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_autopilot_state(self):
        """Show Raft autopilot state."""
        response = self.client.sys_storage_raft_autopilot_state()
        if response.ok:
            dialog = JsonEditorDialog("Autopilot State", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_autopilot_config(self):
        """Show Raft autopilot configuration."""
        response = self.client.sys_storage_raft_autopilot_config()
        if response.ok:
            dialog = JsonEditorDialog("Autopilot Config", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _remove_raft_peer(self):
        """Remove a peer from Raft cluster."""
        server_id, ok = QInputDialog.getText(None, "Remove Raft Peer", "Server ID:")
        if ok and server_id:
            reply = QMessageBox.question(None, "Remove Peer",
                                         f"Remove server '{server_id}' from Raft cluster?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                response = self.client.sys_storage_raft_remove_peer(server_id)
                if response.ok:
                    self.notification.emit("Peer Removed", f"Server {server_id} removed from cluster")
                else:
                    QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_replication_status(self):
        """Show replication status."""
        response = self.client.sys_replication_status()
        if response.ok:
            dialog = JsonEditorDialog("Replication Status", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_client_activity(self):
        """Show client activity data."""
        response = self.client.sys_internal_counters_activity()
        if response.ok:
            dialog = JsonEditorDialog("Client Activity", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_token_count(self):
        """Show token count."""
        response = self.client.sys_internal_counters_tokens()
        if response.ok:
            dialog = JsonEditorDialog("Token Count", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_entity_count(self):
        """Show entity count."""
        response = self.client.sys_internal_counters_entities()
        if response.ok:
            dialog = JsonEditorDialog("Entity Count", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_in_flight_requests(self):
        """Show in-flight requests."""
        response = self.client.sys_in_flight_req()
        if response.ok:
            dialog = JsonEditorDialog("In-Flight Requests", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_cors_config(self):
        """Show CORS configuration."""
        response = self.client.sys_config_cors()
        if response.ok:
            dialog = JsonEditorDialog("CORS Configuration", response.data, readonly=False)
            dialog.saved.connect(self._save_cors_config)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _save_cors_config(self, data: Dict):
        """Save CORS configuration."""
        response = self.client.sys_config_cors_configure(
            enabled=data.get('enabled', False),
            allowed_origins=data.get('allowed_origins'),
            allowed_headers=data.get('allowed_headers')
        )
        if response.ok:
            self.notification.emit("CORS Saved", "CORS configuration saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_ui_headers(self):
        """Show custom UI headers."""
        response = self.client.sys_config_ui_headers()
        if response.ok:
            dialog = JsonEditorDialog("UI Headers", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_config_state(self):
        """Show sanitized configuration state."""
        response = self.client.sys_config_state_sanitized()
        if response.ok:
            dialog = JsonEditorDialog("Sanitized Config State", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_host_info(self):
        """Show host information."""
        response = self.client.sys_host_info()
        if response.ok:
            dialog = JsonEditorDialog("Host Information", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _check_capabilities(self):
        """Check capabilities on paths."""
        paths_str, ok = QInputDialog.getText(None, "Check Capabilities", 
                                             "Paths (comma-separated):")
        if ok and paths_str:
            paths = [p.strip() for p in paths_str.split(',')]
            response = self.client.sys_capabilities_self(paths)
            if response.ok:
                dialog = JsonEditorDialog("Capabilities", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _remount_engine(self):
        """Remount a secrets engine."""
        from_path, ok = QInputDialog.getText(None, "Remount Engine", "Current path:")
        if not ok or not from_path:
            return
        to_path, ok = QInputDialog.getText(None, "Remount Engine", "New path:")
        if not ok or not to_path:
            return
        
        reply = QMessageBox.question(None, "Remount",
                                     f"Remount '{from_path}' to '{to_path}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.sys_remount(from_path, to_path)
            if response.ok:
                self.notification.emit("Remount Started", f"Remounting {from_path} to {to_path}")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _browse_raw_storage(self):
        """Browse raw storage (requires root token)."""
        path, ok = QInputDialog.getText(None, "Raw Storage", "Path (leave empty for root):")
        if ok:
            if path:
                response = self.client.sys_raw_read(path)
            else:
                response = self.client.sys_raw_list(path)
            
            if response.ok:
                dialog = JsonEditorDialog(f"Raw Storage: {path or '/'}", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed (requires root token): {response.error}")
    
    def _show_root_gen_status(self):
        """Show root token generation status."""
        response = self.client.sys_generate_root_status()
        if response.ok:
            dialog = JsonEditorDialog("Root Generation Status", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _init_root_generation(self):
        """Initialize root token generation."""
        otp, ok = QInputDialog.getText(None, "Generate Root Token", 
                                       "OTP (leave empty to generate):")
        if ok:
            response = self.client.sys_generate_root_init(otp=otp if otp else None)
            if response.ok:
                dialog = JsonEditorDialog("Root Generation Initialized", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _cancel_root_generation(self):
        """Cancel root token generation."""
        response = self.client.sys_generate_root_cancel()
        if response.ok:
            self.notification.emit("Cancelled", "Root generation cancelled")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_rekey_status(self):
        """Show rekey status."""
        response = self.client.sys_rekey_init_status()
        if response.ok:
            dialog = JsonEditorDialog("Rekey Status", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _init_rekey(self):
        """Initialize rekey operation."""
        shares, ok = QInputDialog.getInt(None, "Rekey", "Number of key shares:", 5, 1, 10)
        if not ok:
            return
        threshold, ok = QInputDialog.getInt(None, "Rekey", "Key threshold:", 3, 1, shares)
        if not ok:
            return
        
        response = self.client.sys_rekey_init(shares, threshold)
        if response.ok:
            dialog = JsonEditorDialog("Rekey Initialized", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _cancel_rekey(self):
        """Cancel rekey operation."""
        response = self.client.sys_rekey_cancel()
        if response.ok:
            self.notification.emit("Cancelled", "Rekey operation cancelled")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    # ==================== New System Menu Handlers ====================
    
    def _list_secret_mounts(self):
        """List all secret engine mounts."""
        response = self.client.list_mounts()
        if response.ok:
            dialog = JsonEditorDialog("Secret Engine Mounts", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _list_auth_mounts(self):
        """List all auth method mounts."""
        response = self.client.list_auth_methods()
        if response.ok:
            dialog = JsonEditorDialog("Auth Method Mounts", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _tune_mount(self):
        """Tune a mount's configuration."""
        path, ok = QInputDialog.getText(None, "Tune Mount", "Mount path (e.g., secret/, auth/userpass/):")
        if not ok or not path:
            return
        
        # Get current tune settings
        if path.startswith('auth/'):
            response = self.client.read_auth_method(path.replace('auth/', ''))
        else:
            response = self.client.mount_info(path)
        
        current_config = {}
        if response.ok:
            data = response.data.get('data', response.data)
            current_config = data.get('config', {})
        
        tune_template = {
            'default_lease_ttl': current_config.get('default_lease_ttl', ''),
            'max_lease_ttl': current_config.get('max_lease_ttl', ''),
            'description': current_config.get('description', ''),
            'audit_non_hmac_request_keys': current_config.get('audit_non_hmac_request_keys', []),
            'audit_non_hmac_response_keys': current_config.get('audit_non_hmac_response_keys', []),
            'listing_visibility': current_config.get('listing_visibility', 'hidden'),
            'passthrough_request_headers': current_config.get('passthrough_request_headers', []),
        }
        
        dialog = JsonEditorDialog(f"Tune Mount: {path}", tune_template, readonly=False)
        dialog.saved.connect(lambda d: self._save_tune_mount(path, d))
        dialog.exec()
    
    def _save_tune_mount(self, path: str, data: Dict):
        """Save mount tune configuration."""
        # Remove empty values
        tune_data = {k: v for k, v in data.items() if v}
        
        if path.startswith('auth/'):
            response = self.client.tune_auth_method(path.replace('auth/', '').rstrip('/'), **tune_data)
        else:
            response = self.client.api_write(f"sys/mounts/{path.rstrip('/')}/tune", tune_data)
        
        if response.ok:
            self.notification.emit("Mount Tuned", f"Mount {path} tuned successfully")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _disable_mount(self):
        """Disable a secrets engine or auth method."""
        path, ok = QInputDialog.getText(None, "Disable Mount", "Mount path (e.g., secret/, auth/userpass/):")
        if not ok or not path:
            return
        
        reply = QMessageBox.question(None, "⚠️ Disable Mount",
                                     f"Are you sure you want to disable '{path}'?\nThis will delete all secrets in this mount!",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if path.startswith('auth/'):
                response = self.client.disable_auth_method(path.replace('auth/', '').rstrip('/'))
            else:
                response = self.client.disable_secrets_engine(path.rstrip('/'))
            
            if response.ok:
                self.notification.emit("Mount Disabled", f"Mount {path} disabled")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _revoke_lease_prefix(self):
        """Revoke all leases under a prefix."""
        prefix, ok = QInputDialog.getText(None, "Revoke Lease Prefix", 
                                          "Lease prefix (e.g., aws/creds/my-role):")
        if not ok or not prefix:
            return
        
        reply = QMessageBox.question(None, "⚠️ Revoke Prefix",
                                     f"Revoke ALL leases under '{prefix}'?\nThis cannot be undone!",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.api_write(f"sys/leases/revoke-prefix/{prefix}", {})
            if response.ok:
                self.notification.emit("Leases Revoked", f"All leases under {prefix} revoked")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _reload_mounts(self):
        """Reload all plugin mounts."""
        reply = QMessageBox.question(None, "Reload Mounts",
                                     "Reload all plugin mounts?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.sys_plugins_reload()
            if response.ok:
                self.notification.emit("Reloaded", "All plugin mounts reloaded")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _create_rate_limit_quota(self):
        """Create a rate limit quota."""
        name, ok = QInputDialog.getText(None, "Create Rate Limit Quota", "Quota name:")
        if not ok or not name:
            return
        
        template = {
            'rate': 100.0,
            'interval': '1s',
            'path': '',
            'block_interval': '',
        }
        
        dialog = JsonEditorDialog(f"New Rate Limit: {name}", template, readonly=False)
        dialog.saved.connect(lambda d: self._save_rate_limit_quota(name, d))
        dialog.exec()
    
    def _save_rate_limit_quota(self, name: str, data: Dict):
        """Save rate limit quota."""
        response = self.client.sys_quotas_rate_limit_create(
            name, 
            rate=data.get('rate', 100),
            interval=data.get('interval', '1s'),
            path=data.get('path'),
            block_interval=data.get('block_interval')
        )
        if response.ok:
            self.notification.emit("Quota Created", f"Rate limit quota {name} created")
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _download_raft_snapshot(self):
        """Download a Raft snapshot."""
        file_path, _ = QFileDialog.getSaveFileName(None, "Save Snapshot", "vault-snapshot.snap",
                                                    "Snapshot Files (*.snap);;All Files (*)")
        if file_path:
            response = self.client.sys_storage_raft_snapshot()
            if response.ok:
                try:
                    # The snapshot is binary data
                    with open(file_path, 'wb') as f:
                        if isinstance(response.data, bytes):
                            f.write(response.data)
                        else:
                            f.write(str(response.data).encode())
                    self.notification.emit("Snapshot Saved", f"Snapshot saved to {file_path}")
                except Exception as e:
                    QMessageBox.warning(None, "Error", f"Failed to save: {e}")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_prometheus_metrics(self):
        """Show Prometheus metrics."""
        response = self.client.sys_metrics(format='prometheus')
        if response.ok:
            # Metrics are text, show in a text dialog
            from PySide6.QtWidgets import QTextEdit
            dialog = QDialog()
            dialog.setWindowTitle("Prometheus Metrics")
            dialog.setMinimumSize(800, 600)
            layout = QVBoxLayout(dialog)
            
            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(str(response.data))
            layout.addWidget(text)
            
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_audited_request_headers(self):
        """Show audited request headers configuration."""
        response = self.client.sys_config_auditing_request_headers()
        if response.ok:
            dialog = JsonEditorDialog("Audited Request Headers", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_license_info(self):
        """Show license information."""
        response = self.client.sys_license()
        if response.ok:
            dialog = JsonEditorDialog("License Info", response.data, readonly=True)
            dialog.exec()
        else:
            # Community edition doesn't have license endpoint
            QMessageBox.information(None, "License", "Community Edition (no license required)")
    
    def _show_ui_mounts(self):
        """Show internal UI mounts."""
        response = self.client.sys_internal_ui_mounts()
        if response.ok:
            dialog = JsonEditorDialog("UI Mounts", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_ui_namespaces(self):
        """Show internal UI namespaces."""
        response = self.client.sys_internal_ui_namespaces()
        if response.ok:
            dialog = JsonEditorDialog("UI Namespaces", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_openapi_spec(self):
        """Show OpenAPI specification."""
        response = self.client.sys_internal_specs_openapi()
        if response.ok:
            dialog = JsonEditorDialog("OpenAPI Specification", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _check_capabilities_self(self):
        """Check capabilities of current token on paths."""
        paths, ok = QInputDialog.getText(None, "Check My Capabilities", 
                                         "Paths (comma-separated):")
        if ok and paths:
            path_list = [p.strip() for p in paths.split(',')]
            response = self.client.sys_capabilities_self(path_list)
            if response.ok:
                dialog = JsonEditorDialog("My Capabilities", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_pprof(self):
        """Show pprof index."""
        response = self.client.sys_pprof_index()
        if response.ok:
            dialog = JsonEditorDialog("pprof Index", response.data, readonly=True)
            dialog.exec()
        else:
            QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_monitor_logs(self):
        """Show monitor logs."""
        log_levels = ['trace', 'debug', 'info', 'warn', 'error']
        level, ok = QInputDialog.getItem(None, "Monitor Logs", "Log level:", log_levels, 2, False)
        if ok:
            response = self.client.sys_monitor(log_level=level)
            if response.ok:
                from PySide6.QtWidgets import QTextEdit
                dialog = QDialog()
                dialog.setWindowTitle(f"Monitor Logs ({level})")
                dialog.setMinimumSize(800, 600)
                layout = QVBoxLayout(dialog)
                
                text = QTextEdit()
                text.setReadOnly(True)
                text.setPlainText(str(response.data))
                layout.addWidget(text)
                
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _create_tools_menu(self) -> QMenu:
        menu = QMenu("🔧 Tools")
        
        wrap = menu.addAction("📦 Wrap Data")
        wrap.triggered.connect(self._wrap_data)
        
        unwrap = menu.addAction("📭 Unwrap Token")
        unwrap.triggered.connect(self._unwrap_token)
        
        menu.addSeparator()
        
        random_gen = menu.addAction("🎲 Generate Random")
        random_gen.triggered.connect(self._generate_random)
        
        hash_data = menu.addAction("#️⃣ Hash Data")
        hash_data.triggered.connect(self._hash_data)
        
        return menu
    
    def _create_token_menu(self) -> QMenu:
        menu = QMenu("🎫 Token")
        
        lookup = menu.addAction("🔍 Lookup Self")
        lookup.triggered.connect(self._lookup_self_token)
        
        renew = menu.addAction("🔄 Renew Token")
        renew.triggered.connect(self._renew_token)
        
        create = menu.addAction("➕ Create Token")
        create.triggered.connect(self._create_token)
        
        return menu
    
    # Secret operations
    def _show_secret(self, mount_path: str, secret_path: str, is_v2: bool):
        if is_v2:
            response = self.client.kv2_read(mount_path, secret_path)
            data = response.data.get('data', {}).get('data', {}) if response.ok and response.data else {}
        else:
            response = self.client.kv1_read(mount_path, secret_path)
            data = response.data.get('data', {}) if response.ok and response.data else {}
        
        dialog = SecretDialog(secret_path, data)
        dialog.saved.connect(lambda path, d: self._save_secret(mount_path, path, d, is_v2))
        dialog.deleted.connect(lambda path: self._delete_secret(mount_path, path, is_v2))
        dialog.exec()
    
    def _create_secret(self, mount_path: str, folder_path: str, is_v2: bool):
        full_path = f"{folder_path}/" if folder_path else ""
        dialog = SecretDialog(full_path, is_new=True)
        dialog.saved.connect(lambda path, d: self._save_secret(mount_path, path, d, is_v2))
        dialog.exec()
    
    def _save_secret(self, mount_path: str, path: str, data: Dict, is_v2: bool):
        if is_v2:
            response = self.client.kv2_write(mount_path, path, data)
        else:
            response = self.client.kv1_write(mount_path, path, data)
        
        if response.ok:
            self.notification.emit("Secret Saved", f"Secret at {path} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save: {response.error}")
    
    def _delete_secret(self, mount_path: str, path: str, is_v2: bool):
        if is_v2:
            response = self.client.kv2_delete_metadata(mount_path, path)
        else:
            response = self.client.kv1_delete(mount_path, path)
        
        if response.ok:
            self.notification.emit("Secret Deleted", f"Secret at {path} deleted")
    
    # Helper loaders
    def _load_generic_list(self, mount_path: str, endpoint: str) -> list:
        response = self.client.api_list(f"{mount_path}/{endpoint}")
        if not response.ok:
            if response.status_code == 404:
                return []
            raise Exception(response.error or f"Failed to list {endpoint}")
        keys = response.data.get('data', {}).get('keys', []) if response.data else []
        return [(f"📄 {k}", k) for k in keys]
    
    def _load_audit_devices(self) -> list:
        response = self.client.list_audit_devices()
        if not response.ok:
            raise Exception(response.error or "Failed to list audit devices")
        devices = response.data.get('data', response.data) if response.data else {}
        return [(f"📝 {path}", {'path': path, 'info': info}) for path, info in devices.items()]
    
    # Action handlers
    def _show_health(self):
        response = self.client.health()
        if response.ok:
            dialog = JsonEditorDialog("Health Status", response.data, readonly=True)
            dialog.exec()
    
    def _show_seal_status(self):
        response = self.client.seal_status()
        if response.ok:
            dialog = JsonEditorDialog("Seal Status", response.data, readonly=True)
            dialog.exec()
    
    def _show_leader(self):
        response = self.client.leader()
        if response.ok:
            dialog = JsonEditorDialog("Leader Status", response.data, readonly=True)
            dialog.exec()
    
    def _lookup_self_token(self):
        response = self.client.lookup_self_token()
        if response.ok:
            dialog = JsonEditorDialog("Token Info", response.data, readonly=True)
            dialog.exec()
    
    def _renew_token(self):
        response = self.client.renew_self_token()
        if response.ok:
            self.notification.emit("Token Renewed", "Token renewed successfully")
        else:
            QMessageBox.warning(None, "Error", f"Failed to renew: {response.error}")
    
    def _create_token(self):
        dialog = CrudDialog("Create Token", {'policies': '', 'ttl': '1h', 'renewable': True})
        if dialog.exec():
            data = dialog.data
            policies = [p.strip() for p in data.get('policies', '').split(',') if p.strip()]
            response = self.client.create_token(policies=policies, ttl=data.get('ttl', '1h'))
            if response.ok:
                token = response.data.get('auth', {}).get('client_token', '')
                QMessageBox.information(None, "Token Created", f"Token: {token}")
    
    def _wrap_data(self):
        dialog = CrudDialog("Wrap Data", {'key': '', 'value': ''})
        if dialog.exec():
            response = self.client.wrap(dialog.data)
            if response.ok:
                token = response.data.get('wrap_info', {}).get('token', '')
                QMessageBox.information(None, "Data Wrapped", f"Wrap Token: {token}")
    
    def _unwrap_token(self):
        token, ok = QInputDialog.getText(None, "Unwrap Token", "Wrap token:", QLineEdit.EchoMode.Password)
        if ok and token:
            response = self.client.unwrap(token)
            if response.ok:
                dialog = JsonEditorDialog("Unwrapped Data", response.data, readonly=True)
                dialog.exec()
    
    def _generate_random(self):
        bytes_count, ok = QInputDialog.getInt(None, "Generate Random", "Number of bytes:", 32, 1, 1024)
        if ok:
            response = self.client.random(bytes_count)
            if response.ok:
                random_data = response.data.get('data', {}).get('random_bytes', '')
                QMessageBox.information(None, "Random Data", f"Data: {random_data}")
    
    def _hash_data(self):
        data, ok = QInputDialog.getText(None, "Hash Data", "Data to hash:")
        if ok and data:
            response = self.client.hash(data)
            if response.ok:
                hash_value = response.data.get('data', {}).get('sum', '')
                QMessageBox.information(None, "Hash Result", f"Hash: {hash_value}")
    
    def _lookup_lease(self):
        lease_id, ok = QInputDialog.getText(None, "Lookup Lease", "Lease ID:")
        if ok and lease_id:
            response = self.client.lookup_lease(lease_id)
            if response.ok:
                dialog = JsonEditorDialog("Lease Info", response.data, readonly=True)
                dialog.exec()
    
    def _revoke_lease(self):
        lease_id, ok = QInputDialog.getText(None, "Revoke Lease", "Lease ID:")
        if ok and lease_id:
            response = self.client.revoke_lease(lease_id)
            if response.ok:
                self.notification.emit("Lease Revoked", "Lease revoked successfully")
    
    def _enable_secrets_engine(self):
        """Enable a new secrets engine with full configuration dialog."""
        from app.dialogs import EnableEngineDialog
        
        # Try to fetch available plugins
        plugins = []
        response = self.client.sys_plugins_catalog_list()
        if response.ok and response.data:
            data = response.data.get('data', response.data)
            # Plugins are categorized by type
            for plugin_type in ['secret', 'database', 'auth']:
                type_plugins = data.get(plugin_type, [])
                if isinstance(type_plugins, list):
                    plugins.extend(type_plugins)
        
        dialog = EnableEngineDialog(available_plugins=plugins)
        dialog.saved.connect(self._do_enable_secrets_engine)
        dialog.exec()
    
    def _do_enable_secrets_engine(self, path: str, engine_type: str, config: Dict):
        """Actually enable the secrets engine."""
        # Build config dict only with non-empty TTL values
        engine_config = {}
        if config.get('default_lease_ttl'):
            engine_config['default_lease_ttl'] = config['default_lease_ttl']
        if config.get('max_lease_ttl'):
            engine_config['max_lease_ttl'] = config['max_lease_ttl']
        
        response = self.client.enable_secrets_engine(
            path=path,
            engine_type=engine_type,
            description=config.get('description') or None,
            config=engine_config if engine_config else None,
            options=config.get('options'),
            local=config.get('local', False),
            seal_wrap=config.get('seal_wrap', False)
        )
        
        if response.ok:
            self.notification.emit("Engine Enabled", f"Secrets engine '{path}' ({engine_type}) enabled successfully")
        else:
            QMessageBox.warning(None, "Error", f"Failed to enable engine: {response.error}")
    
    def _enable_auth_method(self):
        path, ok = QInputDialog.getText(None, "Enable Auth Method", "Mount path:")
        if not ok or not path:
            return
        method_type, ok = QInputDialog.getItem(None, "Auth Type", "Select type:",
            ['userpass', 'approle', 'ldap', 'oidc', 'jwt', 'kubernetes', 'aws'], 0, False)
        if ok and method_type:
            response = self.client.enable_auth_method(path, method_type)
            if response.ok:
                self.notification.emit("Auth Enabled", f"Auth method {path} enabled")
    
    def _show_policy(self, policy_name: str):
        from app.dialogs import PolicyEditorDialog
        response = self.client.read_policy(policy_name)
        if response.ok and response.data:
            policy_text = response.data.get('data', {}).get('policy', '')
            dialog = PolicyEditorDialog(policy_name, policy_text)
            dialog.saved.connect(lambda name, text: self._save_policy(name, text))
            dialog.deleted.connect(lambda name: self._delete_policy(name))
            dialog.exec()
    
    def _create_policy(self):
        from app.dialogs import PolicyEditorDialog
        name, ok = QInputDialog.getText(None, "New Policy", "Policy name:")
        if ok and name:
            default_policy = '''# Example policy
path "secret/*" {
  capabilities = ["read", "list"]
}

path "secret/data/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}'''
            dialog = PolicyEditorDialog(name, default_policy, is_new=True)
            dialog.saved.connect(lambda n, text: self._save_policy(n, text))
            dialog.exec()
    
    def _save_policy(self, name: str, policy_text: str):
        response = self.client.write_policy(name, policy_text)
        if response.ok:
            self.notification.emit("Policy Saved", f"Policy {name} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save policy: {response.error}")
    
    def _delete_policy(self, name: str):
        response = self.client.delete_policy(name)
        if response.ok:
            self.notification.emit("Policy Deleted", f"Policy {name} deleted")
    
    def _show_engine_info(self, mount_path: str):
        response = self.client.mount_info(mount_path)
        if response.ok:
            dialog = JsonEditorDialog(f"Engine: {mount_path}", response.data, readonly=True)
            dialog.exec()
    
    def _show_transit_key(self, mount_path: str, key_name: str):
        response = self.client.api_read(f"{mount_path}/keys/{key_name}")
        if response.ok:
            dialog = JsonEditorDialog(f"Transit Key: {key_name}", response.data, readonly=True)
            dialog.exec()
    
    def _refresh_schema(self):
        self._schema_cache = None
        self.client._schema_cache = None
        self.client.get_openapi_schema(force_refresh=True)
        self.notification.emit("Schema Refreshed", "OpenAPI schema cache refreshed")
    
    # ============ Transit Engine Handlers ============
    
    def _show_transit_key_info(self, mount_path: str, key_name: str):
        response = self.client.transit_read_key(mount_path, key_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Transit Key: {key_name}", response.data, readonly=True)
            dialog.exec()
    
    def _create_transit_key(self, mount_path: str):
        name, ok = QInputDialog.getText(None, "New Transit Key", "Key name:")
        if ok and name:
            dialog = CrudDialog("New Transit Key", {
                'name': name,
                'type': 'aes256-gcm96',
                'exportable': False,
                'allow_plaintext_backup': False
            })
            if dialog.exec():
                data = dialog.data
                response = self.client.transit_create_key(
                    mount_path, data.get('name', name),
                    key_type=data.get('type', 'aes256-gcm96'),
                    exportable=data.get('exportable', False),
                    allow_plaintext_backup=data.get('allow_plaintext_backup', False)
                )
                if response.ok:
                    self.notification.emit("Key Created", f"Transit key {name} created")
                else:
                    QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _rotate_transit_key(self, mount_path: str, key_name: str):
        reply = QMessageBox.question(None, "Rotate Key", f"Rotate key '{key_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.transit_rotate_key(mount_path, key_name)
            if response.ok:
                self.notification.emit("Key Rotated", f"Key {key_name} rotated")
    
    def _export_transit_key(self, mount_path: str, key_name: str):
        key_type, ok = QInputDialog.getItem(None, "Export Key", "Key type:",
            ['encryption-key', 'signing-key', 'hmac-key'], 0, False)
        if ok:
            response = self.client.transit_export_key(mount_path, key_name, key_type)
            if response.ok:
                dialog = JsonEditorDialog(f"Exported Key: {key_name}", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Export failed (key may not be exportable): {response.error}")
    
    def _configure_transit_key(self, mount_path: str, key_name: str):
        response = self.client.transit_read_key(mount_path, key_name)
        if response.ok:
            key_data = response.data.get('data', {})
            dialog = CrudDialog(f"Configure Key: {key_name}", {
                'deletion_allowed': key_data.get('deletion_allowed', False),
                'min_decryption_version': key_data.get('min_decryption_version', 1),
                'min_encryption_version': key_data.get('min_encryption_version', 0)
            })
            if dialog.exec():
                data = dialog.data
                update_response = self.client.transit_update_key_config(
                    mount_path, key_name,
                    deletion_allowed=data.get('deletion_allowed'),
                    min_decryption_version=data.get('min_decryption_version'),
                    min_encryption_version=data.get('min_encryption_version')
                )
                if update_response.ok:
                    self.notification.emit("Key Configured", f"Key {key_name} updated")
    
    def _delete_transit_key(self, mount_path: str, key_name: str):
        reply = QMessageBox.warning(None, "Delete Key",
            f"⚠️ Delete key '{key_name}'?\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.transit_delete_key(mount_path, key_name)
            if response.ok:
                self.notification.emit("Key Deleted", f"Key {key_name} deleted")
            else:
                QMessageBox.warning(None, "Error", f"Failed (enable deletion first): {response.error}")
    
    def _transit_encrypt_dialog(self, mount_path: str):
        """Dialog to encrypt data with any key."""
        key_name, ok = QInputDialog.getText(None, "Encrypt", "Key name:")
        if ok and key_name:
            self._transit_encrypt_with_key(mount_path, key_name)
    
    def _transit_encrypt_with_key(self, mount_path: str, key_name: str):
        # Ask for input method
        choice = QMessageBox.question(
            None, "Encrypt Data",
            "Select a file to encrypt?\n\nClick 'Yes' for file, 'No' to type text.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        
        if choice == QMessageBox.StandardButton.Cancel:
            return
        
        if choice == QMessageBox.StandardButton.Yes:
            # File selection
            file_path, _ = QFileDialog.getOpenFileName(None, "Select File to Encrypt", "", "All Files (*)")
            if not file_path:
                return
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                encoded = base64.b64encode(data).decode()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to read file: {e}")
                return
        else:
            # Text input
            plaintext, ok = QInputDialog.getMultiLineText(None, "Encrypt", "Plaintext data:")
            if not ok or not plaintext:
                return
            encoded = base64.b64encode(plaintext.encode()).decode()
        
        response = self.client.transit_encrypt(mount_path, key_name, encoded)
        if response.ok:
            ciphertext = response.data.get('data', {}).get('ciphertext', '')
            dialog = JsonEditorDialog("Encrypted Data", {'ciphertext': ciphertext}, readonly=True)
            dialog.exec()
            
            # Offer to save
            save_reply = QMessageBox.question(None, "Save", "Save ciphertext to file?")
            if save_reply == QMessageBox.StandardButton.Yes:
                save_path, _ = QFileDialog.getSaveFileName(None, "Save Ciphertext", "", "Text Files (*.txt);;All Files (*)")
                if save_path:
                    with open(save_path, 'w') as f:
                        f.write(ciphertext)
                    self.notification.emit("Saved", f"Ciphertext saved to {save_path}")
        else:
            QMessageBox.warning(None, "Error", f"Encryption failed: {response.error}")
    
    def _transit_decrypt_dialog(self, mount_path: str):
        key_name, ok = QInputDialog.getText(None, "Decrypt", "Key name:")
        if ok and key_name:
            self._transit_decrypt_with_key(mount_path, key_name)
    
    def _transit_decrypt_with_key(self, mount_path: str, key_name: str):
        # Ask for input method
        choice = QMessageBox.question(
            None, "Decrypt Data",
            "Load ciphertext from file?\n\nClick 'Yes' for file, 'No' to paste.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        
        if choice == QMessageBox.StandardButton.Cancel:
            return
        
        if choice == QMessageBox.StandardButton.Yes:
            file_path, _ = QFileDialog.getOpenFileName(None, "Select Ciphertext File", "", "Text Files (*.txt);;All Files (*)")
            if not file_path:
                return
            try:
                with open(file_path, 'r') as f:
                    ciphertext = f.read().strip()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to read file: {e}")
                return
        else:
            ciphertext, ok = QInputDialog.getText(None, "Decrypt", "Ciphertext (vault:v1:...):")
            if not ok or not ciphertext:
                return
        
        response = self.client.transit_decrypt(mount_path, key_name, ciphertext)
        if response.ok:
            plaintext_b64 = response.data.get('data', {}).get('plaintext', '')
            try:
                plaintext_bytes = base64.b64decode(plaintext_b64)
                # Try to decode as text
                try:
                    plaintext = plaintext_bytes.decode('utf-8')
                    is_binary = False
                except UnicodeDecodeError:
                    plaintext = f"(Binary data, {len(plaintext_bytes)} bytes)"
                    is_binary = True
            except:
                plaintext = plaintext_b64
                plaintext_bytes = None
                is_binary = False
            
            dialog = JsonEditorDialog("Decrypted Data", {'plaintext': plaintext}, readonly=True)
            dialog.exec()
            
            # Offer to save
            if plaintext_bytes:
                save_reply = QMessageBox.question(None, "Save", "Save decrypted data to file?")
                if save_reply == QMessageBox.StandardButton.Yes:
                    save_path, _ = QFileDialog.getSaveFileName(None, "Save Decrypted Data", "", "All Files (*)")
                    if save_path:
                        with open(save_path, 'wb') as f:
                            f.write(plaintext_bytes)
                        self.notification.emit("Saved", f"Decrypted data saved to {save_path}")
        else:
            QMessageBox.warning(None, "Error", f"Decryption failed: {response.error}")
    
    def _transit_rewrap_with_key(self, mount_path: str, key_name: str):
        # Ask for input method
        choice = QMessageBox.question(
            None, "Rewrap",
            "Load ciphertext from file?\n\nClick 'Yes' for file, 'No' to paste.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        
        if choice == QMessageBox.StandardButton.Cancel:
            return
        
        if choice == QMessageBox.StandardButton.Yes:
            file_path, _ = QFileDialog.getOpenFileName(None, "Select Ciphertext File", "", "Text Files (*.txt);;All Files (*)")
            if not file_path:
                return
            try:
                with open(file_path, 'r') as f:
                    ciphertext = f.read().strip()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to read file: {e}")
                return
        else:
            ciphertext, ok = QInputDialog.getText(None, "Rewrap", "Ciphertext to rewrap:")
            if not ok or not ciphertext:
                return
        
        response = self.client.transit_rewrap(mount_path, key_name, ciphertext)
        if response.ok:
            new_ciphertext = response.data.get('data', {}).get('ciphertext', '')
            dialog = JsonEditorDialog("Rewrapped Data", {'ciphertext': new_ciphertext}, readonly=True)
            dialog.exec()
    
    def _transit_sign_dialog(self, mount_path: str):
        key_name, ok = QInputDialog.getText(None, "Sign", "Key name:")
        if ok and key_name:
            self._transit_sign_with_key(mount_path, key_name)
    
    def _transit_sign_with_key(self, mount_path: str, key_name: str):
        # Ask for input method
        choice = QMessageBox.question(
            None, "Sign Data",
            "Select a file to sign?\n\nClick 'Yes' for file, 'No' to type text.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        
        if choice == QMessageBox.StandardButton.Cancel:
            return
        
        if choice == QMessageBox.StandardButton.Yes:
            file_path, _ = QFileDialog.getOpenFileName(None, "Select File to Sign", "", "All Files (*)")
            if not file_path:
                return
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                encoded = base64.b64encode(data).decode()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to read file: {e}")
                return
        else:
            data, ok = QInputDialog.getMultiLineText(None, "Sign Data", "Data to sign:")
            if not ok or not data:
                return
            encoded = base64.b64encode(data.encode()).decode()
        
        response = self.client.transit_sign(mount_path, key_name, encoded)
        if response.ok:
            signature = response.data.get('data', {}).get('signature', '')
            dialog = JsonEditorDialog("Signature", {
                'signature': signature, 
                'key_version': response.data.get('data', {}).get('key_version')
            }, readonly=True)
            dialog.exec()
            
            # Offer to save signature
            save_reply = QMessageBox.question(None, "Save", "Save signature to file?")
            if save_reply == QMessageBox.StandardButton.Yes:
                save_path, _ = QFileDialog.getSaveFileName(None, "Save Signature", "", "Signature Files (*.sig);;Text Files (*.txt);;All Files (*)")
                if save_path:
                    with open(save_path, 'w') as f:
                        f.write(signature)
                    self.notification.emit("Saved", f"Signature saved to {save_path}")
        else:
            QMessageBox.warning(None, "Error", f"Signing failed: {response.error}")
    
    def _transit_verify_dialog(self, mount_path: str):
        key_name, ok = QInputDialog.getText(None, "Verify", "Key name:")
        if ok and key_name:
            self._transit_verify_with_key(mount_path, key_name)
    
    def _transit_verify_with_key(self, mount_path: str, key_name: str):
        # Ask for data input method
        choice = QMessageBox.question(
            None, "Verify Signature",
            "Load data from file?\n\nClick 'Yes' for file, 'No' to type text.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        
        if choice == QMessageBox.StandardButton.Cancel:
            return
        
        if choice == QMessageBox.StandardButton.Yes:
            file_path, _ = QFileDialog.getOpenFileName(None, "Select Data File", "", "All Files (*)")
            if not file_path:
                return
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                encoded = base64.b64encode(data).decode()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to read file: {e}")
                return
        else:
            text_data, ok = QInputDialog.getMultiLineText(None, "Verify", "Data that was signed:")
            if not ok or not text_data:
                return
            encoded = base64.b64encode(text_data.encode()).decode()
        
        # Ask for signature input
        sig_choice = QMessageBox.question(
            None, "Signature",
            "Load signature from file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if sig_choice == QMessageBox.StandardButton.Yes:
            sig_file, _ = QFileDialog.getOpenFileName(None, "Select Signature File", "", "Signature Files (*.sig);;Text Files (*.txt);;All Files (*)")
            if not sig_file:
                return
            try:
                with open(sig_file, 'r') as f:
                    signature = f.read().strip()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to read signature: {e}")
                return
        else:
            signature, ok = QInputDialog.getText(None, "Verify", "Signature (vault:v1:...):")
            if not ok or not signature:
                return
        
        response = self.client.transit_verify(mount_path, key_name, encoded, signature)
        if response.ok:
            valid = response.data.get('data', {}).get('valid', False)
            if valid:
                QMessageBox.information(None, "Verification", "✅ Signature is VALID")
            else:
                QMessageBox.warning(None, "Verification", "❌ Signature is INVALID")
        else:
            QMessageBox.warning(None, "Error", f"Verification failed: {response.error}")
    
    def _transit_hmac_dialog(self, mount_path: str):
        key_name, ok = QInputDialog.getText(None, "HMAC", "Key name:")
        if ok and key_name:
            self._transit_hmac_with_key(mount_path, key_name)
    
    def _transit_hmac_with_key(self, mount_path: str, key_name: str):
        # Ask for input method
        choice = QMessageBox.question(
            None, "Generate HMAC",
            "Load data from file?\n\nClick 'Yes' for file, 'No' to type text.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        
        if choice == QMessageBox.StandardButton.Cancel:
            return
        
        if choice == QMessageBox.StandardButton.Yes:
            file_path, _ = QFileDialog.getOpenFileName(None, "Select Data File", "", "All Files (*)")
            if not file_path:
                return
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                encoded = base64.b64encode(data).decode()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to read file: {e}")
                return
        else:
            text_data, ok = QInputDialog.getMultiLineText(None, "HMAC", "Data:")
            if not ok or not text_data:
                return
            encoded = base64.b64encode(text_data.encode()).decode()
        
        response = self.client.transit_generate_hmac(mount_path, key_name, encoded)
        if response.ok:
            hmac = response.data.get('data', {}).get('hmac', '')
            dialog = JsonEditorDialog("HMAC", {'hmac': hmac}, readonly=True)
            dialog.exec()
            
            # Offer to save
            save_reply = QMessageBox.question(None, "Save", "Save HMAC to file?")
            if save_reply == QMessageBox.StandardButton.Yes:
                save_path, _ = QFileDialog.getSaveFileName(None, "Save HMAC", "", "Text Files (*.txt);;All Files (*)")
                if save_path:
                    with open(save_path, 'w') as f:
                        f.write(hmac)
                    self.notification.emit("Saved", f"HMAC saved to {save_path}")
    
    def _transit_datakey_dialog(self, mount_path: str):
        key_name, ok = QInputDialog.getText(None, "Generate Data Key", "Wrapping key name:")
        if ok and key_name:
            key_type, ok = QInputDialog.getItem(None, "Data Key Type", "Type:",
                ['plaintext', 'wrapped'], 0, False)
            if ok:
                response = self.client.transit_generate_data_key(mount_path, key_name, key_type)
                if response.ok:
                    dialog = JsonEditorDialog("Data Key", response.data.get('data', {}), readonly=True)
                    dialog.exec()
    
    # ============ PKI Engine Handlers ============
    
    def _show_pki_ca(self, mount_path: str):
        response = self.client.pki_read_ca_cert(mount_path)
        if response.ok:
            # Response is raw PEM text
            cert_pem = response.data if isinstance(response.data, str) else response.data.get('data', {}).get('certificate', '')
            dialog = JsonEditorDialog("CA Certificate", {'certificate': cert_pem}, readonly=True)
            dialog.exec()
    
    def _show_pki_crl(self, mount_path: str):
        response = self.client.pki_read_crl(mount_path)
        if response.ok:
            crl_pem = response.data if isinstance(response.data, str) else str(response.data)
            dialog = JsonEditorDialog("CRL", {'crl': crl_pem}, readonly=True)
            dialog.exec()
    
    def _generate_pki_root(self, mount_path: str):
        dialog = CrudDialog("Generate Root CA", {
            'common_name': '',
            'key_type': 'rsa',
            'key_bits': 2048,
            'ttl': '87600h',
            'issuer_name': ''
        })
        if dialog.exec():
            data = dialog.data
            response = self.client.pki_generate_root(
                mount_path,
                common_name=data.get('common_name', ''),
                key_type=data.get('key_type', 'rsa'),
                key_bits=int(data.get('key_bits', 2048)),
                ttl=data.get('ttl', '87600h'),
                issuer_name=data.get('issuer_name') or None
            )
            if response.ok:
                self.notification.emit("Root CA Generated", "Root CA certificate generated")
                dialog = JsonEditorDialog("Root CA", response.data, readonly=True)
                dialog.exec()
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _generate_pki_intermediate(self, mount_path: str):
        dialog = CrudDialog("Generate Intermediate CSR", {
            'common_name': '',
            'key_type': 'rsa',
            'key_bits': 2048
        })
        if dialog.exec():
            data = dialog.data
            response = self.client.pki_generate_intermediate(
                mount_path,
                common_name=data.get('common_name', ''),
                key_type=data.get('key_type', 'rsa'),
                key_bits=int(data.get('key_bits', 2048))
            )
            if response.ok:
                csr = response.data.get('data', {}).get('csr', '')
                dialog = JsonEditorDialog("Intermediate CSR", {'csr': csr}, readonly=True)
                dialog.exec()
    
    def _set_pki_signed_intermediate(self, mount_path: str):
        cert, ok = QInputDialog.getMultiLineText(None, "Set Signed Intermediate",
            "Paste signed intermediate certificate (PEM):")
        if ok and cert:
            response = self.client.pki_set_signed_intermediate(mount_path, cert)
            if response.ok:
                self.notification.emit("Intermediate Set", "Signed intermediate certificate set")
            else:
                QMessageBox.warning(None, "Error", f"Failed: {response.error}")
    
    def _show_pki_role_info(self, mount_path: str, role_name: str):
        response = self.client.pki_read_role(mount_path, role_name)
        if response.ok:
            dialog = JsonEditorDialog(f"PKI Role: {role_name}", response.data, readonly=True)
            dialog.exec()
    
    def _create_pki_role(self, mount_path: str):
        name, ok = QInputDialog.getText(None, "New PKI Role", "Role name:")
        if ok and name:
            dialog = CrudDialog("New PKI Role", {
                'name': name,
                'allowed_domains': '',
                'allow_subdomains': True,
                'allow_any_name': False,
                'max_ttl': '72h',
                'ttl': '24h',
                'key_type': 'rsa',
                'key_bits': 2048
            })
            if dialog.exec():
                data = dialog.data
                domains = [d.strip() for d in data.get('allowed_domains', '').split(',') if d.strip()]
                response = self.client.pki_create_role(
                    mount_path, data.get('name', name),
                    allowed_domains=domains or None,
                    allow_subdomains=data.get('allow_subdomains', True),
                    allow_any_name=data.get('allow_any_name', False),
                    max_ttl=data.get('max_ttl', '72h'),
                    ttl=data.get('ttl', '24h'),
                    key_type=data.get('key_type', 'rsa'),
                    key_bits=int(data.get('key_bits', 2048))
                )
                if response.ok:
                    self.notification.emit("Role Created", f"PKI role {name} created")
    
    def _edit_pki_role(self, mount_path: str, role_name: str):
        response = self.client.pki_read_role(mount_path, role_name)
        if response.ok:
            role_data = response.data.get('data', {})
            domains = ','.join(role_data.get('allowed_domains', []))
            dialog = CrudDialog(f"Edit PKI Role: {role_name}", {
                'allowed_domains': domains,
                'allow_subdomains': role_data.get('allow_subdomains', True),
                'allow_any_name': role_data.get('allow_any_name', False),
                'max_ttl': str(role_data.get('max_ttl', 0)),
                'ttl': str(role_data.get('ttl', 0)),
                'key_type': role_data.get('key_type', 'rsa'),
                'key_bits': role_data.get('key_bits', 2048)
            })
            if dialog.exec():
                data = dialog.data
                domains = [d.strip() for d in data.get('allowed_domains', '').split(',') if d.strip()]
                self.client.pki_create_role(
                    mount_path, role_name,
                    allowed_domains=domains or None,
                    allow_subdomains=data.get('allow_subdomains', True),
                    allow_any_name=data.get('allow_any_name', False),
                    max_ttl=data.get('max_ttl', '72h'),
                    ttl=data.get('ttl', '24h'),
                    key_type=data.get('key_type', 'rsa'),
                    key_bits=int(data.get('key_bits', 2048))
                )
    
    def _delete_pki_role(self, mount_path: str, role_name: str):
        reply = QMessageBox.question(None, "Delete Role", f"Delete role '{role_name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.pki_delete_role(mount_path, role_name)
            if response.ok:
                self.notification.emit("Role Deleted", f"PKI role {role_name} deleted")
    
    def _issue_pki_cert_dialog(self, mount_path: str):
        role_name, ok = QInputDialog.getText(None, "Issue Certificate", "Role name:")
        if ok and role_name:
            self._issue_cert_for_role(mount_path, role_name)
    
    def _issue_cert_for_role(self, mount_path: str, role_name: str):
        dialog = CrudDialog("Issue Certificate", {
            'common_name': '',
            'alt_names': '',
            'ip_sans': '',
            'ttl': ''
        })
        if dialog.exec():
            data = dialog.data
            response = self.client.pki_issue_cert(
                mount_path, role_name,
                common_name=data.get('common_name', ''),
                alt_names=data.get('alt_names') or None,
                ip_sans=data.get('ip_sans') or None,
                ttl=data.get('ttl') or None
            )
            if response.ok:
                cert_data = response.data.get('data', {})
                dialog = JsonEditorDialog("Issued Certificate", cert_data, readonly=True)
                dialog.exec()
                self.notification.emit("Certificate Issued", f"Certificate issued for {data.get('common_name')}")
            else:
                QMessageBox.warning(None, "Error", f"Failed to issue certificate: {response.error}")
    
    def _sign_pki_csr_dialog(self, mount_path: str):
        role_name, ok = QInputDialog.getText(None, "Sign CSR", "Role name:")
        if ok and role_name:
            self._sign_csr_for_role(mount_path, role_name)
    
    def _sign_csr_for_role(self, mount_path: str, role_name: str):
        csr, ok = QInputDialog.getMultiLineText(None, "Sign CSR", "Paste CSR (PEM):")
        if ok and csr:
            response = self.client.pki_sign_csr(mount_path, role_name, csr)
            if response.ok:
                cert_data = response.data.get('data', {})
                dialog = JsonEditorDialog("Signed Certificate", cert_data, readonly=True)
                dialog.exec()
                self.notification.emit("CSR Signed", "CSR signed successfully")
            else:
                QMessageBox.warning(None, "Error", f"Failed to sign CSR: {response.error}")
    
    def _show_pki_issuer(self, mount_path: str, issuer_ref: str):
        response = self.client.pki_read_issuer(mount_path, issuer_ref)
        if response.ok:
            dialog = JsonEditorDialog(f"Issuer: {issuer_ref[:16]}...", response.data, readonly=True)
            dialog.exec()
    
    def _show_pki_cert(self, mount_path: str, serial: str):
        response = self.client.pki_read_cert(mount_path, serial)
        if response.ok:
            dialog = JsonEditorDialog(f"Certificate: {serial[:20]}...", response.data, readonly=True)
            dialog.exec()
    
    def _revoke_pki_cert(self, mount_path: str, serial: str):
        reply = QMessageBox.warning(None, "Revoke Certificate",
            f"⚠️ Revoke certificate {serial[:20]}...?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.pki_revoke_cert(mount_path, serial)
            if response.ok:
                self.notification.emit("Certificate Revoked", f"Certificate {serial[:16]}... revoked")
            else:
                QMessageBox.warning(None, "Error", f"Failed to revoke: {response.error}")
    
    def _tidy_pki(self, mount_path: str):
        reply = QMessageBox.question(None, "Tidy PKI", "Tidy up the certificate store?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.pki_tidy(mount_path)
            if response.ok:
                self.notification.emit("Tidy Started", "PKI tidy operation started")
