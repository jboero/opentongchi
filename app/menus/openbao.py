"""
OpenBao Menu Builder for OpenTongchi
Builds dynamic menus for OpenBao/Vault operations using OpenAPI schema.
"""

import json
from typing import Dict, Any, Optional, Callable
from pathlib import Path
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog, QLineEdit
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
        
        policies_menu = self._create_policies_menu()
        menu.addMenu(policies_menu)
        
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
            keys_menu = AsyncMenu("🔑 Keys", lambda: self._load_generic_list(mount_path, 'keys'))
            keys_menu.set_item_callback(lambda d: self._show_transit_key(mount_path, d))
            menu.addMenu(keys_menu)
        elif engine_type == 'pki':
            roles_menu = AsyncMenu("👤 Roles", lambda: self._load_generic_list(mount_path, 'roles'))
            menu.addMenu(roles_menu)
        elif engine_type == 'database':
            config_menu = AsyncMenu("⚙️ Connections", lambda: self._load_generic_list(mount_path, 'config'))
            menu.addMenu(config_menu)
            roles_menu = AsyncMenu("👤 Roles", lambda: self._load_generic_list(mount_path, 'roles'))
            menu.addMenu(roles_menu)
        
        return menu
    
    def _create_auth_menu(self) -> QMenu:
        menu = AsyncMenu("🔓 Auth Methods", self._load_auth_methods)
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
                    'aws': '☁️', 'kubernetes': '☸️', 'oidc': '🔐'}.get(method_type, '🔑')
            
            items.append({
                'text': f"{icon} {path.rstrip('/')} ({method_type})",
                'data': {'path': path, 'type': method_type},
                'callback': lambda d: self._show_auth_method(d['path'], d['type'])
            })
        return items
    
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
    
    def _create_system_menu(self) -> QMenu:
        menu = QMenu("⚙️ System")
        
        health = menu.addAction("❤️ Health Status")
        health.triggered.connect(self._show_health)
        
        seal = menu.addAction("🔒 Seal Status")
        seal.triggered.connect(self._show_seal_status)
        
        leader = menu.addAction("👑 Leader Status")
        leader.triggered.connect(self._show_leader)
        
        menu.addSeparator()
        
        audit_menu = AsyncMenu("📝 Audit Devices", self._load_audit_devices)
        menu.addMenu(audit_menu)
        
        leases_menu = QMenu("📋 Leases")
        list_leases = leases_menu.addAction("🔍 Lookup Lease")
        list_leases.triggered.connect(self._lookup_lease)
        revoke_lease = leases_menu.addAction("🗑️ Revoke Lease")
        revoke_lease.triggered.connect(self._revoke_lease)
        menu.addMenu(leases_menu)
        
        return menu
    
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
        path, ok = QInputDialog.getText(None, "Enable Secrets Engine", "Mount path:")
        if not ok or not path:
            return
        engine_type, ok = QInputDialog.getItem(None, "Engine Type", "Select type:",
            ['kv', 'transit', 'pki', 'database', 'aws', 'ssh'], 0, False)
        if ok and engine_type:
            response = self.client.enable_secrets_engine(path, engine_type)
            if response.ok:
                self.notification.emit("Engine Enabled", f"Secrets engine {path} enabled")
    
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
    
    def _show_auth_method(self, path: str, method_type: str):
        QMessageBox.information(None, f"Auth Method: {path}", f"Type: {method_type}\nPath: {path}")
    
    def _show_policy(self, policy_name: str):
        response = self.client.read_policy(policy_name)
        if response.ok and response.data:
            policy_text = response.data.get('data', {}).get('policy', '')
            dialog = JsonEditorDialog(f"Policy: {policy_name}", {'name': policy_name, 'policy': policy_text})
            if dialog.exec():
                self.client.write_policy(policy_name, dialog.data.get('policy', ''))
    
    def _create_policy(self):
        name, ok = QInputDialog.getText(None, "New Policy", "Policy name:")
        if ok and name:
            dialog = JsonEditorDialog(f"New Policy: {name}", 
                {'name': name, 'policy': 'path "*" {\n  capabilities = ["read"]\n}'})
            if dialog.exec():
                self.client.write_policy(name, dialog.data.get('policy', ''))
    
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
