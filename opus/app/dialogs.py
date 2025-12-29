"""Dialog windows for OpenTongchi"""

import json
from typing import Dict, Any, Optional, List, Callable
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QSpinBox, QCheckBox, QPushButton,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QComboBox, QGroupBox, QScrollArea, QSplitter,
    QTreeWidget, QTreeWidgetItem, QDialogButtonBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class KeyValueTableWidget(QWidget):
    """Widget for editing key-value pairs in a table format"""
    
    data_changed = pyqtSignal()
    
    def __init__(self, data: Optional[Dict] = None, readonly: bool = False, parent=None):
        super().__init__(parent)
        self.readonly = readonly
        self.setup_ui()
        if data:
            self.set_data(data)
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Key", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultSectionSize(150)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        if not self.readonly:
            # Buttons
            btn_layout = QHBoxLayout()
            
            self.add_btn = QPushButton("➕ Add Row")
            self.add_btn.clicked.connect(self.add_row)
            btn_layout.addWidget(self.add_btn)
            
            self.remove_btn = QPushButton("➖ Remove Row")
            self.remove_btn.clicked.connect(self.remove_selected_row)
            btn_layout.addWidget(self.remove_btn)
            
            btn_layout.addStretch()
            layout.addLayout(btn_layout)
    
    def add_row(self, key: str = "", value: str = ""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        key_item = QTableWidgetItem(str(key))
        value_item = QTableWidgetItem(str(value))
        
        if self.readonly:
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        
        self.table.setItem(row, 0, key_item)
        self.table.setItem(row, 1, value_item)
        
        self.data_changed.emit()
    
    def remove_selected_row(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
            self.data_changed.emit()
    
    def set_data(self, data: Dict):
        """Set table data from dictionary"""
        self.table.setRowCount(0)
        
        def add_items(d: Dict, prefix: str = ""):
            for key, value in d.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    add_items(value, full_key)
                elif isinstance(value, list):
                    self.add_row(full_key, json.dumps(value))
                else:
                    self.add_row(full_key, str(value) if value is not None else "")
        
        add_items(data)
    
    def get_data(self) -> Dict:
        """Get dictionary from table data"""
        result = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            
            if key_item and value_item:
                key = key_item.text()
                value = value_item.text()
                
                # Try to parse as JSON if it looks like JSON
                if value.startswith(('[', '{')):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                elif value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                elif value.isdigit():
                    value = int(value)
                
                # Handle nested keys
                parts = key.split('.')
                current = result
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value
        
        return result


class JsonTableDialog(QDialog):
    """Dialog for editing JSON data as a table"""
    
    def __init__(self, title: str, data: Dict, readonly: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        self.data = data
        self.readonly = readonly
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title label
        title_label = QLabel(self.windowTitle())
        title_label.setFont(QFont("", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)
        
        # Table widget
        self.table_widget = KeyValueTableWidget(self.data, self.readonly)
        layout.addWidget(self.table_widget)
        
        # Buttons
        button_box = QDialogButtonBox()
        if not self.readonly:
            button_box.addButton(QDialogButtonBox.StandardButton.Save)
            button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
        else:
            button_box.addButton(QDialogButtonBox.StandardButton.Close)
            button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_data(self) -> Dict:
        return self.table_widget.get_data()


class CrudDialog(QDialog):
    """Generic CRUD dialog for resources"""
    
    saved = pyqtSignal(dict)
    deleted = pyqtSignal()
    
    def __init__(self, title: str, data: Optional[Dict] = None, 
                 schema: Optional[Dict] = None, is_new: bool = True,
                 can_delete: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 400)
        self.data = data or {}
        self.schema = schema
        self.is_new = is_new
        self.can_delete = can_delete
        self.field_widgets = {}
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Create scroll area for form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        form_layout = QFormLayout(scroll_widget)
        
        # Build form from schema or data
        if self.schema:
            self.build_from_schema(form_layout)
        else:
            self.build_from_data(form_layout)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        if self.can_delete and not self.is_new:
            delete_btn = QPushButton("🗑️ Delete")
            delete_btn.setStyleSheet("color: red;")
            delete_btn.clicked.connect(self.confirm_delete)
            btn_layout.addWidget(delete_btn)
        
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("💾 Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def build_from_schema(self, layout: QFormLayout):
        """Build form fields from JSON schema"""
        properties = self.schema.get("properties", {})
        required = self.schema.get("required", [])
        
        for name, prop in properties.items():
            label = name
            if name in required:
                label += " *"
            
            widget = self.create_widget_for_property(name, prop)
            self.field_widgets[name] = widget
            layout.addRow(label, widget)
    
    def build_from_data(self, layout: QFormLayout):
        """Build form fields from existing data"""
        for key, value in self.data.items():
            widget = self.create_widget_for_value(key, value)
            self.field_widgets[key] = widget
            layout.addRow(key, widget)
        
        # Add empty row for new fields
        if self.is_new or not self.data:
            self.add_new_field_row(layout)
    
    def create_widget_for_property(self, name: str, prop: Dict) -> QWidget:
        """Create appropriate widget based on schema property"""
        prop_type = prop.get("type", "string")
        value = self.data.get(name, prop.get("default", ""))
        
        if prop_type == "boolean":
            widget = QCheckBox()
            widget.setChecked(bool(value))
        elif prop_type == "integer":
            widget = QSpinBox()
            widget.setRange(-2147483648, 2147483647)
            widget.setValue(int(value) if value else 0)
        elif prop_type == "array":
            widget = QTextEdit()
            widget.setMaximumHeight(100)
            if isinstance(value, list):
                widget.setText(json.dumps(value, indent=2))
            else:
                widget.setText("[]")
        elif prop_type == "object":
            widget = QTextEdit()
            widget.setMaximumHeight(100)
            if isinstance(value, dict):
                widget.setText(json.dumps(value, indent=2))
            else:
                widget.setText("{}")
        elif "enum" in prop:
            widget = QComboBox()
            widget.addItems([str(e) for e in prop["enum"]])
            if value:
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
        else:
            widget = QLineEdit()
            widget.setText(str(value) if value is not None else "")
            if prop.get("format") == "password":
                widget.setEchoMode(QLineEdit.EchoMode.Password)
        
        return widget
    
    def create_widget_for_value(self, key: str, value: Any) -> QWidget:
        """Create widget based on value type"""
        if isinstance(value, bool):
            widget = QCheckBox()
            widget.setChecked(value)
        elif isinstance(value, int):
            widget = QSpinBox()
            widget.setRange(-2147483648, 2147483647)
            widget.setValue(value)
        elif isinstance(value, (list, dict)):
            widget = QTextEdit()
            widget.setMaximumHeight(100)
            widget.setText(json.dumps(value, indent=2))
        else:
            widget = QLineEdit()
            widget.setText(str(value) if value is not None else "")
        
        return widget
    
    def add_new_field_row(self, layout: QFormLayout):
        """Add row for creating new fields"""
        container = QWidget()
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(0, 0, 0, 0)
        
        key_edit = QLineEdit()
        key_edit.setPlaceholderText("New key...")
        h_layout.addWidget(key_edit)
        
        value_edit = QLineEdit()
        value_edit.setPlaceholderText("Value")
        h_layout.addWidget(value_edit)
        
        layout.addRow("➕ Add field:", container)
    
    def get_data(self) -> Dict:
        """Get form data as dictionary"""
        result = {}
        
        for name, widget in self.field_widgets.items():
            if isinstance(widget, QCheckBox):
                result[name] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                result[name] = widget.value()
            elif isinstance(widget, QComboBox):
                result[name] = widget.currentText()
            elif isinstance(widget, QTextEdit):
                text = widget.toPlainText()
                try:
                    result[name] = json.loads(text)
                except json.JSONDecodeError:
                    result[name] = text
            elif isinstance(widget, QLineEdit):
                result[name] = widget.text()
        
        return result
    
    def save(self):
        self.saved.emit(self.get_data())
        self.accept()
    
    def confirm_delete(self):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "Are you sure you want to delete this item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit()
            self.accept()


class SettingsDialog(QDialog):
    """Settings dialog for OpenTongchi"""
    
    settings_changed = pyqtSignal()
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("⚙️ OpenTongchi Settings")
        self.setMinimumSize(600, 500)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Tab widget
        tabs = QTabWidget()
        
        # Global settings tab
        tabs.addTab(self.create_global_tab(), "🌐 Global")
        
        # OpenBao tab
        tabs.addTab(self.create_openbao_tab(), "🔐 OpenBao")
        
        # Consul tab
        tabs.addTab(self.create_consul_tab(), "🔍 Consul")
        
        # Nomad tab
        tabs.addTab(self.create_nomad_tab(), "📦 Nomad")
        
        # OpenTofu tab
        tabs.addTab(self.create_opentofu_tab(), "🏗️ OpenTofu")
        
        # Background tasks tab
        tabs.addTab(self.create_background_tab(), "⏰ Background Tasks")
        
        layout.addWidget(tabs)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def create_global_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.global_namespace = QLineEdit(self.config.global_namespace)
        layout.addRow("🏷️ Global Namespace:", self.global_namespace)
        
        self.schema_cache_dir = QLineEdit(self.config.schema_cache_dir)
        browse_btn = QPushButton("📁")
        browse_btn.setMaximumWidth(40)
        browse_btn.clicked.connect(lambda: self.browse_directory(self.schema_cache_dir))
        
        cache_layout = QHBoxLayout()
        cache_layout.addWidget(self.schema_cache_dir)
        cache_layout.addWidget(browse_btn)
        
        layout.addRow("📂 Schema Cache Dir:", cache_layout)
        
        return widget
    
    def create_openbao_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.openbao_address = QLineEdit(self.config.openbao.address)
        layout.addRow("🌐 Address:", self.openbao_address)
        
        self.openbao_token = QLineEdit(self.config.openbao.token)
        self.openbao_token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔑 Token:", self.openbao_token)
        
        self.openbao_namespace = QLineEdit(self.config.openbao.namespace)
        layout.addRow("🏷️ Namespace:", self.openbao_namespace)
        
        self.openbao_skip_verify = QCheckBox()
        self.openbao_skip_verify.setChecked(self.config.openbao.skip_verify)
        layout.addRow("⚠️ Skip TLS Verify:", self.openbao_skip_verify)
        
        return widget
    
    def create_consul_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.consul_address = QLineEdit(self.config.consul.address)
        layout.addRow("🌐 Address:", self.consul_address)
        
        self.consul_token = QLineEdit(self.config.consul.token)
        self.consul_token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔑 Token:", self.consul_token)
        
        self.consul_namespace = QLineEdit(self.config.consul.namespace)
        layout.addRow("🏷️ Namespace:", self.consul_namespace)
        
        self.consul_datacenter = QLineEdit(self.config.consul.datacenter)
        layout.addRow("🏢 Datacenter:", self.consul_datacenter)
        
        self.consul_skip_verify = QCheckBox()
        self.consul_skip_verify.setChecked(self.config.consul.skip_verify)
        layout.addRow("⚠️ Skip TLS Verify:", self.consul_skip_verify)
        
        return widget
    
    def create_nomad_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.nomad_address = QLineEdit(self.config.nomad.address)
        layout.addRow("🌐 Address:", self.nomad_address)
        
        self.nomad_token = QLineEdit(self.config.nomad.token)
        self.nomad_token.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔑 Token:", self.nomad_token)
        
        self.nomad_namespace = QLineEdit(self.config.nomad.namespace)
        layout.addRow("🏷️ Namespace:", self.nomad_namespace)
        
        self.nomad_region = QLineEdit(self.config.nomad.region)
        layout.addRow("🌍 Region:", self.nomad_region)
        
        self.nomad_refresh_interval = QSpinBox()
        self.nomad_refresh_interval.setRange(1, 300)
        self.nomad_refresh_interval.setValue(self.config.nomad.refresh_interval)
        self.nomad_refresh_interval.setSuffix(" seconds")
        layout.addRow("🔄 Refresh Interval:", self.nomad_refresh_interval)
        
        self.nomad_alerts = QCheckBox()
        self.nomad_alerts.setChecked(self.config.nomad.alerts_enabled)
        layout.addRow("🔔 Enable Alerts:", self.nomad_alerts)
        
        self.nomad_skip_verify = QCheckBox()
        self.nomad_skip_verify.setChecked(self.config.nomad.skip_verify)
        layout.addRow("⚠️ Skip TLS Verify:", self.nomad_skip_verify)
        
        return widget
    
    def create_opentofu_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        
        self.opentofu_local_dir = QLineEdit(self.config.opentofu.local_directory)
        browse_btn = QPushButton("📁")
        browse_btn.setMaximumWidth(40)
        browse_btn.clicked.connect(lambda: self.browse_directory(self.opentofu_local_dir))
        
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.opentofu_local_dir)
        dir_layout.addWidget(browse_btn)
        
        layout.addRow("📂 Local Directory:", dir_layout)
        
        # HCP Terraform settings
        group = QGroupBox("☁️ HCP Terraform (Cloud)")
        group_layout = QFormLayout(group)
        
        self.hcp_token = QLineEdit(self.config.opentofu.hcp_token)
        self.hcp_token.setEchoMode(QLineEdit.EchoMode.Password)
        group_layout.addRow("🔑 Token:", self.hcp_token)
        
        self.hcp_org = QLineEdit(self.config.opentofu.hcp_organization)
        group_layout.addRow("🏢 Organization:", self.hcp_org)
        
        layout.addRow(group)
        
        return widget
    
    def create_background_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Token renewal
        group1 = QGroupBox("🔑 Token Renewal")
        group1_layout = QFormLayout(group1)
        
        self.token_renewal_enabled = QCheckBox()
        self.token_renewal_enabled.setChecked(self.config.openbao.token_renewal_enabled)
        group1_layout.addRow("Enable:", self.token_renewal_enabled)
        
        self.token_renewal_interval = QSpinBox()
        self.token_renewal_interval.setRange(60, 3600)
        self.token_renewal_interval.setValue(self.config.openbao.token_renewal_interval)
        self.token_renewal_interval.setSuffix(" seconds")
        group1_layout.addRow("Interval:", self.token_renewal_interval)
        
        layout.addRow(group1)
        
        # Lease renewal
        group2 = QGroupBox("📄 Lease Renewal")
        group2_layout = QFormLayout(group2)
        
        self.lease_renewal_enabled = QCheckBox()
        self.lease_renewal_enabled.setChecked(self.config.openbao.lease_renewal_enabled)
        group2_layout.addRow("Enable:", self.lease_renewal_enabled)
        
        self.lease_renewal_interval = QSpinBox()
        self.lease_renewal_interval.setRange(10, 600)
        self.lease_renewal_interval.setValue(self.config.openbao.lease_renewal_interval)
        self.lease_renewal_interval.setSuffix(" seconds")
        group2_layout.addRow("Interval:", self.lease_renewal_interval)
        
        layout.addRow(group2)
        
        return widget
    
    def browse_directory(self, line_edit: QLineEdit):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory", line_edit.text()
        )
        if directory:
            line_edit.setText(directory)
    
    def save_settings(self):
        # Global
        self.config.set_global_namespace(self.global_namespace.text())
        self.config.schema_cache_dir = self.schema_cache_dir.text()
        
        # OpenBao
        self.config.openbao.address = self.openbao_address.text()
        self.config.openbao.token = self.openbao_token.text()
        self.config.openbao.namespace = self.openbao_namespace.text()
        self.config.openbao.skip_verify = self.openbao_skip_verify.isChecked()
        self.config.openbao.token_renewal_enabled = self.token_renewal_enabled.isChecked()
        self.config.openbao.token_renewal_interval = self.token_renewal_interval.value()
        self.config.openbao.lease_renewal_enabled = self.lease_renewal_enabled.isChecked()
        self.config.openbao.lease_renewal_interval = self.lease_renewal_interval.value()
        
        # Consul
        self.config.consul.address = self.consul_address.text()
        self.config.consul.token = self.consul_token.text()
        self.config.consul.namespace = self.consul_namespace.text()
        self.config.consul.datacenter = self.consul_datacenter.text()
        self.config.consul.skip_verify = self.consul_skip_verify.isChecked()
        
        # Nomad
        self.config.nomad.address = self.nomad_address.text()
        self.config.nomad.token = self.nomad_token.text()
        self.config.nomad.namespace = self.nomad_namespace.text()
        self.config.nomad.region = self.nomad_region.text()
        self.config.nomad.refresh_interval = self.nomad_refresh_interval.value()
        self.config.nomad.alerts_enabled = self.nomad_alerts.isChecked()
        self.config.nomad.skip_verify = self.nomad_skip_verify.isChecked()
        
        # OpenTofu
        self.config.opentofu.local_directory = self.opentofu_local_dir.text()
        self.config.opentofu.hcp_token = self.hcp_token.text()
        self.config.opentofu.hcp_organization = self.hcp_org.text()
        
        # Save to file
        self.config.save()
        
        self.settings_changed.emit()
        self.accept()


class NewSecretDialog(QDialog):
    """Dialog for creating a new secret"""
    
    def __init__(self, path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔐 New Secret")
        self.setMinimumSize(500, 400)
        self.path = path
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        self.path_edit = QLineEdit(self.path)
        self.path_edit.setPlaceholderText("secret/path/to/secret")
        form.addRow("📁 Path:", self.path_edit)
        
        layout.addLayout(form)
        
        # Key-value table
        label = QLabel("📝 Secret Data:")
        layout.addWidget(label)
        
        self.kv_table = KeyValueTableWidget()
        self.kv_table.add_row("key", "value")
        layout.addWidget(self.kv_table)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_path(self) -> str:
        return self.path_edit.text()
    
    def get_data(self) -> Dict:
        return self.kv_table.get_data()


class ViewSecretDialog(QDialog):
    """Dialog for viewing/editing a secret"""
    
    secret_updated = pyqtSignal(str, dict)
    secret_deleted = pyqtSignal(str)
    
    def __init__(self, path: str, data: Dict, readonly: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"🔐 {path}")
        self.setMinimumSize(500, 400)
        self.path = path
        self.readonly = readonly
        self.setup_ui(data)
    
    def setup_ui(self, data: Dict):
        layout = QVBoxLayout(self)
        
        # Path label
        path_label = QLabel(f"📁 Path: {self.path}")
        path_label.setFont(QFont("", 10, QFont.Weight.Bold))
        layout.addWidget(path_label)
        
        # Key-value table
        self.kv_table = KeyValueTableWidget(data, self.readonly)
        layout.addWidget(self.kv_table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        if not self.readonly:
            delete_btn = QPushButton("🗑️ Delete")
            delete_btn.setStyleSheet("color: red;")
            delete_btn.clicked.connect(self.delete_secret)
            btn_layout.addWidget(delete_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)
        
        if not self.readonly:
            save_btn = QPushButton("💾 Save")
            save_btn.clicked.connect(self.save_secret)
            btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def save_secret(self):
        data = self.kv_table.get_data()
        self.secret_updated.emit(self.path, data)
        self.accept()
    
    def delete_secret(self):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete '{self.path}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.secret_deleted.emit(self.path)
            self.accept()


class JobDialog(QDialog):
    """Dialog for viewing/editing Nomad jobs"""
    
    job_submitted = pyqtSignal(dict)
    job_stopped = pyqtSignal(str)
    
    def __init__(self, job_id: str = "", job_data: Optional[Dict] = None, 
                 is_new: bool = True, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.is_new = is_new
        self.setWindowTitle("📦 New Job" if is_new else f"📦 {job_id}")
        self.setMinimumSize(700, 500)
        self.setup_ui(job_data)
    
    def setup_ui(self, job_data: Optional[Dict]):
        layout = QVBoxLayout(self)
        
        # Tabs for different views
        tabs = QTabWidget()
        
        # Overview tab
        if job_data:
            overview = self.create_overview_tab(job_data)
            tabs.addTab(overview, "📊 Overview")
        
        # JSON editor tab
        json_tab = QWidget()
        json_layout = QVBoxLayout(json_tab)
        
        self.json_edit = QTextEdit()
        self.json_edit.setFont(QFont("Monospace", 10))
        if job_data:
            self.json_edit.setText(json.dumps(job_data, indent=2))
        else:
            # Default job template
            template = {
                "ID": "",
                "Name": "",
                "Type": "service",
                "Datacenters": ["dc1"],
                "TaskGroups": [{
                    "Name": "app",
                    "Count": 1,
                    "Tasks": [{
                        "Name": "server",
                        "Driver": "docker",
                        "Config": {
                            "image": "nginx:latest"
                        }
                    }]
                }]
            }
            self.json_edit.setText(json.dumps(template, indent=2))
        
        json_layout.addWidget(self.json_edit)
        tabs.addTab(json_tab, "📝 JSON")
        
        layout.addWidget(tabs)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        if not self.is_new:
            stop_btn = QPushButton("⏹️ Stop Job")
            stop_btn.setStyleSheet("color: red;")
            stop_btn.clicked.connect(self.stop_job)
            btn_layout.addWidget(stop_btn)
        
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        submit_btn = QPushButton("🚀 Submit" if self.is_new else "🔄 Update")
        submit_btn.clicked.connect(self.submit_job)
        btn_layout.addWidget(submit_btn)
        
        layout.addLayout(btn_layout)
    
    def create_overview_tab(self, job_data: Dict) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        
        layout.addRow("ID:", QLabel(job_data.get("ID", "")))
        layout.addRow("Name:", QLabel(job_data.get("Name", "")))
        layout.addRow("Type:", QLabel(job_data.get("Type", "")))
        layout.addRow("Status:", QLabel(job_data.get("Status", "")))
        layout.addRow("Priority:", QLabel(str(job_data.get("Priority", 50))))
        
        datacenters = job_data.get("Datacenters", [])
        layout.addRow("Datacenters:", QLabel(", ".join(datacenters)))
        
        return widget
    
    def submit_job(self):
        try:
            job_spec = json.loads(self.json_edit.toPlainText())
            self.job_submitted.emit(job_spec)
            self.accept()
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", f"JSON parse error: {e}")
    
    def stop_job(self):
        reply = QMessageBox.question(
            self, "Confirm Stop",
            f"Are you sure you want to stop job '{self.job_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.job_stopped.emit(self.job_id)
            self.accept()
