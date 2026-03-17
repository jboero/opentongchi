"""
CRUD Dialogs for OpenTongchi
Provides table-based editing dialogs for key-value data and JSON documents.
"""

import json
import re
from typing import Dict, Any, Optional, List, Callable, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QMessageBox, QHeaderView, QTabWidget, QWidget, QFormLayout,
    QSpinBox, QDoubleSpinBox, QGroupBox, QSplitter, QTreeWidget,
    QTreeWidgetItem, QDialogButtonBox, QInputDialog, QScrollArea,
    QPlainTextEdit
)
from PySide6.QtCore import Qt, Signal, QRegularExpression
from PySide6.QtGui import (
    QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QTextDocument,
    QPalette, QFontMetricsF
)


# ==================== Syntax Highlighters ====================

class HCLSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for HashiCorp Configuration Language (HCL)."""
    
    def __init__(self, document: QTextDocument, dark_mode: bool = False):
        super().__init__(document)
        self.dark_mode = dark_mode
        self._setup_formats()
        self._setup_rules()
    
    def _setup_formats(self):
        """Setup text formats for different token types."""
        # Color schemes for light and dark modes
        if self.dark_mode:
            colors = {
                'keyword': '#569CD6',      # Blue
                'block_type': '#4EC9B0',   # Teal
                'string': '#CE9178',       # Orange
                'number': '#B5CEA8',       # Light green
                'comment': '#6A9955',      # Green
                'boolean': '#569CD6',      # Blue
                'attribute': '#9CDCFE',    # Light blue
                'function': '#DCDCAA',     # Yellow
                'variable': '#4FC1FF',     # Cyan
                'operator': '#D4D4D4',     # Light gray
                'bracket': '#FFD700',      # Gold
            }
        else:
            colors = {
                'keyword': '#0000FF',      # Blue
                'block_type': '#008080',   # Teal
                'string': '#A31515',       # Dark red
                'number': '#098658',       # Green
                'comment': '#008000',      # Green
                'boolean': '#0000FF',      # Blue
                'attribute': '#001080',    # Dark blue
                'function': '#795E26',     # Brown
                'variable': '#0070C1',     # Blue
                'operator': '#000000',     # Black
                'bracket': '#AF00DB',      # Purple
            }
        
        self.formats = {}
        
        # Keywords
        self.formats['keyword'] = QTextCharFormat()
        self.formats['keyword'].setForeground(QColor(colors['keyword']))
        self.formats['keyword'].setFontWeight(QFont.Weight.Bold)
        
        # Block types (job, group, task, resource, etc.)
        self.formats['block_type'] = QTextCharFormat()
        self.formats['block_type'].setForeground(QColor(colors['block_type']))
        self.formats['block_type'].setFontWeight(QFont.Weight.Bold)
        
        # Strings
        self.formats['string'] = QTextCharFormat()
        self.formats['string'].setForeground(QColor(colors['string']))
        
        # Numbers
        self.formats['number'] = QTextCharFormat()
        self.formats['number'].setForeground(QColor(colors['number']))
        
        # Comments
        self.formats['comment'] = QTextCharFormat()
        self.formats['comment'].setForeground(QColor(colors['comment']))
        self.formats['comment'].setFontItalic(True)
        
        # Booleans
        self.formats['boolean'] = QTextCharFormat()
        self.formats['boolean'].setForeground(QColor(colors['boolean']))
        self.formats['boolean'].setFontWeight(QFont.Weight.Bold)
        
        # Attributes
        self.formats['attribute'] = QTextCharFormat()
        self.formats['attribute'].setForeground(QColor(colors['attribute']))
        
        # Functions
        self.formats['function'] = QTextCharFormat()
        self.formats['function'].setForeground(QColor(colors['function']))
        
        # Variables/interpolation
        self.formats['variable'] = QTextCharFormat()
        self.formats['variable'].setForeground(QColor(colors['variable']))
        
        # Brackets
        self.formats['bracket'] = QTextCharFormat()
        self.formats['bracket'].setForeground(QColor(colors['bracket']))
        self.formats['bracket'].setFontWeight(QFont.Weight.Bold)
    
    def _setup_rules(self):
        """Setup highlighting rules."""
        self.rules = []
        
        # HCL/Nomad/Terraform block types
        block_types = [
            'job', 'group', 'task', 'service', 'check', 'network', 'volume',
            'template', 'artifact', 'resources', 'constraint', 'affinity',
            'spread', 'update', 'migrate', 'reschedule', 'restart', 'vault',
            'dispatch_payload', 'periodic', 'parameterized', 'meta', 'env',
            'config', 'logs', 'scaling', 'lifecycle', 'sidecar_service',
            'sidecar_task', 'proxy', 'upstreams', 'expose', 'paths',
            # Terraform/OpenTofu
            'resource', 'data', 'provider', 'variable', 'output', 'module',
            'locals', 'terraform', 'backend', 'required_providers',
            # Consul
            'service', 'connect', 'proxy', 'upstream', 'expose',
            # Vault/OpenBao
            'path', 'policy', 'secret', 'auth', 'storage', 'listener',
            'seal', 'telemetry', 'ui',
        ]
        pattern = r'\b(' + '|'.join(block_types) + r')\b'
        self.rules.append((QRegularExpression(pattern), 'block_type'))
        
        # Keywords
        keywords = [
            'true', 'false', 'null', 'for', 'in', 'if', 'else', 'endif',
            'endfor', 'type', 'datacenters', 'region', 'namespace',
            'priority', 'all_at_once', 'count', 'driver', 'user',
            'mode', 'port', 'to', 'static', 'host_network', 'dns',
            'hostname', 'capabilities', 'enabled', 'destination',
            'source', 'readonly', 'change_mode', 'change_signal',
            'perms', 'uid', 'gid', 'left_delimiter', 'right_delimiter',
            'data', 'env', 'splay', 'wait', 'error_on_missing_key',
        ]
        pattern = r'\b(' + '|'.join(keywords) + r')\b'
        self.rules.append((QRegularExpression(pattern), 'keyword'))
        
        # Booleans
        self.rules.append((QRegularExpression(r'\b(true|false)\b'), 'boolean'))
        
        # Numbers (integers, floats, with optional suffixes)
        self.rules.append((QRegularExpression(r'\b\d+\.?\d*([eE][+-]?\d+)?[kKmMgG]?\b'), 'number'))
        
        # Attributes (word followed by =)
        self.rules.append((QRegularExpression(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*='), 'attribute'))
        
        # Functions (word followed by ()
        self.rules.append((QRegularExpression(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\('), 'function'))
        
        # Variable interpolation ${...}
        self.rules.append((QRegularExpression(r'\$\{[^}]+\}'), 'variable'))
        
        # Variable references (NOMAD_*, attr.*, meta.*, etc.)
        self.rules.append((QRegularExpression(r'\$\{?[A-Z][A-Z0-9_]*\}?'), 'variable'))
        
        # Brackets
        self.rules.append((QRegularExpression(r'[\{\}\[\]]'), 'bracket'))
        
        # Single-line comments (# and //)
        self.rules.append((QRegularExpression(r'#[^\n]*'), 'comment'))
        self.rules.append((QRegularExpression(r'//[^\n]*'), 'comment'))
        
        # Double-quoted strings (handling escapes)
        self.rules.append((QRegularExpression(r'"(?:[^"\\]|\\.)*"'), 'string'))
        
        # Heredoc start (<<EOF, <<-EOF)
        self.rules.append((QRegularExpression(r'<<-?[A-Z]+'), 'string'))
    
    def highlightBlock(self, text: str):
        """Apply highlighting to a block of text."""
        # Apply single-line rules
        for pattern, format_name in self.rules:
            if format_name == 'comment' and pattern.pattern().startswith('#'):
                # Skip if inside string
                pass
            
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart()
                length = match.capturedLength()
                
                # For attribute pattern, only highlight the attribute name
                if format_name == 'attribute':
                    # Find just the word before =
                    attr_match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)', match.captured())
                    if attr_match:
                        length = len(attr_match.group(1))
                
                # For function pattern, only highlight the function name
                if format_name == 'function':
                    func_match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)', match.captured())
                    if func_match:
                        length = len(func_match.group(1))
                
                self.setFormat(start, length, self.formats[format_name])
        
        # Handle multi-line strings (heredocs) and block comments
        self._handle_multiline(text)
    
    def _handle_multiline(self, text: str):
        """Handle multi-line constructs like heredocs and block comments."""
        # Block comments /* ... */
        self.setCurrentBlockState(0)
        
        start_comment = QRegularExpression(r'/\*')
        end_comment = QRegularExpression(r'\*/')
        
        start_index = 0
        if self.previousBlockState() != 1:
            match = start_comment.match(text)
            start_index = match.capturedStart() if match.hasMatch() else -1
        
        while start_index >= 0:
            end_match = end_comment.match(text, start_index)
            if end_match.hasMatch():
                end_index = end_match.capturedEnd()
                length = end_index - start_index
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start_index
            
            self.setFormat(start_index, length, self.formats['comment'])
            
            match = start_comment.match(text, start_index + length)
            start_index = match.capturedStart() if match.hasMatch() else -1


class JSONSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for JSON."""
    
    def __init__(self, document: QTextDocument, dark_mode: bool = False):
        super().__init__(document)
        self.dark_mode = dark_mode
        self._setup_formats()
        self._setup_rules()
    
    def _setup_formats(self):
        """Setup text formats."""
        if self.dark_mode:
            colors = {
                'key': '#9CDCFE',
                'string': '#CE9178',
                'number': '#B5CEA8',
                'boolean': '#569CD6',
                'null': '#569CD6',
                'bracket': '#FFD700',
            }
        else:
            colors = {
                'key': '#001080',
                'string': '#A31515',
                'number': '#098658',
                'boolean': '#0000FF',
                'null': '#0000FF',
                'bracket': '#AF00DB',
            }
        
        self.formats = {}
        
        self.formats['key'] = QTextCharFormat()
        self.formats['key'].setForeground(QColor(colors['key']))
        
        self.formats['string'] = QTextCharFormat()
        self.formats['string'].setForeground(QColor(colors['string']))
        
        self.formats['number'] = QTextCharFormat()
        self.formats['number'].setForeground(QColor(colors['number']))
        
        self.formats['boolean'] = QTextCharFormat()
        self.formats['boolean'].setForeground(QColor(colors['boolean']))
        self.formats['boolean'].setFontWeight(QFont.Weight.Bold)
        
        self.formats['null'] = QTextCharFormat()
        self.formats['null'].setForeground(QColor(colors['null']))
        self.formats['null'].setFontItalic(True)
        
        self.formats['bracket'] = QTextCharFormat()
        self.formats['bracket'].setForeground(QColor(colors['bracket']))
        self.formats['bracket'].setFontWeight(QFont.Weight.Bold)
    
    def _setup_rules(self):
        """Setup highlighting rules."""
        self.rules = []
        
        # Keys (string followed by :)
        self.rules.append((QRegularExpression(r'"[^"]*"\s*:'), 'key'))
        
        # Strings
        self.rules.append((QRegularExpression(r'"(?:[^"\\]|\\.)*"'), 'string'))
        
        # Numbers
        self.rules.append((QRegularExpression(r'\b-?\d+\.?\d*([eE][+-]?\d+)?\b'), 'number'))
        
        # Booleans
        self.rules.append((QRegularExpression(r'\b(true|false)\b'), 'boolean'))
        
        # Null
        self.rules.append((QRegularExpression(r'\bnull\b'), 'null'))
        
        # Brackets
        self.rules.append((QRegularExpression(r'[\{\}\[\]]'), 'bracket'))
    
    def highlightBlock(self, text: str):
        """Apply highlighting to a block of text."""
        for pattern, format_name in self.rules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart()
                length = match.capturedLength()
                
                # For keys, don't include the colon
                if format_name == 'key':
                    # Find the actual string part
                    key_text = match.captured()
                    quote_end = key_text.rfind('"')
                    if quote_end > 0:
                        length = quote_end + 1
                
                self.setFormat(start, length, self.formats[format_name])


