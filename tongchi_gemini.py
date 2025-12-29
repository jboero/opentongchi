#!/usr/bin/env python3
"""
OpenTongchi - Open Source Infrastructure Management System Tray Application
A Qt6-based system tray widget for managing OpenBao, OpenTofu, Nomad, Consul, etc.

Author: John Boero - boeroboy@gmail.com
Refactored and Extended for Full Feature Set
"""

import sys
import os
import json
import time
import threading
import re
import requests
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Union
from dataclasses import dataclass, field, fields
from functools import partial
from urllib.parse import urljoin
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QDialog, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QFormLayout, QMessageBox, QSpinBox, QCheckBox, QGroupBox, QTabWidget,
    QWidget, QHeaderView, QComboBox, QTextEdit, QDialogButtonBox,
    QInputDialog, QSplitter, QTreeWidget, QTreeWidgetItem, QProgressDialog,
    QStyle, QAbstractItemView
)
from PyQt6.QtGui import QIcon, QAction, QCursor, QPixmap, QPainter, QFont, QColor
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QSize, QMutex

# =============================================================================
# Global Constants & Status Utilities
# =============================================================================

STATUS_EMOJIS = {
    'healthy': '🟢', 'passing': '🟢', 'running': '🟢', 'alive': '🟢', 'ready': '🟢', 'complete': '🟢',
    'warning': '🟡', 'pending': '🟡', 'degraded': '🟡', 'unknown': '⚪️',
    'critical': '🔴', 'failed': '🔴', 'dead': '🔴', 'down': '🔴', 'error': '🔴',
    'stopped': '⚪️'
}

def get_status_emoji(status: str) -> str:
    """Returns a status emoji based on the status string."""
    if not status: return '⚪️'
    return STATUS_EMOJIS.get(str(status).lower(), '⚪️')

# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ServiceConfig:
    """Configuration for a single service."""
    name: str
    env_addr: str
    env_token: str
    default_addr: str
    icon_emoji: str
    
    @property
    def address(self) -> str:
        return os.environ.get(self.env_addr, self.default_addr)
    
    @property
    def token(self) -> Optional[str]:
        return os.environ.get(self.env_token)

@dataclass
class AppConfig:
    """Application configuration."""
    token_renewal_enabled: bool = True
    token_renewal_interval: int = 300
    lease_renewal_enabled: bool = True
    lease_renewal_interval: int = 600
    status_refresh_interval: int = 10
    schema_cache_dir: str = os.path.expanduser("~/.opentongchi/cache")
    schema_cache_ttl: int = 3600
    opentofu_local_dir: str = os.path.expanduser("~/.opentongchi/tofu")
    hcp_token: str = os.environ.get('HCP_TOKEN', '')
    global_namespace: str = os.environ.get('HASHICORP_NAMESPACE', '')
    
    # Store unknown config keys here to avoid data loss
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def save(self, path: str = None):
        if path is None:
            path = os.path.expanduser("~/.opentongchi/config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Merge extra config back for saving
        data = {k: v for k, v in self.__dict__.items() if k != 'extra_config'}
        data.update(self.extra_config)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: str = None) -> 'AppConfig':
        if path is None:
            path = os.path.expanduser("~/.opentongchi/config.json")
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            # Smart loading: separate known fields from unknown
            known_fields = {f.name for f in fields(cls)}
            known_args = {k: v for k, v in data.items() if k in known_fields}
            extra_args = {k: v for k, v in data.items() if k not in known_fields}
            
            config = cls(**known_args)
            config.extra_config = extra_args
            return config
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()

SERVICES = {
    'openbao': ServiceConfig('OpenBao', 'VAULT_ADDR', 'VAULT_TOKEN', 'http://127.0.0.1:8200', '🔐'),
    'consul': ServiceConfig('Consul', 'CONSUL_ADDR', 'CONSUL_TOKEN', 'http://127.0.0.1:8500', '🌐'),
    'nomad': ServiceConfig('Nomad', 'NOMAD_ADDR', 'NOMAD_TOKEN', 'http://127.0.0.1:4646', '📦'),
    'opentofu': ServiceConfig('OpenTofu', 'TF_CLI_CONFIG_FILE', 'TF_TOKEN', '', '🏗️'),
}

# =============================================================================
# API Client Classes
# =============================================================================

class APIError(Exception):
    def __init__(self, message: str, status_code: int = 0, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}

