"""
Background Process Manager for OpenTongchi
Handles background tasks, token renewal, and process tracking.
"""

import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from PySide6.QtCore import QObject, QThread, Signal, QTimer, QMutex, QMutexLocker


class ProcessStatus(Enum):
    """Status of a background process."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackgroundProcess:
    """Represents a background process."""
    id: str
    name: str
    description: str
    status: ProcessStatus = ProcessStatus.PENDING
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    progress: int = 0
    cancellable: bool = True
    
    @property
    def runtime_seconds(self) -> float:
        """Get runtime in seconds."""
        if not self.started_at:
            return 0
        end = self.finished_at or datetime.now()
        return (end - self.started_at).total_seconds()
    
    @property
    def runtime_str(self) -> str:
        """Get formatted runtime string."""
        seconds = int(self.runtime_seconds)
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            return f"{hours}h {mins}m"
    
    @property
    def status_emoji(self) -> str:
        """Get status emoji."""
        return {
            ProcessStatus.PENDING: "⏳",
            ProcessStatus.RUNNING: "🔄",
            ProcessStatus.COMPLETED: "✅",
            ProcessStatus.FAILED: "❌",
            ProcessStatus.CANCELLED: "🚫",
        }.get(self.status, "❓")


class WorkerThread(QThread):
    """Worker thread for running background tasks."""
    
    progress = Signal(int)
    finished_with_result = Signal(object)
    error_occurred = Signal(str)
    
    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._cancelled = False
    
    def run(self):
        """Execute the background task."""
        try:
            # Pass cancel checker to function if it accepts it
            if 'cancel_check' in self.func.__code__.co_varnames:
                result = self.func(*self.args, cancel_check=lambda: self._cancelled, **self.kwargs)
            else:
                result = self.func(*self.args, **self.kwargs)
            
            if not self._cancelled:
                self.finished_with_result.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def cancel(self):
        """Request cancellation of the task."""
        self._cancelled = True


class ProcessManager(QObject):
    """Manages all background processes."""
    
    process_started = Signal(str)  # process_id
    process_finished = Signal(str)  # process_id
    process_failed = Signal(str, str)  # process_id, error
    process_progress = Signal(str, int)  # process_id, progress
    processes_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._processes: Dict[str, BackgroundProcess] = {}
        self._threads: Dict[str, WorkerThread] = {}
        self._mutex = QMutex()
        
        # Cleanup timer for finished processes
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._cleanup_old_processes)
        self._cleanup_timer.start(60000)  # Every minute
    
    def start_process(
        self,
        name: str,
        description: str,
        func: Callable,
        *args,
        cancellable: bool = True,
        **kwargs
    ) -> str:
        """Start a new background process."""
        process_id = str(uuid.uuid4())[:8]
        
        process = BackgroundProcess(
            id=process_id,
            name=name,
            description=description,
            status=ProcessStatus.RUNNING,
            started_at=datetime.now(),
            cancellable=cancellable,
        )
        
        thread = WorkerThread(func, *args, **kwargs)
        thread.finished_with_result.connect(
            lambda result: self._on_process_finished(process_id, result)
        )
        thread.error_occurred.connect(
            lambda error: self._on_process_failed(process_id, error)
        )
        thread.progress.connect(
            lambda progress: self._on_process_progress(process_id, progress)
        )
        
        with QMutexLocker(self._mutex):
            self._processes[process_id] = process
            self._threads[process_id] = thread
        
        thread.start()
        self.process_started.emit(process_id)
        self.processes_changed.emit()
        
        return process_id
    
    def cancel_process(self, process_id: str) -> bool:
        """Cancel a running process."""
        with QMutexLocker(self._mutex):
            if process_id not in self._processes:
                return False
            
            process = self._processes[process_id]
            if not process.cancellable or process.status != ProcessStatus.RUNNING:
                return False
            
            if process_id in self._threads:
                self._threads[process_id].cancel()
                self._threads[process_id].quit()
                self._threads[process_id].wait(1000)
            
            process.status = ProcessStatus.CANCELLED
            process.finished_at = datetime.now()
        
        self.processes_changed.emit()
        return True
    
    def get_process(self, process_id: str) -> Optional[BackgroundProcess]:
        """Get a process by ID."""
        with QMutexLocker(self._mutex):
            return self._processes.get(process_id)
    
    def get_running_processes(self) -> List[BackgroundProcess]:
        """Get all running processes."""
        with QMutexLocker(self._mutex):
            return [p for p in self._processes.values() if p.status == ProcessStatus.RUNNING]
    
    def get_all_processes(self) -> List[BackgroundProcess]:
        """Get all processes."""
        with QMutexLocker(self._mutex):
            return list(self._processes.values())
    
    def get_recent_processes(self, limit: int = 10) -> List[BackgroundProcess]:
        """Get recent processes sorted by start time."""
        with QMutexLocker(self._mutex):
            sorted_processes = sorted(
                self._processes.values(),
                key=lambda p: p.started_at or datetime.min,
                reverse=True
            )
            return sorted_processes[:limit]
    
    def _on_process_finished(self, process_id: str, result: Any):
        """Handle process completion."""
        with QMutexLocker(self._mutex):
            if process_id in self._processes:
                process = self._processes[process_id]
                process.status = ProcessStatus.COMPLETED
                process.finished_at = datetime.now()
                process.result = result
        
        self.process_finished.emit(process_id)
        self.processes_changed.emit()
    
    def _on_process_failed(self, process_id: str, error: str):
        """Handle process failure."""
        with QMutexLocker(self._mutex):
            if process_id in self._processes:
                process = self._processes[process_id]
                process.status = ProcessStatus.FAILED
                process.finished_at = datetime.now()
                process.error = error
        
        self.process_failed.emit(process_id, error)
        self.processes_changed.emit()
    
    def _on_process_progress(self, process_id: str, progress: int):
        """Handle process progress update."""
        with QMutexLocker(self._mutex):
            if process_id in self._processes:
                self._processes[process_id].progress = progress
        
        self.process_progress.emit(process_id, progress)
    
    def _cleanup_old_processes(self):
        """Remove old completed/failed processes."""
        cutoff = datetime.now()
        with QMutexLocker(self._mutex):
            to_remove = []
            for pid, process in self._processes.items():
                if process.status in (ProcessStatus.COMPLETED, ProcessStatus.FAILED, ProcessStatus.CANCELLED):
                    if process.finished_at and (cutoff - process.finished_at).total_seconds() > 3600:
                        to_remove.append(pid)
            
            for pid in to_remove:
                del self._processes[pid]
                if pid in self._threads:
                    del self._threads[pid]
        
        if to_remove:
            self.processes_changed.emit()


class TokenRenewalManager(QObject):
    """Manages automatic token and lease renewal."""
    
    renewal_success = Signal(str)  # service name
    renewal_failed = Signal(str, str)  # service name, error
    
    def __init__(self, settings, process_manager: ProcessManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        self._timers: Dict[str, QTimer] = {}
        self._enabled = True
    
    def start_openbao_renewal(self):
        """Start OpenBao token renewal timer."""
        if not self.settings.openbao.auto_renew_token:
            return
        
        if 'openbao' in self._timers:
            self._timers['openbao'].stop()
        
        timer = QTimer(self)
        interval = self.settings.openbao.renew_interval_seconds * 1000
        timer.timeout.connect(self._renew_openbao_token)
        timer.start(interval)
        self._timers['openbao'] = timer
    
    def stop_openbao_renewal(self):
        """Stop OpenBao token renewal."""
        if 'openbao' in self._timers:
            self._timers['openbao'].stop()
            del self._timers['openbao']
    
    def _renew_openbao_token(self):
        """Renew OpenBao token."""
        if not self._enabled:
            return
        
        from app.clients.openbao import OpenBaoClient
        client = OpenBaoClient(self.settings.openbao)
        
        def renew():
            return client.renew_self_token()
        
        self.process_manager.start_process(
            name="Token Renewal",
            description="Renewing OpenBao token",
            func=renew,
            cancellable=False
        )
    
    def set_enabled(self, enabled: bool):
        """Enable or disable all renewals."""
        self._enabled = enabled
    
    def stop_all(self):
        """Stop all renewal timers."""
        for timer in self._timers.values():
            timer.stop()
        self._timers.clear()
