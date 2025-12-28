#!/usr/bin/python
"""
OpenTongchi - OpenBao/HashiCorp Tool Manager
Refactored for Qt6 (PySide6) with Async Loading and Smart KV Support
"""

import sys
import os
import json
import time
import re
import requests
from urllib.parse import urljoin

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QDialog, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QCheckBox, QMessageBox, 
    QSpinBox, QWidget, QStyle, QProgressBar, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtGui import QIcon, QAction, QCursor
from PySide6.QtCore import (
    Qt, QThread, Signal, Slot, QSettings, QObject
)

# --- Configuration & Constants ---
APP_NAME = "OpenTongchi"
ORG_NAME = "OpenTongchiProject"
# Support OPENBAO env vars with fallback to VAULT
DEFAULT_ADDR = os.environ.get("OPENBAO_ADDR", os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200"))
DEFAULT_TOKEN = os.environ.get("OPENBAO_TOKEN", os.environ.get("VAULT_TOKEN", "root"))

# --- Backend Logic ---

class OpenBaoClient:
    def __init__(self):
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.addr = self.settings.value("addr", DEFAULT_ADDR)
        self.token = self.settings.value("token", DEFAULT_TOKEN)
        self.verify = self.settings.value("verify_ssl", "true") == "true"
        
        # Cache for mounts and schema
        self.mounts_cache = {} 
        self.schema_cache = {}

    def get_headers(self):
        return {"X-Vault-Token": self.token}

    def update_config(self, addr, token, verify):
        self.addr = addr
        self.token = token
        self.verify = verify
        self.settings.setValue("addr", addr)
        self.settings.setValue("token", token)
        self.settings.setValue("verify_ssl", str(verify).lower())
        self.refresh_mounts()

    def refresh_mounts(self):
        """Fetches and analyzes sys/mounts to determine KV versions."""
        try:
            url = f"{self.addr}/v1/sys/mounts"
            r = requests.get(url, headers=self.get_headers(), verify=self.verify, timeout=3)
            r.raise_for_status()
            self.mounts_cache = r.json().get("data", {})
            return True
        except Exception as e:
            print(f"Error fetching mounts: {e}")
            return False

    def fetch_schema(self):
        """Fetches OpenAPIv3 schema."""
        try:
            url = f"{self.addr}/v1/sys/internal/specs/openapi"
            r = requests.get(url, headers=self.get_headers(), verify=self.verify, timeout=5)
            r.raise_for_status()
            self.schema_cache = r.json()
            return True, "Schema refreshed."
        except Exception as e:
            return False, str(e)

    def is_kv2(self, path):
        """Checks if a path belongs to a KV v2 mount."""
        # Find the longest matching mount point
        best_match = ""
        for mount in self.mounts_cache:
            if path.startswith(mount) and len(mount) > len(best_match):
                best_match = mount
        
        if best_match:
            options = self.mounts_cache[best_match].get("options", {})
            if options and options.get("version") == "2":
                return True, best_match
        return False, best_match

    def list_path(self, path):
        """
        Smart List: Handles KV v2 'metadata' vs standard listing.
        Returns: (list_of_keys, full_api_path_used)
        """
        # Ensure mounts are loaded
        if not self.mounts_cache:
            self.refresh_mounts()

        # Determine actual API path for listing
        is_v2, mount_point = self.is_kv2(path)
        
        api_path = path
        if is_v2:
            # If path matches mount exactly (e.g. "secret/"), append metadata
            # If path is deeper (e.g. "secret/foo/"), inject metadata after mount
            relative = path[len(mount_point):]
            api_path = f"{mount_point}metadata/{relative}"
            # Remove double slashes if any
            api_path = api_path.replace("//", "/")

        url = f"{self.addr}/v1/{api_path}?list=true"
        
        try:
            r = requests.request("LIST", url, headers=self.get_headers(), verify=self.verify, timeout=5)
            if r.status_code == 404:
                return [], api_path
            r.raise_for_status()
            
            data = r.json().get("data", {})
            keys = data.get("keys", [])
            return keys, api_path
        except Exception as e:
            print(f"List error on {url}: {e}")
            return None, str(e)

    def read_secret(self, path):
        """Smart Read: Handles KV v2 'data' wrapper."""
        is_v2, mount_point = self.is_kv2(path)
        
        api_path = path
        if is_v2:
            relative = path[len(mount_point):]
            api_path = f"{mount_point}data/{relative}"

        url = f"{self.addr}/v1/{api_path}"
        try:
            r = requests.get(url, headers=self.get_headers(), verify=self.verify, timeout=5)
            r.raise_for_status()
            return r.json(), is_v2
        except Exception as e:
            return {"error": str(e)}, False

    def write_secret(self, path, data, is_v2=False):
        """Smart Write."""
        # If we detected v2 earlier, we construct the v2 path
        # but the editor might pass raw data.
        
        # Re-detect to be safe
        is_v2_check, mount_point = self.is_kv2(path)
        
        api_path = path
        payload = data

        if is_v2_check:
            relative = path[len(mount_point):]
            api_path = f"{mount_point}data/{relative}"
            # KV v2 expects JSON: { "data": { ... } }
            if "data" not in data:
                payload = {"data": data}

        url = f"{self.addr}/v1/{api_path}"
        try:
            r = requests.post(url, headers=self.get_headers(), json=payload, verify=self.verify, timeout=5)
            r.raise_for_status()
            return True, "Saved"
        except Exception as e:
            return False, str(e)

    def renew_token(self):
        url = f"{self.addr}/v1/auth/token/renew-self"
        try:
            requests.post(url, headers=self.get_headers(), verify=self.verify, timeout=5)
            return True
        except:
            return False

# --- Async Workers ---

class MenuLoader(QThread):
    """Background thread to list secrets."""
    data_ready = Signal(list, str) # keys, path

    def __init__(self, client, path):
        super().__init__()
        self.client = client
        self.path = path

    def run(self):
        keys, _ = self.client.list_path(self.path)
        # Sort: directories first, then files
        if keys:
            dirs = sorted([k for k in keys if k.endswith('/')])
            files = sorted([k for k in keys if not k.endswith('/')])
            self.data_ready.emit(dirs + files, self.path)
        else:
            self.data_ready.emit([], self.path)

class RenewerThread(QThread):
    """Background thread for token renewal."""
    log_signal = Signal(str)

    def __init__(self, client, interval=300):
        super().__init__()
        self.client = client
        self.interval = interval
        self.running = True

    def run(self):
        while self.running:
            if self.client.renew_token():
                self.log_signal.emit(f"Token renewed at {time.strftime('%H:%M')}")
            else:
                self.log_signal.emit("Token renewal failed")
            
            # Interruptible sleep
            for _ in range(self.interval):
                if not self.running: return
                time.sleep(1)

    def stop(self):
        self.running = False
        self.wait()

# --- UI Components ---

class SecretEditorDialog(QDialog):
    def __init__(self, parent, client, path, initial_data, is_v2):
        super().__init__(parent)
        self.client = client
        self.path = path
        self.is_v2 = is_v2
        self.resize(700, 500)
        self.setWindowTitle(f"Edit: {path}")

        layout = QVBoxLayout()
        
        # Info Header
        info_str = f"<b>Path:</b> {path} &nbsp;|&nbsp; <b>Engine:</b> {'KV v2' if is_v2 else 'KV v1/Generic'}"
        layout.addWidget(QLabel(info_str))

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Key", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Parse Data
        self.raw_data = initial_data
        self.kv_data = {}
        
        # Extract actual KV pairs from Vault wrapper
        data_block = initial_data.get("data", {})
        if self.is_v2 and "data" in data_block:
            self.kv_data = data_block["data"]
        else:
            self.kv_data = data_block

        if not isinstance(self.kv_data, dict):
            # Fallback for non-KV endpoints (like raw reads)
            self.kv_data = {"raw_response": str(initial_data)}

        self.populate_table()

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Key")
        self.btn_add.clicked.connect(self.add_row)
        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save)
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def populate_table(self):
        self.table.setRowCount(0)
        for k, v in self.kv_data.items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(k)))
            val_str = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            self.table.setItem(r, 1, QTableWidgetItem(val_str))

    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem("new_key"))
        self.table.setItem(r, 1, QTableWidgetItem(""))

    def save(self):
        new_data = {}
        for r in range(self.table.rowCount()):
            k = self.table.item(r, 0).text()
            v_raw = self.table.item(r, 1).text()
            try:
                v = json.loads(v_raw)
            except:
                v = v_raw
            if k: new_data[k] = v
        
        success, msg = self.client.write_secret(self.path, new_data, self.is_v2)
        if success:
            QMessageBox.information(self, "Success", "Secret updated.")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", msg)