class BaseClient:
    """Base client for shared HTTP logic."""
    def __init__(self, config: AppConfig, service_key: str):
        self.config = config
        self.svc_config = SERVICES.get(service_key)
        self.address = self.svc_config.address if self.svc_config else ''
        self.token = self.svc_config.token if self.svc_config else ''
        self._schema_cache = {}
    
    def _headers(self) -> dict:
        h = {'Content-Type': 'application/json'}
        # Global namespace support
        if self.config.global_namespace:
            h['X-Namespace'] = self.config.global_namespace
        return h

    def _request(self, method: str, path: str, data: dict = None, params: dict = None, timeout: int = 10) -> Any:
        url = urljoin(self.address + '/', path.lstrip('/'))
        try:
            response = requests.request(
                method=method, url=url, headers=self._headers(),
                json=data, params=params, timeout=timeout
            )
            if response.status_code == 204: return {}
            
            try:
                result = response.json()
            except json.JSONDecodeError:
                result = {'data': response.text}
            
            if response.status_code >= 400:
                errors = result.get('errors', [str(result)])
                raise APIError(f"{method} {path} failed: {errors}", response.status_code, result)
            return result
        except requests.RequestException as e:
            raise APIError(f"Connection error: {e}")

class OpenBaoClient(BaseClient):
    def __init__(self, config: AppConfig):
        super().__init__(config, 'openbao')

    def _headers(self):
        h = super()._headers()
        if self.token: h['X-Vault-Token'] = self.token
        if self.config.global_namespace: h['X-Vault-Namespace'] = self.config.global_namespace
        return h

    # Core Vault Ops
    def seal_status(self): return self._request('GET', '/v1/sys/seal-status')
    def list_mounts(self): return self._request('GET', '/v1/sys/mounts').get('data', {})
    
    def list(self, path):
        try:
            res = self._request('LIST', path)
            return res.get('data', {}).get('keys', [])
        except APIError as e:
            if e.status_code == 404: return []
            raise

    def read(self, path): return self._request('GET', path)
    def write(self, path, data): return self._request('POST', path, data=data)
    
    def get_openapi_schema(self):
        if not self._schema_cache:
            try:
                self._schema_cache = self._request('GET', '/v1/sys/internal/specs/openapi')
            except:
                self._schema_cache = {}
        return self._schema_cache

    def token_renew_self(self): return self._request('POST', '/v1/auth/token/renew-self')
    def list_leases(self): return self.list('/v1/sys/leases/lookup')
    def lease_renew(self, lease_id): return self._request('PUT', '/v1/sys/leases/renew', {'lease_id': lease_id})
    def lease_revoke(self, lease_id): return self._request('PUT', '/v1/sys/leases/revoke', {'lease_id': lease_id})

class ConsulClient(BaseClient):
    def __init__(self, config: AppConfig):
        super().__init__(config, 'consul')

    def _headers(self):
        h = super()._headers()
        if self.token: h['X-Consul-Token'] = self.token
        return h

    def list_services(self): return self._request('GET', '/v1/catalog/services')
    def health_service(self, name): return self._request('GET', f'/v1/health/service/{name}')
    
    def list_keys(self, prefix=''):
        return self._request('GET', f'/v1/kv/{prefix}', params={'keys': 'true', 'separator': '/'})

    def get_key(self, key):
        res = self._request('GET', f'/v1/kv/{key}')
        if isinstance(res, list) and res:
            val = res[0].get('Value')
            if val:
                return base64.b64decode(val).decode('utf-8')
        return ""

    def put_key(self, key, value):
        url = urljoin(self.address + '/', f'/v1/kv/{key}'.lstrip('/'))
        requests.put(url, headers=self._headers(), data=str(value)) # Raw body

class NomadClient(BaseClient):
    def __init__(self, config: AppConfig):
        super().__init__(config, 'nomad')

    def _headers(self):
        h = super()._headers()
        if self.token: h['X-Nomad-Token'] = self.token
        if self.config.global_namespace: h['X-Nomad-Namespace'] = self.config.global_namespace
        return h

    def list_jobs(self): return self._request('GET', '/v1/jobs')
    def get_job(self, jid): return self._request('GET', f'/v1/job/{jid}')
    def list_nodes(self): return self._request('GET', '/v1/nodes')
    def list_allocations(self): return self._request('GET', '/v1/allocations')

