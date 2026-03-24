"""
OpenTongchi System Tray Application
Main systray widget that integrates all menu builders and functionality.
"""

import os
from typing import Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication, QMessageBox
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject, Signal, Slot, QTimer

from app.settings import SettingsManager
from app.process_manager import ProcessManager, TokenRenewalManager, ProcessStatus, SoundManager
from app.dialogs import SettingsDialog
from app.menus import (
    OpenBaoMenuBuilder,
    ConsulMenuBuilder,
    NomadMenuBuilder,
    BoundaryMenuBuilder,
    OpenTofuMenuBuilder,
    PackerMenuBuilder,
    HCPMenuBuilder,
)


class OpenTongchiTray(QObject):
    """Main system tray application."""
    
    def __init__(self, app: QApplication, settings: SettingsManager):
        super().__init__()
        self.app = app
        self.settings = settings
        
        # Initialize process manager
        self.process_manager = ProcessManager(self)
        self.process_manager.process_finished.connect(self._on_process_finished)
        self.process_manager.process_failed.connect(self._on_process_failed)
        
        # Initialize sound manager
        self.sound_manager = SoundManager(settings, self)
        
        # Initialize token renewal manager
        self.renewal_manager = TokenRenewalManager(
            settings, self.process_manager, self
        )
        
        # Initialize menu builders
        self._init_menu_builders()
        
        # Create system tray icon
        self._create_tray_icon()
        
        # Connect notifications
        self._connect_notifications()
        
        # Start background services
        self._start_background_services()
    
    def _init_menu_builders(self):
        """Initialize all menu builders."""
        self.openbao_menu = OpenBaoMenuBuilder(
            self.settings, self.process_manager, self
        )
        self.consul_menu = ConsulMenuBuilder(
            self.settings, self.process_manager, self
        )
        self.nomad_menu = NomadMenuBuilder(
            self.settings, self.process_manager, self
        )
        self.boundary_menu = BoundaryMenuBuilder(
            self.settings, self.process_manager, self
        )
        self.opentofu_menu = OpenTofuMenuBuilder(
            self.settings, self.process_manager, self
        )
        self.packer_menu = PackerMenuBuilder(
            self.settings, self.process_manager, self
        )
        self.hcp_menu = HCPMenuBuilder(
            self.settings, self.process_manager, self
        )
    
    def _create_tray_icon(self):
        """Create and configure the system tray icon."""
        self.tray = QSystemTrayIcon(self)
        
        # Load icon
        icon_path = self._find_icon()
        if icon_path and os.path.exists(icon_path):
            self.tray.setIcon(QIcon(icon_path))
        else:
            # Use spoon emoji as fallback icon
            self.tray.setIcon(self._create_emoji_icon("🥄"))
        
        self.tray.setToolTip("OpenTongchi (汤匙) - Infrastructure Manager")
        
        # Create context menu
        self._create_menu()
        
        # Connect signals
        self.tray.activated.connect(self._on_tray_activated)
    
    def _create_emoji_icon(self, emoji: str, size: int = 64) -> QIcon:
        """Create a QIcon from an emoji character."""
        from PySide6.QtGui import QPixmap, QPainter, QFont
        from PySide6.QtCore import Qt, QRect
        
        # Create a pixmap to render the emoji
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        # Paint the emoji onto the pixmap
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # Use a large font that supports emoji
        font = QFont()
        font.setPointSize(int(size * 0.7))
        font.setFamily("Noto Color Emoji, Apple Color Emoji, Segoe UI Emoji, sans-serif")
        painter.setFont(font)
        
        # Draw emoji centered
        rect = QRect(0, 0, size, size)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, emoji)
        painter.end()
        
        return QIcon(pixmap)
    
    def _find_icon(self) -> Optional[str]:
        """Find the application icon."""
        # Supported icon formats in preference order
        formats = ["webp", "png", "svg"]
        
        # Check paths in priority order
        base_paths = [
            # Package data path (works after pip install)
            os.path.join(os.path.dirname(__file__), "img", "opentongchi"),
            # Development paths
            "../img/opentongchi",
            "img/opentongchi",
            # User local install
            os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/opentongchi"),
            os.path.expanduser("~/.local/share/icons/hicolor/128x128/apps/opentongchi"),
            os.path.expanduser("~/.local/share/icons/hicolor/64x64/apps/opentongchi"),
            os.path.expanduser("~/.local/share/icons/hicolor/48x48/apps/opentongchi"),
            os.path.expanduser("~/.local/share/opentongchi/opentongchi"),
            # System hicolor theme (standard locations)
            "/usr/share/icons/hicolor/256x256/apps/opentongchi",
            "/usr/share/icons/hicolor/128x128/apps/opentongchi",
            "/usr/share/icons/hicolor/64x64/apps/opentongchi",
            "/usr/share/icons/hicolor/48x48/apps/opentongchi",
            # Pixmaps fallback
            "/usr/share/pixmaps/opentongchi",
            # Legacy flat path
            "/usr/share/icons/opentongchi",
        ]
        
        for base_path in base_paths:
            for fmt in formats:
                full_path = f"{base_path}.{fmt}"
                if os.path.exists(full_path):
                    return full_path
        
        return None
    
    def _create_menu(self):
        """Create the main context menu."""
        self.menu = QMenu()
        
        # Title - now clickable and shows About
        title = self.menu.addAction("🏠 OpenTongchi")
        title.triggered.connect(self._show_about)
        self.menu.addSeparator()
        
        # Running processes section
        self._processes_menu = QMenu("⚡ Processes")
        self._update_processes_menu()
        self.menu.addMenu(self._processes_menu)
        self.menu.addSeparator()
        
        # Product menus
        self.menu.addMenu(self.openbao_menu.build_menu())
        self.menu.addMenu(self.consul_menu.build_menu())
        self.menu.addMenu(self.nomad_menu.build_menu())
        self.menu.addMenu(self.boundary_menu.build_menu())
        self.menu.addMenu(self.opentofu_menu.build_menu())
        self.menu.addMenu(self.packer_menu.build_menu())
        self.menu.addSeparator()
        self.menu.addMenu(self.hcp_menu.build_menu())
        self.menu.addMenu(self.hcp_menu.build_tf_menu())
        
        self.menu.addSeparator()
        
        # Settings
        settings_action = self.menu.addAction("⚙️ Settings...")
        settings_action.triggered.connect(self._show_settings)
        
        # Refresh
        refresh_action = self.menu.addAction("🔄 Refresh All")
        refresh_action.triggered.connect(self._refresh_all)
        
        self.menu.addSeparator()
        
        # Quit
        quit_action = self.menu.addAction("🚪 Quit")
        quit_action.triggered.connect(self._quit)
        
        self.tray.setContextMenu(self.menu)
        
        # Update processes menu periodically
        self._processes_timer = QTimer(self)
        self._processes_timer.timeout.connect(self._update_processes_menu)
        self._processes_timer.start(1000)
    
    def _update_processes_menu(self):
        """Update the running processes menu."""
        self._processes_menu.clear()
        
        running = self.process_manager.get_running_processes()
        recent = self.process_manager.get_recent_processes(5)
        
        if running:
            for process in running:
                emoji = process.status_emoji
                action = self._processes_menu.addAction(
                    f"{emoji} {process.name} ({process.runtime_str})"
                )
                if process.cancellable:
                    action.triggered.connect(
                        lambda checked, pid=process.id: self._cancel_process(pid)
                    )
            
            self._processes_menu.addSeparator()
            cancel_all = self._processes_menu.addAction("🚫 Cancel All")
            cancel_all.triggered.connect(self._cancel_all_processes)
        else:
            no_processes = self._processes_menu.addAction("(No running processes)")
            no_processes.setEnabled(False)
        
        # Recent completed
        completed = [p for p in recent if p.status != ProcessStatus.RUNNING]
        if completed:
            self._processes_menu.addSeparator()
            history_label = self._processes_menu.addAction("📜 Recent:")
            history_label.setEnabled(False)
            
            for process in completed[:3]:
                emoji = process.status_emoji
                self._processes_menu.addAction(
                    f"  {emoji} {process.name} - {process.status.value}"
                ).setEnabled(False)
    
    def _connect_notifications(self):
        """Connect notification signals from all menu builders."""
        builders = [
            self.openbao_menu,
            self.consul_menu,
            self.nomad_menu,
            self.boundary_menu,
            self.opentofu_menu,
            self.packer_menu,
            self.hcp_menu,
        ]
        
        for builder in builders:
            builder.notification.connect(self._show_notification)

        # Rebuild menu when HCP org/project context changes
        self.hcp_menu.context_changed.connect(self._create_menu)

        # Connect Nomad job status changes
        self.nomad_menu.job_status_changed.connect(self._on_nomad_job_changed)
    
    def _start_background_services(self):
        """Start background services like token renewal."""
        # Start OpenBao token renewal if configured
        if (self.settings.openbao.address and 
            self.settings.openbao.token and
            self.settings.openbao.auto_renew_token):
            self.renewal_manager.start_openbao_renewal()
        
        # Start Nomad status monitoring
        if self.settings.nomad.address:
            self.nomad_menu.start_monitoring()
    
    def show(self):
        """Show the system tray icon."""
        self.tray.show()
    
    def hide(self):
        """Hide the system tray icon."""
        self.tray.hide()
    
    # Event handlers
    
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Left click - open settings dialog
            self._show_settings()
    
    def _on_process_finished(self, process_id: str):
        """Handle process completion."""
        process = self.process_manager.get_process(process_id)
        if process:
            # Play success sound
            self.sound_manager.play_success()
            
            if self.settings.global_settings.show_notifications:
                self._show_notification(
                    "Process Complete",
                    f"{process.name} completed successfully"
                )
    
    def _on_process_failed(self, process_id: str, error: str):
        """Handle process failure."""
        process = self.process_manager.get_process(process_id)
        if process:
            # Play error sound
            self.sound_manager.play_error()
            
            if self.settings.global_settings.show_notifications:
                self._show_notification(
                    "Process Failed",
                    f"{process.name}: {error}"
                )
    
    def _on_nomad_job_changed(self, job_id: str, status: str):
        """Handle Nomad job status change."""
        if self.settings.global_settings.show_notifications:
            self._show_notification(
                "Nomad Job Status",
                f"Job {job_id} is now {status}"
            )
    
    @Slot(str, str)
    def _show_notification(self, title: str, message: str):
        """Show a system notification."""
        if self.settings.global_settings.show_notifications:
            self.tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
    
    def _cancel_process(self, process_id: str):
        """Cancel a running process."""
        if self.process_manager.cancel_process(process_id):
            self._show_notification("Process Cancelled", "Process was cancelled")
    
    def _cancel_all_processes(self):
        """Cancel all running processes."""
        for process in self.process_manager.get_running_processes():
            self.process_manager.cancel_process(process.id)
    
    def _show_settings(self):
        """Show the settings dialog."""
        # Check if dialog already exists and is visible
        if hasattr(self, '_settings_dialog') and self._settings_dialog is not None:
            if self._settings_dialog.isVisible():
                # Bring existing dialog to front
                self._settings_dialog.raise_()
                self._settings_dialog.activateWindow()
                return
        
        # Create new modal dialog
        self._settings_dialog = SettingsDialog(self.settings)
        self._settings_dialog.setModal(True)
        self._settings_dialog.settings_saved.connect(self._on_settings_saved)
        self._settings_dialog.exec()
        self._settings_dialog = None
    
    def _on_settings_saved(self):
        """Handle settings being saved."""
        # Refresh all clients with new settings
        self._refresh_all()
        
        # Restart background services
        self.renewal_manager.stop_all()
        self.nomad_menu.stop_monitoring()
        self._start_background_services()
    
    def _refresh_all(self):
        """Refresh all menu builders."""
        self.openbao_menu.refresh_client()
        self.consul_menu.refresh_client()
        self.nomad_menu.refresh_client()
        self.boundary_menu.refresh_client()
        self.opentofu_menu.refresh_clients()
        self.packer_menu.refresh_client()
        self.hcp_menu.refresh_client()
        
        # Rebuild menu
        self._create_menu()
        
        self._show_notification("Refreshed", "All connections refreshed")
    
    def _show_about(self):
        """Show about dialog."""
        from app import __version__
        QMessageBox.about(
            None,
            "About OpenTongchi",
            f"""<h3>OpenTongchi (汤匙)</h3>
            <p>System Tray Manager for Open Source Infrastructure Tools</p>
            <p>Version {__version__}</p>
            <p>Manage OpenBao, Consul, Nomad, Boundary, OpenTofu, Packer, 
            and HashiCorp Cloud Platform (HCP) from your system tray.</p>
            <p>Licensed under MPL-2.0</p>
            <hr>
            <p><b>Authors:</b> John Boero and Claude, buddies 4ever 🤝</p>
            <hr>
            <p><b>Features:</b></p>
            <ul>
                <li>🔐 OpenBao secrets and auth management</li>
                <li>🔍 Consul service discovery and KV store</li>
                <li>📦 Nomad job orchestration</li>
                <li>🚪 Boundary secure access</li>
                <li>🏗️ OpenTofu infrastructure management</li>
                <li>📦 Packer image building</li>
                <li>☁️ HCP: Terraform, Vault Secrets, Vault Dedicated,
                    Packer Registry, Boundary, Consul, Waypoint, HVN</li>
            </ul>
            """
        )
    
    def _quit(self):
        """Quit the application."""
        # Stop all background services
        self.renewal_manager.stop_all()
        self.nomad_menu.stop_monitoring()
        
        # Cancel running processes
        for process in self.process_manager.get_running_processes():
            self.process_manager.cancel_process(process.id)
        
        # Hide tray and quit
        self.tray.hide()
        self.app.quit()
