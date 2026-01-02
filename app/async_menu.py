"""
Async Menu Helper for OpenTongchi
Handles lazy loading of menu items with loading indicators.
"""

from typing import Callable, Optional, List, Any
from PySide6.QtWidgets import QMenu, QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor


class AsyncMenu(QMenu):
    """
    A menu that loads its items lazily when first shown.
    Shows wait cursor while fetching data synchronously.
    
    Note: True async loading doesn't work well with Qt menus because
    the menu is already displayed when aboutToShow fires. Instead,
    we load synchronously on first show with a wait cursor.
    """
    
    def __init__(self, title: str, loader_func: Callable, parent=None):
        super().__init__(title, parent)
        self.loader_func = loader_func
        self._loaded = False
        self._loading = False
        self._item_callback: Optional[Callable] = None
        self._submenu_factory: Optional[Callable] = None
        self._new_item_callback: Optional[Callable] = None
        self._new_item_text: str = "➕ New..."
        
        # Add loading placeholder
        self._loading_action = self.addAction("⏳ Loading...")
        self._loading_action.setEnabled(False)
        
        # Connect aboutToShow to trigger loading
        self.aboutToShow.connect(self._on_about_to_show)
    
    def set_item_callback(self, callback: Callable):
        """Set callback for when an item is clicked."""
        self._item_callback = callback
    
    def set_submenu_factory(self, factory: Callable):
        """Set factory function for creating submenus."""
        self._submenu_factory = factory
    
    def set_new_item_callback(self, callback: Callable, text: str = "➕ New..."):
        """Set callback for creating new items."""
        self._new_item_callback = callback
        self._new_item_text = text
    
    def _on_about_to_show(self):
        """Handle menu about to show - load items synchronously."""
        if self._loaded or self._loading:
            return
        
        self._loading = True
        
        # Set wait cursor
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        QApplication.processEvents()  # Ensure cursor updates
        
        try:
            # Load items synchronously
            items = self.loader_func()
            self._populate_menu(items)
            self._loaded = True
        except Exception as e:
            self._show_error(str(e))
        finally:
            self._loading = False
            QApplication.restoreOverrideCursor()
    
    def _populate_menu(self, items: List):
        """Populate the menu with loaded items."""
        self.clear()
        
        # Add "New..." option if callback is set
        if self._new_item_callback:
            new_action = self.addAction(self._new_item_text)
            new_action.triggered.connect(self._new_item_callback)
            self.addSeparator()
        
        if not items:
            no_items = self.addAction("(No items)")
            no_items.setEnabled(False)
        else:
            for item in items:
                self._add_item(item)
    
    def _add_item(self, item):
        """Add a single item to the menu."""
        if isinstance(item, dict):
            text = item.get('text', str(item))
            data = item.get('data')
            is_submenu = item.get('is_submenu', False)
            callback = item.get('callback')
            
            if is_submenu and self._submenu_factory:
                submenu = self._submenu_factory(text, data)
                self.addMenu(submenu)
            elif callback:
                action = self.addAction(text)
                action.setData(data)
                # Capture data properly in closure
                action.triggered.connect(lambda checked, d=data, cb=callback: cb(d))
            elif self._item_callback:
                action = self.addAction(text)
                action.setData(data)
                action.triggered.connect(lambda checked, d=data: self._item_callback(d))
            else:
                action = self.addAction(text)
                action.setData(data)
        elif isinstance(item, tuple) and len(item) >= 2:
            text, data = item[0], item[1]
            callback = item[2] if len(item) > 2 else None
            action = self.addAction(text)
            action.setData(data)
            if callback:
                action.triggered.connect(lambda checked, d=data, cb=callback: cb(d))
            elif self._item_callback:
                action.triggered.connect(lambda checked, d=data: self._item_callback(d))
        else:
            self.addAction(str(item))
    
    def _show_error(self, error: str):
        """Show error in menu."""
        self.clear()
        
        # Truncate long errors
        if len(error) > 50:
            error = error[:47] + "..."
        
        error_action = self.addAction(f"❌ {error}")
        error_action.setEnabled(False)
        
        # Add retry option
        retry = self.addAction("🔄 Retry")
        retry.triggered.connect(self.refresh)
        
        self._loaded = True  # Mark as loaded so retry can work
    
    def refresh(self):
        """Force refresh of menu items."""
        self._loaded = False
        self._loading = False
        self.clear()
        self._loading_action = self.addAction("⏳ Loading...")
        self._loading_action.setEnabled(False)
        # Trigger reload on next show
        QTimer.singleShot(0, self._on_about_to_show)


class LazySubmenu(QMenu):
    """A submenu that loads its contents lazily when opened."""
    
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._populated = False
        self._populate_func: Optional[Callable] = None
        
        # Placeholder
        placeholder = self.addAction("⏳ Loading...")
        placeholder.setEnabled(False)
        
        self.aboutToShow.connect(self._on_about_to_show)
    
    def set_populate_func(self, func: Callable):
        """Set the function to populate this menu."""
        self._populate_func = func
    
    def _on_about_to_show(self):
        """Populate menu when about to show."""
        if self._populated or not self._populate_func:
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        QApplication.processEvents()
        
        self.clear()
        try:
            self._populate_func(self)
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            error_action = self.addAction(f"❌ {error_msg}")
            error_action.setEnabled(False)
        finally:
            QApplication.restoreOverrideCursor()
        
        self._populated = True
    
    def refresh(self):
        """Force refresh of menu."""
        self._populated = False
        self.clear()
        placeholder = self.addAction("⏳ Loading...")
        placeholder.setEnabled(False)


def create_status_prefix(status: str, healthy_statuses: List[str] = None, 
                         error_statuses: List[str] = None) -> str:
    """Create a status emoji prefix based on status string."""
    if healthy_statuses is None:
        healthy_statuses = ['healthy', 'running', 'active', 'passing', 'ok', 'success', 'applied']
    if error_statuses is None:
        error_statuses = ['unhealthy', 'failed', 'error', 'critical', 'dead', 'stopped']
    
    status_lower = status.lower()
    
    if any(s in status_lower for s in healthy_statuses):
        return "🟢"
    elif any(s in status_lower for s in error_statuses):
        return "🔴"
    elif 'pending' in status_lower or 'starting' in status_lower:
        return "🟡"
    elif 'warning' in status_lower:
        return "🟠"
    else:
        return "⚪"
