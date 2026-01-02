"""Packer Menu Builder for OpenTongchi"""

from typing import Dict, Optional
from PySide6.QtWidgets import QMenu, QMessageBox, QTextEdit, QDialog, QVBoxLayout, QPushButton
from PySide6.QtCore import QObject, Signal
from app.clients.packer import PackerClient
from app.async_menu import AsyncMenu
from app.dialogs import JsonEditorDialog


class PackerMenuBuilder(QObject):
    notification = Signal(str, str)
    
    def __init__(self, settings, process_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        self._client: Optional[PackerClient] = None
    
    @property
    def client(self) -> PackerClient:
        if self._client is None:
            self._client = PackerClient(self.settings.packer)
        return self._client
    
    def build_menu(self) -> QMenu:
        menu = QMenu("📦 Packer")
        
        # Templates
        templates_menu = self._create_templates_menu()
        menu.addMenu(templates_menu)
        
        menu.addSeparator()
        
        # Plugins
        plugins_menu = self._create_plugins_menu()
        menu.addMenu(plugins_menu)
        
        return menu
    
    def _create_templates_menu(self) -> QMenu:
        menu = AsyncMenu("📁 Templates", self._load_templates)
        menu.set_submenu_factory(self._create_template_submenu)
        return menu
    
    def _load_templates(self) -> list:
        templates = self.client.list_templates()
        items = []
        for t in templates:
            name = t.get('name', 'unknown')
            status = self.client.get_template_status(name)
            emoji = self.client.get_status_emoji(status)
            items.append({'text': f"{emoji} {name}", 'data': t, 'is_submenu': True})
        return items
    
    def _create_template_submenu(self, title: str, data: Dict) -> QMenu:
        template_name = data.get('name', '')
        menu = QMenu(title)
        
        # Info
        info = menu.addAction("ℹ️ Template Info")
        info.triggered.connect(lambda: self._show_template_info(template_name))
        
        menu.addSeparator()
        
        # Actions
        init = menu.addAction("📥 Initialize")
        init.triggered.connect(lambda: self._init_template(template_name))
        
        validate = menu.addAction("✓ Validate")
        validate.triggered.connect(lambda: self._validate_template(template_name))
        
        fmt = menu.addAction("🎨 Format")
        fmt.triggered.connect(lambda: self._format_template(template_name))
        
        menu.addSeparator()
        
        build = menu.addAction("🔨 Build")
        build.triggered.connect(lambda: self._build_template(template_name))
        
        menu.addSeparator()
        
        # Logs
        logs_menu = AsyncMenu("📜 Logs", lambda: self._load_logs(template_name))
        logs_menu.set_item_callback(lambda d: self._show_log(template_name, d.get('name', '')))
        menu.addMenu(logs_menu)
        
        return menu
    
    def _create_plugins_menu(self) -> QMenu:
        menu = QMenu("🔌 Plugins")
        
        installed = menu.addAction("📋 Installed Plugins")
        installed.triggered.connect(self._show_installed_plugins)
        
        return menu
    
    def _load_logs(self, template_name: str) -> list:
        logs = self.client.list_logs(template_name)
        return [{'text': f"📄 {log['name']}", 'data': log} for log in logs]
    
    # Action handlers
    def _show_template_info(self, template_name: str):
        info = self.client.get_template_info(template_name)
        dialog = JsonEditorDialog(f"Template: {template_name}", info, readonly=True)
        dialog.exec()
    
    def _init_template(self, template_name: str):
        def do_init():
            return self.client.init(template_name)
        
        self.process_manager.start_process(
            name=f"Packer Init {template_name}",
            description=f"Initializing {template_name}",
            func=do_init
        )
        self.notification.emit("Initialize Started", f"Initializing {template_name}")
    
    def _validate_template(self, template_name: str):
        result = self.client.validate(template_name)
        if result.get('success'):
            QMessageBox.information(None, "Validation", "✓ Template is valid")
        else:
            QMessageBox.warning(None, "Validation Failed", 
                               result.get('stderr', result.get('error', 'Unknown error')))
    
    def _format_template(self, template_name: str):
        result = self.client.fmt(template_name)
        if result.get('success'):
            self.notification.emit("Formatted", f"Template {template_name} formatted")
        else:
            QMessageBox.warning(None, "Format Failed",
                               result.get('stderr', result.get('error', 'Unknown error')))
    
    def _build_template(self, template_name: str):
        reply = QMessageBox.question(
            None, "Build Image",
            f"Start build for {template_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        def do_build():
            return self.client.build(template_name)
        
        self.process_manager.start_process(
            name=f"Packer Build {template_name}",
            description=f"Building image from {template_name}",
            func=do_build
        )
        self.notification.emit("Build Started", f"Building {template_name}")
    
    def _show_log(self, template_name: str, log_name: str):
        content = self.client.read_log(template_name, log_name)
        
        dialog = QDialog()
        dialog.setWindowTitle(f"Log: {log_name}")
        dialog.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setPlainText(content)
        text.setReadOnly(True)
        layout.addWidget(text)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def _show_installed_plugins(self):
        result = self.client.plugins_installed()
        plugins = result.get('plugins', [])
        dialog = JsonEditorDialog("Installed Plugins", {'plugins': plugins}, readonly=True)
        dialog.exec()
