"""System tray widget for OpenTongchi"""

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication, QMessageBox
)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
from PyQt6.QtCore import Qt, QSize

from .config import Config
from .dialogs import SettingsDialog, JsonTableDialog
from .openbao import OpenBaoMenuBuilder
from .consul import ConsulMenuBuilder
from .nomad import NomadMenuBuilder
from .opentofu import OpenTofuMenuBuilder
from .background import BackgroundTaskManager


def create_default_icon() -> QIcon:
    """Create a default icon for the tray"""
    # Create a simple icon with "OT" text
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Draw background circle
    painter.setBrush(QColor(64, 156, 255))  # Blue
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    
    # Draw text
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Arial", 20, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "OT")
    
    painter.end()
    
    return QIcon(pixmap)


class OpenTongchiTray(QSystemTrayIcon):
    """Main system tray widget"""
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        
        # Set icon
        self.setIcon(create_default_icon())
        self.setToolTip("OpenTongchi - Infrastructure Management")
        
        # Create menu builders
        self.openbao_builder = OpenBaoMenuBuilder(config)
        self.consul_builder = ConsulMenuBuilder(config)
        self.nomad_builder = NomadMenuBuilder(config)
        self.opentofu_builder = OpenTofuMenuBuilder(config)
        
        # Background task manager
        self.background_manager = BackgroundTaskManager(config)
        self.background_manager.token_renewed.connect(self._on_token_renewed)
        self.background_manager.token_error.connect(self._on_token_error)
        self.background_manager.lease_expired.connect(self._on_lease_expired)
        
        # Give nomad builder access to tray for alerts
        self.nomad_builder.tray_icon = self
        
        # Create menu
        self.menu = QMenu()
        self.build_menu()
        self.setContextMenu(self.menu)
        
        # Connect signals
        self.activated.connect(self._on_activated)
        
        # Start background tasks
        self.background_manager.start()
        
        # Start Nomad refresh timer
        self.nomad_builder.start_refresh_timer()
    
    def build_menu(self):
        """Build the main menu"""
        self.menu.clear()
        
        # Header
        header = self.menu.addAction("🌐 OpenTongchi")
        header.setEnabled(False)
        self.menu.addSeparator()
        
        # Product menus
        self.openbao_builder.build_menu(self.menu)
        self.consul_builder.build_menu(self.menu)
        self.nomad_builder.build_menu(self.menu)
        self.opentofu_builder.build_menu(self.menu)
        
        self.menu.addSeparator()
        
        # Namespace
        ns_action = self.menu.addAction(f"🏷️ Namespace: {self.config.global_namespace or '(default)'}")
        ns_action.triggered.connect(self._show_namespace_dialog)
        
        # Background tasks status
        bg_menu = self.menu.addMenu("⏰ Background Tasks")
        self._build_background_menu(bg_menu)
        
        self.menu.addSeparator()
        
        # Settings
        settings_action = self.menu.addAction("⚙️ Settings...")
        settings_action.triggered.connect(self._show_settings)
        
        # About
        about_action = self.menu.addAction("ℹ️ About")
        about_action.triggered.connect(self._show_about)
        
        self.menu.addSeparator()
        
        # Quit
        quit_action = self.menu.addAction("🚪 Quit")
        quit_action.triggered.connect(self._quit)
    
    def _build_background_menu(self, menu: QMenu):
        """Build the background tasks submenu"""
        # Status
        status = self.background_manager.get_status()
        running = status.get("running", False)
        
        status_action = menu.addAction(f"{'🟢' if running else '🔴'} Status: {'Running' if running else 'Stopped'}")
        status_action.triggered.connect(self._show_background_status)
        
        menu.addSeparator()
        
        # Token renewal info
        token_info = status.get("token_renewal", {})
        if token_info.get("enabled"):
            token_action = menu.addAction(f"🔑 Token Renewal: Every {token_info.get('interval', 0)}s")
            token_action.setEnabled(False)
        else:
            token_action = menu.addAction("🔑 Token Renewal: Disabled")
            token_action.setEnabled(False)
        
        # Lease renewal info
        lease_info = status.get("lease_renewal", {})
        if lease_info.get("enabled"):
            lease_action = menu.addAction(
                f"📄 Lease Renewal: {lease_info.get('tracked_leases', 0)} tracked"
            )
            lease_action.setEnabled(False)
        else:
            lease_action = menu.addAction("📄 Lease Renewal: Disabled")
            lease_action.setEnabled(False)
        
        menu.addSeparator()
        
        # Control actions
        if running:
            stop_action = menu.addAction("⏹️ Stop Tasks")
            stop_action.triggered.connect(self._stop_background_tasks)
        else:
            start_action = menu.addAction("▶️ Start Tasks")
            start_action.triggered.connect(self._start_background_tasks)
    
    def _on_activated(self, reason):
        """Handle tray icon activation"""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.Context):
            # Show menu on click
            self.menu.popup(self.geometry().center())
    
    def _show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self.config)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()
    
    def _on_settings_changed(self):
        """Handle settings change"""
        # Rebuild menu to pick up new settings
        self.build_menu()
        
        # Restart background tasks
        self.background_manager.restart()
        
        # Restart Nomad refresh
        self.nomad_builder.stop_refresh_timer()
        self.nomad_builder.start_refresh_timer()
    
    def _show_namespace_dialog(self):
        """Show dialog to change global namespace"""
        from PyQt6.QtWidgets import QInputDialog
        
        current = self.config.global_namespace or ""
        namespace, ok = QInputDialog.getText(
            None, "Global Namespace",
            "Enter namespace (leave empty for default):",
            text=current
        )
        
        if ok:
            self.config.set_global_namespace(namespace)
            self.config.save()
            self.build_menu()
    
    def _show_background_status(self):
        """Show background tasks status"""
        status = self.background_manager.get_status()
        dialog = JsonTableDialog("⏰ Background Tasks Status", status, readonly=True)
        dialog.exec()
    
    def _start_background_tasks(self):
        """Start background tasks"""
        self.background_manager.start()
        self.build_menu()
    
    def _stop_background_tasks(self):
        """Stop background tasks"""
        self.background_manager.stop()
        self.build_menu()
    
    def _on_token_renewed(self, result: dict):
        """Handle token renewal success"""
        # Optionally show notification
        pass
    
    def _on_token_error(self, error: str):
        """Handle token renewal error"""
        self.showMessage(
            "Token Renewal Failed",
            f"Failed to renew token: {error}",
            QSystemTrayIcon.MessageIcon.Warning,
            3000
        )
    
    def _on_lease_expired(self, lease_id: str):
        """Handle lease expiration"""
        self.showMessage(
            "Lease Expired",
            f"Lease {lease_id[:8]}... has expired",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )
    
    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            None,
            "About OpenTongchi",
            """<h2>OpenTongchi</h2>
            <p>Version 0.1.0</p>
            <p>A system tray widget for managing open source infrastructure tools.</p>
            <p>Supports:</p>
            <ul>
                <li>🔐 OpenBao (Vault-compatible secrets management)</li>
                <li>🔍 Consul (Service discovery and KV store)</li>
                <li>📦 Nomad (Workload orchestration)</li>
                <li>🏗️ OpenTofu (Infrastructure as Code)</li>
            </ul>
            <p>Licensed under MIT License</p>
            """
        )
    
    def _quit(self):
        """Quit the application"""
        # Stop background tasks
        self.background_manager.stop()
        self.nomad_builder.stop_refresh_timer()
        
        # Quit
        QApplication.quit()