class OpenTofuClient:
    """Hybrid client for Local and HCP."""
    def __init__(self, config: AppConfig):
        self.config = config
        self.hcp_api = "https://app.terraform.io/api/v2"
    
    def list_local_workspaces(self) -> List[dict]:
        """Scan local directory for TF projects."""
        results = []
        if not os.path.exists(self.config.opentofu_local_dir):
            return results
        
        for root, dirs, files in os.walk(self.config.opentofu_local_dir):
            if '.terraform' in dirs or any(f.endswith('.tf') for f in files):
                state_file = os.path.join(root, 'terraform.tfstate')
                status = 'unknown'
                if os.path.exists(state_file):
                    status = 'ready'
                results.append({'path': root, 'name': os.path.basename(root), 'status': status})
                dirs[:] = [] # Don't recurse
        return results

    def list_hcp_orgs(self):
        if not self.config.hcp_token: return []
        headers = {'Authorization': f'Bearer {self.config.hcp_token}', 'Content-Type': 'application/vnd.api+json'}
        r = requests.get(f"{self.hcp_api}/organizations", headers=headers, timeout=5)
        if r.status_code == 200:
            return r.json().get('data', [])
        return []

    def list_hcp_workspaces(self, org_name):
        if not self.config.hcp_token: return []
        headers = {'Authorization': f'Bearer {self.config.hcp_token}', 'Content-Type': 'application/vnd.api+json'}
        r = requests.get(f"{self.hcp_api}/organizations/{org_name}/workspaces", headers=headers, timeout=5)
        if r.status_code == 200:
            return r.json().get('data', [])
        return []

# =============================================================================
# Background Workers
# =============================================================================

class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

class AsyncWorker(QThread):
    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
    
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

class RenewalWorker(QThread):
    """Background worker for token and lease renewal."""
    log_signal = pyqtSignal(str)
    
    def __init__(self, config: AppConfig, client: OpenBaoClient):
        super().__init__()
        self.config = config
        self.client = client
        self._running = True
        self._token_due = 0
        self._lease_due = 0
    
    def stop(self):
        self._running = False
        self.wait()
    
    def run(self):
        while self._running:
            now = time.time()
            if self.config.token_renewal_enabled and now >= self._token_due:
                try:
                    self.client.token_renew_self()
                    self.log_signal.emit("Token renewed")
                    self._token_due = now + self.config.token_renewal_interval
                except: pass
            
            if self.config.lease_renewal_enabled and now >= self._lease_due:
                try:
                    for lease in self.client.list_leases():
                        self.client.lease_renew(lease)
                    self._lease_due = now + self.config.lease_renewal_interval
                except: pass
            
            for _ in range(10): 
                if not self._running: return
                time.sleep(1)

class StatusMonitorWorker(QThread):
    """Background thread to poll statuses and alerts."""
    status_updated = pyqtSignal(dict) # Broadcasts full status map
    alert_triggered = pyqtSignal(str, str) # Title, Message

    def __init__(self, config: AppConfig, clients: dict):
        super().__init__()
        self.config = config
        self.clients = clients
        self._running = True
        self._cache = {}
        self._known_job_states = {}

    def stop(self):
        self._running = False
        self.wait()

    def run(self):
        while self._running:
            new_status = {}
            
            # 1. OpenBao Seal Status
            try:
                s = self.clients['openbao'].seal_status()
                new_status['openbao'] = 'running' if not s.get('sealed') else 'warning'
            except: new_status['openbao'] = 'down'

            # 2. Nomad Jobs & Alerts
            try:
                jobs = self.clients['nomad'].list_jobs()
                new_status['nomad'] = 'running'
                for job in jobs:
                    jid = job['ID']
                    status = job['Status']
                    # Alert logic
                    if jid in self._known_job_states:
                        if self._known_job_states[jid] != status and status in ['dead', 'failed']:
                            self.alert_triggered.emit("Nomad Alert", f"Job {jid} is now {status} {get_status_emoji(status)}")
                    self._known_job_states[jid] = status
                    new_status[f"nomad_job_{jid}"] = status
            except: new_status['nomad'] = 'down'

            # 3. Consul Reachability
            try:
                self.clients['consul'].list_services()
                new_status['consul'] = 'running'
            except: new_status['consul'] = 'down'

            self.status_updated.emit(new_status)
            self._cache = new_status
            
            # Sleep interruptible
            for _ in range(self.config.status_refresh_interval):
                if not self._running: return
                time.sleep(1)

# =============================================================================
# Dynamic Menu Builder (Restored)
# =============================================================================

