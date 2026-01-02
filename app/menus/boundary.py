"""Boundary Menu Builder for OpenTongchi"""

from typing import Dict, Optional
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
        self._client = None
    
    def build_menu(self) -> QMenu:
        menu = QMenu("🚪 Boundary")
        
        if not self.settings.boundary.address:
            not_configured = menu.addAction("⚠️ Not Configured")
            not_configured.setEnabled(False)
            return menu
        
        self._add_status_menu(menu)
        menu.addSeparator()
        
        # Targets
        targets_menu = self._create_targets_menu()
        menu.addMenu(targets_menu)
        
        # Active Sessions
        sessions_menu = self._create_sessions_menu()
        menu.addMenu(sessions_menu)
        
        # Active Connections (local)
        connections_menu = self._create_connections_menu()
        menu.addMenu(connections_menu)
        
        menu.addSeparator()
        
        # Scopes
        scopes_menu = self._create_scopes_menu()
        menu.addMenu(scopes_menu)
        
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
    
    def _create_targets_menu(self) -> QMenu:
        menu = AsyncMenu("🎯 Targets", self._load_targets)
        menu.set_submenu_factory(self._create_target_submenu)
        return menu
    
    def _load_targets(self) -> list:
        result = self.client.target_list()
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list targets'))
        
        data = result.get('data', {})
        targets = data.get('items', []) if isinstance(data, dict) else []
        items = []
        
        for target in targets:
            target_id = target.get('id', '')
            name = target.get('name', 'unnamed')
            target_type = target.get('type', '')
            
            # Check if connected
            connected = self.client.is_connected(target_id)
            emoji = '🟢' if connected else '⚪'
            lock = '🔓' if connected else '🔒'
            
            items.append({
                'text': f"{emoji} {lock} {name} ({target_type})",
                'data': target,
                'is_submenu': True
            })
        return items
    
    def _create_target_submenu(self, title: str, data: Dict) -> QMenu:
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
    
    def _create_sessions_menu(self) -> QMenu:
        menu = AsyncMenu("📋 Sessions", self._load_sessions)
        menu.set_submenu_factory(self._create_session_submenu)
        return menu
    
    def _load_sessions(self) -> list:
        result = self.client.session_list()
        if not result.get('success'):
            raise Exception(result.get('error', 'Failed to list sessions'))
        
        data = result.get('data', {})
        sessions = data.get('items', []) if isinstance(data, dict) else []
        items = []
        
        for session in sessions:
            session_id = session.get('id', '')[:8]
            status = session.get('status', '')
            target_id = session.get('target_id', '')
            
            emoji = {'active': '🟢', 'pending': '🟡', 'canceling': '🟠'}.get(status, '⚪')
            
            items.append({
                'text': f"{emoji} {session_id}... ({status})",
                'data': session,
                'is_submenu': True
            })
        return items
    
    def _create_session_submenu(self, title: str, data: Dict) -> QMenu:
        session_id = data.get('id', '')
        menu = QMenu(title)
        
        info = menu.addAction("ℹ️ Session Details")
        info.triggered.connect(lambda: self._show_session(session_id))
        
        menu.addSeparator()
        
        cancel = menu.addAction("🚫 Cancel Session")
        cancel.triggered.connect(lambda: self._cancel_session(session_id))
        
        return menu
    
    def _create_connections_menu(self) -> QMenu:
        menu = QMenu("🔌 Active Connections")
        
        active = self.client.get_active_connections()
        
        if not active:
            no_conn = menu.addAction("(No active connections)")
            no_conn.setEnabled(False)
        else:
            for target_id in active:
                action = menu.addAction(f"🟢 {target_id[:8]}...")
                action.triggered.connect(lambda checked, tid=target_id: self._disconnect_target(tid))
        
        menu.addSeparator()
        
        disconnect_all = menu.addAction("🔌 Disconnect All")
        disconnect_all.triggered.connect(self._disconnect_all)
        
        return menu
    
    def _create_scopes_menu(self) -> QMenu:
        menu = AsyncMenu("📂 Scopes", self._load_scopes)
        menu.set_item_callback(self._show_scope)
        return menu
    
    def _load_scopes(self) -> list:
        response = self.client.scope_list()
        if not response.ok:
            raise Exception(response.error or "Failed to list scopes")
        
        data = response.data or {}
        scopes = data.get('items', []) if isinstance(data, dict) else []
        
        return [(f"📂 {s.get('name', s.get('id', 'unknown'))}", s) for s in scopes]
    
    # Action handlers
    def _show_target(self, target_id: str):
        result = self.client.target_read(target_id)
        if result.get('success'):
            dialog = JsonEditorDialog(f"Target: {target_id[:8]}...", result.get('data'), readonly=True)
            dialog.exec()
    
    def _connect_target(self, target_id: str):
        def do_connect():
            try:
                process = self.client.connect(target_id)
                return {'success': True, 'target_id': target_id}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        self.process_manager.start_process(
            name=f"Boundary Connect",
            description=f"Connecting to target {target_id[:8]}...",
            func=do_connect,
            cancellable=True
        )
        self.notification.emit("Connecting", f"Establishing connection to {target_id[:8]}...")
    
    def _connect_target_custom_port(self, target_id: str):
        port, ok = QInputDialog.getInt(None, "Custom Port", "Listen port:", 0, 0, 65535)
        if ok:
            try:
                self.client.connect(target_id, listen_port=port if port > 0 else None)
                self.notification.emit("Connected", f"Connected on port {port}")
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to connect: {e}")
    
    def _disconnect_target(self, target_id: str):
        if self.client.disconnect(target_id):
            self.notification.emit("Disconnected", f"Disconnected from {target_id[:8]}...")
    
    def _disconnect_all(self):
        active = self.client.get_active_connections()
        for target_id in active:
            self.client.disconnect(target_id)
        self.notification.emit("Disconnected", f"Disconnected {len(active)} connections")
    
    def _show_session(self, session_id: str):
        result = self.client.session_read(session_id)
        if result.get('success'):
            dialog = JsonEditorDialog(f"Session: {session_id[:8]}...", result.get('data'), readonly=True)
            dialog.exec()
    
    def _cancel_session(self, session_id: str):
        result = self.client.session_cancel(session_id)
        if result.get('success'):
            self.notification.emit("Session Cancelled", f"Session {session_id[:8]}... cancelled")
    
    def _show_scope(self, scope: Dict):
        dialog = JsonEditorDialog(f"Scope: {scope.get('name', '')}", scope, readonly=True)
        dialog.exec()
