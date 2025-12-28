#!/usr/bin/env python3
"""
HashiCorp Vault/OpenBao System Tray Manager - Qt6 Version
Supports reading, writing, and managing secrets via VAULT_* environment variables.
Supports both HashiCorp Vault and OpenBao.

Cross-platform: Linux (KDE/GNOME), Windows, macOS

Requirements: 
  pip install PyQt6 requests
  OR
  pip install PySide6 requests

Original: John Boero - jboero@hashicorp.com
Enhanced with full Vault API integration and Qt6 support
"""

import sys
import os
import json
import requests
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

try:
    from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QDialog, 
                                  QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                                  QPushButton, QScrollArea, QWidget, QMessageBox,
                                  QInputDialog)
    from PyQt6.QtGui import QIcon, QAction
    from PyQt6.QtCore import Qt
except ImportError:
    try:
        from PySide6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QDialog,
                                        QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                                        QPushButton, QScrollArea, QWidget, QMessageBox,
                                        QInputDialog)
        from PySide6.QtGui import QIcon, QAction
        from PySide6.QtCore import Qt
    except ImportError:
        print("Error: Please install PyQt6 or PySide6:")
        print("  pip install PyQt6 requests")
        print("  OR")
        print("  pip install PySide6 requests")
        sys.exit(1)