class DynamicMenuBuilder:
    """Builds menus dynamically from OpenAPI schema."""
    def __init__(self, client: OpenBaoClient, parent_menu: QMenu, action_callback: Callable):
        self.client = client
        self.parent_menu = parent_menu
        self.on_action = action_callback
        self._schema = None
        self._loading_menus = set()
    
    def set_schema(self, schema: dict):
        self._schema = schema
    
    def parse_paths(self) -> dict:
        if not self._schema: return {}
        paths = self._schema.get('paths', {})
        tree = {}
        for path, methods in paths.items():
            parts = [p for p in path.split('/') if p]
            current = tree
            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {
                        '_methods': {}, '_path': '/' + '/'.join(parts[:i+1]),
                        '_is_param': part.startswith('{') and part.endswith('}')
                    }
                current = current[part]
            current['_methods'] = methods
        return tree
    
    def build_path_menu(self, menu: QMenu, tree: dict, current_path: str = ''):
        for key, value in sorted(tree.items()):
            if key.startswith('_'): continue
            is_param = value.get('_is_param', False)
            path = value.get('_path', '')
            methods = value.get('_methods', {})
            children = {k: v for k, v in value.items() if not k.startswith('_')}
            
            if is_param:
                submenu = menu.addMenu(f"📂 {key}")
                submenu.aboutToShow.connect(partial(self._populate_param_menu, submenu, path, value))
            elif children:
                submenu = menu.addMenu(f"📁 {key}")
                self.build_path_menu(submenu, children, path)
            else:
                action = menu.addAction(f"📄 {key}")
                action.triggered.connect(partial(self.on_action, path, methods))

    def _populate_param_menu(self, menu: QMenu, path: str, tree: dict):
        if menu in self._loading_menus: return
        menu.clear()
        self._loading_menus.add(menu)
        menu.addAction("⏳ Loading...").setEnabled(False)
        
        def do_list():
            try:
                list_path = '/v1' + re.sub(r'/\{[^}]+\}$', '', path)
                return self.client.list(list_path)
            except: return []

        def on_complete(items):
            self._loading_menus.discard(menu)
            menu.clear()
            menu.addAction("✨ New...").triggered.connect(partial(self.on_action, path, {}, True))
            menu.addSeparator()
            if not items:
                menu.addAction("(empty)").setEnabled(False)
            for item in items:
                item_path = path.replace(re.search(r'\{[^}]+\}', path).group(), item.rstrip('/'))
                if item.endswith('/'):
                    sm = menu.addMenu(f"📁 {item.rstrip('/')}")
                    # Recursively populate needs careful handling, for now just show leaf actions
                    sm.addAction("Open").triggered.connect(partial(self.on_action, '/v1'+item_path, {}))
                else:
                    menu.addAction(f"🔐 {item}").triggered.connect(partial(self.on_action, '/v1'+item_path, {}))
        
        worker = AsyncWorker(do_list)
        worker.signals.finished.connect(on_complete)
        worker.start()
        menu._worker = worker

# =============================================================================
# UI Components
# =============================================================================

class KeyValueEditorDialog(QDialog):
    """Enhanced CRUD editor for JSON/KV data."""
    def __init__(self, title: str, data: Union[dict, list, str] = None, readonly: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 500)
        self.data = data or {}
        self.readonly = readonly
        self.result_data = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Decide view based on data type
        self.is_tabular = isinstance(self.data, dict) and all(isinstance(v, (str, int, float, bool, type(None))) for v in self.data.values())
        
        if self.is_tabular:
            self.table = QTableWidget()
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels(['Key', 'Value'])
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self._populate_table()
            layout.addWidget(self.table)
            
            if not self.readonly:
                btn_layout = QHBoxLayout()
                add_btn = QPushButton("➕ Add Row")
                add_btn.clicked.connect(self._add_row)
                btn_layout.addWidget(add_btn)
                layout.addLayout(btn_layout)
        else:
            self.text_edit = QTextEdit()
            formatted_json = json.dumps(self.data, indent=2) if not isinstance(self.data, str) else self.data
            self.text_edit.setPlainText(formatted_json)
            self.text_edit.setFont(QFont("Monospace"))
            if self.readonly: self.text_edit.setReadOnly(True)
            layout.addWidget(self.text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        if self.readonly: buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_table(self):
        self.table.setRowCount(0)
        for k, v in self.data.items():
            self._add_row(k, str(v))

    def _add_row(self, key="", val=""):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(str(key)))
        self.table.setItem(r, 1, QTableWidgetItem(str(val)))

    def _save(self):
        if self.is_tabular:
            res = {}
            for i in range(self.table.rowCount()):
                k = self.table.item(i, 0).text()
                if k: res[k] = self.table.item(i, 1).text()
            self.result_data = res
        else:
            txt = self.text_edit.toPlainText()
            try:
                self.result_data = json.loads(txt)
            except:
                self.result_data = txt
        self.accept()

    def get_data(self): return self.result_data

