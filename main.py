#!/usr/bin/env python3
"""
OpenTongchi - System Tray Manager for Open Source Infrastructure Tools
A Qt6-based systray widget for managing OpenBao, OpenTofu, Consul, Nomad, Boundary, Waypoint, and Packer.
Licensed under MPL-2.0
"""

import sys
import os
import fcntl
from pathlib import Path

# Set environment defaults before importing Qt
os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


def check_singleton() -> bool:
    """
    Check if another instance is already running.
    Returns True if this is the only instance, False otherwise.
    """
    # Use a lock file in the user's runtime directory or tmp
    runtime_dir = os.environ.get('XDG_RUNTIME_DIR', '/tmp')
    lock_file = Path(runtime_dir) / 'opentongchi.lock'
    
    try:
        # Open or create the lock file
        lock_fd = open(lock_file, 'w')
        
        # Try to acquire an exclusive lock (non-blocking)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # Write our PID to the lock file
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        
        # Keep the file descriptor open (don't close it) to maintain the lock
        # Store it globally so it doesn't get garbage collected
        global _lock_fd
        _lock_fd = lock_fd
        
        return True
        
    except (IOError, OSError):
        # Another instance has the lock
        return False


def main():
    """Main entry point for OpenTongchi."""
    # Check for existing instance
    if not check_singleton():
        # Another instance is running, exit silently
        sys.exit(0)
    
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("OpenTongchi")
    app.setOrganizationName("OpenTongchi")
    
    # Import here to avoid issues if singleton check fails
    from app.systray import OpenTongchiTray
    from app.settings import SettingsManager
    
    # Initialize settings
    settings = SettingsManager()
    
    # Create and show systray
    tray = OpenTongchiTray(app, settings)
    tray.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
