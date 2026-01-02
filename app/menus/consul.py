"""Consul Menu Builder for OpenTongchi"""

from typing import Dict, Optional
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog
from PySide6.QtCore import QObject, Signal
from app.clients.consul import ConsulClient
from app.async_menu import AsyncMenu, create_status_prefix
from app.dialogs import JsonEditorDialog, CrudDialog
import base64


class ConsulMenuBuilder(QObject):
    notification = Signal(str, str)
    
    def __init__(self, settings, process_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        self._client: Optional[ConsulClient] = None
    
    @property
    def client(self) -> ConsulClient:
        if self._client is None:
            self._client = ConsulClient(self.settings.consul)
        return self._client
    
    def refresh_client(self):
        self._client = None
    
    def build_menu(self) -> QMenu:
        menu = QMenu("🔍 Consul")
        
        if not self.settings.consul.address:
            not_configured = menu.addAction("⚠️ Not Configured")
            not_configured.setEnabled(False)
            return menu
        
        self._add_status_menu(menu)
        menu.addSeparator()
        
        # Services
        services_menu = self._create_services_menu()
        menu.addMenu(services_menu)
        
        # KV Store
        kv_menu = self._create_kv_menu()
        menu.addMenu(kv_menu)
        
        # Nodes
        nodes_menu = self._create_nodes_menu()
        menu.addMenu(nodes_menu)
        
        # Health
        health_menu = self._create_health_menu()
        menu.addMenu(health_menu)
        
        menu.addSeparator()
        
        # ACL
        acl_menu = self._create_acl_menu()
        menu.addMenu(acl_menu)
        
        # Sessions
        sessions_menu = AsyncMenu("📋 Sessions", self._load_sessions)
        menu.addMenu(sessions_menu)
        
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
    
    def _create_services_menu(self) -> QMenu:
        menu = AsyncMenu("🌐 Services", self._load_services)
        menu.set_submenu_factory(self._create_service_submenu)
        return menu
    
    def _load_services(self) -> list:
        response = self.client.catalog_services()
        if not response.ok:
            raise Exception(response.error or "Failed to list services")
        
        services = response.data or {}
        items = []
        
        for service_name, tags in services.items():
            status = self.client.get_service_health_status(service_name)
            emoji = {'passing': '🟢', 'warning': '🟠', 'critical': '🔴'}.get(status, '⚪')
            
            items.append({
                'text': f"{emoji} {service_name}",
                'data': {'name': service_name, 'tags': tags},
                'is_submenu': True
            })
        return items
    
    def _create_service_submenu(self, title: str, data: Dict) -> QMenu:
        service_name = data['name']
        menu = QMenu(title)
        
        info = menu.addAction("ℹ️ Service Info")
        info.triggered.connect(lambda: self._show_service_info(service_name))
        
        health = menu.addAction("❤️ Health Checks")
        health.triggered.connect(lambda: self._show_service_health(service_name))
        
        instances = menu.addAction("📋 Instances")
        instances.triggered.connect(lambda: self._show_service_instances(service_name))
        
        return menu
    
    def _create_kv_menu(self) -> QMenu:
        def load_kv(prefix: str = ""):
            response = self.client.kv_list(prefix)
            if not response.ok:
                if response.status_code == 404:
                    return []
                raise Exception(response.error or "Failed to list KV")
            
            keys = response.data or []
            items = []
            
            # Group by directory level
            seen_dirs = set()
            for key in keys:
                if prefix:
                    key = key[len(prefix):] if key.startswith(prefix) else key
                
                if '/' in key:
                    dir_name = key.split('/')[0] + '/'
                    if dir_name not in seen_dirs:
                        seen_dirs.add(dir_name)
                        full_path = prefix + dir_name
                        items.append({
                            'text': f"📁 {dir_name}",
                            'data': {'path': full_path, 'is_folder': True},
                            'is_submenu': True
                        })
                else:
                    items.append({
                        'text': f"🔑 {key}",
                        'data': {'path': prefix + key, 'is_folder': False},
                        'callback': lambda d: self._show_kv_value(d['path'])
                    })
            return items
        
        menu = AsyncMenu("📦 KV Store", lambda: load_kv(""))
        menu.set_new_item_callback(lambda: self._create_kv(""), "➕ New Key...")
        
        def create_folder_submenu(title: str, data: Dict) -> QMenu:
            path = data['path']
            submenu = AsyncMenu(title, lambda: load_kv(path))
            submenu.set_new_item_callback(lambda: self._create_kv(path), "➕ New Key...")
            submenu.set_submenu_factory(create_folder_submenu)
            return submenu
        
        menu.set_submenu_factory(create_folder_submenu)
        return menu
    
    def _create_nodes_menu(self) -> QMenu:
        menu = AsyncMenu("🖥️ Nodes", self._load_nodes)
        menu.set_item_callback(self._show_node)
        return menu
    
    def _load_nodes(self) -> list:
        response = self.client.catalog_nodes()
        if not response.ok:
            raise Exception(response.error or "Failed to list nodes")
        
        nodes = response.data or []
        items = []
        
        for node in nodes:
            node_name = node.get('Node', 'unknown')
            address = node.get('Address', '')
            items.append((f"🖥️ {node_name} ({address})", node))
        return items
    
    def _create_health_menu(self) -> QMenu:
        menu = QMenu("❤️ Health")
        
        all_checks = menu.addAction("📋 All Checks")
        all_checks.triggered.connect(self._show_all_checks)
        
        menu.addSeparator()
        
        passing = menu.addAction("🟢 Passing")
        passing.triggered.connect(lambda: self._show_checks_by_state('passing'))
        
        warning = menu.addAction("🟠 Warning")
        warning.triggered.connect(lambda: self._show_checks_by_state('warning'))
        
        critical = menu.addAction("🔴 Critical")
        critical.triggered.connect(lambda: self._show_checks_by_state('critical'))
        
        return menu
    
    def _create_acl_menu(self) -> QMenu:
        menu = QMenu("🔐 ACL")
        
        tokens = AsyncMenu("🎫 Tokens", self._load_acl_tokens)
        menu.addMenu(tokens)
        
        policies = AsyncMenu("📜 Policies", self._load_acl_policies)
        menu.addMenu(policies)
        
        return menu
    
    def _load_sessions(self) -> list:
        response = self.client.session_list()
        if not response.ok:
            raise Exception(response.error or "Failed to list sessions")
        
        sessions = response.data or []
        return [(f"📋 {s.get('ID', '')[:8]}... ({s.get('Name', 'unnamed')})", s) for s in sessions]
    
    def _load_acl_tokens(self) -> list:
        response = self.client.acl_token_list()
        if not response.ok:
            if response.status_code == 403:
                return [("🔒 ACL Disabled or Unauthorized", None)]
            raise Exception(response.error or "Failed to list tokens")
        
        tokens = response.data or []
        return [(f"🎫 {t.get('AccessorID', '')[:8]}... ({t.get('Description', 'no desc')})", t) for t in tokens]
    
    def _load_acl_policies(self) -> list:
        response = self.client.acl_policy_list()
        if not response.ok:
            if response.status_code == 403:
                return [("🔒 ACL Disabled or Unauthorized", None)]
            raise Exception(response.error or "Failed to list policies")
        
        policies = response.data or []
        return [(f"📜 {p.get('Name', 'unnamed')}", p) for p in policies]
    
    # Action handlers
    def _show_service_info(self, service_name: str):
        response = self.client.catalog_service(service_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Service: {service_name}", response.data, readonly=True)
            dialog.exec()
    
    def _show_service_health(self, service_name: str):
        response = self.client.health_checks(service_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Health: {service_name}", response.data, readonly=True)
            dialog.exec()
    
    def _show_service_instances(self, service_name: str):
        response = self.client.health_service(service_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Instances: {service_name}", response.data, readonly=True)
            dialog.exec()
    
    def _show_kv_value(self, key: str):
        response = self.client.kv_get(key)
        if response.ok and response.data:
            entries = response.data if isinstance(response.data, list) else [response.data]
            if entries:
                entry = entries[0]
                value = entry.get('Value', '')
                if value:
                    try:
                        value = base64.b64decode(value).decode('utf-8')
                    except:
                        pass
                
                dialog = CrudDialog(f"KV: {key}", {'key': key, 'value': value})
                dialog.saved.connect(lambda d: self._save_kv(key, d.get('value', '')))
                dialog.deleted.connect(lambda: self._delete_kv(key))
                dialog.exec()
    
    def _create_kv(self, prefix: str):
        key, ok = QInputDialog.getText(None, "New Key", "Key name:")
        if ok and key:
            full_key = prefix + key if prefix else key
            value, ok = QInputDialog.getText(None, "Value", "Value:")
            if ok:
                self._save_kv(full_key, value)
    
    def _save_kv(self, key: str, value: str):
        response = self.client.kv_put(key, value)
        if response.ok:
            self.notification.emit("KV Saved", f"Key {key} saved")
        else:
            QMessageBox.warning(None, "Error", f"Failed to save: {response.error}")
    
    def _delete_kv(self, key: str):
        response = self.client.kv_delete(key)
        if response.ok:
            self.notification.emit("KV Deleted", f"Key {key} deleted")
    
    def _show_node(self, node: Dict):
        node_name = node.get('Node', 'unknown')
        response = self.client.catalog_node(node_name)
        if response.ok:
            dialog = JsonEditorDialog(f"Node: {node_name}", response.data, readonly=True)
            dialog.exec()
    
    def _show_all_checks(self):
        response = self.client.health_state('any')
        if response.ok:
            dialog = JsonEditorDialog("All Health Checks", response.data, readonly=True)
            dialog.exec()
    
    def _show_checks_by_state(self, state: str):
        response = self.client.health_state(state)
        if response.ok:
            dialog = JsonEditorDialog(f"Health Checks: {state}", response.data, readonly=True)
            dialog.exec()
