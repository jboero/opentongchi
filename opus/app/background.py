"""Background tasks for token and lease renewal"""

from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QThread, QRunnable, QThreadPool

from .openbao import OpenBaoClient
from .http_client import ApiError


class TokenRenewalWorker(QObject):
    """Worker for renewing tokens in the background"""
    
    renewed = pyqtSignal(str, dict)  # token_type, result
    error = pyqtSignal(str, str)  # token_type, error message
    
    def __init__(self, client: OpenBaoClient, parent=None):
        super().__init__(parent)
        self.client = client
    
    def renew(self):
        """Renew the current token"""
        try:
            result = self.client.renew_self()
            self.renewed.emit("self", result)
        except ApiError as e:
            self.error.emit("self", str(e))
        except Exception as e:
            self.error.emit("self", str(e))


class LeaseRenewalWorker(QObject):
    """Worker for renewing leases in the background"""
    
    renewed = pyqtSignal(str, dict)  # lease_id, result
    error = pyqtSignal(str, str)  # lease_id, error message
    expired = pyqtSignal(str)  # lease_id
    
    def __init__(self, client: OpenBaoClient, parent=None):
        super().__init__(parent)
        self.client = client
        self.tracked_leases: Dict[str, datetime] = {}  # lease_id -> expiration time
    
    def add_lease(self, lease_id: str, ttl: int):
        """Add a lease to track"""
        expiration = datetime.now() + timedelta(seconds=ttl)
        self.tracked_leases[lease_id] = expiration
    
    def remove_lease(self, lease_id: str):
        """Remove a lease from tracking"""
        self.tracked_leases.pop(lease_id, None)
    
    def renew_all(self):
        """Renew all tracked leases"""
        now = datetime.now()
        to_remove = []
        
        for lease_id, expiration in self.tracked_leases.items():
            # Renew if expiring in the next 2 minutes
            if expiration - now < timedelta(minutes=2):
                try:
                    result = self.client.renew_lease(lease_id)
                    new_ttl = result.get("lease_duration", 0)
                    if new_ttl > 0:
                        self.tracked_leases[lease_id] = datetime.now() + timedelta(seconds=new_ttl)
                        self.renewed.emit(lease_id, result)
                    else:
                        to_remove.append(lease_id)
                        self.expired.emit(lease_id)
                except ApiError as e:
                    if e.status_code == 400:
                        # Lease not found or expired
                        to_remove.append(lease_id)
                        self.expired.emit(lease_id)
                    else:
                        self.error.emit(lease_id, str(e))
                except Exception as e:
                    self.error.emit(lease_id, str(e))
        
        # Remove expired leases
        for lease_id in to_remove:
            self.tracked_leases.pop(lease_id, None)