class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("⚙️ OpenTongchi Settings")
        self.resize(500, 400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        
        # General
        gen_tab = QWidget()
        gen_form = QFormLayout(gen_tab)
        self.ns_edit = QLineEdit(self.config.global_namespace)
        gen_form.addRow("🌍 Global Namespace:", self.ns_edit)
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1, 3600)
        self.refresh_spin.setValue(self.config.status_refresh_interval)
        gen_form.addRow("⏱️ Status Refresh (s):", self.refresh_spin)
        tabs.addTab(gen_tab, "General")

        # OpenTofu
        tf_tab = QWidget()
        tf_form = QFormLayout(tf_tab)
        self.hcp_edit = QLineEdit(self.config.hcp_token)
        self.hcp_edit.setEchoMode(QLineEdit.EchoMode.Password)
        tf_form.addRow("☁️ HCP Token:", self.hcp_edit)
        self.local_dir = QLineEdit(self.config.opentofu_local_dir)
        tf_form.addRow("📂 Local Tofu Dir:", self.local_dir)
        tabs.addTab(tf_tab, "OpenTofu")

        # Automation
        auto_tab = QWidget()
        auto_layout = QVBoxLayout(auto_tab)
        self.chk_token = QCheckBox("Auto-renew Tokens")
        self.chk_token.setChecked(self.config.token_renewal_enabled)
        auto_layout.addWidget(self.chk_token)
        self.chk_lease = QCheckBox("Auto-renew Leases")
        self.chk_lease.setChecked(self.config.lease_renewal_enabled)
        auto_layout.addWidget(self.chk_lease)
        tabs.addTab(auto_tab, "Automation")

        layout.addWidget(tabs)
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self):
        self.config.global_namespace = self.ns_edit.text()
        self.config.status_refresh_interval = self.refresh_spin.value()
        self.config.hcp_token = self.hcp_edit.text()
        self.config.opentofu_local_dir = self.local_dir.text()
        self.config.token_renewal_enabled = self.chk_token.isChecked()
        self.config.lease_renewal_enabled = self.chk_lease.isChecked()
        self.config.save()
        self.accept()

# =============================================================================
# Main Tray Application
# =============================================================================

