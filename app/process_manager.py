"""
Background Process Manager for OpenTongchi
Handles background tasks, token renewal, and process tracking.
"""

import time
import uuid
from datetime import datetime
from pathlib import Path
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
        self._external_processes: Dict[str, Dict] = {}  # For tracking subprocess.Popen objects
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
        """Cancel a running process (either worker thread or external process)."""
        # First check if it's an external process
        with QMutexLocker(self._mutex):
            if process_id in self._external_processes:
                # Unlock mutex and call external cancel (which re-acquires it)
                pass  # Fall through to external cancel
            elif process_id not in self._processes:
                return False
            else:
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
        
        # Handle external process cancellation
        return self.cancel_external_process(process_id)
    
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
    
    def register_external_process(
        self,
        name: str,
        description: str,
        process,  # subprocess.Popen
        on_cancel: Optional[Callable] = None
    ) -> str:
        """Register an external subprocess (like Boundary connect) for tracking.
        
        Args:
            name: Display name for the process
            description: Description of what the process is doing
            process: A subprocess.Popen object
            on_cancel: Optional callback to run when cancelling
        
        Returns:
            process_id: The ID assigned to this process
        """
        process_id = str(uuid.uuid4())[:8]
        
        bg_process = BackgroundProcess(
            id=process_id,
            name=name,
            description=description,
            status=ProcessStatus.RUNNING,
            started_at=datetime.now(),
            cancellable=True,
        )
        
        with QMutexLocker(self._mutex):
            self._processes[process_id] = bg_process
            # Store the external process and callback for cancellation
            self._external_processes[process_id] = {
                'process': process,
                'on_cancel': on_cancel
            }
        
        self.process_started.emit(process_id)
        self.processes_changed.emit()
        
        # Start a timer to monitor the external process
        self._start_external_process_monitor(process_id)
        
        return process_id
    
    def _start_external_process_monitor(self, process_id: str):
        """Start monitoring an external process for completion."""
        def check_process():
            with QMutexLocker(self._mutex):
                if process_id not in self._external_processes:
                    return
                
                ext_proc = self._external_processes[process_id]
                process = ext_proc['process']
                
                # Check if process has finished
                if process.poll() is not None:
                    # Process finished
                    bg_process = self._processes.get(process_id)
                    if bg_process and bg_process.status == ProcessStatus.RUNNING:
                        if process.returncode == 0:
                            bg_process.status = ProcessStatus.COMPLETED
                        else:
                            bg_process.status = ProcessStatus.FAILED
                            bg_process.error = f"Exit code: {process.returncode}"
                        bg_process.finished_at = datetime.now()
                        
                        # Clean up
                        del self._external_processes[process_id]
                        self.processes_changed.emit()
                    return
            
            # Still running, check again later
            QTimer.singleShot(2000, check_process)
        
        QTimer.singleShot(2000, check_process)
    
    def cancel_external_process(self, process_id: str) -> bool:
        """Cancel an external process."""
        with QMutexLocker(self._mutex):
            if process_id not in self._external_processes:
                return False
            
            ext_proc = self._external_processes[process_id]
            process = ext_proc['process']
            on_cancel = ext_proc.get('on_cancel')
            
            # Terminate the process
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            
            # Call the cancel callback if provided
            if on_cancel:
                try:
                    on_cancel()
                except Exception:
                    pass
            
            # Update status
            bg_process = self._processes.get(process_id)
            if bg_process:
                bg_process.status = ProcessStatus.CANCELLED
                bg_process.finished_at = datetime.now()
            
            del self._external_processes[process_id]
        
        self.processes_changed.emit()
        return True
    
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