class SyntaxHighlightedTextEdit(QPlainTextEdit):
    """A text editor with syntax highlighting and line numbers."""
    
    def __init__(self, syntax: str = 'hcl', parent=None):
        super().__init__(parent)
        self.syntax = syntax
        
        # Setup font
        font = QFont("Monospace", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.setFont(font)
        
        # Tab width
        metrics = QFontMetricsF(font)
        self.setTabStopDistance(4 * metrics.horizontalAdvance(' '))
        
        # Detect dark mode
        palette = self.palette()
        bg_color = palette.color(QPalette.ColorRole.Base)
        self.dark_mode = bg_color.lightness() < 128
        
        # Apply syntax highlighter
        self._highlighter = None
        self.set_syntax(syntax)
    
    def set_syntax(self, syntax: str):
        """Set the syntax highlighting mode."""
        self.syntax = syntax.lower()
        
        if self._highlighter:
            self._highlighter.setDocument(None)
        
        if self.syntax in ('hcl', 'terraform', 'nomad', 'vault', 'consul'):
            self._highlighter = HCLSyntaxHighlighter(self.document(), self.dark_mode)
        elif self.syntax == 'json':
            self._highlighter = JSONSyntaxHighlighter(self.document(), self.dark_mode)
        else:
            self._highlighter = None


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
        
        # Raw JSON tab with syntax highlighting
        json_widget = QWidget()
        json_layout = QVBoxLayout(json_widget)
        self.json_edit = SyntaxHighlightedTextEdit(syntax='json')
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
        
        # Sound settings section
        sound_group = QGroupBox("🔊 Sound Notifications")
        sound_layout = QFormLayout(sound_group)
        
        self.sounds_enabled = QCheckBox()
        self.sounds_enabled.toggled.connect(self._on_sounds_toggled)
        sound_layout.addRow("Enable Sounds:", self.sounds_enabled)
        
        # Success sound
        success_layout = QHBoxLayout()
        self.sound_success = QComboBox()
        self.sound_success.setEditable(True)
        self.sound_success.addItems(["system", "none"])
        self._populate_sound_combo(self.sound_success)
        success_layout.addWidget(self.sound_success, 1)
        
        test_success_btn = QPushButton("▶️ Test")
        test_success_btn.clicked.connect(lambda: self._test_sound("success"))
        success_layout.addWidget(test_success_btn)
        sound_layout.addRow("Success Sound:", success_layout)
        
        # Error sound
        error_layout = QHBoxLayout()
        self.sound_error = QComboBox()
        self.sound_error.setEditable(True)
        self.sound_error.addItems(["system", "none"])
        self._populate_sound_combo(self.sound_error)
        error_layout.addWidget(self.sound_error, 1)
        
        test_error_btn = QPushButton("▶️ Test")
        test_error_btn.clicked.connect(lambda: self._test_sound("error"))
        error_layout.addWidget(test_error_btn)
        sound_layout.addRow("Error Sound:", error_layout)
        
        layout.addRow(sound_group)
        
        self.tabs.addTab(widget, "🌍 Global")
    
    def _populate_sound_combo(self, combo: QComboBox):
        """Populate a combo box with available system sounds."""
        from app.process_manager import SoundManager
        
        # Create temporary sound manager to discover sounds
        sound_mgr = SoundManager(self.settings)
        available = sound_mgr.get_available_sounds()
        
        for name in sorted(available.keys()):
            if name not in ["system", "none"]:
                combo.addItem(name)
    
    def _on_sounds_toggled(self, enabled: bool):
        """Handle sounds enabled checkbox toggle."""
        self.sound_success.setEnabled(enabled)
        self.sound_error.setEnabled(enabled)
    
    def _test_sound(self, sound_type: str):
        """Test play a sound."""
        from app.process_manager import SoundManager
        
        # Temporarily apply current settings for test
        old_enabled = self.settings.global_settings.sounds_enabled
        old_success = self.settings.global_settings.sound_success
        old_error = self.settings.global_settings.sound_error
        
        self.settings.global_settings.sounds_enabled = True
        self.settings.global_settings.sound_success = self.sound_success.currentText()
        self.settings.global_settings.sound_error = self.sound_error.currentText()
        
        sound_mgr = SoundManager(self.settings)
        if sound_type == "success":
            sound_mgr.play_success()
        else:
            sound_mgr.play_error()
        
        # Restore settings
        self.settings.global_settings.sounds_enabled = old_enabled
        self.settings.global_settings.sound_success = old_success
        self.settings.global_settings.sound_error = old_error
    
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
        
        # Token auth section
        layout.addRow(QLabel("<b>Token Authentication</b>"))
        
        self.boundary_token = QLineEdit()
        self.boundary_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.boundary_token.setPlaceholderText("(leave empty to use password auth)")
        layout.addRow("🔑 Token:", self.boundary_token)
        
        # Password auth section
        layout.addRow(QLabel("<b>Password Authentication</b>"))
        
        self.boundary_auth_method = QLineEdit()
        self.boundary_auth_method.setPlaceholderText("ampw_1234567890")
        layout.addRow("🔐 Auth Method ID:", self.boundary_auth_method)
        
        self.boundary_login_name = QLineEdit()
        self.boundary_login_name.setPlaceholderText("username")
        layout.addRow("👤 Login Name:", self.boundary_login_name)
        
        self.boundary_password = QLineEdit()
        self.boundary_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("🔒 Password:", self.boundary_password)
        
        self.boundary_scope_id = QLineEdit()
        self.boundary_scope_id.setPlaceholderText("global")
        layout.addRow("📂 Scope ID:", self.boundary_scope_id)
        
        # Binary path
        layout.addRow(QLabel("<b>CLI Settings</b>"))
        
        self.boundary_binary = QLineEdit()
        self.boundary_binary.setPlaceholderText("boundary")
        layout.addRow("⚙️ Binary Path:", self.boundary_binary)
        
        # Help text
        help_label = QLabel(
            "💡 Use either Token OR Password authentication.\n"
            "Password auth requires Auth Method ID, Login Name, and Password."
        )
        help_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addRow(help_label)
        
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
        
        # Sound settings
        self.sounds_enabled.setChecked(self.settings.global_settings.sounds_enabled)
        self.sound_success.setCurrentText(self.settings.global_settings.sound_success)
        self.sound_error.setCurrentText(self.settings.global_settings.sound_error)
        self._on_sounds_toggled(self.settings.global_settings.sounds_enabled)
        
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
        self.boundary_login_name.setText(self.settings.boundary.login_name)
        self.boundary_password.setText(self.settings.boundary.password)
        self.boundary_scope_id.setText(self.settings.boundary.scope_id)
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
        
        # Sound settings
        self.settings.global_settings.sounds_enabled = self.sounds_enabled.isChecked()
        self.settings.global_settings.sound_success = self.sound_success.currentText()
        self.settings.global_settings.sound_error = self.sound_error.currentText()
        
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
        self.settings.boundary.login_name = self.boundary_login_name.text()
        self.settings.boundary.password = self.boundary_password.text()
        self.settings.boundary.scope_id = self.boundary_scope_id.text() or "global"
        self.settings.boundary.binary_path = self.boundary_binary.text()
        
        # Packer
        self.settings.packer.home_dir = self.packer_home.text()
        self.settings.packer.binary_path = self.packer_binary.text()
        
        # Persist
        self.settings.save()
        self.settings_saved.emit()
        self.accept()


class PolicyEditorDialog(QDialog):
    """Dialog for editing HCL policies with a large text area."""
    
    saved = Signal(str, str)  # name, policy_text
    deleted = Signal(str)  # name
    
    def __init__(self, name: str, policy_text: str = "", is_new: bool = False, 
                 readonly: bool = False, parent=None):
        super().__init__(parent)
        self.name = name
        self.policy_text = policy_text
        self.is_new = is_new
        self.readonly = readonly
        
        self.setWindowTitle(f"{'New ' if is_new else ''}Policy: {name}")
        self.setMinimumSize(700, 500)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Policy name (editable for new policies)
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Policy Name:"))
        self.name_input = QLineEdit(self.name)
        self.name_input.setReadOnly(not self.is_new)
        if not self.is_new:
            self.name_input.setStyleSheet("background-color: #f0f0f0;")
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # Policy text editor with HCL syntax highlighting
        layout.addWidget(QLabel("Policy (HCL):"))
        self.editor = SyntaxHighlightedTextEdit(syntax='hcl')
        self.editor.setPlainText(self.policy_text)
        self.editor.setReadOnly(self.readonly)
        layout.addWidget(self.editor)
        
        # Help text
        help_label = QLabel(
            "💡 Example: path \"secret/*\" { capabilities = [\"read\", \"list\"] }"
        )
        help_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(help_label)
        
        # Buttons
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
        
        cancel_btn = QPushButton("Cancel" if not self.readonly else "Close")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _save(self):
        """Save the policy."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Policy name is required")
            return
        
        policy_text = self.editor.toPlainText()
        if not policy_text.strip():
            QMessageBox.warning(self, "Error", "Policy text is required")
            return
        
        self.saved.emit(name, policy_text)
        self.accept()
    
    def _delete(self):
        """Delete the policy."""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete policy '{self.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit(self.name)
            self.accept()

class TemplateSelectionDialog(QDialog):
    """Dialog for selecting and editing templates (Nomad jobs, Consul services, etc.)."""
    
    saved = Signal(str)  # Emits the final text content
    
    def __init__(self, title: str, templates: Dict[str, str], 
                 syntax_hint: str = "hcl", parent=None,
                 submit_callback: Optional[Callable[[str], Tuple[bool, str]]] = None):
        """
        Args:
            title: Dialog title
            templates: Dict of {template_name: template_content}
            syntax_hint: 'hcl', 'json', or 'yaml' for syntax highlighting
            submit_callback: Optional callback(content) -> (success, error_msg)
                             If provided, dialog only closes on success.
                             If not provided, uses saved signal and closes immediately.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 700)
        self.templates = templates
        self.syntax_hint = syntax_hint
        self.submit_callback = submit_callback
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Template selection
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("Template:"))
        
        self.template_combo = QComboBox()
        self.template_combo.addItems(list(self.templates.keys()))
        self.template_combo.currentTextChanged.connect(self._on_template_changed)
        select_layout.addWidget(self.template_combo, 1)
        
        layout.addLayout(select_layout)
        
        # Editor with syntax highlighting
        self.editor = SyntaxHighlightedTextEdit(syntax=self.syntax_hint)
        layout.addWidget(self.editor, 1)
        
        # Load first template
        if self.templates:
            first_key = list(self.templates.keys())[0]
            self.editor.setPlainText(self.templates[first_key])
        
        # Buttons
        button_layout = QHBoxLayout()
        
        save_btn = QPushButton("💾 Submit")
        save_btn.clicked.connect(self._save)
        button_layout.addWidget(save_btn)
        
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _on_template_changed(self, template_name: str):
        """Load the selected template into the editor."""
        if template_name in self.templates:
            self.editor.setPlainText(self.templates[template_name])
    
    def _save(self):
        """Save and emit the content."""
        content = self.editor.toPlainText()
        if not content.strip():
            QMessageBox.warning(self, "Error", "Content cannot be empty")
            return
        
        if self.submit_callback:
            # Use callback for validation - only close on success
            success, error_msg = self.submit_callback(content)
            if success:
                self.accept()
            else:
                QMessageBox.warning(self, "Error", error_msg)
                # Dialog stays open for user to fix the error
        else:
            # Legacy behavior: emit signal and close
            self.saved.emit(content)
            self.accept()
    
    def get_content(self) -> str:
        """Get the current editor content."""
        return self.editor.toPlainText()


