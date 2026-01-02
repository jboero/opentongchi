"""
CRUD Dialogs for OpenTongchi
Provides table-based editing dialogs for key-value data and JSON documents.
"""

import json
from typing import Dict, Any, Optional, List, Callable
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QMessageBox, QHeaderView, QTabWidget, QWidget, QFormLayout,
    QSpinBox, QDoubleSpinBox, QGroupBox, QSplitter, QTreeWidget,
    QTreeWidgetItem, QDialogButtonBox, QInputDialog, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class KeyValueTableWidget(QTableWidget):
    """A table widget for editing key-value pairs."""
    
    data_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Key", "Value"])
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.setAlternatingRowColors(True)
        
        # Enable editing
        self.cellChanged.connect(self._on_cell_changed)
    
    def set_data(self, data: Dict[str, Any]):
        """Set the table data from a dictionary."""
        self.blockSignals(True)
        self.setRowCount(0)
        
        for key, value in data.items():
            row = self.rowCount()
            self.insertRow(row)
            
            key_item = QTableWidgetItem(str(key))
            self.setItem(row, 0, key_item)
            
            # Handle different value types
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, indent=2)
            else:
                value_str = str(value) if value is not None else ""
            
            value_item = QTableWidgetItem(value_str)
            self.setItem(row, 1, value_item)
        
        self.blockSignals(False)
    
    def get_data(self) -> Dict[str, Any]:
        """Get the table data as a dictionary."""
        data = {}
        for row in range(self.rowCount()):
            key_item = self.item(row, 0)
            value_item = self.item(row, 1)
            
            if key_item and key_item.text():
                key = key_item.text()
                value = value_item.text() if value_item else ""
                
                # Try to parse JSON values
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    pass
                
                data[key] = value
        
        return data
    
    def add_row(self, key: str = "", value: str = ""):
        """Add a new row to the table."""
        row = self.rowCount()
        self.insertRow(row)
        self.setItem(row, 0, QTableWidgetItem(key))
        self.setItem(row, 1, QTableWidgetItem(value))
        self.data_changed.emit()
    
    def remove_selected_row(self):
        """Remove the currently selected row."""
        current_row = self.currentRow()
        if current_row >= 0:
            self.removeRow(current_row)
            self.data_changed.emit()
    
    def _on_cell_changed(self, row: int, column: int):
        """Handle cell changes."""
        self.data_changed.emit()