class SoundManager(QObject):
    """Manages notification sounds for the application."""
    
    # Common system sound paths on Linux
    SYSTEM_SOUND_PATHS = [
        # Freedesktop sound theme locations
        "/usr/share/sounds/freedesktop/stereo",
        "/usr/share/sounds/Yaru/stereo",
        "/usr/share/sounds/ubuntu/stereo", 
        "/usr/share/sounds/gnome/default/alerts",
        "/usr/share/sounds/KDE-Sys-App-Positive.ogg",
        # Fallback paths
        "/usr/share/sounds",
        str(Path.home() / ".local/share/sounds"),
    ]
    
    # Common success sound names
    SUCCESS_SOUNDS = [
        "complete.oga", "complete.ogg", "complete.wav",
        "message.oga", "message.ogg", "message.wav",
        "bell.oga", "bell.ogg", "bell.wav",
        "dialog-information.oga", "dialog-information.ogg",
    ]
    
    # Common error sound names
    ERROR_SOUNDS = [
        "dialog-error.oga", "dialog-error.ogg", "dialog-error.wav",
        "dialog-warning.oga", "dialog-warning.ogg", "dialog-warning.wav",
        "suspend-error.oga", "suspend-error.ogg",
        "bell.oga", "bell.ogg", "bell.wav",
    ]
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._success_sound = None
        self._error_sound = None
        self._available_sounds: Dict[str, str] = {}
        
        # Discover available system sounds
        self._discover_sounds()
    
    def _discover_sounds(self):
        """Discover available system sounds."""
        self._available_sounds = {"none": "", "system": "system"}
        
        for base_path in self.SYSTEM_SOUND_PATHS:
            path = Path(base_path)
            if path.is_dir():
                for sound_file in path.glob("*.og[ag]"):
                    name = sound_file.stem
                    if name not in self._available_sounds:
                        self._available_sounds[name] = str(sound_file)
                for sound_file in path.glob("*.wav"):
                    name = sound_file.stem
                    if name not in self._available_sounds:
                        self._available_sounds[name] = str(sound_file)
    
    def get_available_sounds(self) -> Dict[str, str]:
        """Get dict of available sounds {display_name: path}."""
        return self._available_sounds.copy()
    
    def _find_system_sound(self, sound_names: List[str]) -> Optional[str]:
        """Find first available system sound from list of names."""
        for base_path in self.SYSTEM_SOUND_PATHS:
            path = Path(base_path)
            if path.is_dir():
                for name in sound_names:
                    sound_path = path / name
                    if sound_path.exists():
                        return str(sound_path)
        return None
    
    def _get_sound_path(self, setting_value: str, fallback_sounds: List[str]) -> Optional[str]:
        """Get the actual sound file path from a setting value."""
        if not setting_value or setting_value == "none":
            return None
        
        if setting_value == "system":
            return self._find_system_sound(fallback_sounds)
        
        # Check if it's a known sound name
        if setting_value in self._available_sounds:
            return self._available_sounds[setting_value]
        
        # Check if it's a direct path
        if Path(setting_value).exists():
            return setting_value
        
        return None
    
    def play_success(self):
        """Play success notification sound."""
        if not self.settings.global_settings.sounds_enabled:
            return
        
        sound_path = self._get_sound_path(
            self.settings.global_settings.sound_success,
            self.SUCCESS_SOUNDS
        )
        
        if sound_path:
            self._play_sound(sound_path)
    
    def play_error(self):
        """Play error notification sound."""
        if not self.settings.global_settings.sounds_enabled:
            return
        
        sound_path = self._get_sound_path(
            self.settings.global_settings.sound_error,
            self.ERROR_SOUNDS
        )
        
        if sound_path:
            self._play_sound(sound_path)
    
    def _play_sound(self, path: str):
        """Play a sound file."""
        # Try command-line players first (more reliable for various formats)
        if self._play_sound_cli(path):
            return
        
        # Fall back to Qt
        self._play_sound_qt(path)
    
    def _play_sound_cli(self, path: str) -> bool:
        """Play sound using command-line tools. Returns True if successful."""
        import subprocess
        import shutil
        
        # Try various players in order of preference
        players = [
            ('paplay', [path]),           # PulseAudio
            ('pw-play', [path]),          # PipeWire
            ('aplay', ['-q', path]),      # ALSA (quiet mode)
            ('play', ['-q', path]),       # SoX
            ('afplay', [path]),           # macOS
        ]
        
        for cmd, args in players:
            if shutil.which(cmd):
                try:
                    subprocess.Popen(
                        [cmd] + args,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return True
                except Exception:
                    continue
        
        return False
    
    def _play_sound_qt(self, path: str):
        """Play sound using Qt multimedia."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl
            
            # Create player with audio output
            player = QMediaPlayer(self)
            audio_output = QAudioOutput(self)
            player.setAudioOutput(audio_output)
            audio_output.setVolume(0.7)
            
            player.setSource(QUrl.fromLocalFile(path))
            player.play()
            
            # Clean up after playing
            QTimer.singleShot(10000, player.deleteLater)
            QTimer.singleShot(10000, audio_output.deleteLater)
            
        except ImportError:
            pass
        except Exception:
            pass
    
    def test_sound(self, sound_type: str = "success"):
        """Test play a sound."""
        if sound_type == "success":
            # Temporarily enable sounds for test
            old_enabled = self.settings.global_settings.sounds_enabled
            self.settings.global_settings.sounds_enabled = True
            self.play_success()
            self.settings.global_settings.sounds_enabled = old_enabled
        else:
            old_enabled = self.settings.global_settings.sounds_enabled
            self.settings.global_settings.sounds_enabled = True
            self.play_error()
            self.settings.global_settings.sounds_enabled = old_enabled