class VaultClient:
    """Client for interacting with HashiCorp Vault or OpenBao"""
    
    def __init__(self):
        self.addr = os.environ.get('VAULT_ADDR', 'http://127.0.0.1:8200')
        self.token = os.environ.get('VAULT_TOKEN', '')
        self.namespace = os.environ.get('VAULT_NAMESPACE', '')
        self.skip_verify = os.environ.get('VAULT_SKIP_VERIFY', 'false').lower() == 'true'
        self.session = requests.Session()
        self.session.verify = not self.skip_verify
        
    def _headers(self) -> Dict[str, str]:
        """Build headers for Vault requests"""
        headers = {'X-Vault-Token': self.token}
        if self.namespace:
            headers['X-Vault-Namespace'] = self.namespace
        return headers
    
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make a request to Vault"""
        url = urljoin(self.addr, path)
        response = self.session.request(
            method, url, headers=self._headers(), **kwargs
        )
        return response
    
    def is_authenticated(self) -> bool:
        """Check if current token is valid"""
        try:
            response = self._request('GET', '/v1/auth/token/lookup-self')
            return response.status_code == 200
        except:
            return False
    
    def list_secrets(self, path: str, mount: str = 'secret') -> List[str]:
        """List secrets at a given path"""
        try:
            # Handle KV v2 vs v1
            list_path = f'/v1/{mount}/metadata/{path}' if path else f'/v1/{mount}/metadata'
            response = self._request('LIST', list_path)
            
            if response.status_code == 404:
                # Try KV v1
                list_path = f'/v1/{mount}/{path}' if path else f'/v1/{mount}'
                response = self._request('LIST', list_path)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {}).get('keys', [])
            return []
        except Exception as e:
            print(f"Error listing secrets: {e}")
            return []
    
    def read_secret(self, path: str, mount: str = 'secret') -> Optional[Dict[str, Any]]:
        """Read a secret from Vault"""
        try:
            # Try KV v2 first
            read_path = f'/v1/{mount}/data/{path}'
            response = self._request('GET', read_path)
            
            if response.status_code == 404:
                # Try KV v1
                read_path = f'/v1/{mount}/{path}'
                response = self._request('GET', read_path)
            
            if response.status_code == 200:
                data = response.json()
                # KV v2 has data.data, KV v1 has data
                return data.get('data', {}).get('data', data.get('data', {}))
            return None
        except Exception as e:
            print(f"Error reading secret: {e}")
            return None
    
    def write_secret(self, path: str, data: Dict[str, Any], mount: str = 'secret') -> bool:
        """Write a secret to Vault"""
        try:
            # Try KV v2 first
            write_path = f'/v1/{mount}/data/{path}'
            payload = {'data': data}
            response = self._request('POST', write_path, json=payload)
            
            if response.status_code == 404:
                # Try KV v1
                write_path = f'/v1/{mount}/{path}'
                response = self._request('POST', write_path, json=data)
            
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Error writing secret: {e}")
            return False
    
    def delete_secret(self, path: str, mount: str = 'secret') -> bool:
        """Delete a secret from Vault"""
        try:
            # Try KV v2 metadata delete
            delete_path = f'/v1/{mount}/metadata/{path}'
            response = self._request('DELETE', delete_path)
            
            if response.status_code == 404:
                # Try KV v1
                delete_path = f'/v1/{mount}/{path}'
                response = self._request('DELETE', delete_path)
            
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Error deleting secret: {e}")
            return False
    
    def undelete_secret(self, path: str, versions: List[int], mount: str = 'secret') -> bool:
        """Undelete secret versions (KV v2 only)"""
        try:
            undelete_path = f'/v1/{mount}/undelete/{path}'
            payload = {'versions': versions}
            response = self._request('POST', undelete_path, json=payload)
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Error undeleting secret: {e}")
            return False
    
    def destroy_secret(self, path: str, versions: List[int], mount: str = 'secret') -> bool:
        """Permanently destroy secret versions (KV v2 only)"""
        try:
            destroy_path = f'/v1/{mount}/destroy/{path}'
            payload = {'versions': versions}
            response = self._request('POST', destroy_path, json=payload)
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Error destroying secret: {e}")
            return False
    
    def get_secret_metadata(self, path: str, mount: str = 'secret') -> Optional[Dict[str, Any]]:
        """Get secret metadata (KV v2 only)"""
        try:
            metadata_path = f'/v1/{mount}/metadata/{path}'
            response = self._request('GET', metadata_path)
            if response.status_code == 200:
                return response.json().get('data', {})
            return None
        except Exception as e:
            print(f"Error getting metadata: {e}")
            return None
    
    def list_secret_versions(self, path: str, mount: str = 'secret') -> Optional[Dict[str, Any]]:
        """List all versions of a secret (KV v2 only)"""
        metadata = self.get_secret_metadata(path, mount)
        if metadata:
            return metadata.get('versions', {})
        return None
    
    def read_secret_version(self, path: str, version: int, mount: str = 'secret') -> Optional[Dict[str, Any]]:
        """Read a specific version of a secret (KV v2 only)"""
        try:
            read_path = f'/v1/{mount}/data/{path}?version={version}'
            response = self._request('GET', read_path)
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {}).get('data', {})
            return None
        except Exception as e:
            print(f"Error reading secret version: {e}")
            return None
    
    def list_mounts(self) -> Dict[str, Any]:
        """List all secret engines"""
        try:
            response = self._request('GET', '/v1/sys/mounts')
            if response.status_code == 200:
                return response.json().get('data', {})
            return {}
        except Exception as e:
            print(f"Error listing mounts: {e}")
            return {}
    
    def get_mount_config(self, mount: str) -> Optional[Dict[str, Any]]:
        """Get mount configuration"""
        try:
            response = self._request('GET', f'/v1/sys/mounts/{mount}/tune')
            if response.status_code == 200:
                return response.json().get('data', {})
            return None
        except Exception as e:
            print(f"Error getting mount config: {e}")
            return None
    
    def is_kv_v2(self, mount: str) -> bool:
        """Check if mount is KV v2"""
        config = self.get_mount_config(mount)
        if config:
            options = config.get('options', {})
            return options.get('version') == '2'
        # Try to detect by attempting a v2 operation
        try:
            response = self._request('LIST', f'/v1/{mount}/metadata')
            return response.status_code != 404
        except:
            return False
    
    def copy_secret(self, source_path: str, dest_path: str, source_mount: str = 'secret', 
                   dest_mount: str = 'secret') -> bool:
        """Copy a secret from source to destination"""
        try:
            data = self.read_secret(source_path, source_mount)
            if data:
                return self.write_secret(dest_path, data, dest_mount)
            return False
        except Exception as e:
            print(f"Error copying secret: {e}")
            return False
    
    def move_secret(self, source_path: str, dest_path: str, source_mount: str = 'secret',
                   dest_mount: str = 'secret') -> bool:
        """Move a secret from source to destination"""
        try:
            if self.copy_secret(source_path, dest_path, source_mount, dest_mount):
                return self.delete_secret(source_path, source_mount)
            return False
        except Exception as e:
            print(f"Error moving secret: {e}")
            return False


class SecretDialog(QDialog):
    """Dialog for viewing/editing secrets"""
    
    def __init__(self, parent, path: str, data: Dict[str, Any] = None, 
                 read_only: bool = False, callback=None):
        super().__init__(parent)
        self.path = path
        self.data = data or {}
        self.read_only = read_only
        self.callback = callback
        self.key_value_rows = []
        
        self.setWindowTitle(f"Secret: {path}")
        self.setMinimumSize(600, 400)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Path display
        path_label = QLabel(f"Path: {self.path}")
        path_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(path_label)
        
        # Scrollable area for key-value pairs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.kvp_layout = QVBoxLayout(scroll_widget)
        
        # Add existing key-value pairs
        for key, value in self.data.items():
            self.add_key_value_row(key, value)
        
        self.kvp_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Add button (only if not read-only)
        if not self.read_only:
            add_btn = QPushButton("Add Field")
            add_btn.clicked.connect(lambda: self.add_key_value_row())
            layout.addWidget(add_btn)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        if not self.read_only:
            save_btn = QPushButton("Save")
            save_btn.clicked.connect(self.on_save)
            button_layout.addWidget(save_btn)
        
        close_btn = QPushButton("Close" if self.read_only else "Cancel")
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def add_key_value_row(self, key: str = "", value: str = ""):
        row_layout = QHBoxLayout()
        
        key_entry = QLineEdit(key)
        key_entry.setPlaceholderText("Key")
        key_entry.setReadOnly(self.read_only)
        
        value_entry = QLineEdit(str(value))
        value_entry.setPlaceholderText("Value")
        value_entry.setReadOnly(self.read_only)
        
        remove_btn = QPushButton("✕")
        remove_btn.setMaximumWidth(30)
        remove_btn.setEnabled(not self.read_only)
        
        row_layout.addWidget(key_entry, 1)
        row_layout.addWidget(value_entry, 2)
        row_layout.addWidget(remove_btn)
        
        # Store reference
        row_data = (key_entry, value_entry, remove_btn, row_layout)
        self.key_value_rows.append(row_data)
        
        # Connect remove button
        remove_btn.clicked.connect(lambda: self.remove_row(row_data))
        
        # Insert before the stretch
        self.kvp_layout.insertLayout(self.kvp_layout.count() - 1, row_layout)
    
    def remove_row(self, row_data):
        key_entry, value_entry, remove_btn, row_layout = row_data
        self.key_value_rows.remove(row_data)
        
        # Remove widgets
        while row_layout.count():
            item = row_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.kvp_layout.removeItem(row_layout)
    
    def on_save(self):
        self.data = {}
        for key_entry, value_entry, _, _ in self.key_value_rows:
            key = key_entry.text().strip()
            value = value_entry.text()
            if key:
                self.data[key] = value
        
        if self.callback:
            self.callback(self.data)
        
        self.accept()


class VaultTrayApp(QApplication):
    """System tray application for Vault management"""
    
    def __init__(self, argv):
        super().__init__(argv)
        self.vault = VaultClient()
        self.mounts = []
        
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Try to use system icon, fallback to text indicator
        icon = QIcon.fromTheme("security-high")
        if icon.isNull():
            icon = QIcon.fromTheme("dialog-password")
        if icon.isNull():
            # Create a simple icon from text if no icon available
            from PyQt6.QtGui import QPixmap, QPainter, QColor
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "V")
            painter.end()
            icon = QIcon(pixmap)
        
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("HashiCorp Vault Manager")
        
        # Build menu
        self.refresh_mounts()
        self.build_menu()
        
        # Show tray icon
        self.tray_icon.show()
        
        # Set application to not quit when last window closes
        self.setQuitOnLastWindowClosed(False)
    
    def build_menu(self):
        """Build the system tray menu"""
        menu = QMenu()
        
        # Status
        if self.vault.is_authenticated():
            status_action = QAction(f"✓ Connected: {self.vault.addr}", self)
        else:
            status_action = QAction("✗ Not authenticated", self)
        status_action.setEnabled(False)
        menu.addAction(status_action)
        
        menu.addSeparator()
        
        # Vault submenu
        vault_menu = menu.addMenu("🔐 Vault/OpenBao")
        
        # Browse by mount
        browse_menu = vault_menu.addMenu("Browse Secrets")
        for mount in self.mounts:
            mount_action = browse_menu.addAction(mount)
            mount_action.triggered.connect(
                lambda checked=False, m=mount: self.show_browse_menu(m, "")
            )
        
        vault_menu.addSeparator()
        
        quick_read_action = vault_menu.addAction("Quick Read...")
        quick_read_action.triggered.connect(self.on_quick_read)
        
        quick_write_action = vault_menu.addAction("Quick Write...")
        quick_write_action.triggered.connect(self.on_quick_write)
        
        vault_menu.addSeparator()
        
        set_token_action = vault_menu.addAction("Set Token...")
        set_token_action.triggered.connect(self.on_set_token)
        
        conn_info_action = vault_menu.addAction("Connection Info")
        conn_info_action.triggered.connect(self.on_connection_info)
        
        menu.addSeparator()
        
        # Other HashiCorp products
        nomad_action = menu.addAction("📦 Nomad")
        nomad_action.triggered.connect(lambda: self.show_coming_soon("Nomad"))
        
        consul_action = menu.addAction("🔗 Consul")
        consul_action.triggered.connect(lambda: self.show_coming_soon("Consul"))
        
        terraform_action = menu.addAction("🏗️ Terraform")
        terraform_action.triggered.connect(lambda: self.show_coming_soon("Terraform"))
        
        menu.addSeparator()
        
        # Refresh
        refresh_action = menu.addAction("🔄 Refresh Mounts")
        refresh_action.triggered.connect(self.refresh_mounts_and_rebuild)
        
        menu.addSeparator()
        
        # Exit
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.quit)
        
        self.tray_icon.setContextMenu(menu)
    
    def show_browse_menu(self, mount: str, path: str):
        """Show a context menu for browsing secrets at path"""
        if not self.vault.is_authenticated():
            QMessageBox.critical(None, "Error", "Not authenticated. Please set a valid VAULT_TOKEN.")
            return
        
        secrets = self.vault.list_secrets(path, mount)
        
        if not secrets:
            # Might be a leaf node
            if path:
                self.read_secret(path.rstrip('/'), mount)
            return
        
        # Create dynamic menu
        browse_menu = QMenu()
        browse_menu.setTitle(f"{mount}/{path}" if path else mount)
        
        for secret in secrets:
            if secret.endswith('/'):
                # Folder - create submenu
                folder_menu = browse_menu.addMenu(f"📁 {secret}")
                new_path = path + secret
                
                # Add "Browse" action
                browse_action = folder_menu.addAction("Browse →")
                browse_action.triggered.connect(
                    lambda checked=False, m=mount, p=new_path: self.show_browse_menu(m, p)
                )
                
                folder_menu.addSeparator()
                
                # Add "List Contents" action
                list_action = folder_menu.addAction("List Contents")
                list_action.triggered.connect(
                    lambda checked=False, m=mount, p=new_path: self.show_folder_contents(m, p)
                )
            else:
                # Secret - create submenu with operations
                secret_menu = browse_menu.addMenu(f"📄 {secret}")
                secret_path = path + secret
                
                # Read
                read_action = secret_menu.addAction("👁️ Read")
                read_action.triggered.connect(
                    lambda checked=False, p=secret_path, m=mount: self.read_secret(p, m)
                )
                
                # Edit
                edit_action = secret_menu.addAction("✏️ Edit")
                edit_action.triggered.connect(
                    lambda checked=False, p=secret_path, m=mount: self.edit_secret(p, m)
                )
                
                secret_menu.addSeparator()
                
                # Copy
                copy_action = secret_menu.addAction("📋 Copy...")
                copy_action.triggered.connect(
                    lambda checked=False, p=secret_path, m=mount: self.copy_secret(p, m)
                )
                
                # Move/Rename
                move_action = secret_menu.addAction("➡️ Move/Rename...")
                move_action.triggered.connect(
                    lambda checked=False, p=secret_path, m=mount: self.move_secret(p, m)
                )
                
                secret_menu.addSeparator()
                
                # Versions (KV v2 only)
                if self.vault.is_kv_v2(mount):
                    versions_action = secret_menu.addAction("🕒 View Versions...")
                    versions_action.triggered.connect(
                        lambda checked=False, p=secret_path, m=mount: self.show_versions(p, m)
                    )
                    
                    metadata_action = secret_menu.addAction("ℹ️ View Metadata")
                    metadata_action.triggered.connect(
                        lambda checked=False, p=secret_path, m=mount: self.show_metadata(p, m)
                    )
                    
                    secret_menu.addSeparator()
                
                # Delete
                delete_action = secret_menu.addAction("🗑️ Delete")
                delete_action.triggered.connect(
                    lambda checked=False, p=secret_path, m=mount: self.delete_secret_confirm(p, m)
                )
                
                # Destroy (KV v2 only)
                if self.vault.is_kv_v2(mount):
                    destroy_action = secret_menu.addAction("💥 Destroy Permanently...")
                    destroy_action.triggered.connect(
                        lambda checked=False, p=secret_path, m=mount: self.destroy_secret_confirm(p, m)
                    )
        
        browse_menu.addSeparator()
        
        # Actions at this level
        write_action = browse_menu.addAction("✏️ Write New Secret Here...")
        write_action.triggered.connect(lambda: self.write_new_secret_at_path(mount, path))
        
        # Refresh
        refresh_action = browse_menu.addAction("🔄 Refresh")
        refresh_action.triggered.connect(lambda: self.show_browse_menu(mount, path))
        
        # Show menu at cursor
        browse_menu.exec(QApplication.primaryScreen().availableGeometry().center())
    
    def write_new_secret_at_path(self, mount: str, path: str):
        """Write a new secret at the given path"""
        name, ok = QInputDialog.getText(None, "New Secret", 
                                        f"Create secret in: {mount}/{path}\n\nEnter secret name:")
        if ok and name:
            full_path = path + name
            
            def save_callback(data):
                if self.vault.write_secret(full_path, data, mount):
                    QMessageBox.information(None, "Success", "Secret saved successfully!")
                else:
                    QMessageBox.critical(None, "Error", "Failed to save secret")
            
            dialog = SecretDialog(None, f"{mount}/{full_path}", callback=save_callback)
            dialog.exec()
    
    def read_secret(self, path: str, mount: str = "secret"):
        """Read and display a secret"""
        data = self.vault.read_secret(path, mount)
        
        if data is not None:
            dialog = SecretDialog(None, f"{mount}/{path}", data, read_only=True)
            dialog.exec()
        else:
            QMessageBox.critical(None, "Error", f"Failed to read secret: {mount}/{path}")
    
    def edit_secret(self, path: str, mount: str = "secret"):
        """Edit an existing secret"""
        data = self.vault.read_secret(path, mount)
        
        if data is not None:
            def save_callback(new_data):
                if self.vault.write_secret(path, new_data, mount):
                    QMessageBox.information(None, "Success", "Secret updated successfully!")
                else:
                    QMessageBox.critical(None, "Error", "Failed to update secret")
            
            dialog = SecretDialog(None, f"{mount}/{path}", data, read_only=False, callback=save_callback)
            dialog.exec()
        else:
            QMessageBox.critical(None, "Error", f"Failed to read secret: {mount}/{path}")
    
    def copy_secret(self, source_path: str, source_mount: str = "secret"):
        """Copy a secret to a new location"""
        dest_path, ok = QInputDialog.getText(None, "Copy Secret",
                                             f"Copy from: {source_mount}/{source_path}\n\n"
                                             "Enter destination path:")
        if ok and dest_path:
            # Ask for destination mount
            dest_mount, ok = QInputDialog.getText(None, "Destination Mount",
                                                  "Enter destination mount:",
                                                  text=source_mount)
            if ok and dest_mount:
                if self.vault.copy_secret(source_path, dest_path, source_mount, dest_mount):
                    QMessageBox.information(None, "Success", 
                                          f"Secret copied to {dest_mount}/{dest_path}")
                else:
                    QMessageBox.critical(None, "Error", "Failed to copy secret")
    
    def move_secret(self, source_path: str, source_mount: str = "secret"):
        """Move/rename a secret"""
        dest_path, ok = QInputDialog.getText(None, "Move/Rename Secret",
                                             f"Move from: {source_mount}/{source_path}\n\n"
                                             "Enter new path:")
        if ok and dest_path:
            # Ask for destination mount
            dest_mount, ok = QInputDialog.getText(None, "Destination Mount",
                                                  "Enter destination mount:",
                                                  text=source_mount)
            if ok and dest_mount:
                reply = QMessageBox.question(None, "Confirm Move",
                                           f"Move secret from {source_mount}/{source_path}\n"
                                           f"to {dest_mount}/{dest_path}?\n\n"
                                           "This will delete the original.",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    if self.vault.move_secret(source_path, dest_path, source_mount, dest_mount):
                        QMessageBox.information(None, "Success", 
                                              f"Secret moved to {dest_mount}/{dest_path}")
                    else:
                        QMessageBox.critical(None, "Error", "Failed to move secret")
    
    def delete_secret_confirm(self, path: str, mount: str = "secret"):
        """Delete a secret with confirmation"""
        reply = QMessageBox.question(None, "Confirm Delete",
                                    f"Are you sure you want to delete:\n{mount}/{path}?\n\n"
                                    "For KV v2, this soft-deletes the latest version.\n"
                                    "You can undelete it later.",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self.vault.delete_secret(path, mount):
                QMessageBox.information(None, "Success", "Secret deleted successfully!")
            else:
                QMessageBox.critical(None, "Error", "Failed to delete secret")
    
    def destroy_secret_confirm(self, path: str, mount: str = "secret"):
        """Permanently destroy secret versions"""
        from PyQt6.QtWidgets import QSpinBox
        
        dialog = QDialog()
        dialog.setWindowTitle("Destroy Secret Versions")
        layout = QVBoxLayout()
        
        label = QLabel(f"Permanently destroy versions of:\n{mount}/{path}\n\n"
                      "This action CANNOT be undone!")
        label.setWordWrap(True)
        layout.addWidget(label)
        
        version_layout = QHBoxLayout()
        version_layout.addWidget(QLabel("Version to destroy:"))
        version_spin = QSpinBox()
        version_spin.setMinimum(1)
        version_spin.setMaximum(1000)
        version_layout.addWidget(version_spin)
        layout.addLayout(version_layout)
        
        button_layout = QHBoxLayout()
        destroy_btn = QPushButton("Destroy")
        destroy_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(destroy_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            version = version_spin.value()
            reply = QMessageBox.warning(None, "Final Confirmation",
                                       f"PERMANENTLY destroy version {version}?\n\n"
                                       "This CANNOT be undone!",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                if self.vault.destroy_secret(path, [version], mount):
                    QMessageBox.information(None, "Success", f"Version {version} destroyed")
                else:
                    QMessageBox.critical(None, "Error", "Failed to destroy version")
    
    def show_versions(self, path: str, mount: str = "secret"):
        """Show all versions of a secret"""
        versions = self.vault.list_secret_versions(path, mount)
        
        if versions:
            dialog = QDialog()
            dialog.setWindowTitle(f"Versions: {mount}/{path}")
            dialog.setMinimumSize(500, 400)
            layout = QVBoxLayout()
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll_widget = QWidget()
            scroll_layout = QVBoxLayout(scroll_widget)
            
            # Sort versions by number (descending)
            sorted_versions = sorted(versions.items(), key=lambda x: int(x[0]), reverse=True)
            
            for version_num, version_data in sorted_versions:
                version_frame = QWidget()
                version_layout = QVBoxLayout(version_frame)
                version_frame.setStyleSheet("QWidget { border: 1px solid #ccc; border-radius: 4px; padding: 8px; margin: 4px; }")
                
                # Version info
                info_text = f"Version {version_num}"
                if version_data.get('deleted_time'):
                    info_text += " [DELETED]"
                if version_data.get('destroyed'):
                    info_text += " [DESTROYED]"
                
                info_label = QLabel(info_text)
                info_label.setStyleSheet("font-weight: bold;")
                version_layout.addWidget(info_label)
                
                created_time = version_data.get('created_time', 'Unknown')
                version_layout.addWidget(QLabel(f"Created: {created_time}"))
                
                if version_data.get('deleted_time'):
                    version_layout.addWidget(QLabel(f"Deleted: {version_data.get('deleted_time')}"))
                
                # Action buttons
                btn_layout = QHBoxLayout()
                
                if not version_data.get('destroyed'):
                    read_btn = QPushButton("Read")
                    read_btn.clicked.connect(
                        lambda checked=False, v=int(version_num): self.read_version(path, v, mount)
                    )
                    btn_layout.addWidget(read_btn)
                    
                    if version_data.get('deleted_time'):
                        undelete_btn = QPushButton("Undelete")
                        undelete_btn.clicked.connect(
                            lambda checked=False, v=int(version_num): self.undelete_version(path, v, mount)
                        )
                        btn_layout.addWidget(undelete_btn)
                
                version_layout.addLayout(btn_layout)
                scroll_layout.addWidget(version_frame)
            
            scroll_layout.addStretch()
            scroll.setWidget(scroll_widget)
            layout.addWidget(scroll)
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.exec()
        else:
            QMessageBox.information(None, "No Versions", "No version information available (KV v1?)")
    
    def read_version(self, path: str, version: int, mount: str = "secret"):
        """Read a specific version of a secret"""
        data = self.vault.read_secret_version(path, version, mount)
        
        if data is not None:
            dialog = SecretDialog(None, f"{mount}/{path} (v{version})", data, read_only=True)
            dialog.exec()
        else:
            QMessageBox.critical(None, "Error", f"Failed to read version {version}")
    
    def undelete_version(self, path: str, version: int, mount: str = "secret"):
        """Undelete a secret version"""
        reply = QMessageBox.question(None, "Confirm Undelete",
                                    f"Undelete version {version} of:\n{mount}/{path}?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self.vault.undelete_secret(path, [version], mount):
                QMessageBox.information(None, "Success", f"Version {version} undeleted!")
            else:
                QMessageBox.critical(None, "Error", "Failed to undelete version")
    
    def show_metadata(self, path: str, mount: str = "secret"):
        """Show secret metadata"""
        metadata = self.vault.get_secret_metadata(path, mount)
        
        if metadata:
            info_text = f"Secret Metadata: {mount}/{path}\n\n"
            info_text += f"Created: {metadata.get('created_time', 'Unknown')}\n"
            info_text += f"Updated: {metadata.get('updated_time', 'Unknown')}\n"
            info_text += f"Current Version: {metadata.get('current_version', 'Unknown')}\n"
            info_text += f"Oldest Version: {metadata.get('oldest_version', 'Unknown')}\n"
            info_text += f"Max Versions: {metadata.get('max_versions', 'Unlimited')}\n"
            info_text += f"CAS Required: {metadata.get('cas_required', False)}\n"
            info_text += f"Delete Version After: {metadata.get('delete_version_after', 'None')}\n"
            
            versions = metadata.get('versions', {})
            info_text += f"\nTotal Versions: {len(versions)}"
            
            QMessageBox.information(None, "Metadata", info_text)
        else:
            QMessageBox.information(None, "No Metadata", "No metadata available (KV v1?)")
    
    def show_folder_contents(self, mount: str, path: str):
        """Show a list of all contents in a folder"""
        secrets = self.vault.list_secrets(path, mount)
        
        if secrets:
            folders = [s for s in secrets if s.endswith('/')]
            files = [s for s in secrets if not s.endswith('/')]
            
            content_text = f"Contents of: {mount}/{path}\n\n"
            
            if folders:
                content_text += f"Folders ({len(folders)}):\n"
                for folder in sorted(folders):
                    content_text += f"  📁 {folder}\n"
                content_text += "\n"
            
            if files:
                content_text += f"Secrets ({len(files)}):\n"
                for file in sorted(files):
                    content_text += f"  📄 {file}\n"
            
            QMessageBox.information(None, "Folder Contents", content_text)
        else:
            QMessageBox.information(None, "Empty", "This folder is empty or doesn't exist.")
    
    def on_quick_read(self):
        if not self.vault.is_authenticated():
            QMessageBox.critical(None, "Error", "Not authenticated. Please set a valid VAULT_TOKEN.")
            return
        
        path, ok = QInputDialog.getText(None, "Quick Read", 
                                        "Enter secret path (e.g., myapp/config):")
        if ok and path:
            self.read_secret(path)
    
    def on_quick_write(self):
        if not self.vault.is_authenticated():
            QMessageBox.critical(None, "Error", "Not authenticated. Please set a valid VAULT_TOKEN.")
            return
        
        path, ok = QInputDialog.getText(None, "Quick Write", 
                                        "Enter secret path (e.g., myapp/config):")
        if ok and path:
            def save_callback(data):
                if self.vault.write_secret(path, data):
                    QMessageBox.information(None, "Success", "Secret saved successfully!")
                else:
                    QMessageBox.critical(None, "Error", "Failed to save secret")
            
            dialog = SecretDialog(None, path, callback=save_callback)
            dialog.exec()
    
    def on_set_token(self):
        current_token = self.vault.token[:20] + "..." if self.vault.token else "No token set"
        token, ok = QInputDialog.getText(None, "Set Vault Token", 
                                         f"Current: {current_token}\n\nEnter new token:",
                                         QLineEdit.EchoMode.Password)
        if ok and token:
            self.vault.token = token
            os.environ['VAULT_TOKEN'] = token
            
            if self.vault.is_authenticated():
                QMessageBox.information(None, "Success", "Token validated successfully!")
                self.build_menu()
            else:
                QMessageBox.warning(None, "Warning", "Token set, but authentication failed.")
    
    def on_connection_info(self):
        info = f"""Vault Connection Information:

