"""
Boundary Client for OpenTongchi
"""

import subprocess
import json
import os
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
        self._authenticated = False
        self._auth_error: Optional[str] = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers including Boundary token."""
        headers = super()._get_headers()
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers
    
    def ensure_authenticated(self) -> bool:
        """Ensure we have a valid token, authenticating if necessary."""
        # If we already have a token, we're good
        if self.token:
            self._authenticated = True
            return True
        
        # If we already tried and failed, don't retry
        if self._auth_error:
            return False
        
        # Try to authenticate with username/password
        if self.settings.login_name and self.settings.password and self.settings.auth_method_id:
            result = self.authenticate_password(
                self.settings.auth_method_id,
                self.settings.login_name,
                self.settings.password
            )
            
            if result.get('success') and result.get('data'):
                # Extract token from response
                # Boundary returns: {"attributes": {"token": "..."}, ...}
                # or sometimes: {"item": {"attributes": {"token": "..."}}}
                token_data = result.get('data', {})
                
                if isinstance(token_data, dict):
                    new_token = None
                    
                    # Try direct attributes.token
                    if 'attributes' in token_data:
                        new_token = token_data['attributes'].get('token')
                    
                    # Try item.attributes.token
                    if not new_token and 'item' in token_data:
                        item = token_data.get('item', {})
                        if isinstance(item, dict) and 'attributes' in item:
                            new_token = item['attributes'].get('token')
                    
                    # Try auth_token at top level (some versions)
                    if not new_token:
                        new_token = token_data.get('auth_token') or token_data.get('token')
                    
                    if new_token:
                        self.token = new_token
                        self._authenticated = True
                        self._auth_error = None
                        return True
                    else:
                        self._auth_error = f"No token in auth response: {list(token_data.keys())}"
            else:
                self._auth_error = result.get('error', 'Authentication failed')
        else:
            missing = []
            configured = []
            if not self.settings.login_name:
                missing.append('login_name')
            else:
                configured.append(f"login_name={self.settings.login_name}")
            if not self.settings.password:
                missing.append('password')
            else:
                configured.append("password=***")
            if not self.settings.auth_method_id:
                missing.append('auth_method_id')
            else:
                configured.append(f"auth_method_id={self.settings.auth_method_id}")
            
            self._auth_error = f"Missing: {', '.join(missing)}"
            if configured:
                self._auth_error += f" (have: {', '.join(configured)})"
        
        return False
    
    def get_auth_error(self) -> Optional[str]:
        """Get the last authentication error, if any."""
        return self._auth_error
    
    def reset_auth(self):
        """Reset authentication state to allow retry."""
        self._authenticated = False
        self._auth_error = None
        self.token = ""
    
    # ============ CLI Operations ============
    
    def _run_cli(self, *args, input_data: str = None, env_vars: Dict = None, 
                 skip_auth: bool = False) -> Dict:
        """Run a Boundary CLI command."""
        # Ensure we're authenticated before running commands (unless skipping)
        if not skip_auth:
            if not self.ensure_authenticated():
                # Return the auth error instead of running the command
                return {
                    'success': False, 
                    'error': self._auth_error or 'Authentication required but no token available'
                }
        
        cmd = [self.binary_path] + list(args)
        
        # Build environment - use env vars for token (more secure than CLI args)
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        
        # Pass token via environment variable for security
        if self.token:
            env['BOUNDARY_TOKEN'] = self.token
        
        if self.settings.address:
            env['BOUNDARY_ADDR'] = self.settings.address
        
        # Add format flag if not already present
        if '-format' not in args:
            cmd.extend(['-format', 'json'])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input=input_data,
                timeout=30,
                env=env
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
    
    # ============ Authentication ============
    
    def authenticate_password(self, auth_method_id: str, 
                               login_name: str, password: str) -> Dict:
        """Authenticate with username/password."""
        # Use environment variable for password to avoid command line exposure
        env_vars = {'BOUNDARY_AUTHENTICATE_PASSWORD_PASSWORD': password}
        
        cmd = [self.binary_path, 'authenticate', 'password',
               '-auth-method-id', auth_method_id,
               '-login-name', login_name,
               '-password', 'env://BOUNDARY_AUTHENTICATE_PASSWORD_PASSWORD',
               '-format', 'json']
        
        if self.settings.address:
            cmd.extend(['-addr', self.settings.address])
        
        env = os.environ.copy()
        env.update(env_vars)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            if result.returncode == 0:
                try:
                    return {'success': True, 'data': json.loads(result.stdout)}
                except json.JSONDecodeError:
                    return {'success': True, 'data': result.stdout}
            else:
                return {'success': False, 'error': result.stderr or result.stdout}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def authenticate_oidc(self, auth_method_id: str) -> Dict:
        """Authenticate with OIDC (opens browser)."""
        return self._run_cli('authenticate', 'oidc',
                            '-auth-method-id', auth_method_id, skip_auth=True)
    
    def get_token_info(self) -> Dict:
        """Get current token information."""
        if not self.token:
            return {'success': False, 'error': 'No token configured'}
        # There's no direct "whoami" but we can try listing scopes
        return self._run_cli('scopes', 'list', '-scope-id', 'global')
    
    # ============ Status ============
    
    def is_healthy(self) -> bool:
        """Check if Boundary is reachable."""
        result = self._run_cli('scopes', 'list', '-scope-id', 'global')
        return result.get('success', False)
    
    # ============ Scopes / Orgs / Projects ============
    
    def scope_list(self, scope_id: str = 'global', recursive: bool = False) -> Dict:
        """List scopes (orgs under global, projects under orgs)."""
        args = ['scopes', 'list', '-scope-id', scope_id]
        if recursive:
            args.append('-recursive')
        return self._run_cli(*args)
    
    def scope_read(self, scope_id: str) -> Dict:
        """Read a scope."""
        return self._run_cli('scopes', 'read', '-id', scope_id)
    
    def scope_create(self, scope_id: str, name: str, description: str = None) -> Dict:
        """Create a scope (org or project)."""
        args = ['scopes', 'create', '-scope-id', scope_id, '-name', name]
        if description:
            args.extend(['-description', description])
        return self._run_cli(*args)
    
    def scope_delete(self, scope_id: str) -> Dict:
        """Delete a scope."""
        return self._run_cli('scopes', 'delete', '-id', scope_id)
    
    # ============ Targets ============
    
    def target_list(self, scope_id: str = None, recursive: bool = True) -> Dict:
        """List targets using CLI."""
        args = ['targets', 'list']
        if scope_id:
            args.extend(['-scope-id', scope_id])
        if recursive:
            args.append('-recursive')
        return self._run_cli(*args)
    
    def target_read(self, target_id: str) -> Dict:
        """Read a target."""
        return self._run_cli('targets', 'read', '-id', target_id)
    
    def target_authorize_session(self, target_id: str) -> Dict:
        """Authorize a session to a target."""
        return self._run_cli('targets', 'authorize-session', '-id', target_id)
    
    # ============ Sessions ============
    
    def session_list(self, scope_id: str = None, recursive: bool = True) -> Dict:
        """List sessions."""
        args = ['sessions', 'list']
        if scope_id:
            args.extend(['-scope-id', scope_id])
        if recursive:
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
        self.ensure_authenticated()
        
        cmd = [self.binary_path, 'connect']
        
        # Build environment with token
        env = os.environ.copy()
        if self.token:
            env['BOUNDARY_TOKEN'] = self.token
        if self.settings.address:
            env['BOUNDARY_ADDR'] = self.settings.address
        
        cmd.extend(['-target-id', target_id])
        
        if listen_port:
            cmd.extend(['-listen-port', str(listen_port)])
        
        # Start connection in background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
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
    
    def auth_method_read(self, auth_method_id: str) -> Dict:
        """Read an auth method."""
        return self._run_cli('auth-methods', 'read', '-id', auth_method_id)
    
    # Legacy method for backwards compatibility
    def authenticate(self, auth_method_id: str, 
                     login_name: str, password: str) -> Dict:
        """Authenticate with password (legacy wrapper)."""
        return self.authenticate_password(auth_method_id, login_name, password)
    
    # ============ Accounts ============
    
    def account_list(self, auth_method_id: str) -> Dict:
        """List accounts for an auth method."""
        return self._run_cli('accounts', 'list', '-auth-method-id', auth_method_id)
    
    def account_read(self, account_id: str) -> Dict:
        """Read an account."""
        return self._run_cli('accounts', 'read', '-id', account_id)
    
    # ============ Users ============
    
    def user_list(self, scope_id: str = 'global') -> Dict:
        """List users."""
        return self._run_cli('users', 'list', '-scope-id', scope_id)
    
    def user_read(self, user_id: str) -> Dict:
        """Read a user."""
        return self._run_cli('users', 'read', '-id', user_id)
    
    # ============ Groups ============
    
    def group_list(self, scope_id: str = 'global') -> Dict:
        """List groups."""
        return self._run_cli('groups', 'list', '-scope-id', scope_id)
    
    def group_read(self, group_id: str) -> Dict:
        """Read a group."""
        return self._run_cli('groups', 'read', '-id', group_id)
    
    # ============ Roles ============
    
    def role_list(self, scope_id: str = 'global') -> Dict:
        """List roles."""
        return self._run_cli('roles', 'list', '-scope-id', scope_id)
    
    def role_read(self, role_id: str) -> Dict:
        """Read a role."""
        return self._run_cli('roles', 'read', '-id', role_id)
    
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
    
    # ============ Workers ============
    
    def worker_list(self, scope_id: str = 'global') -> Dict:
        """List workers."""
        return self._run_cli('workers', 'list', '-scope-id', scope_id)
    
    def worker_read(self, worker_id: str) -> Dict:
        """Read a worker."""
        return self._run_cli('workers', 'read', '-id', worker_id)
    
    # ============ Aliases ============
    
    def alias_list(self, scope_id: str = 'global') -> Dict:
        """List aliases."""
        return self._run_cli('aliases', 'list', '-scope-id', scope_id)
    
    def alias_read(self, alias_id: str) -> Dict:
        """Read an alias."""
        return self._run_cli('aliases', 'read', '-id', alias_id)
    
    def alias_create(self, scope_id: str, value: str, destination_id: str, 
                     alias_type: str = 'target') -> Dict:
        """Create a new alias."""
        args = ['aliases', 'create', alias_type,
                '-scope-id', scope_id,
                '-value', value,
                '-destination-id', destination_id]
        return self._run_cli(*args)
    
    def alias_delete(self, alias_id: str) -> Dict:
        """Delete an alias."""
        return self._run_cli('aliases', 'delete', '-id', alias_id)
    
    # ============ Create Methods ============
    
    def scope_create(self, parent_scope_id: str, name: str, 
                     description: str = None, scope_type: str = None) -> Dict:
        """Create a new scope (org or project)."""
        args = ['scopes', 'create', '-scope-id', parent_scope_id, '-name', name]
        if description:
            args.extend(['-description', description])
        return self._run_cli(*args)
    
    def scope_delete(self, scope_id: str) -> Dict:
        """Delete a scope."""
        return self._run_cli('scopes', 'delete', '-id', scope_id)
    
    def user_create(self, scope_id: str, name: str, description: str = None) -> Dict:
        """Create a new user."""
        args = ['users', 'create', '-scope-id', scope_id, '-name', name]
        if description:
            args.extend(['-description', description])
        return self._run_cli(*args)
    
    def user_delete(self, user_id: str) -> Dict:
        """Delete a user."""
        return self._run_cli('users', 'delete', '-id', user_id)
    
    def group_create(self, scope_id: str, name: str, description: str = None) -> Dict:
        """Create a new group."""
        args = ['groups', 'create', '-scope-id', scope_id, '-name', name]
        if description:
            args.extend(['-description', description])
        return self._run_cli(*args)
    
    def group_delete(self, group_id: str) -> Dict:
        """Delete a group."""
        return self._run_cli('groups', 'delete', '-id', group_id)
    
    def role_create(self, scope_id: str, name: str, description: str = None) -> Dict:
        """Create a new role."""
        args = ['roles', 'create', '-scope-id', scope_id, '-name', name]
        if description:
            args.extend(['-description', description])
        return self._run_cli(*args)
    
    def role_delete(self, role_id: str) -> Dict:
        """Delete a role."""
        return self._run_cli('roles', 'delete', '-id', role_id)
    
    # ============ Helpers ============
    
    def get_connection_status_emoji(self, target_id: str) -> str:
        """Get connection status emoji for a target."""
        if self.is_connected(target_id):
            return '🟢'
        return '⚪'