class OpenTongchiTray(QSystemTrayIcon):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.config = AppConfig.load()
        
        # Initialize Clients
        self.bao = OpenBaoClient(self.config)
        self.consul = ConsulClient(self.config)
        self.nomad = NomadClient(self.config)
        self.tofu = OpenTofuClient(self.config)

        self._workers = []
        self._status_cache = {}
        
        # Start Workers
        self.monitor = StatusMonitorWorker(self.config, {'openbao': self.bao, 'consul': self.consul, 'nomad': self.nomad})
        self.monitor.status_updated.connect(self._on_status_update)
        self.monitor.alert_triggered.connect(self._on_alert)
        self.monitor.start()

        self.renewer = RenewalWorker(self.config, self.bao)
        self.renewer.start()

        self._setup_icon()
        self._setup_menu()
        self.show()

    def _setup_icon(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setFont(QFont("Arial", 40))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🐉")
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setToolTip("OpenTongchi Infrastructure Manager")

    def _on_status_update(self, statuses):
        self._status_cache = statuses

    def _on_alert(self, title, msg):
        self.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Warning)

    def _setup_menu(self):
        self.menu = QMenu()
        self._build_root_menu()
        self.setContextMenu(self.menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.Context):
            self._build_root_menu()

    def _build_root_menu(self):
        self.menu.clear()
        
        # Header Info
        ns = self.config.global_namespace or "root"
        self.menu.addAction(f"🏢 Namespace: {ns}").setEnabled(False)
        self.menu.addSeparator()

        # --- OpenBao ---
        s_bao = self._status_cache.get('openbao', 'unknown')
        m_bao = self.menu.addMenu(f"{get_status_emoji(s_bao)} OpenBao")
        self._build_lazy_menu(m_bao, self._populate_bao_menu)

        # --- Consul ---
        s_consul = self._status_cache.get('consul', 'unknown')
        m_consul = self.menu.addMenu(f"{get_status_emoji(s_consul)} Consul")
        self._build_lazy_menu(m_consul, self._populate_consul_menu)

        # --- Nomad ---
        s_nomad = self._status_cache.get('nomad', 'unknown')
        m_nomad = self.menu.addMenu(f"{get_status_emoji(s_nomad)} Nomad")
        self._build_lazy_menu(m_nomad, self._populate_nomad_menu)

        # --- OpenTofu ---
        m_tofu = self.menu.addMenu("🏗️ OpenTofu")
        self._build_lazy_menu(m_tofu, self._populate_tofu_menu)

        self.menu.addSeparator()
        self.menu.addAction("⚙️ Settings...").triggered.connect(self._show_settings)
        self.menu.addAction("🔄 Refresh Config").triggered.connect(lambda: [self.config.load(), self.showMessage("Done", "Reloaded")])
        self.menu.addAction("🚪 Exit").triggered.connect(self._exit)

    def _build_lazy_menu(self, menu: QMenu, populator_func):
        menu.aboutToShow.connect(partial(self._run_menu_worker, menu, populator_func))

    def _run_menu_worker(self, menu, func):
        if not menu.isEmpty(): return 
        menu.addAction("⏳ Loading...")
        worker = AsyncWorker(func, menu)
        worker.signals.finished.connect(lambda res: self._finalize_menu(menu, res))
        worker.signals.error.connect(lambda err: self._finalize_menu(menu, None, err))
        self._workers.append(worker)
        worker.start()

    def _finalize_menu(self, menu, result_func, error=None):
        menu.clear()
        if error:
            menu.addAction(f"⚠️ Error: {error}").setEnabled(False)
        elif result_func:
            result_func()

    # =========================================================================
    # Service Logic (OpenBao)
    # =========================================================================

    def _populate_bao_menu(self, menu):
        try:
            mounts = self.bao.list_mounts()
            schema = self.bao.get_openapi_schema()
            return partial(self._render_bao_menu, menu, mounts, schema)
        except Exception as e:
            raise e

    def _render_bao_menu(self, menu, mounts, schema):
        # Status
        status_menu = menu.addMenu("📊 System Status")
        status_menu.addAction("🔒 Seal Status").triggered.connect(self._show_bao_seal)
        
        menu.addSeparator()
        
        # Schema Browser (Using restored DynamicMenuBuilder)
        schema_menu = menu.addMenu("📖 API Explorer")
        builder = DynamicMenuBuilder(self.bao, schema_menu, self._on_schema_action)
        builder.set_schema(schema)
        tree = builder.parse_paths()
        if 'v1' in tree:
            for k, v in sorted(tree['v1'].items()):
                if k.startswith('_'): continue
                sm = schema_menu.addMenu(f"📁 {k}")
                builder.build_path_menu(sm, v, f"/v1/{k}")

        menu.addSeparator()
        
        # Mounts
        for path, info in sorted(mounts.items()):
            if info['type'] == 'system': continue
            icon = '📁' if info['type'] == 'kv' else '⚙️'
            sm = menu.addMenu(f"{icon} {path}")
            self._build_lazy_menu(sm, partial(self._populate_bao_mount, path, info['type']))

    def _on_schema_action(self, path, methods, is_new=False):
        if is_new:
            self._create_bao_secret(path, 'generic')
        else:
            self._edit_bao_secret('sys', path, 'generic')

    def _populate_bao_mount(self, mount_path, mount_type, menu):
        try:
            list_path = f"/v1/{mount_path}metadata/" if mount_type == 'kv' else f"/v1/{mount_path}"
            keys = self.bao.list(list_path)
            return partial(self._render_bao_keys, menu, mount_path, mount_type, keys, prefix="")
        except:
            keys = self.bao.list(f"/v1/{mount_path}")
            return partial(self._render_bao_keys, menu, mount_path, mount_type, keys, prefix="")

    def _render_bao_keys(self, menu, mount, mtype, keys, prefix):
        full_prefix = mount + prefix
        menu.addAction("✨ New Secret...").triggered.connect(lambda: self._create_bao_secret(full_prefix, mtype))
        menu.addSeparator()

        if not keys:
            menu.addAction("(Empty)").setEnabled(False)
            return

        for key in keys:
            if key.endswith('/'):
                sm = menu.addMenu(f"📂 {key}")
                self._build_lazy_menu(sm, partial(self._populate_bao_recursive, mount, mtype, prefix + key))
            else:
                menu.addAction(f"🔐 {key}").triggered.connect(partial(self._edit_bao_secret, mount, prefix + key, mtype))

    def _populate_bao_recursive(self, mount, mtype, prefix, menu):
        try:
            list_path = f"/v1/{mount}metadata/{prefix}" if mtype == 'kv' else f"/v1/{mount}{prefix}"
            keys = self.bao.list(list_path)
            return partial(self._render_bao_keys, menu, mount, mtype, keys, prefix)
        except Exception as e:
            raise e

    def _edit_bao_secret(self, mount, path, mtype):
        try:
            if mtype == 'generic':
                 # Handle Schema Browser paths directly
                full_path = path if path.startswith('/v1') else f"/v1/{path}"
            else:
                full_path = f"/v1/{mount}data/{path}" if mtype == 'kv' else f"/v1/{mount}{path}"
                if mtype != 'kv': full_path = full_path.replace('//', '/')

            res = self.bao.read(full_path)
            data = res.get('data', {}).get('data', {}) if mtype == 'kv' else res.get('data', {})
            
            dlg = KeyValueEditorDialog(f"Secret: {path}", data)
            if dlg.exec():
                new_data = dlg.get_data()
                payload = {'data': new_data} if mtype == 'kv' else new_data
                self.bao.write(full_path, payload)
                self.showMessage("Success", "Secret updated.")
        except Exception as e:
            QMessageBox.critical(None, "Error", str(e))

    def _create_bao_secret(self, prefix, mtype):
        name, ok = QInputDialog.getText(None, "New Secret", f"Name (under {prefix}):")
        if ok and name:
            self._edit_bao_secret(prefix.split('/')[0] + '/', prefix.split('/', 1)[1] + name if '/' in prefix else name, mtype)

    def _show_bao_seal(self):
        s = self.bao.seal_status()
        KeyValueEditorDialog("Seal Status", s, readonly=True).exec()

    # =========================================================================
    # Service Logic (Consul)
    # =========================================================================

    def _populate_consul_menu(self, menu):
        return partial(self._render_consul_menu, menu)

    def _render_consul_menu(self, menu):
        s_menu = menu.addMenu("🧩 Services")
        self._build_lazy_menu(s_menu, self._populate_consul_services)
        
        k_menu = menu.addMenu("🔑 Key/Value")
        self._build_lazy_menu(k_menu, partial(self._populate_consul_kv, ''))

    def _populate_consul_services(self, menu):
        svcs = self.consul.list_services()
        return partial(self._render_consul_services, menu, svcs)

    def _render_consul_services(self, menu, svcs):
        for name in svcs:
            menu.addAction(f"🔹 {name}").triggered.connect(partial(self._view_consul_service, name))

    def _view_consul_service(self, name):
        try:
            health = self.consul.health_service(name)
            status = 'passing'
            for node in health:
                for check in node.get('Checks', []):
                    if check['Status'] != 'passing': status = check['Status']
            KeyValueEditorDialog(f"Service: {name} {get_status_emoji(status)}", health, readonly=True).exec()
        except Exception as e:
            QMessageBox.critical(None, "Error", str(e))

    def _populate_consul_kv(self, prefix, menu):
        try:
            keys = self.consul.list_keys(prefix)
            return partial(self._render_consul_kv, menu, keys, prefix)
        except:
            return partial(lambda m: m.addAction("(Empty)").setEnabled(False), menu)

    def _render_consul_kv(self, menu, full_keys, prefix):
        menu.addAction("✨ New Key...").triggered.connect(lambda: self._create_consul_key(prefix))
        menu.addSeparator()

        current_level_folders = set()
        current_level_files = set()
        prefix_len = len(prefix)
        
        for k in full_keys:
            rel = k[prefix_len:]
            if '/' in rel:
                current_level_folders.add(rel.split('/')[0] + '/')
            else:
                current_level_files.add(rel)

        for folder in sorted(current_level_folders):
            sm = menu.addMenu(f"📂 {folder}")
            self._build_lazy_menu(sm, partial(self._populate_consul_kv, prefix + folder))
        
        for file in sorted(current_level_files):
            menu.addAction(f"📝 {file}").triggered.connect(partial(self._edit_consul_key, prefix + file))

    def _edit_consul_key(self, key):
        try:
            val = self.consul.get_key(key)
            try: data = json.loads(val)
            except: data = {'value': val}
            
            dlg = KeyValueEditorDialog(f"KV: {key}", data)
            if dlg.exec():
                new_data = dlg.get_data()
                to_send = new_data['value'] if 'value' in new_data and len(new_data) == 1 else json.dumps(new_data)
                self.consul.put_key(key, to_send)
                self.showMessage("Saved", "Consul KV updated")
        except Exception as e:
            QMessageBox.critical(None, "Error", str(e))

    def _create_consul_key(self, prefix):
        name, ok = QInputDialog.getText(None, "New Key", f"Name (prefix: {prefix}):")
        if ok and name: self._edit_consul_key(prefix + name)

    # =========================================================================
    # Service Logic (Nomad)
    # =========================================================================

    def _populate_nomad_menu(self, menu):
        return partial(self._render_nomad_menu, menu)

    def _render_nomad_menu(self, menu):
        menu.addAction("🚀 Jobs List").triggered.connect(lambda: self._view_nomad_list('jobs'))
        menu.addAction("🖥️ Nodes List").triggered.connect(lambda: self._view_nomad_list('nodes'))
        menu.addSeparator()
        jb = menu.addMenu("📂 Job Browser")
        self._build_lazy_menu(jb, self._populate_nomad_jobs)

    def _populate_nomad_jobs(self, menu):
        jobs = self.nomad.list_jobs()
        return partial(self._render_nomad_jobs, menu, jobs)

    def _render_nomad_jobs(self, menu, jobs):
        for job in jobs:
            menu.addAction(f"{get_status_emoji(job['Status'])} {job['ID']}").triggered.connect(partial(self._view_nomad_job_detail, job['ID']))

    def _view_nomad_job_detail(self, jid):
        try:
            job = self.nomad.get_job(jid)
            KeyValueEditorDialog(f"Job: {jid}", job, readonly=True).exec()
        except Exception as e:
            QMessageBox.critical(None, "Error", str(e))

    def _view_nomad_list(self, kind):
        try:
            if kind == 'jobs':
                data = self.nomad.list_jobs()
                display = {f"{get_status_emoji(x['Status'])} {x['ID']}": x['Status'] for x in data}
            elif kind == 'nodes':
                data = self.nomad.list_nodes()
                display = {f"{get_status_emoji(x['Status'])} {x['ID']}": x['Name'] for x in data}
            KeyValueEditorDialog(f"Nomad {kind}", display, readonly=True).exec()
        except Exception as e:
            QMessageBox.critical(None, "Error", str(e))

    # =========================================================================
    # Service Logic (OpenTofu)
    # =========================================================================

    def _populate_tofu_menu(self, menu):
        return partial(self._render_tofu_menu, menu)

    def _render_tofu_menu(self, menu):
        lm = menu.addMenu("💻 Local Directories")
        self._build_lazy_menu(lm, self._populate_tofu_local)
        hm = menu.addMenu("☁️ HCP Terraform")
        self._build_lazy_menu(hm, self._populate_tofu_hcp)

    def _populate_tofu_local(self, menu):
        data = self.tofu.list_local_workspaces()
        return partial(self._render_tofu_local, menu, data)

    def _render_tofu_local(self, menu, data):
        if not data:
            menu.addAction("(No local projects found)").setEnabled(False)
        for item in data:
            menu.addAction(f"{get_status_emoji(item['status'])} {item['name']}").triggered.connect(
                lambda p=item['path']: QMessageBox.information(None, "Path", p)
            )

    def _populate_tofu_hcp(self, menu):
        try:
            orgs = self.tofu.list_hcp_orgs()
            return partial(self._render_tofu_hcp_orgs, menu, orgs)
        except Exception as e:
            return partial(lambda m: m.addAction(f"Error: {e}").setEnabled(False), menu)

    def _render_tofu_hcp_orgs(self, menu, orgs):
        for org in orgs:
            name = org['attributes']['name']
            sm = menu.addMenu(f"🏢 {name}")
            self._build_lazy_menu(sm, partial(self._populate_tofu_workspaces, name))

    def _populate_tofu_workspaces(self, org, menu):
        ws = self.tofu.list_hcp_workspaces(org)
        return partial(self._render_tofu_workspaces, menu, ws)

    def _render_tofu_workspaces(self, menu, workspaces):
        for ws in workspaces:
            wname = ws['attributes']['name']
            menu.addAction(f"🟢 {wname}")

    def _exit(self):
        self.monitor.stop()
        self.renewer.stop()
        self.app.quit()

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("OpenTongchi")
    
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Error", "System tray not available.")
        sys.exit(1)
    
    tray = OpenTongchiTray(app)
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