Address: {self.vault.addr}
Token: {'Set' if self.vault.token else 'Not set'}
Namespace: {self.vault.namespace if self.vault.namespace else 'None'}
Skip Verify: {self.vault.skip_verify}
Authenticated: {self.vault.is_authenticated()}

Environment Variables:
VAULT_ADDR={os.environ.get('VAULT_ADDR', 'not set')}
VAULT_TOKEN={'***' if os.environ.get('VAULT_TOKEN') else 'not set'}
VAULT_NAMESPACE={os.environ.get('VAULT_NAMESPACE', 'not set')}
VAULT_SKIP_VERIFY={os.environ.get('VAULT_SKIP_VERIFY', 'not set')}
"""
        QMessageBox.information(None, "Connection Info", info)
    
    def show_coming_soon(self, product: str):
        QMessageBox.information(None, "Coming Soon", f"{product} integration coming soon!")
    
    def refresh_mounts(self):
        """Refresh the list of mounts"""
        mounts = self.vault.list_mounts()
        self.mounts = [m.rstrip('/') for m in mounts.keys()]
        if not self.mounts:
            self.mounts = ["secret"]
    
    def refresh_mounts_and_rebuild(self):
        """Refresh mounts and rebuild menu"""
        self.refresh_mounts()
        self.build_menu()
        QMessageBox.information(None, "Refreshed", f"Found {len(self.mounts)} mount(s)")


def main():
    app = VaultTrayApp(sys.argv)
    
    # Show initial notification
    if app.tray_icon.isVisible():
        app.tray_icon.showMessage(
            "Vault Manager",
            "HashiCorp Vault Manager is running in system tray",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
    