class SchemaBrowser(QDialog):
    """
    Parses OpenAPI schema to show a tree of all available paths.
    """
    def __init__(self, parent, schema):
        super().__init__(parent)
        self.setWindowTitle("API Schema Explorer")
        self.resize(800, 600)
        
        layout = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["API Path", "Methods"])
        layout.addWidget(self.tree)
        
        paths = schema.get("paths", {})
        
        # Naive tree builder: split path by '/'
        root_items = {}
        
        for path_str, methods in sorted(paths.items()):
            parts = [p for p in path_str.strip('/').split('/') if p]
            parent = self.tree
            current_key = ""
            
            for i, part in enumerate(parts):
                current_key += part + "/"
                # Check if node exists at this level (simple approximation)
                # For a perfect tree we'd need a recursive node finder, but this works for flat list
                
                # Simply add the full path as a leaf if it's the last part
                if i == len(parts) - 1:
                    item = QTreeWidgetItem(parent)
                    item.setText(0, f"/{path_str}")
                    item.setText(1, ", ".join(methods.keys()).upper())
                
        self.setLayout(layout)

class TrayApp(QSystemTrayIcon):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.client = OpenBaoClient()
        self.active_loaders = []
        
        # Ensure mounts are fetched on startup
        self.client.refresh_mounts()
        
        # Background Renewer
        self.renewer = RenewerThread(self.client)
        self.renewer.log_signal.connect(self.show_notif)
        self.renewer.start()

        # Icon
        self.setup_icon()
        
        # Menu
        self.menu = QMenu()
        self.setContextMenu(self.menu)
        self.activated.connect(self.on_click)
        
        self.build_root_menu()
        self.show()

    def setup_icon(self):
        if os.path.exists("img/hashicon.png"):
            self.setIcon(QIcon("img/hashicon.png"))
        else:
            self.setIcon(QApplication.style().standardIcon(QStyle.SP_ComputerIcon))

    def on_click(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.menu.exec(QCursor.pos())

    def show_notif(self, msg):
        if "failed" in msg:
            self.showMessage("OpenTongchi", msg, QSystemTrayIcon.Warning)

    # --- Menu Logic ---

    def build_root_menu(self):
        self.menu.clear()
        
        # Header
        lbl = self.menu.addAction(f"Connected: {self.client.addr}")
        lbl.setEnabled(False)
        self.menu.addSeparator()

        # Secret Engines (Root Mounts)
        secrets_menu = self.menu.addMenu("Secrets")
        # Populate mounts immediately since we have them cached
        self.populate_mounts_menu(secrets_menu)
        
        # Schema Browser
        schema_act = self.menu.addAction("Explore API Schema...")
        schema_act.triggered.connect(self.open_schema_browser)

        self.menu.addSeparator()
        
        # Tools
        self.menu.addAction("Settings...").triggered.connect(self.open_settings)
        self.menu.addAction("Refresh Mounts/Schema").triggered.connect(self.refresh_all)
        self.menu.addAction("Exit").triggered.connect(self.exit_app)

    def populate_mounts_menu(self, menu):
        if not self.client.mounts_cache:
            menu.addAction("No mounts found (Check Token/Connection)").setEnabled(False)
            return

        for mount, data in sorted(self.client.mounts_cache.items()):
            # Create a submenu for each mount
            m_type = data.get("type", "unknown")
            desc = data.get("description", "")
            
            # We treat mounts as directories
            mount_menu = menu.addMenu(f"{mount} ({m_type})")
            
            # Add a placeholder so the Hover works
            loading = mount_menu.addAction("Loading...")
            loading.setEnabled(False)
            
            # Connect the Hover event to Lazy Load
            # Use QTimer to delay slightly or just direct connect?
            # PySide6 menus don't have a simple "onHover" for population easily without subclassing.
            # Standard approach: Connect aboutToShow
            mount_menu.aboutToShow.connect(lambda m=mount_menu, p=mount: self.lazy_load(m, p))

    def lazy_load(self, menu, path):
        """
        Triggered when a menu is about to be shown.
        Checks if it needs population.
        """
        # If menu has more than 1 item or first item is not "Loading...", it's likely loaded.
        # Strict check: if it has actions and the first one is valid data, return.
        actions = menu.actions()
        if len(actions) > 1: 
            return
        if len(actions) == 1 and actions[0].text() != "Loading...":
            return

        # Start Loader
        loader = MenuLoader(self.client, path)
        loader.data_ready.connect(lambda k, p: self.on_menu_data_ready(menu, k, p))
        
        # Keep reference to prevent GC
        self.active_loaders.append(loader)
        loader.start()

    def on_menu_data_ready(self, menu, keys, path):
        menu.clear()
        
        if not keys:
            menu.addAction("(Empty)").setEnabled(False)
        else:
            # "New..." Action
            new_act = menu.addAction("New Secret...")
            new_act.triggered.connect(lambda: self.open_editor(f"{path}new", is_new=True))
            menu.addSeparator()

            for k in keys:
                full_path = f"{path}{k}"
                if k.endswith("/"):
                    # Subdirectory
                    sub = menu.addMenu(k)
                    sub.addAction("Loading...")
                    sub.aboutToShow.connect(lambda m=sub, p=full_path: self.lazy_load(m, p))
                else:
                    # Leaf
                    act = menu.addAction(k)
                    act.triggered.connect(lambda c=False, p=full_path: self.open_editor(p))

    def open_editor(self, path, is_new=False):
        data = {}
        is_v2 = False
        
        if not is_new:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            data, is_v2 = self.client.read_secret(path)
            QApplication.restoreOverrideCursor()
            
            if "error" in data:
                QMessageBox.warning(None, "Read Error", data["error"])
                return
        else:
            # Check if mount is V2 to set flag correctly for new secret
            is_v2, _ = self.client.is_kv2(path)

        dlg = SecretEditorDialog(None, self.client, path, data, is_v2)
        dlg.exec()

    def open_schema_browser(self):
        if not self.client.schema_cache:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.client.fetch_schema()
            QApplication.restoreOverrideCursor()
        
        if not self.client.schema_cache:
            QMessageBox.warning(None, "Error", "Could not fetch schema.")
            return

        dlg = SchemaBrowser(None, self.client.schema_cache)
        dlg.exec()

    def open_settings(self):
        # Simple Settings Dialog
        d = QDialog()
        d.setWindowTitle("Settings")
        l = QVBoxLayout(d)
        
        addr = QLineEdit(self.client.addr)
        l.addWidget(QLabel("Address:"))
        l.addWidget(addr)
        
        tok = QLineEdit(self.client.token)
        tok.setEchoMode(QLineEdit.Password)
        l.addWidget(QLabel("Token:"))
        l.addWidget(tok)
        
        btn = QPushButton("Save")
        btn.clicked.connect(lambda: [self.client.update_config(addr.text(), tok.text(), True), d.accept()])
        l.addWidget(btn)
        d.exec()

    def refresh_all(self):
        self.client.refresh_mounts()
        self.client.fetch_schema()
        self.build_root_menu()
        self.showMessage("Refreshed", "Mounts and Schema updated.")

    def exit_app(self):
        self.renewer.stop()
        self.app.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    tray = TrayApp(app)
    sys.exit(app.exec())