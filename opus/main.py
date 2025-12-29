#!/usr/bin/env python3
"""
OpenTongchi - System Tray Widget for Managing Open Source Infrastructure Tools
Supports OpenBao, OpenTofu, Consul, and Nomad
"""

import sys
import os

# Add the directory containing this script to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from app.tray import OpenTongchiTray
from app.config import Config


def main():
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("OpenTongchi")
    app.setOrganizationName("OpenTongchi")
    
    # Load configuration
    config = Config()
    
    # Create system tray
    tray = OpenTongchiTray(config)
    tray.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