# ==================== Nomad Job Templates ====================

NOMAD_JOB_TEMPLATES = {
    "Service (Docker)": '''# Nomad Service Job - Docker Container
# A long-running service using Docker driver

job "my-service" {
  # Datacenter where job should run
  datacenters = ["dc1"]
  
  # Job type: service (long-running), batch, or system
  type = "service"
  
  # Optional namespace (Enterprise feature)
  # namespace = "default"
  
  # Update strategy for rolling deployments
  update {
    max_parallel     = 1        # Number of allocations to update at once
    min_healthy_time = "10s"    # Minimum time for allocation to be healthy
    healthy_deadline = "3m"     # Deadline for allocation to become healthy
    auto_revert      = true     # Revert to last stable version on failure
    canary           = 0        # Number of canary allocations
  }
  
  # Task group - a set of tasks that run together
  group "web" {
    # Number of instances to run
    count = 3
    
    # Networking mode and port mappings
    network {
      port "http" {
        to = 8080              # Container port
      }
    }
    
    # Service registration (Consul or Nomad native)
    service {
      name = "my-service"
      port = "http"
      
      # Health check
      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
      }
      
      # Service tags
      tags = ["web", "production"]
    }
    
    # Restart policy on task failure
    restart {
      attempts = 3
      interval = "5m"
      delay    = "15s"
      mode     = "delay"        # delay, fail
    }
    
    # Task definition
    task "app" {
      # Driver: docker, exec, java, raw_exec, etc.
      driver = "docker"
      
      config {
        image = "nginx:latest"
        ports = ["http"]
        
        # Mount volumes
        # volumes = [
        #   "local/config:/etc/myapp"
        # ]
      }
      
      # Resource requirements
      resources {
        cpu    = 500            # MHz
        memory = 256            # MB
      }
      
      # Environment variables
      env {
        APP_ENV = "production"
      }
      
      # Template for config files (from Consul KV or Vault)
      # template {
      #   data = <<EOF
      # {{ key "config/myapp" }}
      # EOF
      #   destination = "local/config/app.conf"
      # }
    }
  }
}
''',

    "Service (Exec)": '''# Nomad Service Job - Exec Driver
# Run a native binary or script

job "my-exec-service" {
  datacenters = ["dc1"]
  type = "service"
  
  group "app" {
    count = 1
    
    network {
      port "http" {
        static = 8080
      }
    }
    
    task "server" {
      driver = "exec"
      
      config {
        # Path to binary (must be on client filesystem)
        command = "/usr/local/bin/myapp"
        
        # Command arguments
        args = [
          "--port", "${NOMAD_PORT_http}",
          "--config", "local/config.yaml"
        ]
      }
      
      # Artifact to download (binary, config, etc.)
      artifact {
        source      = "https://releases.example.com/myapp-v1.0.0-linux-amd64"
        destination = "local/myapp"
        mode        = "file"
        
        # Optional checksum verification
        # options {
        #   checksum = "sha256:abc123..."
        # }
      }
      
      resources {
        cpu    = 200
        memory = 128
      }
      
      env {
        LOG_LEVEL = "info"
      }
    }
  }
}
''',

    "Batch Job": '''# Nomad Batch Job
# Runs to completion and exits

job "my-batch" {
  datacenters = ["dc1"]
  type = "batch"
  
  # Periodic scheduling (like cron)
  # periodic {
  #   cron             = "0 * * * *"   # Every hour
  #   prohibit_overlap = true
  #   time_zone        = "UTC"
  # }
  
  group "process" {
    count = 1
    
    # Reschedule policy for batch jobs
    reschedule {
      attempts       = 3
      interval       = "1h"
      delay          = "30s"
      delay_function = "exponential"
      max_delay      = "5m"
      unlimited      = false
    }
    
    task "etl" {
      driver = "docker"
      
      config {
        image   = "python:3.11"
        command = "python"
        args    = ["/scripts/etl.py"]
        
        volumes = [
          "local/scripts:/scripts"
        ]
      }
      
      # Template to create script from embedded content
      template {
        data = <<EOF
#!/usr/bin/env python3
import os
print(f"Running ETL job in {os.environ.get('NOMAD_ALLOC_ID', 'unknown')}")
# Your ETL logic here
EOF
        destination = "local/scripts/etl.py"
      }
      
      resources {
        cpu    = 1000
        memory = 512
      }
    }
  }
}
''',

    "System Job": '''# Nomad System Job
# Runs on every node in the cluster

job "node-agent" {
  datacenters = ["dc1"]
  type = "system"
  
  # Constraints to limit which nodes
  # constraint {
  #   attribute = "${attr.kernel.name}"
  #   value     = "linux"
  # }
  
  group "agent" {
    task "collector" {
      driver = "docker"
      
      config {
        image        = "prometheus/node-exporter:latest"
        network_mode = "host"
        
        # Privileged for system metrics
        # privileged = true
      }
      
      resources {
        cpu    = 100
        memory = 64
      }
      
      service {
        name = "node-exporter"
        port = "9100"
        
        check {
          type     = "http"
          path     = "/metrics"
          interval = "30s"
          timeout  = "5s"
        }
      }
    }
  }
}
''',

    "Parameterized Job": '''# Nomad Parameterized Job
# Template job that accepts parameters at dispatch time

job "report-generator" {
  datacenters = ["dc1"]
  type = "batch"
  
  # Parameterized configuration
  parameterized {
    # Metadata keys that must be provided at dispatch
    meta_required = ["report_type", "customer_id"]
    
    # Optional metadata keys
    meta_optional = ["date_range"]
    
    # Accept payload data
    payload = "optional"   # required, optional, forbidden
  }
  
  group "generate" {
    task "run" {
      driver = "docker"
      
      config {
        image   = "my-reports:latest"
        command = "/generate.sh"
        args    = [
          "--type", "${NOMAD_META_report_type}",
          "--customer", "${NOMAD_META_customer_id}",
          "--range", "${NOMAD_META_date_range}"
        ]
      }
      
      # Payload is available at this path
      dispatch_payload {
        file = "config/payload.json"
      }
      
      resources {
        cpu    = 500
        memory = 256
      }
    }
  }
}

# Dispatch with: nomad job dispatch -meta report_type=monthly -meta customer_id=123 report-generator
''',

    "Java Application": '''# Nomad Java Application
# Run a JAR file with the Java driver

job "java-app" {
  datacenters = ["dc1"]
  type = "service"
  
  group "app" {
    count = 2
    
    network {
      port "http" {
        to = 8080
      }
    }
    
    service {
      name = "java-app"
      port = "http"
      
      check {
        type     = "http"
        path     = "/actuator/health"
        interval = "15s"
        timeout  = "3s"
      }
    }
    
    task "server" {
      driver = "java"
      
      config {
        # Path to JAR file
        jar_path = "local/app.jar"
        
        # JVM options
        jvm_options = [
          "-Xms256m",
          "-Xmx512m",
          "-XX:+UseG1GC",
          "-Dspring.profiles.active=production"
        ]
        
        # Main class (if not in manifest)
        # class = "com.example.Application"
        
        # Classpath additions
        # class_path = "local/lib"
      }
      
      # Download the JAR artifact
      artifact {
        source      = "https://releases.example.com/app-1.0.0.jar"
        destination = "local/app.jar"
        mode        = "file"
      }
      
      resources {
        cpu    = 1000
        memory = 768
      }
      
      env {
        SPRING_DATASOURCE_URL = "jdbc:postgresql://db:5432/myapp"
      }
    }
  }
}
''',

    "Raw Exec (Script)": '''# Nomad Raw Exec Job
# Run scripts or commands directly (requires raw_exec enabled)

job "maintenance" {
  datacenters = ["dc1"]
  type = "batch"
  
  group "scripts" {
    task "cleanup" {
      driver = "raw_exec"
      
      config {
        # Run a shell command directly
        command = "/bin/bash"
        args    = ["-c", <<EOF
echo "Starting cleanup at $(date)"
find /var/log -name "*.log" -mtime +7 -delete
echo "Cleanup complete"
EOF
        ]
      }
      
      # Or run a script file
      # config {
      #   command = "local/cleanup.sh"
      # }
      
      resources {
        cpu    = 100
        memory = 64
      }
    }
  }
}
''',

    "Connect Sidecar (Service Mesh)": '''# Nomad Connect Job
# Service mesh with Consul Connect sidecar proxy

job "web-api" {
  datacenters = ["dc1"]
  type = "service"
  
  group "api" {
    count = 2
    
    network {
      mode = "bridge"    # Required for Connect
      
      port "http" {
        to = 8080
      }
    }
    
    # Consul Connect service definition
    service {
      name = "web-api"
      port = "8080"
      
      connect {
        sidecar_service {
          # Upstream services this app needs
          proxy {
            upstreams {
              destination_name = "database"
              local_bind_port  = 5432
            }
            upstreams {
              destination_name = "cache"
              local_bind_port  = 6379
            }
          }
        }
      }
      
      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
        expose   = true    # Expose check through proxy
      }
    }
    
    task "api" {
      driver = "docker"
      
      config {
        image = "my-api:latest"
        ports = ["http"]
      }
      
      env {
        # Connect to upstreams via localhost
        DATABASE_URL = "postgresql://localhost:5432/mydb"
        REDIS_URL    = "redis://localhost:6379"
      }
      
      resources {
        cpu    = 500
        memory = 256
      }
    }
  }
}
'''
}


