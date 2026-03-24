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
        
        # HCP tab
        self._create_hcp_tab()
        
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
    
    def _create_hcp_tab(self):
        """Create the HCP (HashiCorp Cloud Platform) settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Cloud API credentials (OAuth2 service principal)
        cloud_label = QLabel("<b>☁️ HCP Cloud API (OAuth2 Service Principal)</b>")
        layout.addRow(cloud_label)
        
        self.hcp_client_id = QLineEdit()
        self.hcp_client_id.setEchoMode(QLineEdit.EchoMode.Password)
        self.hcp_client_id.setPlaceholderText("Service principal client ID")
        layout.addRow("🔑 Client ID:", self.hcp_client_id)
        
        self.hcp_client_secret = QLineEdit()
        self.hcp_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.hcp_client_secret.setPlaceholderText("Service principal client secret")
        layout.addRow("🔐 Client Secret:", self.hcp_client_secret)
        
        self.hcp_organization_id = QLineEdit()
        self.hcp_organization_id.setPlaceholderText("HCP organization UUID")
        layout.addRow("🏢 Organization ID:", self.hcp_organization_id)

        self.hcp_project_id = QLineEdit()
        self.hcp_project_id.setPlaceholderText("HCP project UUID")
        layout.addRow("📂 Project ID:", self.hcp_project_id)

        # Endpoint URLs
        endpoint_label = QLabel("<b>🌐 Endpoint URLs</b>")
        layout.addRow(endpoint_label)

        self.hcp_api_url = QLineEdit()
        self.hcp_api_url.setPlaceholderText("https://api.cloud.hashicorp.com")
        layout.addRow("🔗 HCP API URL:", self.hcp_api_url)

        self.hcp_auth_url = QLineEdit()
        self.hcp_auth_url.setPlaceholderText("https://auth.idp.hashicorp.com")
        layout.addRow("🔗 HCP Auth URL:", self.hcp_auth_url)

        # Separator
        sep_label = QLabel("<b>🏗️ HCP Terraform</b>")
        layout.addRow(sep_label)

        self.hcp_terraform_url = QLineEdit()
        self.hcp_terraform_url.setPlaceholderText("https://app.terraform.io")
        layout.addRow("🔗 TFE URL:", self.hcp_terraform_url)

        self.hcp_terraform_token = QLineEdit()
        self.hcp_terraform_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.hcp_terraform_token.setPlaceholderText("TFE/TFC bearer token")
        layout.addRow("🔑 TFE Token:", self.hcp_terraform_token)

        self.hcp_terraform_org = QLineEdit()
        self.hcp_terraform_org.setPlaceholderText("Default organization name")
        layout.addRow("🏢 TF Organization:", self.hcp_terraform_org)
        
        self.tabs.addTab(widget, "☁️ HCP")
    
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
        
        # HCP
        self.hcp_client_id.setText(self.settings.hcp.client_id)
        self.hcp_client_secret.setText(self.settings.hcp.client_secret)
        self.hcp_organization_id.setText(self.settings.hcp.organization_id)
        self.hcp_project_id.setText(self.settings.hcp.project_id)
        self.hcp_api_url.setText(self.settings.hcp.hcp_api_url)
        self.hcp_auth_url.setText(self.settings.hcp.hcp_auth_url)
        self.hcp_terraform_url.setText(self.settings.hcp.hcp_terraform_url)
        self.hcp_terraform_token.setText(self.settings.hcp.hcp_terraform_token)
        self.hcp_terraform_org.setText(self.settings.hcp.hcp_terraform_org)
        
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
        
        # HCP
        self.settings.hcp.client_id = self.hcp_client_id.text()
        self.settings.hcp.client_secret = self.hcp_client_secret.text()
        self.settings.hcp.organization_id = self.hcp_organization_id.text()
        self.settings.hcp.project_id = self.hcp_project_id.text()
        self.settings.hcp.hcp_api_url = self.hcp_api_url.text() or "https://api.cloud.hashicorp.com"
        self.settings.hcp.hcp_auth_url = self.hcp_auth_url.text() or "https://auth.idp.hashicorp.com"
        self.settings.hcp.hcp_terraform_url = self.hcp_terraform_url.text() or "https://app.terraform.io"
        self.settings.hcp.hcp_terraform_token = self.hcp_terraform_token.text()
        self.settings.hcp.hcp_terraform_org = self.hcp_terraform_org.text()
        
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


# ==================== Enable Secrets Engine Dialog ====================

# Known secret engine types with descriptions
SECRET_ENGINE_TYPES = {
    'kv': {
        'name': 'KV (Key-Value)',
        'description': 'Versioned or unversioned key-value store',
        'options': ['version'],  # 1 or 2
    },
    'transit': {
        'name': 'Transit',
        'description': 'Encryption as a service - encrypt/decrypt/sign data',
        'options': [],
    },
    'pki': {
        'name': 'PKI',
        'description': 'Public Key Infrastructure - issue X.509 certificates',
        'options': [],
    },
    'database': {
        'name': 'Database',
        'description': 'Dynamic database credentials',
        'options': [],
    },
    'aws': {
        'name': 'AWS',
        'description': 'Dynamic AWS IAM credentials',
        'options': [],
    },
    'ssh': {
        'name': 'SSH',
        'description': 'SSH key signing and OTP credentials',
        'options': [],
    },
    'totp': {
        'name': 'TOTP',
        'description': 'Time-based one-time passwords',
        'options': [],
    },
    'rabbitmq': {
        'name': 'RabbitMQ',
        'description': 'Dynamic RabbitMQ credentials',
        'options': [],
    },
    'ldap': {
        'name': 'LDAP',
        'description': 'Dynamic LDAP credentials',
        'options': [],
    },
    'consul': {
        'name': 'Consul',
        'description': 'Dynamic Consul ACL tokens',
        'options': [],
    },
    'nomad': {
        'name': 'Nomad',
        'description': 'Dynamic Nomad ACL tokens',
        'options': [],
    },
    'terraform': {
        'name': 'Terraform Cloud',
        'description': 'Dynamic Terraform Cloud tokens',
        'options': [],
    },
    'gcp': {
        'name': 'Google Cloud',
        'description': 'Dynamic GCP credentials',
        'options': [],
    },
    'azure': {
        'name': 'Azure',
        'description': 'Dynamic Azure credentials',
        'options': [],
    },
    'kubernetes': {
        'name': 'Kubernetes',
        'description': 'Dynamic Kubernetes service account tokens',
        'options': [],
    },
    'mongodbatlas': {
        'name': 'MongoDB Atlas',
        'description': 'Dynamic MongoDB Atlas credentials',
        'options': [],
    },
    'openldap': {
        'name': 'OpenLDAP',
        'description': 'Dynamic OpenLDAP credentials',
        'options': [],
    },
    'transform': {
        'name': 'Transform',
        'description': 'Data transformation and tokenization',
        'options': [],
    },
    'kmip': {
        'name': 'KMIP',
        'description': 'Key Management Interoperability Protocol server',
        'options': [],
    },
}


class EnableEngineDialog(QDialog):
    """Dialog for enabling a secrets engine with configuration."""
    
    saved = Signal(str, str, dict)  # path, type, config
    
    def __init__(self, available_plugins: List[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enable Secrets Engine")
        self.setMinimumSize(500, 400)
        self.available_plugins = available_plugins or []
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # Engine type selection
        self.engine_combo = QComboBox()
        for key, info in SECRET_ENGINE_TYPES.items():
            self.engine_combo.addItem(f"{info['name']} ({key})", key)
        
        # Add any additional plugins from the server
        for plugin in self.available_plugins:
            if plugin not in SECRET_ENGINE_TYPES:
                self.engine_combo.addItem(f"{plugin} (plugin)", plugin)
        
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        form.addRow("Engine Type:", self.engine_combo)
        
        # Description label
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: gray; font-style: italic;")
        form.addRow("", self.description_label)
        
        # Mount path
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("e.g., secret, aws-prod, pki-internal")
        form.addRow("Mount Path:", self.path_edit)
        
        # Description (optional)
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Optional description")
        form.addRow("Description:", self.desc_edit)
        
        layout.addLayout(form)
        
        # Configuration group
        config_group = QGroupBox("Configuration")
        config_layout = QFormLayout(config_group)
        
        # Default lease TTL
        self.default_ttl = QLineEdit()
        self.default_ttl.setPlaceholderText("e.g., 1h, 24h, 768h (leave empty for default)")
        config_layout.addRow("Default Lease TTL:", self.default_ttl)
        
        # Max lease TTL
        self.max_ttl = QLineEdit()
        self.max_ttl.setPlaceholderText("e.g., 24h, 768h, 87600h (leave empty for default)")
        config_layout.addRow("Max Lease TTL:", self.max_ttl)
        
        # KV version (shown only for KV)
        self.kv_version_group = QWidget()
        kv_layout = QHBoxLayout(self.kv_version_group)
        kv_layout.setContentsMargins(0, 0, 0, 0)
        self.kv_v1 = QCheckBox("Version 1")
        self.kv_v2 = QCheckBox("Version 2")
        self.kv_v2.setChecked(True)
        self.kv_v1.toggled.connect(lambda c: self.kv_v2.setChecked(not c) if c else None)
        self.kv_v2.toggled.connect(lambda c: self.kv_v1.setChecked(not c) if c else None)
        kv_layout.addWidget(self.kv_v1)
        kv_layout.addWidget(self.kv_v2)
        kv_layout.addStretch()
        config_layout.addRow("KV Version:", self.kv_version_group)
        
        # Local mount
        self.local_mount = QCheckBox("Local mount (not replicated)")
        config_layout.addRow("", self.local_mount)
        
        # Seal wrap
        self.seal_wrap = QCheckBox("Seal wrap (Enterprise)")
        config_layout.addRow("", self.seal_wrap)
        
        layout.addWidget(config_group)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        enable_btn = QPushButton("✅ Enable")
        enable_btn.clicked.connect(self._enable)
        button_layout.addWidget(enable_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Initialize
        self._on_engine_changed()
    
    def _on_engine_changed(self):
        """Update UI based on selected engine."""
        engine_type = self.engine_combo.currentData()
        
        # Update description
        if engine_type in SECRET_ENGINE_TYPES:
            info = SECRET_ENGINE_TYPES[engine_type]
            self.description_label.setText(info['description'])
        else:
            self.description_label.setText("Custom plugin")
        
        # Update path placeholder
        self.path_edit.setPlaceholderText(engine_type or "mount-path")
        if not self.path_edit.text():
            self.path_edit.setText(engine_type or "")
        
        # Show/hide KV version selector
        self.kv_version_group.setVisible(engine_type == 'kv')
    
    def _enable(self):
        """Enable the secrets engine."""
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Error", "Mount path is required")
            return
        
        engine_type = self.engine_combo.currentData()
        
        config = {}
        
        if self.desc_edit.text().strip():
            config['description'] = self.desc_edit.text().strip()
        
        if self.default_ttl.text().strip():
            config['default_lease_ttl'] = self.default_ttl.text().strip()
        
        if self.max_ttl.text().strip():
            config['max_lease_ttl'] = self.max_ttl.text().strip()
        
        if self.local_mount.isChecked():
            config['local'] = True
        
        if self.seal_wrap.isChecked():
            config['seal_wrap'] = True
        
        # KV version option
        if engine_type == 'kv':
            config['options'] = {'version': '1' if self.kv_v1.isChecked() else '2'}
        
        self.saved.emit(path, engine_type, config)
        self.accept()


class DatabaseConnectionDialog(QDialog):
    """Dialog for creating/editing database connections."""
    
    saved = Signal(str, dict)  # name, config
    
    # Database plugin types
    DB_PLUGINS = {
        'postgresql-database-plugin': 'PostgreSQL',
        'mysql-database-plugin': 'MySQL',
        'mysql-aurora-database-plugin': 'MySQL Aurora',
        'mysql-rds-database-plugin': 'MySQL RDS',
        'mysql-legacy-database-plugin': 'MySQL (Legacy)',
        'mssql-database-plugin': 'Microsoft SQL Server',
        'oracle-database-plugin': 'Oracle',
        'mongodb-database-plugin': 'MongoDB',
        'mongodbatlas-database-plugin': 'MongoDB Atlas',
        'elasticsearch-database-plugin': 'Elasticsearch',
        'snowflake-database-plugin': 'Snowflake',
        'redshift-database-plugin': 'Redshift',
        'cassandra-database-plugin': 'Cassandra',
        'couchbase-database-plugin': 'Couchbase',
        'influxdb-database-plugin': 'InfluxDB',
        'hanadb-database-plugin': 'SAP HANA',
    }
    
    def __init__(self, name: str = "", config: Dict = None, is_new: bool = True, parent=None):
        super().__init__(parent)
        self.name = name
        self.config = config or {}
        self.is_new = is_new
        self.setWindowTitle("New Database Connection" if is_new else f"Edit Connection: {name}")
        self.setMinimumSize(600, 500)
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # Connection name
        self.name_edit = QLineEdit()
        self.name_edit.setEnabled(self.is_new)
        form.addRow("Connection Name:", self.name_edit)
        
        # Plugin type
        self.plugin_combo = QComboBox()
        for plugin, display in self.DB_PLUGINS.items():
            self.plugin_combo.addItem(display, plugin)
        self.plugin_combo.currentIndexChanged.connect(self._on_plugin_changed)
        form.addRow("Database Type:", self.plugin_combo)
        
        layout.addLayout(form)
        
        # Connection details group
        conn_group = QGroupBox("Connection Details")
        conn_layout = QFormLayout(conn_group)
        
        self.conn_url = QLineEdit()
        self.conn_url.setPlaceholderText("e.g., postgresql://{{username}}:{{password}}@host:5432/dbname")
        conn_layout.addRow("Connection URL:", self.conn_url)
        
        self.username = QLineEdit()
        self.username.setPlaceholderText("Root/admin username")
        conn_layout.addRow("Username:", self.username)
        
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Root/admin password")
        conn_layout.addRow("Password:", self.password)
        
        layout.addWidget(conn_group)
        
        # Advanced options
        adv_group = QGroupBox("Advanced Options")
        adv_layout = QFormLayout(adv_group)
        
        self.max_open = QSpinBox()
        self.max_open.setRange(0, 1000)
        self.max_open.setValue(4)
        self.max_open.setSpecialValueText("Default")
        adv_layout.addRow("Max Open Connections:", self.max_open)
        
        self.max_idle = QSpinBox()
        self.max_idle.setRange(0, 1000)
        self.max_idle.setValue(0)
        self.max_idle.setSpecialValueText("Default")
        adv_layout.addRow("Max Idle Connections:", self.max_idle)
        
        self.max_lifetime = QLineEdit()
        self.max_lifetime.setPlaceholderText("e.g., 0s (unlimited)")
        adv_layout.addRow("Max Connection Lifetime:", self.max_lifetime)
        
        self.allowed_roles = QLineEdit()
        self.allowed_roles.setPlaceholderText("* for all, or comma-separated role names")
        adv_layout.addRow("Allowed Roles:", self.allowed_roles)
        
        self.verify_conn = QCheckBox("Verify connection on save")
        self.verify_conn.setChecked(True)
        adv_layout.addRow("", self.verify_conn)
        
        layout.addWidget(adv_group)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self._save)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _on_plugin_changed(self):
        """Update placeholder based on plugin type."""
        plugin = self.plugin_combo.currentData()
        
        placeholders = {
            'postgresql-database-plugin': 'postgresql://{{username}}:{{password}}@host:5432/dbname',
            'mysql-database-plugin': '{{username}}:{{password}}@tcp(host:3306)/dbname',
            'mssql-database-plugin': 'sqlserver://{{username}}:{{password}}@host:1433',
            'mongodb-database-plugin': 'mongodb://{{username}}:{{password}}@host:27017/admin',
            'oracle-database-plugin': '{{username}}/{{password}}@host:1521/ORCL',
        }
        
        self.conn_url.setPlaceholderText(
            placeholders.get(plugin, 'Connection string with {{username}} and {{password}} placeholders')
        )
    
    def _load_config(self):
        """Load existing config into form."""
        self.name_edit.setText(self.name)
        
        if 'plugin_name' in self.config:
            idx = self.plugin_combo.findData(self.config['plugin_name'])
            if idx >= 0:
                self.plugin_combo.setCurrentIndex(idx)
        
        self.conn_url.setText(self.config.get('connection_url', ''))
        self.username.setText(self.config.get('username', ''))
        # Don't load password for security
        
        self.max_open.setValue(self.config.get('max_open_connections', 4))
        self.max_idle.setValue(self.config.get('max_idle_connections', 0))
        self.max_lifetime.setText(self.config.get('max_connection_lifetime', ''))
        
        allowed = self.config.get('allowed_roles', [])
        if isinstance(allowed, list):
            self.allowed_roles.setText(','.join(allowed))
        else:
            self.allowed_roles.setText(str(allowed))
        
        self.verify_conn.setChecked(self.config.get('verify_connection', True))
    
    def _save(self):
        """Save the connection config."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Connection name is required")
            return
        
        if not self.conn_url.text().strip():
            QMessageBox.warning(self, "Error", "Connection URL is required")
            return
        
        config = {
            'plugin_name': self.plugin_combo.currentData(),
            'connection_url': self.conn_url.text().strip(),
            'verify_connection': self.verify_conn.isChecked(),
        }
        
        if self.username.text().strip():
            config['username'] = self.username.text().strip()
        
        if self.password.text():
            config['password'] = self.password.text()
        
        if self.max_open.value() > 0:
            config['max_open_connections'] = self.max_open.value()
        
        if self.max_idle.value() > 0:
            config['max_idle_connections'] = self.max_idle.value()
        
        if self.max_lifetime.text().strip():
            config['max_connection_lifetime'] = self.max_lifetime.text().strip()
        
        allowed = self.allowed_roles.text().strip()
        if allowed:
            config['allowed_roles'] = [r.strip() for r in allowed.split(',')]
        
        self.saved.emit(name, config)
        self.accept()