class CrudDialog(QDialog):
    """Base CRUD dialog for viewing and editing data."""
    
    saved = Signal(dict)
    deleted = Signal()
    
    def __init__(self, title: str, data: Dict[str, Any] = None, 
                 readonly: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        self.data = data or {}
        self.readonly = readonly
        
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Table for key-value pairs
        self.table = KeyValueTableWidget()
        layout.addWidget(self.table)
        
        # Buttons for table manipulation
        if not self.readonly:
            btn_layout = QHBoxLayout()
            
            add_btn = QPushButton("➕ Add Field")
            add_btn.clicked.connect(self._add_field)
            btn_layout.addWidget(add_btn)
            
            remove_btn = QPushButton("➖ Remove Field")
            remove_btn.clicked.connect(self.table.remove_selected_row)
            btn_layout.addWidget(remove_btn)
            
            btn_layout.addStretch()
            layout.addLayout(btn_layout)
        
        # Dialog buttons
        button_box = QDialogButtonBox()
        
        if not self.readonly:
            save_btn = button_box.addButton("💾 Save", QDialogButtonBox.ButtonRole.AcceptRole)
            save_btn.clicked.connect(self._save)
            
            delete_btn = button_box.addButton("🗑️ Delete", QDialogButtonBox.ButtonRole.DestructiveRole)
            delete_btn.clicked.connect(self._delete)
        
        cancel_btn = button_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.clicked.connect(self.reject)
        
        layout.addWidget(button_box)
    
    def _load_data(self):
        """Load data into the table."""
        self.table.set_data(self.data)
    
    def _add_field(self):
        """Add a new field to the table."""
        key, ok = QInputDialog.getText(self, "Add Field", "Field name:")
        if ok and key:
            self.table.add_row(key, "")
    
    def _save(self):
        """Save the data."""
        self.data = self.table.get_data()
        self.saved.emit(self.data)
        self.accept()
    
    def _delete(self):
        """Delete the item."""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "Are you sure you want to delete this item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit()
            self.accept()


class JsonEditorDialog(QDialog):
    """Dialog for editing complex JSON documents with nested structure."""
    
    saved = Signal(object)
    
    def __init__(self, title: str, data: Any = None, 
                 schema: Dict = None, readonly: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        self.data = data
        self.schema = schema
        self.readonly = readonly
        
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Tab widget for different views
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Tree view tab
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Key", "Value", "Type"])
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        tree_layout.addWidget(self.tree)
        self.tabs.addTab(tree_widget, "🌳 Tree View")
        
        # Table view tab
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        self.table = KeyValueTableWidget()
        table_layout.addWidget(self.table)
        self.tabs.addTab(table_widget, "📊 Table View")
        
        # Raw JSON tab
        json_widget = QWidget()
        json_layout = QVBoxLayout(json_widget)
        self.json_edit = QTextEdit()
        self.json_edit.setFont(QFont("Monospace", 10))
        self.json_edit.setReadOnly(self.readonly)
        json_layout.addWidget(self.json_edit)
        self.tabs.addTab(json_widget, "📝 Raw JSON")
        
        # Buttons
        button_layout = QHBoxLayout()
        
        if not self.readonly:
            format_btn = QPushButton("🎨 Format JSON")
            format_btn.clicked.connect(self._format_json)
            button_layout.addWidget(format_btn)
        
        button_layout.addStretch()
        
        if not self.readonly:
            save_btn = QPushButton("💾 Save")
            save_btn.clicked.connect(self._save)
            button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _load_data(self):
        """Load data into all views."""
        # Load tree view
        self.tree.clear()
        self._populate_tree(self.tree.invisibleRootItem(), self.data)
        
        # Load table view (only for flat dicts)
        if isinstance(self.data, dict):
            flat_data = {}
            for k, v in self.data.items():
                if not isinstance(v, (dict, list)):
                    flat_data[k] = v
            self.table.set_data(flat_data)
        
        # Load JSON view
        try:
            json_str = json.dumps(self.data, indent=2, default=str)
            self.json_edit.setPlainText(json_str)
        except Exception as e:
            self.json_edit.setPlainText(f"Error serializing data: {e}")
    
    def _populate_tree(self, parent_item: QTreeWidgetItem, data: Any, key: str = ""):
        """Recursively populate tree widget."""
        if isinstance(data, dict):
            for k, v in data.items():
                item = QTreeWidgetItem(parent_item)
                item.setText(0, str(k))
                item.setData(0, Qt.ItemDataRole.UserRole, (k, v))
                
                if isinstance(v, dict):
                    item.setText(1, f"{{{len(v)} items}}")
                    item.setText(2, "object")
                    self._populate_tree(item, v, k)
                elif isinstance(v, list):
                    item.setText(1, f"[{len(v)} items]")
                    item.setText(2, "array")
                    self._populate_tree(item, v, k)
                else:
                    item.setText(1, str(v) if v is not None else "null")
                    item.setText(2, type(v).__name__)
        
        elif isinstance(data, list):
            for i, v in enumerate(data):
                item = QTreeWidgetItem(parent_item)
                item.setText(0, f"[{i}]")
                item.setData(0, Qt.ItemDataRole.UserRole, (i, v))
                
                if isinstance(v, dict):
                    item.setText(1, f"{{{len(v)} items}}")
                    item.setText(2, "object")
                    self._populate_tree(item, v, str(i))
                elif isinstance(v, list):
                    item.setText(1, f"[{len(v)} items]")
                    item.setText(2, "array")
                    self._populate_tree(item, v, str(i))
                else:
                    item.setText(1, str(v) if v is not None else "null")
                    item.setText(2, type(v).__name__)
    
    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on tree item for editing."""
        if self.readonly:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            key, value = data
            if not isinstance(value, (dict, list)):
                new_value, ok = QInputDialog.getText(
                    self, "Edit Value",
                    f"Value for '{key}':",
                    QLineEdit.EchoMode.Normal,
                    str(value) if value is not None else ""
                )
                if ok:
                    item.setText(1, new_value)
                    # Update underlying data - would need path tracking for full implementation
    
    def _format_json(self):
        """Format the JSON in the text editor."""
        try:
            data = json.loads(self.json_edit.toPlainText())
            formatted = json.dumps(data, indent=2, default=str)
            self.json_edit.setPlainText(formatted)
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", f"Cannot parse JSON: {e}")
    
    def _save(self):
        """Save the data from the current tab."""
        try:
            # Get data from JSON tab (most authoritative)
            self.data = json.loads(self.json_edit.toPlainText())
            self.saved.emit(self.data)
            self.accept()
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", f"Cannot parse JSON: {e}")


class SecretDialog(QDialog):
    """Dialog specifically for viewing/editing secrets."""
    
    saved = Signal(str, dict)  # path, data
    deleted = Signal(str)  # path
    
    def __init__(self, path: str, data: Dict[str, Any] = None,
                 readonly: bool = False, is_new: bool = False, parent=None):
        super().__init__(parent)
        self.path = path
        self.data = data or {}
        self.readonly = readonly
        self.is_new = is_new
        
        title = "🔐 New Secret" if is_new else f"🔐 Secret: {path}"
        self.setWindowTitle(title)
        self.setMinimumSize(500, 400)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Path input for new secrets
        if self.is_new:
            path_layout = QHBoxLayout()
            path_layout.addWidget(QLabel("Path:"))
            self.path_input = QLineEdit(self.path)
            path_layout.addWidget(self.path_input)
            layout.addLayout(path_layout)
        
        # Key-value table
        layout.addWidget(QLabel("Secret Data:"))
        self.table = KeyValueTableWidget()
        self.table.set_data(self.data)
        layout.addWidget(self.table)
        
        # Table buttons
        if not self.readonly:
            btn_layout = QHBoxLayout()
            
            add_btn = QPushButton("➕ Add Field")
            add_btn.clicked.connect(lambda: self.table.add_row())
            btn_layout.addWidget(add_btn)
            
            remove_btn = QPushButton("➖ Remove Field")
            remove_btn.clicked.connect(self.table.remove_selected_row)
            btn_layout.addWidget(remove_btn)
            
            btn_layout.addStretch()
            layout.addLayout(btn_layout)
        
        # Show/hide values toggle
        self.show_values = QCheckBox("👁️ Show values")
        self.show_values.setChecked(False)
        self.show_values.stateChanged.connect(self._toggle_values)
        layout.addWidget(self.show_values)
        
        # Initially hide values
        self._toggle_values(False)
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        
        if not self.readonly:
            save_btn = QPushButton("💾 Save")
            save_btn.clicked.connect(self._save)
            button_layout.addWidget(save_btn)
            
            if not self.is_new:
                delete_btn = QPushButton("🗑️ Delete")
                delete_btn.clicked.connect(self._delete)
                button_layout.addWidget(delete_btn)
        
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _toggle_values(self, show: bool):
        """Toggle visibility of secret values."""
        for row in range(self.table.rowCount()):
            value_item = self.table.item(row, 1)
            if value_item:
                if show or self.show_values.isChecked():
                    # Show actual value (stored in user data)
                    actual = value_item.data(Qt.ItemDataRole.UserRole)
                    if actual is not None:
                        value_item.setText(str(actual))
                else:
                    # Hide value
                    actual = value_item.text()
                    value_item.setData(Qt.ItemDataRole.UserRole, actual)
                    value_item.setText("••••••••")
    
    def _save(self):
        """Save the secret."""
        path = self.path_input.text() if self.is_new else self.path
        if not path:
            QMessageBox.warning(self, "Error", "Path is required")
            return
        
        data = self.table.get_data()
        if not data:
            QMessageBox.warning(self, "Error", "At least one key-value pair is required")
            return
        
        self.saved.emit(path, data)
        self.accept()
    
    def _delete(self):
        """Delete the secret."""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete the secret at '{self.path}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit(self.path)
            self.accept()


class SettingsDialog(QDialog):
    """Settings dialog for configuring OpenTongchi."""
    
    settings_saved = Signal()
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("⚙️ OpenTongchi Settings")
        self.setMinimumSize(700, 500)
        
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        """Set up the settings UI."""
        layout = QVBoxLayout(self)
        
        # Tab widget for different settings sections
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Global settings tab
        self._create_global_tab()
        
        # OpenBao tab
        self._create_openbao_tab()
        
        # OpenTofu tab
        self._create_opentofu_tab()
        
        # Consul tab
        self._create_consul_tab()
        
        # Nomad tab
        self._create_nomad_tab()
        
        # Boundary tab
        self._create_boundary_tab()
        
        # Packer tab
        self._create_packer_tab()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _create_global_tab(self):
        """Create the global settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.global_namespace = QLineEdit()
        layout.addRow("🌐 Global Namespace:", self.global_namespace)
        
        self.show_notifications = QCheckBox()
        layout.addRow("🔔 Show Notifications:", self.show_notifications)
        
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        layout.addRow("📋 Log Level:", self.log_level)
        
        self.cache_dir = QLineEdit()
        layout.addRow("📁 Cache Directory:", self.cache_dir)
        
        self.tabs.addTab(widget, "🌍 Global")
    
    def _create_openbao_tab(self):
        """Create the OpenBao settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.bao_address = QLineEdit()
        self.bao_address.setPlaceholderText("http://127.0.0.1:8200")
        layout.addRow("🔗 Address:", self.bao_address)
        
        self.bao_token = QLineEdit()
        self.bao_token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔑 Token:", self.bao_token)
        
        self.bao_namespace = QLineEdit()
        layout.addRow("📂 Namespace:", self.bao_namespace)
        
        self.bao_skip_verify = QCheckBox()
        layout.addRow("⚠️ Skip TLS Verify:", self.bao_skip_verify)
        
        self.bao_auto_renew = QCheckBox()
        layout.addRow("🔄 Auto-renew Token:", self.bao_auto_renew)
        
        self.bao_renew_interval = QSpinBox()
        self.bao_renew_interval.setRange(60, 3600)
        self.bao_renew_interval.setSuffix(" seconds")
        layout.addRow("⏱️ Renew Interval:", self.bao_renew_interval)
        
        self.tabs.addTab(widget, "🔐 OpenBao")
    
    def _create_opentofu_tab(self):
        """Create the OpenTofu settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.tofu_home = QLineEdit()
        self.tofu_home.setPlaceholderText("~/opentofu")
        layout.addRow("📁 Home Directory:", self.tofu_home)
        
        self.tofu_binary = QLineEdit()
        self.tofu_binary.setPlaceholderText("tofu or terraform")
        layout.addRow("⚙️ Binary Path:", self.tofu_binary)
        
        self.hcp_token = QLineEdit()
        self.hcp_token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔑 HCP Token:", self.hcp_token)
        
        self.hcp_org = QLineEdit()
        layout.addRow("🏢 HCP Organization:", self.hcp_org)
        
        self.tabs.addTab(widget, "🏗️ OpenTofu")
    
    def _create_consul_tab(self):
        """Create the Consul settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.consul_address = QLineEdit()
        self.consul_address.setPlaceholderText("http://127.0.0.1:8500")
        layout.addRow("🔗 Address:", self.consul_address)
        
        self.consul_token = QLineEdit()
        self.consul_token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔑 Token:", self.consul_token)
        
        self.consul_namespace = QLineEdit()
        layout.addRow("📂 Namespace:", self.consul_namespace)
        
        self.consul_datacenter = QLineEdit()
        layout.addRow("🌐 Datacenter:", self.consul_datacenter)
        
        self.tabs.addTab(widget, "🔍 Consul")
    
    def _create_nomad_tab(self):
        """Create the Nomad settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.nomad_address = QLineEdit()
        self.nomad_address.setPlaceholderText("http://127.0.0.1:4646")
        layout.addRow("🔗 Address:", self.nomad_address)
        
        self.nomad_token = QLineEdit()
        self.nomad_token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔑 Token:", self.nomad_token)
        
        self.nomad_namespace = QLineEdit()
        layout.addRow("📂 Namespace:", self.nomad_namespace)
        
        self.nomad_region = QLineEdit()
        layout.addRow("🌍 Region:", self.nomad_region)
        
        self.nomad_refresh = QSpinBox()
        self.nomad_refresh.setRange(5, 300)
        self.nomad_refresh.setSuffix(" seconds")
        layout.addRow("🔄 Refresh Interval:", self.nomad_refresh)
        
        self.tabs.addTab(widget, "📦 Nomad")
    
    def _create_boundary_tab(self):
        """Create the Boundary settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.boundary_address = QLineEdit()
        self.boundary_address.setPlaceholderText("http://127.0.0.1:9200")
        layout.addRow("🔗 Address:", self.boundary_address)
        
        self.boundary_token = QLineEdit()
        self.boundary_token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔑 Token:", self.boundary_token)
        
        self.boundary_auth_method = QLineEdit()
        layout.addRow("🔐 Auth Method ID:", self.boundary_auth_method)
        
        self.boundary_binary = QLineEdit()
        self.boundary_binary.setPlaceholderText("boundary")
        layout.addRow("⚙️ Binary Path:", self.boundary_binary)
        
        self.tabs.addTab(widget, "🚪 Boundary")
    
    def _create_packer_tab(self):
        """Create the Packer settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.packer_home = QLineEdit()
        self.packer_home.setPlaceholderText("~/packer")
        layout.addRow("📁 Home Directory:", self.packer_home)
        
        self.packer_binary = QLineEdit()
        self.packer_binary.setPlaceholderText("packer")
        layout.addRow("⚙️ Binary Path:", self.packer_binary)
        
        self.tabs.addTab(widget, "📦 Packer")
    
    def _load_settings(self):
        """Load current settings into the form."""
        # Global
        self.global_namespace.setText(self.settings.global_settings.namespace)
        self.show_notifications.setChecked(self.settings.global_settings.show_notifications)
        self.log_level.setCurrentText(self.settings.global_settings.log_level)
        self.cache_dir.setText(self.settings.global_settings.cache_dir)
        
        # OpenBao
        self.bao_address.setText(self.settings.openbao.address)
        self.bao_token.setText(self.settings.openbao.token)
        self.bao_namespace.setText(self.settings.openbao.namespace)
        self.bao_skip_verify.setChecked(self.settings.openbao.skip_verify)
        self.bao_auto_renew.setChecked(self.settings.openbao.auto_renew_token)
        self.bao_renew_interval.setValue(self.settings.openbao.renew_interval_seconds)
        
        # OpenTofu
        self.tofu_home.setText(self.settings.opentofu.home_dir)
        self.tofu_binary.setText(self.settings.opentofu.binary_path)
        self.hcp_token.setText(self.settings.opentofu.hcp_token)
        self.hcp_org.setText(self.settings.opentofu.hcp_org)
        
        # Consul
        self.consul_address.setText(self.settings.consul.address)
        self.consul_token.setText(self.settings.consul.token)
        self.consul_namespace.setText(self.settings.consul.namespace)
        self.consul_datacenter.setText(self.settings.consul.datacenter)
        
        # Nomad
        self.nomad_address.setText(self.settings.nomad.address)
        self.nomad_token.setText(self.settings.nomad.token)
        self.nomad_namespace.setText(self.settings.nomad.namespace)
        self.nomad_region.setText(self.settings.nomad.region)
        self.nomad_refresh.setValue(self.settings.nomad.refresh_interval_seconds)
        
        # Boundary
        self.boundary_address.setText(self.settings.boundary.address)
        self.boundary_token.setText(self.settings.boundary.token)
        self.boundary_auth_method.setText(self.settings.boundary.auth_method_id)
        self.boundary_binary.setText(self.settings.boundary.binary_path)
        
        # Packer
        self.packer_home.setText(self.settings.packer.home_dir)
        self.packer_binary.setText(self.settings.packer.binary_path)
    
    def _save_settings(self):
        """Save settings from the form."""
        # Global
        self.settings.global_settings.namespace = self.global_namespace.text()
        self.settings.global_settings.show_notifications = self.show_notifications.isChecked()
        self.settings.global_settings.log_level = self.log_level.currentText()
        self.settings.global_settings.cache_dir = self.cache_dir.text()
        
        # OpenBao
        self.settings.openbao.address = self.bao_address.text()
        self.settings.openbao.token = self.bao_token.text()
        self.settings.openbao.namespace = self.bao_namespace.text()
        self.settings.openbao.skip_verify = self.bao_skip_verify.isChecked()
        self.settings.openbao.auto_renew_token = self.bao_auto_renew.isChecked()
        self.settings.openbao.renew_interval_seconds = self.bao_renew_interval.value()
        
        # OpenTofu
        self.settings.opentofu.home_dir = self.tofu_home.text()
        self.settings.opentofu.binary_path = self.tofu_binary.text()
        self.settings.opentofu.hcp_token = self.hcp_token.text()
        self.settings.opentofu.hcp_org = self.hcp_org.text()
        
        # Consul
        self.settings.consul.address = self.consul_address.text()
        self.settings.consul.token = self.consul_token.text()
        self.settings.consul.namespace = self.consul_namespace.text()
        self.settings.consul.datacenter = self.consul_datacenter.text()
        
        # Nomad
        self.settings.nomad.address = self.nomad_address.text()
        self.settings.nomad.token = self.nomad_token.text()
        self.settings.nomad.namespace = self.nomad_namespace.text()
        self.settings.nomad.region = self.nomad_region.text()
        self.settings.nomad.refresh_interval_seconds = self.nomad_refresh.value()
        
        # Boundary
        self.settings.boundary.address = self.boundary_address.text()
        self.settings.boundary.token = self.boundary_token.text()
        self.settings.boundary.auth_method_id = self.boundary_auth_method.text()
        self.settings.boundary.binary_path = self.boundary_binary.text()
        
        # Packer
        self.settings.packer.home_dir = self.packer_home.text()
        self.settings.packer.binary_path = self.packer_binary.text()
        
        # Persist
        self.settings.save()
        self.settings_saved.emit()
        self.accept()