# ==================== Consul Service Templates ====================

CONSUL_SERVICE_TEMPLATES = {
    "Basic Service": '''{
  "ID": "my-service-1",
  "Name": "my-service",
  "Tags": ["primary", "v1"],
  "Address": "10.0.0.10",
  "Port": 8080,
  "Meta": {
    "version": "1.0.0",
    "environment": "production"
  },
  "EnableTagOverride": false,
  "Check": {
    "HTTP": "http://10.0.0.10:8080/health",
    "Method": "GET",
    "Interval": "10s",
    "Timeout": "2s",
    "DeregisterCriticalServiceAfter": "30m"
  }
}''',

    "Service with Multiple Checks": '''{
  "ID": "web-server-1",
  "Name": "web-server",
  "Tags": ["web", "frontend"],
  "Address": "10.0.0.20",
  "Port": 80,
  "Checks": [
    {
      "Name": "HTTP Health",
      "HTTP": "http://10.0.0.20:80/health",
      "Interval": "10s",
      "Timeout": "2s"
    },
    {
      "Name": "TCP Port",
      "TCP": "10.0.0.20:80",
      "Interval": "15s",
      "Timeout": "3s"
    },
    {
      "Name": "Memory Usage",
      "Args": ["/usr/local/bin/check_memory.sh"],
      "Interval": "30s",
      "Timeout": "5s"
    }
  ]
}''',

    "gRPC Service": '''{
  "ID": "grpc-api-1",
  "Name": "grpc-api",
  "Tags": ["grpc", "api"],
  "Address": "10.0.0.30",
  "Port": 50051,
  "Meta": {
    "protocol": "grpc"
  },
  "Check": {
    "GRPC": "10.0.0.30:50051",
    "GRPCUseTLS": false,
    "Interval": "10s",
    "Timeout": "3s"
  }
}''',

    "Service with Weights": '''{
  "ID": "weighted-service-1",
  "Name": "weighted-service",
  "Tags": ["canary"],
  "Address": "10.0.0.40",
  "Port": 8080,
  "Weights": {
    "Passing": 10,
    "Warning": 1
  },
  "Check": {
    "HTTP": "http://10.0.0.40:8080/health",
    "Interval": "10s",
    "Timeout": "2s"
  }
}''',

    "Connect Proxy": '''{
  "ID": "web-proxy",
  "Name": "web",
  "Kind": "connect-proxy",
  "Port": 21000,
  "Proxy": {
    "DestinationServiceName": "web",
    "DestinationServiceID": "web-1",
    "LocalServiceAddress": "127.0.0.1",
    "LocalServicePort": 8080,
    "Upstreams": [
      {
        "DestinationType": "service",
        "DestinationName": "database",
        "LocalBindPort": 5432
      },
      {
        "DestinationType": "service",
        "DestinationName": "cache",
        "LocalBindPort": 6379
      }
    ]
  },
  "Check": {
    "TCP": "127.0.0.1:21000",
    "Interval": "10s",
    "Timeout": "2s"
  }
}''',

    "TTL Check Service": '''{
  "ID": "batch-worker-1",
  "Name": "batch-worker",
  "Tags": ["worker", "async"],
  "Address": "10.0.0.50",
  "Port": 9000,
  "Check": {
    "Name": "Heartbeat",
    "TTL": "30s",
    "Notes": "Application must call /v1/agent/check/pass/service:batch-worker-1 within TTL"
  }
}''',

    "Sidecar Service": '''{
  "ID": "app-sidecar",
  "Name": "app",
  "Kind": "connect-sidecar",
  "Port": 20000,
  "Proxy": {
    "DestinationServiceName": "app",
    "DestinationServiceID": "app-1",
    "LocalServicePort": 8080,
    "Config": {
      "protocol": "http",
      "local_request_timeout_ms": 30000
    },
    "MeshGateway": {
      "Mode": "local"
    },
    "Expose": {
      "Checks": true,
      "Paths": [
        {
          "Path": "/metrics",
          "LocalPathPort": 9102,
          "ListenerPort": 21500,
          "Protocol": "http"
        }
      ]
    }
  }
}'''
}