class DatabaseRoleDialog(QDialog):
    """Dialog for creating/editing database roles."""
    
    saved = Signal(str, dict)  # name, config
    
    def __init__(self, name: str = "", config: Dict = None, connections: List[str] = None,
                 is_static: bool = False, is_new: bool = True, parent=None):
        super().__init__(parent)
        self.name = name
        self.config = config or {}
        self.connections = connections or []
        self.is_static = is_static
        self.is_new = is_new
        
        title = "New Static Role" if is_static else "New Dynamic Role"
        if not is_new:
            title = f"Edit {'Static' if is_static else 'Dynamic'} Role: {name}"
        self.setWindowTitle(title)
        self.setMinimumSize(600, 500)
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # Role name
        self.name_edit = QLineEdit()
        self.name_edit.setEnabled(self.is_new)
        form.addRow("Role Name:", self.name_edit)
        
        # Database connection
        self.db_combo = QComboBox()
        for conn in self.connections:
            self.db_combo.addItem(conn)
        form.addRow("Database Connection:", self.db_combo)
        
        layout.addLayout(form)
        
        if self.is_static:
            # Static role specific
            static_group = QGroupBox("Static Role Settings")
            static_layout = QFormLayout(static_group)
            
            self.db_username = QLineEdit()
            self.db_username.setPlaceholderText("Existing database username to manage")
            static_layout.addRow("Database Username:", self.db_username)
            
            self.rotation_period = QLineEdit()
            self.rotation_period.setPlaceholderText("e.g., 24h, 7d")
            self.rotation_period.setText("24h")
            static_layout.addRow("Rotation Period:", self.rotation_period)
            
            layout.addWidget(static_group)
        else:
            # Dynamic role specific
            dynamic_group = QGroupBox("Dynamic Role Settings")
            dynamic_layout = QFormLayout(dynamic_group)
            
            self.default_ttl = QLineEdit()
            self.default_ttl.setPlaceholderText("e.g., 1h")
            self.default_ttl.setText("1h")
            dynamic_layout.addRow("Default TTL:", self.default_ttl)
            
            self.max_ttl = QLineEdit()
            self.max_ttl.setPlaceholderText("e.g., 24h")
            self.max_ttl.setText("24h")
            dynamic_layout.addRow("Max TTL:", self.max_ttl)
            
            layout.addWidget(dynamic_group)
        
        # SQL statements
        sql_group = QGroupBox("SQL Statements")
        sql_layout = QVBoxLayout(sql_group)
        
        sql_layout.addWidget(QLabel("Creation Statements:"))
        self.creation_sql = SyntaxHighlightedTextEdit(syntax=None)
        self.creation_sql.setPlaceholderText(
            "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}';\n"
            "GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";"
        )
        self.creation_sql.setMaximumHeight(120)
        sql_layout.addWidget(self.creation_sql)
        
        if not self.is_static:
            sql_layout.addWidget(QLabel("Revocation Statements:"))
            self.revocation_sql = SyntaxHighlightedTextEdit(syntax=None)
            self.revocation_sql.setPlaceholderText(
                "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM \"{{name}}\";\n"
                "DROP ROLE IF EXISTS \"{{name}}\";"
            )
            self.revocation_sql.setMaximumHeight(100)
            sql_layout.addWidget(self.revocation_sql)
            
            sql_layout.addWidget(QLabel("Rollback Statements (optional):"))
            self.rollback_sql = SyntaxHighlightedTextEdit(syntax=None)
            self.rollback_sql.setPlaceholderText("Optional: statements to run if creation fails")
            self.rollback_sql.setMaximumHeight(80)
            sql_layout.addWidget(self.rollback_sql)
        
        layout.addWidget(sql_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self._save)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _load_config(self):
        """Load existing config."""
        self.name_edit.setText(self.name)
        
        db_name = self.config.get('db_name', '')
        idx = self.db_combo.findText(db_name)
        if idx >= 0:
            self.db_combo.setCurrentIndex(idx)
        
        if self.is_static:
            self.db_username.setText(self.config.get('username', ''))
            self.rotation_period.setText(self.config.get('rotation_period', '24h'))
        else:
            self.default_ttl.setText(self.config.get('default_ttl', '1h'))
            self.max_ttl.setText(self.config.get('max_ttl', '24h'))
        
        creation = self.config.get('creation_statements', [])
        if isinstance(creation, list):
            self.creation_sql.setPlainText('\n'.join(creation))
        else:
            self.creation_sql.setPlainText(str(creation))
        
        if not self.is_static:
            revocation = self.config.get('revocation_statements', [])
            if isinstance(revocation, list):
                self.revocation_sql.setPlainText('\n'.join(revocation))
            else:
                self.revocation_sql.setPlainText(str(revocation))
            
            rollback = self.config.get('rollback_statements', [])
            if isinstance(rollback, list):
                self.rollback_sql.setPlainText('\n'.join(rollback))
            else:
                self.rollback_sql.setPlainText(str(rollback))
    
    def _save(self):
        """Save the role."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Role name is required")
            return
        
        if not self.db_combo.currentText():
            QMessageBox.warning(self, "Error", "Database connection is required")
            return
        
        creation = self.creation_sql.toPlainText().strip()
        if not creation:
            QMessageBox.warning(self, "Error", "Creation statements are required")
            return
        
        config = {
            'db_name': self.db_combo.currentText(),
            'creation_statements': [creation],
        }
        
        if self.is_static:
            if not self.db_username.text().strip():
                QMessageBox.warning(self, "Error", "Database username is required for static roles")
                return
            config['username'] = self.db_username.text().strip()
            config['rotation_period'] = self.rotation_period.text().strip() or '24h'
        else:
            config['default_ttl'] = self.default_ttl.text().strip() or '1h'
            config['max_ttl'] = self.max_ttl.text().strip() or '24h'
            
            revocation = self.revocation_sql.toPlainText().strip()
            if revocation:
                config['revocation_statements'] = [revocation]
            
            rollback = self.rollback_sql.toPlainText().strip()
            if rollback:
                config['rollback_statements'] = [rollback]
        
        self.saved.emit(name, config)
        self.accept()


class SSHRoleDialog(QDialog):
    """Dialog for creating/editing SSH roles."""
    
    saved = Signal(str, dict)  # name, config
    
    def __init__(self, name: str = "", config: Dict = None, is_new: bool = True, parent=None):
        super().__init__(parent)
        self.name = name
        self.config = config or {}
        self.is_new = is_new
        self.setWindowTitle("New SSH Role" if is_new else f"Edit SSH Role: {name}")
        self.setMinimumSize(600, 550)
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # Role name
        self.name_edit = QLineEdit()
        self.name_edit.setEnabled(self.is_new)
        form.addRow("Role Name:", self.name_edit)
        
        # Key type
        self.key_type = QComboBox()
        self.key_type.addItems(['ca', 'otp', 'dynamic'])
        self.key_type.currentTextChanged.connect(self._on_key_type_changed)
        form.addRow("Key Type:", self.key_type)
        
        layout.addLayout(form)
        
        # CA signing options (for 'ca' type)
        self.ca_group = QGroupBox("CA Certificate Options")
        ca_layout = QFormLayout(self.ca_group)
        
        self.default_user = QLineEdit()
        self.default_user.setPlaceholderText("e.g., ubuntu, ec2-user")
        ca_layout.addRow("Default Username:", self.default_user)
        
        self.allowed_users = QLineEdit()
        self.allowed_users.setPlaceholderText("Comma-separated list, or * for any")
        ca_layout.addRow("Allowed Users:", self.allowed_users)
        
        self.allowed_domains = QLineEdit()
        self.allowed_domains.setPlaceholderText("Comma-separated domains, or * for any")
        ca_layout.addRow("Allowed Domains:", self.allowed_domains)
        
        self.ttl = QLineEdit()
        self.ttl.setPlaceholderText("e.g., 30m, 1h")
        self.ttl.setText("30m")
        ca_layout.addRow("TTL:", self.ttl)
        
        self.max_ttl = QLineEdit()
        self.max_ttl.setPlaceholderText("e.g., 24h")
        self.max_ttl.setText("24h")
        ca_layout.addRow("Max TTL:", self.max_ttl)
        
        self.allow_user_certs = QCheckBox("Allow user certificates")
        self.allow_user_certs.setChecked(True)
        ca_layout.addRow("", self.allow_user_certs)
        
        self.allow_host_certs = QCheckBox("Allow host certificates")
        ca_layout.addRow("", self.allow_host_certs)
        
        layout.addWidget(self.ca_group)
        
        # OTP options (for 'otp' type)
        self.otp_group = QGroupBox("OTP Options")
        otp_layout = QFormLayout(self.otp_group)
        
        self.otp_default_user = QLineEdit()
        self.otp_default_user.setPlaceholderText("e.g., root")
        otp_layout.addRow("Default Username:", self.otp_default_user)
        
        self.cidr_list = QLineEdit()
        self.cidr_list.setPlaceholderText("e.g., 10.0.0.0/8, 192.168.0.0/16")
        otp_layout.addRow("CIDR List:", self.cidr_list)
        
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        otp_layout.addRow("Port:", self.port)
        
        layout.addWidget(self.otp_group)
        
        # Key options
        key_group = QGroupBox("Key Options")
        key_layout = QFormLayout(key_group)
        
        self.algorithm_signer = QComboBox()
        self.algorithm_signer.addItems(['', 'rsa-sha2-256', 'rsa-sha2-512', 'ssh-rsa'])
        key_layout.addRow("Algorithm Signer:", self.algorithm_signer)
        
        self.allowed_extensions = QLineEdit()
        self.allowed_extensions.setPlaceholderText("e.g., permit-pty,permit-port-forwarding")
        key_layout.addRow("Allowed Extensions:", self.allowed_extensions)
        
        self.default_extensions = QLineEdit()
        self.default_extensions.setPlaceholderText("Extensions to include by default")
        key_layout.addRow("Default Extensions:", self.default_extensions)
        
        layout.addWidget(key_group)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self._save)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        self._on_key_type_changed()
    
    def _on_key_type_changed(self):
        """Show/hide options based on key type."""
        key_type = self.key_type.currentText()
        self.ca_group.setVisible(key_type == 'ca')
        self.otp_group.setVisible(key_type == 'otp')
    
    def _load_config(self):
        """Load existing config."""
        self.name_edit.setText(self.name)
        
        key_type = self.config.get('key_type', 'ca')
        idx = self.key_type.findText(key_type)
        if idx >= 0:
            self.key_type.setCurrentIndex(idx)
        
        self.default_user.setText(self.config.get('default_user', ''))
        self.allowed_users.setText(self.config.get('allowed_users', ''))
        self.allowed_domains.setText(self.config.get('allowed_domains', ''))
        self.ttl.setText(self.config.get('ttl', '30m'))
        self.max_ttl.setText(self.config.get('max_ttl', '24h'))
        self.allow_user_certs.setChecked(self.config.get('allow_user_certificates', True))
        self.allow_host_certs.setChecked(self.config.get('allow_host_certificates', False))
        
        self.otp_default_user.setText(self.config.get('default_user', ''))
        self.cidr_list.setText(self.config.get('cidr_list', ''))
        self.port.setValue(self.config.get('port', 22))
        
        algo = self.config.get('algorithm_signer', '')
        idx = self.algorithm_signer.findText(algo)
        if idx >= 0:
            self.algorithm_signer.setCurrentIndex(idx)
        
        self.allowed_extensions.setText(self.config.get('allowed_extensions', ''))
        self.default_extensions.setText(self.config.get('default_extensions', ''))
    
    def _save(self):
        """Save the role."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Role name is required")
            return
        
        key_type = self.key_type.currentText()
        
        config = {'key_type': key_type}
        
        if key_type == 'ca':
            if self.default_user.text().strip():
                config['default_user'] = self.default_user.text().strip()
            if self.allowed_users.text().strip():
                config['allowed_users'] = self.allowed_users.text().strip()
            if self.allowed_domains.text().strip():
                config['allowed_domains'] = self.allowed_domains.text().strip()
            config['ttl'] = self.ttl.text().strip() or '30m'
            config['max_ttl'] = self.max_ttl.text().strip() or '24h'
            config['allow_user_certificates'] = self.allow_user_certs.isChecked()
            config['allow_host_certificates'] = self.allow_host_certs.isChecked()
        
        elif key_type == 'otp':
            if self.otp_default_user.text().strip():
                config['default_user'] = self.otp_default_user.text().strip()
            if self.cidr_list.text().strip():
                config['cidr_list'] = self.cidr_list.text().strip()
            config['port'] = self.port.value()
        
        if self.algorithm_signer.currentText():
            config['algorithm_signer'] = self.algorithm_signer.currentText()
        
        if self.allowed_extensions.text().strip():
            config['allowed_extensions'] = self.allowed_extensions.text().strip()
        
        if self.default_extensions.text().strip():
            config['default_extensions'] = self.default_extensions.text().strip()
        
        self.saved.emit(name, config)
        self.accept()