class BackgroundTaskManager(QObject):
    """Manages background tasks for token and lease renewal"""
    
    token_renewed = pyqtSignal(dict)
    token_error = pyqtSignal(str)
    lease_renewed = pyqtSignal(str, dict)
    lease_error = pyqtSignal(str, str)
    lease_expired = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.client: Optional[OpenBaoClient] = None
        
        # Timers
        self.token_timer: Optional[QTimer] = None
        self.lease_timer: Optional[QTimer] = None
        
        # Workers
        self.token_worker: Optional[TokenRenewalWorker] = None
        self.lease_worker: Optional[LeaseRenewalWorker] = None
        
        # State
        self.running = False
        self.last_token_renewal: Optional[datetime] = None
        self.last_lease_renewal: Optional[datetime] = None
    
    def get_client(self) -> OpenBaoClient:
        """Get or create the OpenBao client"""
        if self.client is None:
            self.client = OpenBaoClient(
                self.config.openbao.address,
                self.config.openbao.token,
                self.config.openbao.namespace,
                self.config.openbao.skip_verify
            )
        else:
            # Update token in case it changed
            self.client.token = self.config.openbao.token
            self.client.namespace = self.config.openbao.namespace
        return self.client
    
    def start(self):
        """Start background tasks"""
        if self.running:
            return
        
        self.running = True
        self.status_changed.emit("started")
        
        client = self.get_client()
        
        # Start token renewal
        if self.config.openbao.token_renewal_enabled and self.config.openbao.token:
            self.token_worker = TokenRenewalWorker(client)
            self.token_worker.renewed.connect(self._on_token_renewed)
            self.token_worker.error.connect(self._on_token_error)
            
            self.token_timer = QTimer()
            self.token_timer.timeout.connect(self._renew_token)
            interval = self.config.openbao.token_renewal_interval * 1000
            self.token_timer.start(interval)
        
        # Start lease renewal
        if self.config.openbao.lease_renewal_enabled and self.config.openbao.token:
            self.lease_worker = LeaseRenewalWorker(client)
            self.lease_worker.renewed.connect(self._on_lease_renewed)
            self.lease_worker.error.connect(self._on_lease_error)
            self.lease_worker.expired.connect(self._on_lease_expired)
            
            self.lease_timer = QTimer()
            self.lease_timer.timeout.connect(self._renew_leases)
            interval = self.config.openbao.lease_renewal_interval * 1000
            self.lease_timer.start(interval)
    
    def stop(self):
        """Stop background tasks"""
        if not self.running:
            return
        
        self.running = False
        
        if self.token_timer:
            self.token_timer.stop()
            self.token_timer = None
        
        if self.lease_timer:
            self.lease_timer.stop()
            self.lease_timer = None
        
        self.token_worker = None
        self.lease_worker = None
        
        self.status_changed.emit("stopped")
    
    def restart(self):
        """Restart background tasks with new settings"""
        self.stop()
        # Reset client to pick up new settings
        self.client = None
        self.start()
    
    def add_lease(self, lease_id: str, ttl: int):
        """Add a lease to track for renewal"""
        if self.lease_worker:
            self.lease_worker.add_lease(lease_id, ttl)
    
    def remove_lease(self, lease_id: str):
        """Remove a lease from tracking"""
        if self.lease_worker:
            self.lease_worker.remove_lease(lease_id)
    
    def _renew_token(self):
        """Perform token renewal"""
        if self.token_worker:
            self.token_worker.renew()
    
    def _renew_leases(self):
        """Perform lease renewal"""
        if self.lease_worker:
            self.lease_worker.renew_all()
    
    def _on_token_renewed(self, token_type: str, result: dict):
        """Handle successful token renewal"""
        self.last_token_renewal = datetime.now()
        self.token_renewed.emit(result)
    
    def _on_token_error(self, token_type: str, error: str):
        """Handle token renewal error"""
        self.token_error.emit(error)
    
    def _on_lease_renewed(self, lease_id: str, result: dict):
        """Handle successful lease renewal"""
        self.last_lease_renewal = datetime.now()
        self.lease_renewed.emit(lease_id, result)
    
    def _on_lease_error(self, lease_id: str, error: str):
        """Handle lease renewal error"""
        self.lease_error.emit(lease_id, error)
    
    def _on_lease_expired(self, lease_id: str):
        """Handle expired lease"""
        self.lease_expired.emit(lease_id)
    
    def get_status(self) -> Dict:
        """Get current status of background tasks"""
        status = {
            "running": self.running,
            "token_renewal": {
                "enabled": self.config.openbao.token_renewal_enabled,
                "interval": self.config.openbao.token_renewal_interval,
                "last_renewal": self.last_token_renewal.isoformat() if self.last_token_renewal else None,
            },
            "lease_renewal": {
                "enabled": self.config.openbao.lease_renewal_enabled,
                "interval": self.config.openbao.lease_renewal_interval,
                "last_renewal": self.last_lease_renewal.isoformat() if self.last_lease_renewal else None,
                "tracked_leases": len(self.lease_worker.tracked_leases) if self.lease_worker else 0,
            },
        }
        return status
