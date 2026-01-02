#!/usr/bin/env python3
"""
OpenTongchi - System Tray Manager for Open Source Infrastructure Tools
A Qt6-based systray widget for managing OpenBao, OpenTofu, Consul, Nomad, Boundary, Waypoint, and Packer.
Licensed under MPL-2.0
"""

import sys
import os

# Set environment defaults before importing Qt
os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.systray import OpenTongchiTray
from app.settings import SettingsManager


def main():
    """Main entry point for OpenTongchi."""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("OpenTongchi")
    app.setOrganizationName("OpenTongchi")
    
    # Initialize settings
    settings = SettingsManager()
    
    # Create and show systray
    tray = OpenTongchiTray(app, settings)
    tray.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