class AWSRoleDialog(QDialog):
    """Dialog for creating/editing AWS roles."""
    
    saved = Signal(str, dict)  # name, config
    
    def __init__(self, name: str = "", config: Dict = None, is_new: bool = True, parent=None):
        super().__init__(parent)
        self.name = name
        self.config = config or {}
        self.is_new = is_new
        self.setWindowTitle("New AWS Role" if is_new else f"Edit AWS Role: {name}")
        self.setMinimumSize(600, 500)
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # Role name
        self.name_edit = QLineEdit()
        self.name_edit.setEnabled(self.is_new)
        form.addRow("Role Name:", self.name_edit)
        
        # Credential type
        self.cred_type = QComboBox()
        self.cred_type.addItems(['iam_user', 'assumed_role', 'federation_token'])
        self.cred_type.currentTextChanged.connect(self._on_cred_type_changed)
        form.addRow("Credential Type:", self.cred_type)
        
        layout.addLayout(form)
        
        # IAM user options
        self.iam_group = QGroupBox("IAM User Options")
        iam_layout = QFormLayout(self.iam_group)
        
        self.policy_arns = QLineEdit()
        self.policy_arns.setPlaceholderText("Comma-separated ARNs, e.g., arn:aws:iam::aws:policy/ReadOnlyAccess")
        iam_layout.addRow("Policy ARNs:", self.policy_arns)
        
        iam_layout.addWidget(QLabel("Inline Policy (JSON):"))
        self.policy_document = SyntaxHighlightedTextEdit(syntax='json')
        self.policy_document.setPlaceholderText('{"Version": "2012-10-17", "Statement": [...]}')
        self.policy_document.setMaximumHeight(150)
        iam_layout.addRow(self.policy_document)
        
        layout.addWidget(self.iam_group)
        
        # Assumed role options
        self.assume_group = QGroupBox("Assumed Role Options")
        assume_layout = QFormLayout(self.assume_group)
        
        self.role_arns = QLineEdit()
        self.role_arns.setPlaceholderText("Comma-separated role ARNs to assume")
        assume_layout.addRow("Role ARNs:", self.role_arns)
        
        layout.addWidget(self.assume_group)
        
        # Common options
        common_group = QGroupBox("Common Options")
        common_layout = QFormLayout(common_group)
        
        self.default_ttl = QLineEdit()
        self.default_ttl.setPlaceholderText("e.g., 1h, 3600")
        common_layout.addRow("Default TTL:", self.default_ttl)
        
        self.max_ttl = QLineEdit()
        self.max_ttl.setPlaceholderText("e.g., 12h, 43200")
        common_layout.addRow("Max TTL:", self.max_ttl)
        
        self.user_path = QLineEdit()
        self.user_path.setPlaceholderText("/")
        common_layout.addRow("IAM User Path:", self.user_path)
        
        self.permissions_boundary = QLineEdit()
        self.permissions_boundary.setPlaceholderText("ARN of permissions boundary policy")
        common_layout.addRow("Permissions Boundary:", self.permissions_boundary)
        
        layout.addWidget(common_group)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self._save)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        self._on_cred_type_changed()
    
    def _on_cred_type_changed(self):
        """Show/hide options based on credential type."""
        cred_type = self.cred_type.currentText()
        self.iam_group.setVisible(cred_type == 'iam_user')
        self.assume_group.setVisible(cred_type in ['assumed_role', 'federation_token'])
    
    def _load_config(self):
        """Load existing config."""
        self.name_edit.setText(self.name)
        
        cred_type = self.config.get('credential_type', 'iam_user')
        idx = self.cred_type.findText(cred_type)
        if idx >= 0:
            self.cred_type.setCurrentIndex(idx)
        
        policy_arns = self.config.get('policy_arns', [])
        if isinstance(policy_arns, list):
            self.policy_arns.setText(','.join(policy_arns))
        else:
            self.policy_arns.setText(str(policy_arns))
        
        policy_doc = self.config.get('policy_document', '')
        if isinstance(policy_doc, dict):
            self.policy_document.setPlainText(json.dumps(policy_doc, indent=2))
        else:
            self.policy_document.setPlainText(str(policy_doc))
        
        role_arns = self.config.get('role_arns', [])
        if isinstance(role_arns, list):
            self.role_arns.setText(','.join(role_arns))
        else:
            self.role_arns.setText(str(role_arns))
        
        self.default_ttl.setText(self.config.get('default_sts_ttl', ''))
        self.max_ttl.setText(self.config.get('max_sts_ttl', ''))
        self.user_path.setText(self.config.get('user_path', ''))
        self.permissions_boundary.setText(self.config.get('permissions_boundary_arn', ''))
    
    def _save(self):
        """Save the role."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Role name is required")
            return
        
        cred_type = self.cred_type.currentText()
        
        config = {'credential_type': cred_type}
        
        if cred_type == 'iam_user':
            if self.policy_arns.text().strip():
                config['policy_arns'] = [a.strip() for a in self.policy_arns.text().split(',') if a.strip()]
            
            policy_doc = self.policy_document.toPlainText().strip()
            if policy_doc:
                try:
                    config['policy_document'] = json.loads(policy_doc)
                except json.JSONDecodeError as e:
                    QMessageBox.warning(self, "Error", f"Invalid policy JSON: {e}")
                    return
        
        if cred_type in ['assumed_role', 'federation_token']:
            if self.role_arns.text().strip():
                config['role_arns'] = [a.strip() for a in self.role_arns.text().split(',') if a.strip()]
        
        if self.default_ttl.text().strip():
            config['default_sts_ttl'] = self.default_ttl.text().strip()
        
        if self.max_ttl.text().strip():
            config['max_sts_ttl'] = self.max_ttl.text().strip()
        
        if self.user_path.text().strip():
            config['user_path'] = self.user_path.text().strip()
        
        if self.permissions_boundary.text().strip():
            config['permissions_boundary_arn'] = self.permissions_boundary.text().strip()
        
        self.saved.emit(name, config)
        self.accept()



class CloudRoleDialog(QDialog):
    """Dialog for creating/editing cloud provider roles (GCP, Azure, AliCloud, Oracle, DigitalOcean)."""
    
    saved = Signal(str, dict)  # name, config
    
    # Cloud provider role templates
    CLOUD_ROLE_TEMPLATES = {
        'gcp': {
            'name': 'Google Cloud',
            'fields': {
                'type': {'label': 'Secret Type', 'type': 'combo', 'options': ['access_token', 'service_account_key'], 'default': 'access_token'},
                'project': {'label': 'GCP Project', 'type': 'string', 'required': True},
                'bindings': {'label': 'IAM Bindings (HCL)', 'type': 'text', 'default': 'resource "//cloudresourcemanager.googleapis.com/projects/PROJECT_ID" {\n  roles = ["roles/viewer"]\n}'},
                'token_scopes': {'label': 'Token Scopes (comma-separated)', 'type': 'string', 'default': 'https://www.googleapis.com/auth/cloud-platform'},
            }
        },
        'azure': {
            'name': 'Microsoft Azure',
            'fields': {
                'azure_roles': {'label': 'Azure Roles (JSON array)', 'type': 'text', 'default': '[{"role_name": "Reader", "scope": "/subscriptions/SUBSCRIPTION_ID"}]'},
                'ttl': {'label': 'TTL', 'type': 'string', 'default': '1h'},
                'max_ttl': {'label': 'Max TTL', 'type': 'string', 'default': '24h'},
                'application_object_id': {'label': 'Application Object ID (optional)', 'type': 'string'},
            }
        },
        'alicloud': {
            'name': 'Alibaba Cloud',
            'fields': {
                'remote_policies': {'label': 'Remote Policies (JSON array)', 'type': 'text', 'default': '[{"policy_name": "AliyunOSSReadOnlyAccess", "policy_type": "System"}]'},
                'inline_policies': {'label': 'Inline Policies (JSON)', 'type': 'text'},
                'role_arn': {'label': 'Role ARN (for assume_role)', 'type': 'string'},
                'ttl': {'label': 'TTL', 'type': 'string', 'default': '3600s'},
                'max_ttl': {'label': 'Max TTL', 'type': 'string', 'default': '86400s'},
            }
        },
        'oracle': {
            'name': 'Oracle Cloud',
            'fields': {
                'ocid': {'label': 'User OCID', 'type': 'string', 'required': True},
                'home_tenancy_id': {'label': 'Home Tenancy ID', 'type': 'string'},
                'ttl': {'label': 'TTL', 'type': 'string', 'default': '1h'},
                'max_ttl': {'label': 'Max TTL', 'type': 'string', 'default': '24h'},
            }
        },
        'digitalocean': {
            'name': 'DigitalOcean',
            'fields': {
                'token_scopes': {'label': 'Token Scopes (comma-separated)', 'type': 'string', 'default': 'read,write'},
                'ttl': {'label': 'TTL', 'type': 'string', 'default': '3600s'},
                'max_ttl': {'label': 'Max TTL', 'type': 'string', 'default': '86400s'},
            }
        },
    }
    
    def __init__(self, cloud_type: str, name: str = "", config: Dict = None, is_new: bool = True, parent=None):
        super().__init__(parent)
        self.cloud_type = cloud_type
        self.name = name
        self.config = config or {}
        self.is_new = is_new
        self.field_widgets = {}
        
        provider = self.CLOUD_ROLE_TEMPLATES.get(cloud_type, {})
        provider_name = provider.get('name', cloud_type.upper())
        
        self.setWindowTitle(f"New {provider_name} Role" if is_new else f"Edit {provider_name} Role: {name}")
        self.setMinimumSize(600, 450)
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        provider = self.CLOUD_ROLE_TEMPLATES.get(self.cloud_type, {})
        fields = provider.get('fields', {})
        
        form = QFormLayout()
        
        # Role name
        self.name_edit = QLineEdit()
        self.name_edit.setEnabled(self.is_new)
        form.addRow("Role Name:", self.name_edit)
        
        layout.addLayout(form)
        
        # Dynamic fields based on cloud type
        fields_group = QGroupBox("Role Configuration")
        fields_layout = QFormLayout(fields_group)
        
        for field_name, field_info in fields.items():
            label = field_info.get('label', field_name)
            field_type = field_info.get('type', 'string')
            default = field_info.get('default', '')
            
            if field_type == 'combo':
                widget = QComboBox()
                widget.addItems(field_info.get('options', []))
                if default:
                    idx = widget.findText(default)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
            elif field_type == 'text':
                widget = SyntaxHighlightedTextEdit(syntax=None)
                widget.setPlaceholderText(str(default))
                widget.setMaximumHeight(120)
            else:
                widget = QLineEdit()
                widget.setPlaceholderText(str(default))
            
            self.field_widgets[field_name] = widget
            fields_layout.addRow(f"{label}:", widget)
        
        layout.addWidget(fields_group)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self._save)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _load_config(self):
        """Load existing config."""
        self.name_edit.setText(self.name)
        
        for field_name, widget in self.field_widgets.items():
            value = self.config.get(field_name, '')
            
            if isinstance(widget, QComboBox):
                idx = widget.findText(str(value))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
                if isinstance(value, (dict, list)):
                    widget.setPlainText(json.dumps(value, indent=2))
                else:
                    widget.setPlainText(str(value) if value else '')
            else:
                if isinstance(value, list):
                    widget.setText(','.join(value))
                else:
                    widget.setText(str(value) if value else '')
    
    def _save(self):
        """Save the role."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Role name is required")
            return
        
        provider = self.CLOUD_ROLE_TEMPLATES.get(self.cloud_type, {})
        fields = provider.get('fields', {})
        
        config = {}
        
        for field_name, widget in self.field_widgets.items():
            field_info = fields.get(field_name, {})
            
            if isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
                text = widget.toPlainText().strip()
                # Try to parse as JSON for certain fields
                if text and field_name in ('azure_roles', 'remote_policies', 'inline_policies'):
                    try:
                        value = json.loads(text)
                    except json.JSONDecodeError:
                        value = text
                else:
                    value = text
            else:
                text = widget.text().strip()
                # Convert comma-separated to list for certain fields
                if text and field_name in ('token_scopes',):
                    value = [s.strip() for s in text.split(',')]
                else:
                    value = text
            
            if value:
                config[field_name] = value
        
        self.saved.emit(name, config)
        self.accept()
