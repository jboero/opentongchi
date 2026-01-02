"""
Boundary Client for OpenTongchi
"""

import subprocess
import json
from typing import Dict, Any, Optional, List
from .base import BaseHTTPClient, APIResponse


class BoundaryClient(BaseHTTPClient):
    """Client for Boundary API and CLI."""
    
    def __init__(self, settings):
        super().__init__(
            base_url=settings.address,
            token=settings.token
        )
        self.settings = settings
        self.binary_path = settings.binary_path or 'boundary'
        self._active_sessions: Dict[str, subprocess.Popen] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers including Boundary token."""
        headers = super()._get_headers()
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers
    
    # ============ CLI Operations ============
    
    def _run_cli(self, *args, input_data: str = None) -> Dict:
        """Run a Boundary CLI command."""
        cmd = [self.binary_path] + list(args)
        
        if self.token:
            cmd.extend(['-token', self.token])
        if self.settings.address:
            cmd.extend(['-addr', self.settings.address])
        
        cmd.extend(['-format', 'json'])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input=input_data,
                timeout=30
            )
            
            if result.returncode == 0:
                try:
                    return {'success': True, 'data': json.loads(result.stdout)}
                except json.JSONDecodeError:
                    return {'success': True, 'data': result.stdout}
            else:
                return {'success': False, 'error': result.stderr or result.stdout}
        
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Command timed out'}
        except FileNotFoundError:
            return {'success': False, 'error': f'Boundary binary not found: {self.binary_path}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============ Status ============
    
    def is_healthy(self) -> bool:
        """Check if Boundary is reachable."""
        result = self._run_cli('scopes', 'list', '-scope-id', 'global')
        return result.get('success', False)
    
    # ============ Scopes ============
    
    def scope_list(self, scope_id: str = 'global') -> APIResponse:
        """List scopes."""
        return self.get(f'/v1/scopes', params={'scope_id': scope_id})
    
    def scope_read(self, scope_id: str) -> APIResponse:
        """Read a scope."""
        return self.get(f'/v1/scopes/{scope_id}')
    
    # ============ Targets ============
    
    def target_list(self, scope_id: str = None) -> Dict:
        """List targets using CLI."""
        args = ['targets', 'list']
        if scope_id:
            args.extend(['-scope-id', scope_id])
        else:
            args.append('-recursive')
        return self._run_cli(*args)
    
    def target_read(self, target_id: str) -> Dict:
        """Read a target."""
        return self._run_cli('targets', 'read', '-id', target_id)
    
    def target_authorize_session(self, target_id: str) -> Dict:
        """Authorize a session to a target."""
        return self._run_cli('targets', 'authorize-session', '-id', target_id)
    
    # ============ Sessions ============
    
    def session_list(self, scope_id: str = None) -> Dict:
        """List sessions."""
        args = ['sessions', 'list']
        if scope_id:
            args.extend(['-scope-id', scope_id])
        else:
            args.append('-recursive')
        return self._run_cli(*args)
    
    def session_read(self, session_id: str) -> Dict:
        """Read a session."""
        return self._run_cli('sessions', 'read', '-id', session_id)
    
    def session_cancel(self, session_id: str) -> Dict:
        """Cancel a session."""
        return self._run_cli('sessions', 'cancel', '-id', session_id)
    
    # ============ Connect ============
    
    def connect(self, target_id: str, listen_port: int = None) -> subprocess.Popen:
        """
        Connect to a target. Returns the subprocess for the connection.
        The connection runs in the background until stopped.
        """
        cmd = [self.binary_path, 'connect']
        
        if self.token:
            cmd.extend(['-token', self.token])
        if self.settings.address:
            cmd.extend(['-addr', self.settings.address])
        
        cmd.extend(['-target-id', target_id])
        
        if listen_port:
            cmd.extend(['-listen-port', str(listen_port)])
        
        # Start connection in background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        self._active_sessions[target_id] = process
        return process
    
    def disconnect(self, target_id: str) -> bool:
        """Disconnect from a target."""
        if target_id in self._active_sessions:
            process = self._active_sessions[target_id]
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            del self._active_sessions[target_id]
            return True
        return False
    
    def is_connected(self, target_id: str) -> bool:
        """Check if connected to a target."""
        if target_id in self._active_sessions:
            process = self._active_sessions[target_id]
            return process.poll() is None
        return False
    
    def get_active_connections(self) -> List[str]:
        """Get list of active connection target IDs."""
        active = []
        for target_id, process in list(self._active_sessions.items()):
            if process.poll() is None:
                active.append(target_id)
            else:
                # Clean up finished processes
                del self._active_sessions[target_id]
        return active
    
    # ============ Auth Methods ============
    
    def auth_method_list(self, scope_id: str = 'global') -> Dict:
        """List auth methods."""
        return self._run_cli('auth-methods', 'list', '-scope-id', scope_id)
    
    def authenticate(self, auth_method_id: str, 
                     login_name: str, password: str) -> Dict:
        """Authenticate with password."""
        return self._run_cli(
            'authenticate', 'password',
            '-auth-method-id', auth_method_id,
            '-login-name', login_name,
            '-password', 'env://BOUNDARY_PASSWORD',
            input_data=password
        )
    
    # ============ Hosts ============
    
    def host_catalog_list(self, scope_id: str) -> Dict:
        """List host catalogs."""
        return self._run_cli('host-catalogs', 'list', '-scope-id', scope_id)
    
    def host_set_list(self, host_catalog_id: str) -> Dict:
        """List host sets."""
        return self._run_cli('host-sets', 'list', 
                            '-host-catalog-id', host_catalog_id)
    
    def host_list(self, host_catalog_id: str) -> Dict:
        """List hosts."""
        return self._run_cli('hosts', 'list', 
                            '-host-catalog-id', host_catalog_id)
    
    # ============ Credentials ============
    
    def credential_store_list(self, scope_id: str) -> Dict:
        """List credential stores."""
        return self._run_cli('credential-stores', 'list', '-scope-id', scope_id)
    
    def credential_library_list(self, credential_store_id: str) -> Dict:
        """List credential libraries."""
        return self._run_cli('credential-libraries', 'list',
                            '-credential-store-id', credential_store_id)
    
    # ============ Helpers ============
    
    def get_connection_status_emoji(self, target_id: str) -> str:
        """Get connection status emoji for a target."""
        if self.is_connected(target_id):
            return '🟢'
        return '⚪'
