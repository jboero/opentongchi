#!/usr/bin/env python3
"""
OpenTongchi - Open Source Infrastructure Management System Tray Application
A Qt6-based system tray widget for managing OpenBao, OpenTofu, Nomad, Consul, etc.

Author: John Boero - boeroboy@gmail.com
Refactored from wxWidgets/GTK3 to Qt6
"""

import sys
import os
import json
import time
import threading
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from functools import partial
from urllib.parse import urljoin
import requests
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QDialog, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QFormLayout, QMessageBox, QSpinBox, QCheckBox, QGroupBox, QTabWidget,
    QWidget, QHeaderView, QComboBox, QTextEdit, QDialogButtonBox,
    QInputDialog, QSplitter, QTreeWidget, QTreeWidgetItem, QProgressDialog,
    QStyle
)
from PyQt6.QtGui import QIcon, QAction, QCursor, QPixmap, QPainter, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QSize


# =============================================================================
# Configuration and Constants
# =============================================================================

@dataclass
class ServiceConfig:
    """Configuration for a single service."""
    name: str
    env_addr: str
    env_token: str
    default_addr: str
    icon_emoji: str
    enabled: bool = True
    
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
    token_renewal_interval: int = 300  # seconds
    lease_renewal_enabled: bool = True
    lease_renewal_interval: int = 600  # seconds
    schema_cache_dir: str = os.path.expanduser("~/.opentongchi/cache")
    schema_cache_ttl: int = 3600  # seconds
    
    def save(self, path: str = None):
        if path is None:
            path = os.path.expanduser("~/.opentongchi/config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)
    
    @classmethod
    def load(cls, path: str = None) -> 'AppConfig':
        if path is None:
            path = os.path.expanduser("~/.opentongchi/config.json")
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                return cls(**data)
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()


# Service configurations
SERVICES = {
    'openbao': ServiceConfig(
        name='OpenBao',
        env_addr='VAULT_ADDR',
        env_token='VAULT_TOKEN',
        default_addr='http://127.0.0.1:8200',
        icon_emoji='🔐'
    ),
    'consul': ServiceConfig(
        name='Consul',
        env_addr='CONSUL_ADDR',
        env_token='CONSUL_TOKEN',
        default_addr='http://127.0.0.1:8500',
        icon_emoji='🌐'
    ),
    'nomad': ServiceConfig(
        name='Nomad',
        env_addr='NOMAD_ADDR',
        env_token='NOMAD_TOKEN',
        default_addr='http://127.0.0.1:4646',
        icon_emoji='📦'
    ),
    'opentofu': ServiceConfig(
        name='OpenTofu',
        env_addr='TF_CLI_CONFIG_FILE',
        env_token='TF_TOKEN',
        default_addr='',
        icon_emoji='🏗️'
    ),
    'waypoint': ServiceConfig(
        name='Waypoint',
        env_addr='WAYPOINT_ADDR',
        env_token='WAYPOINT_TOKEN',
        default_addr='http://127.0.0.1:9701',
        icon_emoji='🚀'
    ),
    'boundary': ServiceConfig(
        name='Boundary',
        env_addr='BOUNDARY_ADDR',
        env_token='BOUNDARY_TOKEN',
        default_addr='http://127.0.0.1:9200',
        icon_emoji='🛡️'
    ),
}


# =============================================================================
# API Client Classes
# =============================================================================

class APIError(Exception):
    """API error with status code and message."""
    def __init__(self, message: str, status_code: int = 0, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class OpenBaoClient:
    """Direct API client for OpenBao/Vault."""
    
    def __init__(self, address: str = None, token: str = None, namespace: str = None):
        self.address = address or os.environ.get('VAULT_ADDR', 'http://127.0.0.1:8200')
        self.token = token or os.environ.get('VAULT_TOKEN', '')
        self.namespace = namespace
        self._schema_cache = {}
        self._schema_cache_time = 0
        self._leases = {}
        
    def _headers(self) -> dict:
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['X-Vault-Token'] = self.token
        if self.namespace:
            headers['X-Vault-Namespace'] = self.namespace
        return headers
    
    def _request(self, method: str, path: str, data: dict = None, 
                 params: dict = None, timeout: int = 30) -> dict:
        url = urljoin(self.address + '/', path.lstrip('/'))
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._headers(),
                json=data,
                params=params,
                timeout=timeout
            )
            
            if response.status_code == 204:
                return {}
            
            try:
                result = response.json()
            except json.JSONDecodeError:
                result = {'data': response.text}
            
            if response.status_code >= 400:
                errors = result.get('errors', [str(result)])
                raise APIError(
                    '; '.join(errors) if isinstance(errors, list) else str(errors),
                    status_code=response.status_code,
                    response=result
                )
            
            return result
            
        except requests.RequestException as e:
            raise APIError(f"Connection error: {e}")
    
    def get(self, path: str, params: dict = None) -> dict:
        return self._request('GET', path, params=params)
    
    def post(self, path: str, data: dict = None) -> dict:
        return self._request('POST', path, data=data)
    
    def put(self, path: str, data: dict = None) -> dict:
        return self._request('PUT', path, data=data)
    
    def delete(self, path: str) -> dict:
        return self._request('DELETE', path)
    
    def list(self, path: str) -> List[str]:
        try:
            result = self._request('LIST', path)
            return result.get('data', {}).get('keys', [])
        except APIError as e:
            if e.status_code == 404:
                return []
            raise
    
    # Health and status
    def health(self) -> dict:
        return self.get('/v1/sys/health')
    
    def seal_status(self) -> dict:
        return self.get('/v1/sys/seal-status')
    
    # Token operations
    def token_lookup_self(self) -> dict:
        return self.get('/v1/auth/token/lookup-self')
    
    def token_renew_self(self, increment: str = None) -> dict:
        data = {}
        if increment:
            data['increment'] = increment
        return self.post('/v1/auth/token/renew-self', data=data if data else None)
    
    # Lease operations
    def lease_lookup(self, lease_id: str) -> dict:
        return self.put('/v1/sys/leases/lookup', {'lease_id': lease_id})
    
    def lease_renew(self, lease_id: str, increment: int = None) -> dict:
        data = {'lease_id': lease_id}
        if increment:
            data['increment'] = increment
        return self.put('/v1/sys/leases/renew', data)
    
    def lease_revoke(self, lease_id: str) -> dict:
        return self.put('/v1/sys/leases/revoke', {'lease_id': lease_id})
    
    def list_leases(self, prefix: str = '') -> List[str]:
        return self.list(f'/v1/sys/leases/lookup/{prefix}')
    
    # Secret engines
    def list_mounts(self) -> dict:
        result = self.get('/v1/sys/mounts')
        return result.get('data', result)
    
    def read_secret(self, path: str, version: int = None) -> dict:
        if version is not None:
            return self.get(path, params={'version': version})
        return self.get(path)
    
    def write_secret(self, path: str, data: dict) -> dict:
        return self.post(path, data)
    
    def delete_secret(self, path: str) -> dict:
        return self.delete(path)
    
    def list_secrets(self, path: str) -> List[str]:
        return self.list(path)
    
    # Auth methods
    def list_auth_methods(self) -> dict:
        result = self.get('/v1/sys/auth')
        return result.get('data', result)
    
    # Policies
    def list_policies(self) -> List[str]:
        result = self.get('/v1/sys/policies/acl')
        return result.get('data', {}).get('keys', [])
    
    def read_policy(self, name: str) -> dict:
        return self.get(f'/v1/sys/policies/acl/{name}')
    
    def write_policy(self, name: str, policy: str) -> dict:
        return self.put(f'/v1/sys/policies/acl/{name}', {'policy': policy})
    
    def delete_policy(self, name: str) -> dict:
        return self.delete(f'/v1/sys/policies/acl/{name}')
    
    # Namespaces
    def list_namespaces(self) -> List[str]:
        try:
            return self.list('/v1/sys/namespaces')
        except APIError:
            return []
    
    # OpenAPI Schema
    def get_openapi_schema(self, use_cache: bool = True) -> dict:
        cache_ttl = 3600
        now = time.time()
        
        if use_cache and self._schema_cache and (now - self._schema_cache_time) < cache_ttl:
            return self._schema_cache
        
        result = self.get('/v1/sys/internal/specs/openapi')
        self._schema_cache = result
        self._schema_cache_time = now
        return result
    
    # Audit
    def list_audit_devices(self) -> dict:
        result = self.get('/v1/sys/audit')
        return result.get('data', result)
    
    # Tools
    def random_bytes(self, num_bytes: int = 32, format: str = 'base64') -> dict:
        return self.post('/v1/sys/tools/random', {'bytes': num_bytes, 'format': format})
    
    def hash_data(self, input_data: str, algorithm: str = 'sha2-256', 
                  format: str = 'base64') -> dict:
        return self.post('/v1/sys/tools/hash', {
            'input': input_data,
            'algorithm': algorithm,
            'format': format
        })


# =============================================================================
# Background Worker Threads
# =============================================================================

class WorkerSignals(QObject):
    """Signals for worker threads."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)


class AsyncWorker(QThread):
    """Generic async worker thread."""
    
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


class TokenRenewalWorker(QThread):
    """Background worker for token and lease renewal."""
    
    status_update = pyqtSignal(str)
    renewal_error = pyqtSignal(str)
    
    def __init__(self, config: AppConfig, client: OpenBaoClient):
        super().__init__()
        self.config = config
        self.client = client
        self._running = True
        self._token_renewal_due = 0
        self._lease_renewal_due = 0
    
    def stop(self):
        self._running = False
    
    def run(self):
        while self._running:
            now = time.time()
            
            # Token renewal
            if self.config.token_renewal_enabled and now >= self._token_renewal_due:
                try:
                    self.client.token_renew_self()
                    self.status_update.emit("Token renewed successfully")
                    self._token_renewal_due = now + self.config.token_renewal_interval
                except APIError as e:
                    self.renewal_error.emit(f"Token renewal failed: {e}")
                except Exception as e:
                    self.renewal_error.emit(f"Token renewal error: {e}")
            
            # Lease renewal
            if self.config.lease_renewal_enabled and now >= self._lease_renewal_due:
                try:
                    self._renew_leases()
                    self._lease_renewal_due = now + self.config.lease_renewal_interval
                except Exception as e:
                    self.renewal_error.emit(f"Lease renewal error: {e}")
            
            # Sleep in short intervals to allow quick shutdown
            for _ in range(10):
                if not self._running:
                    break
                time.sleep(1)
    
    def _renew_leases(self):
        try:
            leases = self.client.list_leases()
            for lease_id in leases:
                try:
                    self.client.lease_renew(lease_id)
                except APIError:
                    pass
        except APIError:
            pass


# =============================================================================
# Dialog Classes
# =============================================================================

class KeyValueEditorDialog(QDialog):
    """Dialog for editing key-value pairs (secrets, configurations)."""
    
    def __init__(self, title: str, data: dict = None, readonly: bool = False, 
                 parent=None, schema: dict = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        self.data = data or {}
        self.readonly = readonly
        self.schema = schema
        self.result_data = None
        self._setup_ui()
        self._populate_table()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Table for key-value pairs
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['🔑 Key', '📝 Value'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 200)
        
        if self.readonly:
            self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        if not self.readonly:
            add_btn = QPushButton("➕ Add Row")
            add_btn.clicked.connect(self._add_row)
            button_layout.addWidget(add_btn)
            
            remove_btn = QPushButton("➖ Remove Row")
            remove_btn.clicked.connect(self._remove_row)
            button_layout.addWidget(remove_btn)
        
        button_layout.addStretch()
        
        button_box = QDialogButtonBox()
        if self.readonly:
            button_box.addButton(QDialogButtonBox.StandardButton.Close)
        else:
            button_box.addButton(QDialogButtonBox.StandardButton.Save)
            button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
    
    def _populate_table(self):
        self.table.setRowCount(0)
        for key, value in self.data.items():
            self._add_row(key, self._format_value(value))
    
    def _format_value(self, value) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        return str(value) if value is not None else ''
    
    def _parse_value(self, value_str: str):
        """Try to parse as JSON, fall back to string."""
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            return value_str
    
    def _add_row(self, key: str = '', value: str = ''):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key))
        self.table.setItem(row, 1, QTableWidgetItem(value))
    
    def _remove_row(self):
        current = self.table.currentRow()
        if current >= 0:
            self.table.removeRow(current)
    
    def _save(self):
        self.result_data = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if key_item and key_item.text():
                key = key_item.text()
                value = value_item.text() if value_item else ''
                self.result_data[key] = self._parse_value(value)
        self.accept()
    
    def get_data(self) -> Optional[dict]:
        return self.result_data


class SettingsDialog(QDialog):
    """Settings dialog for configuring the application."""
    
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ OpenTongchi Settings")
        self.setMinimumSize(500, 400)
        self.config = config
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        tabs = QTabWidget()
        
        # Token Renewal Tab
        token_tab = QWidget()
        token_layout = QFormLayout(token_tab)
        
        self.token_renewal_enabled = QCheckBox("Enable automatic token renewal")
        self.token_renewal_enabled.setChecked(self.config.token_renewal_enabled)
        token_layout.addRow(self.token_renewal_enabled)
        
        self.token_renewal_interval = QSpinBox()
        self.token_renewal_interval.setRange(60, 86400)
        self.token_renewal_interval.setValue(self.config.token_renewal_interval)
        self.token_renewal_interval.setSuffix(" seconds")
        token_layout.addRow("🔄 Renewal interval:", self.token_renewal_interval)
        
        tabs.addTab(token_tab, "🔑 Token Renewal")
        
        # Lease Renewal Tab
        lease_tab = QWidget()
        lease_layout = QFormLayout(lease_tab)
        
        self.lease_renewal_enabled = QCheckBox("Enable automatic lease renewal")
        self.lease_renewal_enabled.setChecked(self.config.lease_renewal_enabled)
        lease_layout.addRow(self.lease_renewal_enabled)
        
        self.lease_renewal_interval = QSpinBox()
        self.lease_renewal_interval.setRange(60, 86400)
        self.lease_renewal_interval.setValue(self.config.lease_renewal_interval)
        self.lease_renewal_interval.setSuffix(" seconds")
        lease_layout.addRow("🔄 Renewal interval:", self.lease_renewal_interval)
        
        tabs.addTab(lease_tab, "📜 Lease Renewal")
        
        # Cache Tab
        cache_tab = QWidget()
        cache_layout = QFormLayout(cache_tab)
        
        self.schema_cache_ttl = QSpinBox()
        self.schema_cache_ttl.setRange(60, 86400)
        self.schema_cache_ttl.setValue(self.config.schema_cache_ttl)
        self.schema_cache_ttl.setSuffix(" seconds")
        cache_layout.addRow("📁 Schema cache TTL:", self.schema_cache_ttl)
        
        cache_dir_layout = QHBoxLayout()
        self.cache_dir = QLineEdit(self.config.schema_cache_dir)
        cache_dir_layout.addWidget(self.cache_dir)
        cache_layout.addRow("📂 Cache directory:", cache_dir_layout)
        
        tabs.addTab(cache_tab, "💾 Cache")
        
        # Connection Tab
        conn_tab = QWidget()
        conn_layout = QFormLayout(conn_tab)
        
        for service_id, service in SERVICES.items():
            addr_edit = QLineEdit(service.address)
            addr_edit.setObjectName(f"{service_id}_addr")
            conn_layout.addRow(f"{service.icon_emoji} {service.name} Address:", addr_edit)
        
        tabs.addTab(conn_tab, "🌐 Connections")
        
        layout.addWidget(tabs)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _save(self):
        self.config.token_renewal_enabled = self.token_renewal_enabled.isChecked()
        self.config.token_renewal_interval = self.token_renewal_interval.value()
        self.config.lease_renewal_enabled = self.lease_renewal_enabled.isChecked()
        self.config.lease_renewal_interval = self.lease_renewal_interval.value()
        self.config.schema_cache_ttl = self.schema_cache_ttl.value()
        self.config.schema_cache_dir = self.cache_dir.text()
        self.config.save()
        self.accept()


class NewSecretDialog(QDialog):
    """Dialog for creating a new secret or value."""
    
    def __init__(self, path_prefix: str = '', parent=None):
        super().__init__(parent)
        self.setWindowTitle("✨ Create New Secret")
        self.setMinimumSize(500, 400)
        self.path_prefix = path_prefix
        self.result_path = None
        self.result_data = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Path input
        path_layout = QFormLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("secret/path/name")
        if self.path_prefix:
            self.path_edit.setText(self.path_prefix)
        path_layout.addRow("📍 Secret Path:", self.path_edit)
        layout.addLayout(path_layout)
        
        # Key-value table
        layout.addWidget(QLabel("📝 Secret Data:"))
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['🔑 Key', '📝 Value'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 200)
        layout.addWidget(self.table)
        
        # Add initial empty row
        self._add_row()
        
        # Row buttons
        row_btn_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Add Row")
        add_btn.clicked.connect(self._add_row)
        row_btn_layout.addWidget(add_btn)
        
        remove_btn = QPushButton("➖ Remove Row")
        remove_btn.clicked.connect(self._remove_row)
        row_btn_layout.addWidget(remove_btn)
        row_btn_layout.addStretch()
        layout.addLayout(row_btn_layout)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _add_row(self, key: str = '', value: str = ''):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key))
        self.table.setItem(row, 1, QTableWidgetItem(value))
    
    def _remove_row(self):
        current = self.table.currentRow()
        if current >= 0:
            self.table.removeRow(current)
    
    def _save(self):
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Error", "Please enter a secret path")
            return
        
        self.result_path = path
        self.result_data = {}
        
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if key_item and key_item.text():
                key = key_item.text()
                value = value_item.text() if value_item else ''
                try:
                    self.result_data[key] = json.loads(value)
                except json.JSONDecodeError:
                    self.result_data[key] = value
        
        self.accept()


class PolicyEditorDialog(QDialog):
    """Dialog for viewing/editing policies."""
    
    def __init__(self, name: str, policy_text: str = '', readonly: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"📜 Policy: {name}")
        self.setMinimumSize(600, 500)
        self.name = name
        self.readonly = readonly
        self.result_policy = None
        self._setup_ui(policy_text)
    
    def _setup_ui(self, policy_text: str):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(f"Policy Name: {self.name}"))
        
        self.editor = QTextEdit()
        self.editor.setPlainText(policy_text)
        self.editor.setFontFamily("monospace")
        if self.readonly:
            self.editor.setReadOnly(True)
        layout.addWidget(self.editor)
        
        button_box = QDialogButtonBox()
        if self.readonly:
            button_box.addButton(QDialogButtonBox.StandardButton.Close)
        else:
            button_box.addButton(QDialogButtonBox.StandardButton.Save)
            button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _save(self):
        self.result_policy = self.editor.toPlainText()
        self.accept()


class TokenInfoDialog(QDialog):
    """Dialog showing token information."""
    
    def __init__(self, token_info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔑 Token Information")
        self.setMinimumSize(500, 400)
        self._setup_ui(token_info)
    
    def _setup_ui(self, token_info: dict):
        layout = QVBoxLayout(self)
        
        data = token_info.get('data', token_info)
        
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(['Attribute', 'Value'])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        important_keys = ['display_name', 'policies', 'ttl', 'creation_ttl', 
                          'expire_time', 'renewable', 'entity_id', 'accessor']
        
        rows = []
        for key in important_keys:
            if key in data:
                rows.append((key, data[key]))
        
        for key, value in data.items():
            if key not in important_keys:
                rows.append((key, value))
        
        table.setRowCount(len(rows))
        for i, (key, value) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(key))
            if isinstance(value, (list, dict)):
                value = json.dumps(value, indent=2)
            table.setItem(i, 1, QTableWidgetItem(str(value)))
        
        layout.addWidget(table)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class SealStatusDialog(QDialog):
    """Dialog showing seal status."""
    
    def __init__(self, status: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔒 Seal Status")
        self.setMinimumSize(400, 300)
        self._setup_ui(status)
    
    def _setup_ui(self, status: dict):
        layout = QVBoxLayout(self)
        
        sealed = status.get('sealed', True)
        status_label = QLabel(f"Status: {'🔒 Sealed' if sealed else '🔓 Unsealed'}")
        status_label.setFont(QFont('', 14, QFont.Weight.Bold))
        layout.addWidget(status_label)
        
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(['Attribute', 'Value'])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        rows = [(k, v) for k, v in status.items()]
        table.setRowCount(len(rows))
        for i, (key, value) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(key))
            table.setItem(i, 1, QTableWidgetItem(str(value)))
        
        layout.addWidget(table)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


# =============================================================================
# Dynamic Menu Builder
# =============================================================================

class DynamicMenuBuilder:
    """Builds menus dynamically from OpenAPI schema."""
    
    def __init__(self, client: OpenBaoClient, parent_menu: QMenu):
        self.client = client
        self.parent_menu = parent_menu
        self._schema = None
        self._loading_menus = set()
    
    def set_schema(self, schema: dict):
        self._schema = schema
    
    def get_schema(self) -> Optional[dict]:
        return self._schema
    
    def parse_paths(self) -> dict:
        """Parse OpenAPI paths into a tree structure."""
        if not self._schema:
            return {}
        
        paths = self._schema.get('paths', {})
        tree = {}
        
        for path, methods in paths.items():
            parts = [p for p in path.split('/') if p]
            current = tree
            
            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {
                        '_methods': {},
                        '_path': '/' + '/'.join(parts[:i+1]),
                        '_is_param': part.startswith('{') and part.endswith('}')
                    }
                current = current[part]
            
            current['_methods'] = methods
        
        return tree
    
    def build_path_menu(self, menu: QMenu, tree: dict, current_path: str = '',
                        on_action: Callable = None):
        """Build menu from path tree."""
        for key, value in sorted(tree.items()):
            if key.startswith('_'):
                continue
            
            is_param = value.get('_is_param', False)
            path = value.get('_path', '')
            methods = value.get('_methods', {})
            
            # Check if this node has children
            children = {k: v for k, v in value.items() if not k.startswith('_')}
            
            if is_param:
                # This is a parameterized path - need to list actual values
                submenu = menu.addMenu(f"📂 {key}")
                submenu.aboutToShow.connect(
                    partial(self._populate_param_menu, submenu, path, value, on_action)
                )
            elif children:
                # Has children - create submenu
                submenu = menu.addMenu(f"📁 {key}")
                self.build_path_menu(submenu, children, path, on_action)
            else:
                # Leaf node
                action = menu.addAction(f"📄 {key}")
                if on_action:
                    action.triggered.connect(partial(on_action, path, methods))
    
    def _populate_param_menu(self, menu: QMenu, path: str, tree: dict, 
                              on_action: Callable):
        """Populate a menu with actual values for a parameterized path."""
        if menu in self._loading_menus:
            return
        
        menu.clear()
        self._loading_menus.add(menu)
        
        loading_action = menu.addAction("⏳ Loading...")
        loading_action.setEnabled(False)
        
        # Try to list values at this path
        def do_list():
            try:
                # Remove parameter placeholder from path for listing
                list_path = '/v1' + re.sub(r'/\{[^}]+\}$', '', path)
                items = self.client.list(list_path)
                return items
            except Exception as e:
                return []
        
        def on_complete(items):
            self._loading_menus.discard(menu)
            menu.clear()
            
            # Add "New..." option
            new_action = menu.addAction("✨ New...")
            if on_action:
                new_action.triggered.connect(partial(on_action, path, {'post': {}}, True))
            menu.addSeparator()
            
            if items:
                for item in items:
                    item_path = path.replace(re.search(r'\{[^}]+\}', path).group(), item.rstrip('/'))
                    
                    if item.endswith('/'):
                        # It's a directory
                        submenu = menu.addMenu(f"📁 {item.rstrip('/')}")
                        submenu.aboutToShow.connect(
                            partial(self._populate_listing_menu, submenu, 
                                   '/v1' + item_path + '/', tree, on_action)
                        )
                    else:
                        # It's a leaf
                        action = menu.addAction(f"🔐 {item}")
                        if on_action:
                            action.triggered.connect(partial(on_action, '/v1' + item_path, {}))
            else:
                empty_action = menu.addAction("(empty)")
                empty_action.setEnabled(False)
        
        def on_error(error):
            self._loading_menus.discard(menu)
            menu.clear()
            new_action = menu.addAction("✨ New...")
            if on_action:
                new_action.triggered.connect(partial(on_action, path, {'post': {}}, True))
            menu.addSeparator()
            error_action = menu.addAction(f"⚠️ Error: {error[:30]}...")
            error_action.setEnabled(False)
        
        worker = AsyncWorker(do_list)
        worker.signals.finished.connect(on_complete)
        worker.signals.error.connect(on_error)
        worker.start()
        menu._worker = worker  # Keep reference
    
    def _populate_listing_menu(self, menu: QMenu, path: str, tree: dict,
                                on_action: Callable):
        """Populate menu with listing of secrets/values."""
        if menu in self._loading_menus:
            return
        
        menu.clear()
        self._loading_menus.add(menu)
        
        loading_action = menu.addAction("⏳ Loading...")
        loading_action.setEnabled(False)
        
        def do_list():
            try:
                items = self.client.list(path)
                return items
            except Exception as e:
                return []
        
        def on_complete(items):
            self._loading_menus.discard(menu)
            menu.clear()
            
            new_action = menu.addAction("✨ New...")
            if on_action:
                new_action.triggered.connect(partial(on_action, path, {'post': {}}, True))
            menu.addSeparator()
            
            if items:
                for item in items:
                    item_path = path.rstrip('/') + '/' + item.rstrip('/')
                    
                    if item.endswith('/'):
                        submenu = menu.addMenu(f"📁 {item.rstrip('/')}")
                        submenu.aboutToShow.connect(
                            partial(self._populate_listing_menu, submenu, item_path, tree, on_action)
                        )
                    else:
                        action = menu.addAction(f"🔐 {item}")
                        if on_action:
                            action.triggered.connect(partial(on_action, item_path, {}))
            else:
                empty_action = menu.addAction("(empty)")
                empty_action.setEnabled(False)
        
        def on_error(error):
            self._loading_menus.discard(menu)
            menu.clear()
            new_action = menu.addAction("✨ New...")
            if on_action:
                new_action.triggered.connect(partial(on_action, path, {'post': {}}, True))
        
        worker = AsyncWorker(do_list)
        worker.signals.finished.connect(on_complete)
        worker.signals.error.connect(on_error)
        worker.start()
        menu._worker = worker


# =============================================================================
# Main System Tray Application
# =============================================================================

class OpenTongchiTray(QSystemTrayIcon):
    """Main system tray application."""
    
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.config = AppConfig.load()
        self.client = OpenBaoClient()
        self.menu_builder = None
        self._workers = []
        self._renewal_worker = None
        
        self._setup_icon()
        self._setup_menu()
        self._start_background_workers()
        
        self.show()
    
    def _setup_icon(self):
        """Set up the system tray icon."""
        # Create a simple icon with text
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setFont(QFont('', 40))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🔐")
        painter.end()
        
        icon = QIcon(pixmap)
        self.setIcon(icon)
        self.setToolTip("OpenTongchi - Infrastructure Manager")
    
    def _setup_menu(self):
        """Set up the context menu."""
        self.menu = QMenu()
        self._build_menu()
        self.setContextMenu(self.menu)
        
        # Connect both left and right click to show menu
        self.activated.connect(self._on_activated)
    
    def _on_activated(self, reason):
        """Handle tray icon activation."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.Context):
            self._build_menu()
    
    def _build_menu(self):
        """Build or rebuild the context menu."""
        self.menu.clear()
        
        # OpenBao menu
        openbao_menu = self.menu.addMenu("🔐 OpenBao")
        self._build_openbao_menu(openbao_menu)
        
        # Consul menu
        consul_menu = self.menu.addMenu("🌐 Consul")
        consul_menu.addAction("📋 Services").triggered.connect(
            lambda: self._show_not_implemented("Consul Services"))
        consul_menu.addAction("🔑 KV Store").triggered.connect(
            lambda: self._show_not_implemented("Consul KV"))
        consul_menu.addAction("🏥 Health Checks").triggered.connect(
            lambda: self._show_not_implemented("Consul Health"))
        
        # Nomad menu
        nomad_menu = self.menu.addMenu("📦 Nomad")
        nomad_menu.addAction("💼 Jobs").triggered.connect(
            lambda: self._show_not_implemented("Nomad Jobs"))
        nomad_menu.addAction("🖥️ Nodes").triggered.connect(
            lambda: self._show_not_implemented("Nomad Nodes"))
        nomad_menu.addAction("📊 Allocations").triggered.connect(
            lambda: self._show_not_implemented("Nomad Allocations"))
        
        # OpenTofu menu
        tofu_menu = self.menu.addMenu("🏗️ OpenTofu")
        tofu_menu.addAction("📂 Workspaces").triggered.connect(
            lambda: self._show_not_implemented("OpenTofu Workspaces"))
        tofu_menu.addAction("📋 State").triggered.connect(
            lambda: self._show_not_implemented("OpenTofu State"))
        
        # Waypoint menu
        waypoint_menu = self.menu.addMenu("🚀 Waypoint")
        waypoint_menu.addAction("📦 Projects").triggered.connect(
            lambda: self._show_not_implemented("Waypoint Projects"))
        waypoint_menu.addAction("🚢 Deployments").triggered.connect(
            lambda: self._show_not_implemented("Waypoint Deployments"))
        
        # Boundary menu
        boundary_menu = self.menu.addMenu("🛡️ Boundary")
        boundary_menu.addAction("🎯 Targets").triggered.connect(
            lambda: self._show_not_implemented("Boundary Targets"))
        boundary_menu.addAction("📡 Sessions").triggered.connect(
            lambda: self._show_not_implemented("Boundary Sessions"))
        
        self.menu.addSeparator()
        
        # Namespace menu
        ns_menu = self.menu.addMenu("🏢 Namespace")
        self._build_namespace_menu(ns_menu)
        
        self.menu.addSeparator()
        
        # Settings
        settings_action = self.menu.addAction("⚙️ Settings...")
        settings_action.triggered.connect(self._show_settings)
        
        # Refresh schema
        refresh_action = self.menu.addAction("🔄 Refresh Schemas")
        refresh_action.triggered.connect(self._refresh_schemas)
        
        # About
        about_action = self.menu.addAction("ℹ️ About")
        about_action.triggered.connect(self._show_about)
        
        self.menu.addSeparator()
        
        # Exit
        exit_action = self.menu.addAction("🚪 Exit")
        exit_action.triggered.connect(self._exit)
    
    def _build_openbao_menu(self, menu: QMenu):
        """Build the OpenBao submenu."""
        # Status section
        status_menu = menu.addMenu("📊 Status")
        status_menu.addAction("🔒 Seal Status").triggered.connect(self._show_seal_status)
        status_menu.addAction("❤️ Health").triggered.connect(self._show_health)
        status_menu.addAction("🔑 Token Info").triggered.connect(self._show_token_info)
        
        menu.addSeparator()
        
        # Secrets section
        secrets_menu = menu.addMenu("🔐 Secrets")
        secrets_menu.aboutToShow.connect(lambda: self._populate_secrets_menu(secrets_menu))
        
        # Auth section
        auth_menu = menu.addMenu("🔓 Auth Methods")
        auth_menu.aboutToShow.connect(lambda: self._populate_auth_menu(auth_menu))
        
        # Policies section
        policies_menu = menu.addMenu("📜 Policies")
        policies_menu.aboutToShow.connect(lambda: self._populate_policies_menu(policies_menu))
        
        menu.addSeparator()
        
        # Tools section
        tools_menu = menu.addMenu("🔧 Tools")
        tools_menu.addAction("🎲 Random Bytes").triggered.connect(self._show_random_tool)
        tools_menu.addAction("#️⃣ Hash").triggered.connect(self._show_hash_tool)
        
        # System section
        sys_menu = menu.addMenu("⚙️ System")
        sys_menu.addAction("📋 Audit Devices").triggered.connect(self._show_audit_devices)
        sys_menu.addAction("💾 Mounts").triggered.connect(self._show_mounts)
        
        menu.addSeparator()
        
        # Schema browser
        schema_menu = menu.addMenu("📖 API Schema Browser")
        schema_menu.aboutToShow.connect(lambda: self._populate_schema_menu(schema_menu))
        
        menu.addSeparator()
        
        # Leases section
        leases_menu = menu.addMenu("📄 Leases")
        leases_menu.aboutToShow.connect(lambda: self._populate_leases_menu(leases_menu))
    
    def _build_namespace_menu(self, menu: QMenu):
        """Build namespace submenu."""
        menu.clear()
        
        # Add current namespace indicator
        current = self.client.namespace or 'root'
        menu.addAction(f"✓ Current: {current}").setEnabled(False)
        menu.addSeparator()
        
        # Default namespaces
        for ns in ['root', 'default']:
            action = menu.addAction(f"📁 {ns}")
            action.triggered.connect(partial(self._set_namespace, ns if ns != 'root' else None))
        
        menu.addSeparator()
        
        # Try to list actual namespaces
        try:
            namespaces = self.client.list_namespaces()
            for ns in namespaces:
                action = menu.addAction(f"📁 {ns}")
                action.triggered.connect(partial(self._set_namespace, ns))
        except:
            pass
        
        menu.addSeparator()
        menu.addAction("➕ New Namespace...").triggered.connect(self._create_namespace)
    
    def _populate_secrets_menu(self, menu: QMenu):
        """Populate secrets menu with mounted secret engines."""
        menu.clear()
        menu.addAction("⏳ Loading...").setEnabled(False)
        
        def load_mounts():
            try:
                return self.client.list_mounts()
            except Exception as e:
                return {'error': str(e)}
        
        def on_complete(mounts):
            menu.clear()
            
            if 'error' in mounts:
                menu.addAction(f"⚠️ {mounts['error'][:40]}").setEnabled(False)
                return
            
            for mount_path, mount_info in sorted(mounts.items()):
                mount_type = mount_info.get('type', 'unknown')
                description = mount_info.get('description', '')
                
                # Choose icon based on type
                icons = {
                    'kv': '📁', 'generic': '📁', 'cubbyhole': '📦',
                    'transit': '🔐', 'pki': '📜', 'ssh': '🖥️',
                    'aws': '☁️', 'database': '🗄️', 'totp': '🔢'
                }
                icon = icons.get(mount_type, '📄')
                
                submenu = menu.addMenu(f"{icon} {mount_path.rstrip('/')} ({mount_type})")
                submenu.aboutToShow.connect(
                    partial(self._populate_mount_secrets, submenu, mount_path, mount_type)
                )
        
        worker = AsyncWorker(load_mounts)
        worker.signals.finished.connect(on_complete)
        worker.start()
        self._workers.append(worker)
    
    def _populate_mount_secrets(self, menu: QMenu, mount_path: str, mount_type: str):
        """Populate secrets for a specific mount."""
        menu.clear()
        menu.addAction("⏳ Loading...").setEnabled(False)
        
        # Determine API version path
        if mount_type == 'kv':
            # Try to determine KV version
            list_path = f"/v1/{mount_path}metadata/"
        else:
            list_path = f"/v1/{mount_path}"
        
        def load_secrets():
            try:
                return self.client.list(list_path)
            except:
                # Fall back to basic path
                try:
                    return self.client.list(f"/v1/{mount_path}")
                except Exception as e:
                    return []
        
        def on_complete(secrets):
            menu.clear()
            
            # Add "New..." option
            new_action = menu.addAction("✨ New Secret...")
            new_action.triggered.connect(partial(self._create_secret, mount_path, mount_type))
            menu.addSeparator()
            
            if secrets:
                for secret in secrets:
                    if secret.endswith('/'):
                        # It's a directory
                        submenu = menu.addMenu(f"📁 {secret.rstrip('/')}")
                        submenu.aboutToShow.connect(
                            partial(self._populate_secret_path, submenu, 
                                   mount_path + secret, mount_type)
                        )
                    else:
                        # It's a secret
                        action = menu.addAction(f"🔐 {secret}")
                        action.triggered.connect(
                            partial(self._show_secret, mount_path, secret, mount_type)
                        )
            else:
                menu.addAction("(empty)").setEnabled(False)
        
        worker = AsyncWorker(load_secrets)
        worker.signals.finished.connect(on_complete)
        worker.start()
        self._workers.append(worker)
    
    def _populate_secret_path(self, menu: QMenu, path: str, mount_type: str):
        """Populate secrets at a specific path."""
        menu.clear()
        menu.addAction("⏳ Loading...").setEnabled(False)
        
        if mount_type == 'kv':
            list_path = f"/v1/{path.split('/')[0]}/metadata/{'/'.join(path.split('/')[1:])}"
        else:
            list_path = f"/v1/{path}"
        
        def load_secrets():
            try:
                return self.client.list(list_path)
            except:
                return []
        
        def on_complete(secrets):
            menu.clear()
            
            new_action = menu.addAction("✨ New Secret...")
            new_action.triggered.connect(partial(self._create_secret, path, mount_type))
            menu.addSeparator()
            
            if secrets:
                for secret in secrets:
                    if secret.endswith('/'):
                        submenu = menu.addMenu(f"📁 {secret.rstrip('/')}")
                        submenu.aboutToShow.connect(
                            partial(self._populate_secret_path, submenu,
                                   path + secret, mount_type)
                        )
                    else:
                        action = menu.addAction(f"🔐 {secret}")
                        action.triggered.connect(
                            partial(self._show_secret, path, secret, mount_type)
                        )
            else:
                menu.addAction("(empty)").setEnabled(False)
        
        worker = AsyncWorker(load_secrets)
        worker.signals.finished.connect(on_complete)
        worker.start()
        self._workers.append(worker)
    
    def _populate_auth_menu(self, menu: QMenu):
        """Populate auth methods menu."""
        menu.clear()
        menu.addAction("⏳ Loading...").setEnabled(False)
        
        def load_auth():
            try:
                return self.client.list_auth_methods()
            except Exception as e:
                return {'error': str(e)}
        
        def on_complete(methods):
            menu.clear()
            
            if 'error' in methods:
                menu.addAction(f"⚠️ {methods['error'][:40]}").setEnabled(False)
                return
            
            for path, info in sorted(methods.items()):
                method_type = info.get('type', 'unknown')
                icons = {
                    'token': '🎫', 'userpass': '👤', 'ldap': '🏢',
                    'approle': '🤖', 'aws': '☁️', 'oidc': '🔗',
                    'github': '🐙', 'cert': '📜'
                }
                icon = icons.get(method_type, '🔓')
                
                action = menu.addAction(f"{icon} {path.rstrip('/')} ({method_type})")
                action.triggered.connect(partial(self._show_auth_method, path, info))
        
        worker = AsyncWorker(load_auth)
        worker.signals.finished.connect(on_complete)
        worker.start()
        self._workers.append(worker)
    
    def _populate_policies_menu(self, menu: QMenu):
        """Populate policies menu."""
        menu.clear()
        menu.addAction("⏳ Loading...").setEnabled(False)
        
        def load_policies():
            try:
                return self.client.list_policies()
            except Exception as e:
                return []
        
        def on_complete(policies):
            menu.clear()
            
            new_action = menu.addAction("✨ New Policy...")
            new_action.triggered.connect(self._create_policy)
            menu.addSeparator()
            
            if policies:
                for policy in sorted(policies):
                    action = menu.addAction(f"📜 {policy}")
                    action.triggered.connect(partial(self._show_policy, policy))
            else:
                menu.addAction("(no policies)").setEnabled(False)
        
        worker = AsyncWorker(load_policies)
        worker.signals.finished.connect(on_complete)
        worker.start()
        self._workers.append(worker)
    
    def _populate_schema_menu(self, menu: QMenu):
        """Populate API schema browser menu."""
        menu.clear()
        menu.addAction("⏳ Loading schema...").setEnabled(False)
        
        def load_schema():
            try:
                return self.client.get_openapi_schema()
            except Exception as e:
                return {'error': str(e)}
        
        def on_complete(schema):
            menu.clear()
            
            if 'error' in schema:
                menu.addAction(f"⚠️ {schema['error'][:40]}").setEnabled(False)
                return
            
            # Create menu builder
            self.menu_builder = DynamicMenuBuilder(self.client, menu)
            self.menu_builder.set_schema(schema)
            
            # Parse and build menu from paths
            tree = self.menu_builder.parse_paths()
            
            if 'v1' in tree:
                for key, value in sorted(tree['v1'].items()):
                    if key.startswith('_'):
                        continue
                    
                    children = {k: v for k, v in value.items() if not k.startswith('_')}
                    if children:
                        submenu = menu.addMenu(f"📁 {key}")
                        self.menu_builder.build_path_menu(
                            submenu, children, value.get('_path', ''),
                            on_action=self._on_schema_path_action
                        )
                    else:
                        action = menu.addAction(f"📄 {key}")
                        path = value.get('_path', '')
                        methods = value.get('_methods', {})
                        action.triggered.connect(
                            partial(self._on_schema_path_action, path, methods)
                        )
        
        worker = AsyncWorker(load_schema)
        worker.signals.finished.connect(on_complete)
        worker.start()
        self._workers.append(worker)
    
    def _on_schema_path_action(self, path: str, methods: dict, is_new: bool = False):
        """Handle action on a schema path."""
        if is_new:
            dialog = NewSecretDialog(path)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    self.client.post(dialog.result_path, dialog.result_data)
                    self.showMessage("Success", "Created successfully", 
                                    QSystemTrayIcon.MessageIcon.Information)
                except APIError as e:
                    QMessageBox.critical(None, "Error", str(e))
            return
        
        # Try to read and display the data
        try:
            result = self.client.get('/v1' + path if not path.startswith('/v1') else path)
            data = result.get('data', result)
            
            dialog = KeyValueEditorDialog(f"View: {path}", data)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_data = dialog.get_data()
                if new_data:
                    self.client.post('/v1' + path if not path.startswith('/v1') else path, 
                                    {'data': new_data})
                    self.showMessage("Success", "Updated successfully",
                                    QSystemTrayIcon.MessageIcon.Information)
        except APIError as e:
            QMessageBox.warning(None, "Error", str(e))
    
    def _populate_leases_menu(self, menu: QMenu):
        """Populate leases menu."""
        menu.clear()
        menu.addAction("⏳ Loading...").setEnabled(False)
        
        def load_leases():
            try:
                return self.client.list_leases()
            except Exception as e:
                return []
        
        def on_complete(leases):
            menu.clear()
            
            if leases:
                for lease in leases:
                    submenu = menu.addMenu(f"📄 {lease[:40]}...")
                    submenu.addAction("🔄 Renew").triggered.connect(
                        partial(self._renew_lease, lease))
                    submenu.addAction("🗑️ Revoke").triggered.connect(
                        partial(self._revoke_lease, lease))
                    submenu.addAction("ℹ️ Info").triggered.connect(
                        partial(self._show_lease_info, lease))
            else:
                menu.addAction("(no leases)").setEnabled(False)
        
        worker = AsyncWorker(load_leases)
        worker.signals.finished.connect(on_complete)
        worker.start()
        self._workers.append(worker)
    
    # =========================================================================
    # Action Handlers
    # =========================================================================
    
    def _show_seal_status(self):
        """Show seal status dialog."""
        try:
            status = self.client.seal_status()
            dialog = SealStatusDialog(status)
            dialog.exec()
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to get seal status: {e}")
    
    def _show_health(self):
        """Show health status."""
        try:
            health = self.client.health()
            dialog = KeyValueEditorDialog("❤️ Health Status", health, readonly=True)
            dialog.exec()
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to get health: {e}")
    
    def _show_token_info(self):
        """Show token information dialog."""
        try:
            info = self.client.token_lookup_self()
            dialog = TokenInfoDialog(info)
            dialog.exec()
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to get token info: {e}")
    
    def _show_secret(self, mount_path: str, secret_name: str, mount_type: str):
        """Show secret details with CRUD options."""
        try:
            if mount_type == 'kv':
                # Try KV v2 first
                try:
                    path = f"/v1/{mount_path.split('/')[0]}/data/{'/'.join(mount_path.split('/')[1:])}{secret_name}"
                    result = self.client.get(path)
                    data = result.get('data', {}).get('data', result.get('data', {}))
                except:
                    # Fall back to KV v1
                    path = f"/v1/{mount_path}{secret_name}"
                    result = self.client.get(path)
                    data = result.get('data', {})
            else:
                path = f"/v1/{mount_path}{secret_name}"
                result = self.client.get(path)
                data = result.get('data', {})
            
            dialog = KeyValueEditorDialog(f"🔐 Secret: {secret_name}", data)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_data = dialog.get_data()
                if new_data:
                    if mount_type == 'kv':
                        self.client.post(path, {'data': new_data})
                    else:
                        self.client.post(path, new_data)
                    self.showMessage("Success", "Secret updated", 
                                    QSystemTrayIcon.MessageIcon.Information)
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to read secret: {e}")
    
    def _create_secret(self, base_path: str, mount_type: str):
        """Create a new secret."""
        dialog = NewSecretDialog(base_path)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                if mount_type == 'kv':
                    path = dialog.result_path
                    if not path.startswith('/v1/'):
                        path = f"/v1/{path}"
                    # Convert to KV v2 data path if needed
                    parts = path.split('/')
                    if len(parts) > 2 and 'data' not in parts:
                        parts.insert(3, 'data')
                        path = '/'.join(parts)
                    self.client.post(path, {'data': dialog.result_data})
                else:
                    path = f"/v1/{dialog.result_path}"
                    self.client.post(path, dialog.result_data)
                
                self.showMessage("Success", "Secret created successfully",
                                QSystemTrayIcon.MessageIcon.Information)
            except APIError as e:
                QMessageBox.critical(None, "Error", f"Failed to create secret: {e}")
    
    def _show_auth_method(self, path: str, info: dict):
        """Show auth method details."""
        dialog = KeyValueEditorDialog(f"🔓 Auth Method: {path}", info, readonly=True)
        dialog.exec()
    
    def _show_policy(self, name: str):
        """Show policy with edit option."""
        try:
            result = self.client.read_policy(name)
            policy_text = result.get('data', {}).get('policy', '')
            
            # Check if it's a built-in policy
            readonly = name in ['root', 'default']
            
            dialog = PolicyEditorDialog(name, policy_text, readonly=readonly)
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_policy:
                self.client.write_policy(name, dialog.result_policy)
                self.showMessage("Success", "Policy updated",
                                QSystemTrayIcon.MessageIcon.Information)
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to read policy: {e}")
    
    def _create_policy(self):
        """Create a new policy."""
        name, ok = QInputDialog.getText(None, "New Policy", "Policy name:")
        if ok and name:
            dialog = PolicyEditorDialog(name, "# New policy\n\npath \"*\" {\n  capabilities = [\"read\"]\n}")
            if dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    self.client.write_policy(name, dialog.result_policy)
                    self.showMessage("Success", "Policy created",
                                    QSystemTrayIcon.MessageIcon.Information)
                except APIError as e:
                    QMessageBox.critical(None, "Error", f"Failed to create policy: {e}")
    
    def _show_random_tool(self):
        """Show random bytes generator."""
        bytes_count, ok = QInputDialog.getInt(None, "Random Bytes", 
                                               "Number of bytes:", 32, 1, 1024)
        if ok:
            try:
                result = self.client.random_bytes(bytes_count)
                data = result.get('data', {})
                dialog = KeyValueEditorDialog("🎲 Random Bytes", data, readonly=True)
                dialog.exec()
            except APIError as e:
                QMessageBox.critical(None, "Error", f"Failed to generate random: {e}")
    
    def _show_hash_tool(self):
        """Show hash tool."""
        text, ok = QInputDialog.getText(None, "Hash Tool", "Text to hash:")
        if ok and text:
            try:
                result = self.client.hash_data(text)
                data = result.get('data', {})
                dialog = KeyValueEditorDialog("#️⃣ Hash Result", data, readonly=True)
                dialog.exec()
            except APIError as e:
                QMessageBox.critical(None, "Error", f"Failed to hash: {e}")
    
    def _show_audit_devices(self):
        """Show audit devices."""
        try:
            devices = self.client.list_audit_devices()
            dialog = KeyValueEditorDialog("📋 Audit Devices", devices, readonly=True)
            dialog.exec()
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to list audit devices: {e}")
    
    def _show_mounts(self):
        """Show secret engine mounts."""
        try:
            mounts = self.client.list_mounts()
            dialog = KeyValueEditorDialog("💾 Secret Engine Mounts", mounts, readonly=True)
            dialog.exec()
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to list mounts: {e}")
    
    def _renew_lease(self, lease_id: str):
        """Renew a lease."""
        try:
            self.client.lease_renew(lease_id)
            self.showMessage("Success", "Lease renewed",
                            QSystemTrayIcon.MessageIcon.Information)
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to renew lease: {e}")
    
    def _revoke_lease(self, lease_id: str):
        """Revoke a lease."""
        reply = QMessageBox.question(None, "Confirm Revoke",
                                      f"Are you sure you want to revoke this lease?\n{lease_id[:50]}...")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.client.lease_revoke(lease_id)
                self.showMessage("Success", "Lease revoked",
                                QSystemTrayIcon.MessageIcon.Information)
            except APIError as e:
                QMessageBox.critical(None, "Error", f"Failed to revoke lease: {e}")
    
    def _show_lease_info(self, lease_id: str):
        """Show lease information."""
        try:
            info = self.client.lease_lookup(lease_id)
            dialog = KeyValueEditorDialog(f"📄 Lease: {lease_id[:30]}...", 
                                          info.get('data', info), readonly=True)
            dialog.exec()
        except APIError as e:
            QMessageBox.critical(None, "Error", f"Failed to get lease info: {e}")
    
    def _set_namespace(self, namespace: str):
        """Set the current namespace."""
        self.client.namespace = namespace
        self.showMessage("Namespace Changed", 
                        f"Now using namespace: {namespace or 'root'}",
                        QSystemTrayIcon.MessageIcon.Information)
    
    def _create_namespace(self):
        """Create a new namespace."""
        name, ok = QInputDialog.getText(None, "New Namespace", "Namespace name:")
        if ok and name:
            try:
                self.client.post(f"/v1/sys/namespaces/{name}", {})
                self.showMessage("Success", f"Namespace '{name}' created",
                                QSystemTrayIcon.MessageIcon.Information)
            except APIError as e:
                QMessageBox.critical(None, "Error", f"Failed to create namespace: {e}")
    
    def _show_settings(self):
        """Show settings dialog."""
        dialog = SettingsDialog(self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._restart_background_workers()
    
    def _refresh_schemas(self):
        """Refresh cached schemas."""
        self.client._schema_cache = {}
        self.client._schema_cache_time = 0
        self.showMessage("Schemas Refreshed", "Schema cache cleared",
                        QSystemTrayIcon.MessageIcon.Information)
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(None, "About OpenTongchi",
                         "🔐 OpenTongchi v1.0\n\n"
                         "Open Source Infrastructure Manager\n\n"
                         "A Qt6 system tray application for managing:\n"
                         "• OpenBao (Secrets Management)\n"
                         "• Consul (Service Discovery)\n"
                         "• Nomad (Workload Orchestration)\n"
                         "• OpenTofu (Infrastructure as Code)\n"
                         "• Waypoint (Application Deployment)\n"
                         "• Boundary (Secure Access)\n\n"
                         "Author: John Boero\n"
                         "Email: boeroboy@gmail.com")
    
    def _show_not_implemented(self, feature: str):
        """Show not implemented message."""
        QMessageBox.information(None, "Not Implemented",
                               f"{feature} is not yet implemented.\n"
                               "Focus is currently on OpenBao.")
    
    def _exit(self):
        """Exit the application."""
        self._stop_background_workers()
        self.hide()
        self.app.quit()
    
    # =========================================================================
    # Background Workers
    # =========================================================================
    
    def _start_background_workers(self):
        """Start background workers for token/lease renewal."""
        self._renewal_worker = TokenRenewalWorker(self.config, self.client)
        self._renewal_worker.status_update.connect(self._on_renewal_status)
        self._renewal_worker.renewal_error.connect(self._on_renewal_error)
        self._renewal_worker.start()
    
    def _stop_background_workers(self):
        """Stop background workers."""
        if self._renewal_worker:
            self._renewal_worker.stop()
            self._renewal_worker.wait()
    
    def _restart_background_workers(self):
        """Restart background workers with new config."""
        self._stop_background_workers()
        self._start_background_workers()
    
    def _on_renewal_status(self, message: str):
        """Handle renewal status update."""
        # Could show as tooltip or notification
        pass
    
    def _on_renewal_error(self, error: str):
        """Handle renewal error."""
        self.showMessage("Renewal Error", error, QSystemTrayIcon.MessageIcon.Warning)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("OpenTongchi")
    app.setApplicationDisplayName("OpenTongchi - Infrastructure Manager")
    
    # Check for system tray availability
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Error", 
                            "System tray is not available on this system.")
        sys.exit(1)
    
    # Create and show tray icon
    tray = OpenTongchiTray(app)
    
    # Start event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
    