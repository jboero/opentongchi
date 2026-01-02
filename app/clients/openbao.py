"""
OpenBao (Vault) Client for OpenTongchi
Direct API client without HVAC dependency.
"""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from .base import BaseHTTPClient, APIResponse


class OpenBaoClient(BaseHTTPClient):
    """Client for OpenBao/Vault API."""
    
    def __init__(self, settings):
        super().__init__(
            base_url=settings.address,
            token=settings.token,
            namespace=settings.namespace,
            skip_verify=settings.skip_verify
        )
        self.settings = settings
        self._schema_cache: Optional[Dict] = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers including Vault token."""
        headers = super()._get_headers()
        if self.token:
            headers['X-Vault-Token'] = self.token
        if self.namespace:
            headers['X-Vault-Namespace'] = self.namespace
        return headers
    
    # ============ Health & Status ============
    
    def health(self) -> APIResponse:
        """Get health status."""
        return self.get('/v1/sys/health')
    
    def is_healthy(self) -> bool:
        """Check if Vault is healthy."""
        response = self.health()
        return response.ok
    
    def seal_status(self) -> APIResponse:
        """Get seal status."""
        return self.get('/v1/sys/seal-status')
    
    def leader(self) -> APIResponse:
        """Get leader status."""
        return self.get('/v1/sys/leader')
    
    # ============ Token Operations ============
    
    def lookup_self_token(self) -> APIResponse:
        """Look up current token."""
        return self.get('/v1/auth/token/lookup-self')
    
    def renew_self_token(self) -> APIResponse:
        """Renew the current token."""
        return self.post('/v1/auth/token/renew-self')
    
    def revoke_self_token(self) -> APIResponse:
        """Revoke the current token."""
        return self.post('/v1/auth/token/revoke-self')
    
    def create_token(self, policies: List[str] = None, ttl: str = None,
                     renewable: bool = True, metadata: Dict = None) -> APIResponse:
        """Create a new token."""
        data = {'renewable': renewable}
        if policies:
            data['policies'] = policies
        if ttl:
            data['ttl'] = ttl
        if metadata:
            data['meta'] = metadata
        return self.post('/v1/auth/token/create', data)
    
    # ============ OpenAPI Schema ============
    
    def get_openapi_schema(self, force_refresh: bool = False) -> Dict:
        """Get OpenAPI schema, with caching."""
        if self._schema_cache and not force_refresh:
            return self._schema_cache
        
        response = self.get('/v1/sys/internal/specs/openapi')
        if response.ok and response.data:
            self._schema_cache = response.data
            return response.data
        return {}
    
    def parse_schema_paths(self) -> Dict[str, Any]:
        """Parse OpenAPI schema into navigable structure."""
        schema = self.get_openapi_schema()
        paths = schema.get('paths', {})
        
        # Build tree structure from paths
        tree = {}
        for path, methods in paths.items():
            parts = [p for p in path.split('/') if p and p != 'v1']
            current = tree
            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {
                        '_path': '/' + '/'.join(['v1'] + parts[:i+1]),
                        '_methods': {},
                        '_is_param': part.startswith('{') and part.endswith('}'),
                    }
                current = current[part]
            current['_methods'] = methods
        
        return tree
    
    # ============ Secrets Engines ============
    
    def list_mounts(self) -> APIResponse:
        """List all secret engine mounts."""
        return self.get('/v1/sys/mounts')
    
    def mount_info(self, path: str) -> APIResponse:
        """Get info about a specific mount."""
        return self.get(f'/v1/sys/mounts/{path}')
    
    def enable_secrets_engine(self, path: str, engine_type: str,
                               options: Dict = None) -> APIResponse:
        """Enable a secrets engine."""
        data = {'type': engine_type}
        if options:
            data['options'] = options
        return self.post(f'/v1/sys/mounts/{path}', data)
    
    def disable_secrets_engine(self, path: str) -> APIResponse:
        """Disable a secrets engine."""
        return self.delete(f'/v1/sys/mounts/{path}')
    
    # ============ KV v1 Operations ============
    
    def kv1_read(self, mount: str, path: str) -> APIResponse:
        """Read a KV v1 secret."""
        return self.get(f'/v1/{mount}/{path}')
    
    def kv1_write(self, mount: str, path: str, data: Dict) -> APIResponse:
        """Write a KV v1 secret."""
        return self.post(f'/v1/{mount}/{path}', data)
    
    def kv1_delete(self, mount: str, path: str) -> APIResponse:
        """Delete a KV v1 secret."""
        return self.delete(f'/v1/{mount}/{path}')
    
    def kv1_list(self, mount: str, path: str = "") -> APIResponse:
        """List KV v1 secrets."""
        full_path = f'/v1/{mount}/{path}' if path else f'/v1/{mount}'
        return self.list(full_path)
    
    # ============ KV v2 Operations ============
    
    def kv2_read(self, mount: str, path: str, version: int = None) -> APIResponse:
        """Read a KV v2 secret."""
        url = f'/v1/{mount}/data/{path}'
        params = {'version': str(version)} if version else None
        return self.get(url, params=params)
    
    def kv2_write(self, mount: str, path: str, data: Dict,
                   cas: int = None) -> APIResponse:
        """Write a KV v2 secret."""
        payload = {'data': data}
        if cas is not None:
            payload['options'] = {'cas': cas}
        return self.post(f'/v1/{mount}/data/{path}', payload)
    
    def kv2_delete(self, mount: str, path: str) -> APIResponse:
        """Delete latest version of a KV v2 secret."""
        return self.delete(f'/v1/{mount}/data/{path}')
    
    def kv2_delete_versions(self, mount: str, path: str, 
                             versions: List[int]) -> APIResponse:
        """Delete specific versions of a KV v2 secret."""
        return self.post(f'/v1/{mount}/delete/{path}', {'versions': versions})
    
    def kv2_undelete(self, mount: str, path: str, 
                      versions: List[int]) -> APIResponse:
        """Undelete specific versions of a KV v2 secret."""
        return self.post(f'/v1/{mount}/undelete/{path}', {'versions': versions})
    
    def kv2_destroy(self, mount: str, path: str,
                     versions: List[int]) -> APIResponse:
        """Permanently destroy specific versions."""
        return self.post(f'/v1/{mount}/destroy/{path}', {'versions': versions})
    
    def kv2_list(self, mount: str, path: str = "") -> APIResponse:
        """List KV v2 secrets."""
        full_path = f'/v1/{mount}/metadata/{path}' if path else f'/v1/{mount}/metadata'
        return self.list(full_path)
    
    def kv2_metadata(self, mount: str, path: str) -> APIResponse:
        """Get metadata for a KV v2 secret."""
        return self.get(f'/v1/{mount}/metadata/{path}')
    
    def kv2_delete_metadata(self, mount: str, path: str) -> APIResponse:
        """Delete all versions and metadata for a KV v2 secret."""
        return self.delete(f'/v1/{mount}/metadata/{path}')
    
    # ============ Auth Methods ============
    
    def list_auth_methods(self) -> APIResponse:
        """List all auth methods."""
        return self.get('/v1/sys/auth')
    
    def enable_auth_method(self, path: str, method_type: str,
                           options: Dict = None) -> APIResponse:
        """Enable an auth method."""
        data = {'type': method_type}
        if options:
            data['options'] = options
        return self.post(f'/v1/sys/auth/{path}', data)
    
    def disable_auth_method(self, path: str) -> APIResponse:
        """Disable an auth method."""
        return self.delete(f'/v1/sys/auth/{path}')
    
    # ============ Policies ============
    
    def list_policies(self) -> APIResponse:
        """List all policies."""
        return self.list('/v1/sys/policies/acl')
    
    def read_policy(self, name: str) -> APIResponse:
        """Read a policy."""
        return self.get(f'/v1/sys/policies/acl/{name}')
    
    def write_policy(self, name: str, policy: str) -> APIResponse:
        """Write a policy."""
        return self.put(f'/v1/sys/policies/acl/{name}', {'policy': policy})
    
    def delete_policy(self, name: str) -> APIResponse:
        """Delete a policy."""
        return self.delete(f'/v1/sys/policies/acl/{name}')
    
    # ============ Audit Devices ============
    
    def list_audit_devices(self) -> APIResponse:
        """List audit devices."""
        return self.get('/v1/sys/audit')
    
    def enable_audit_device(self, path: str, device_type: str,
                            options: Dict = None) -> APIResponse:
        """Enable an audit device."""
        data = {'type': device_type}
        if options:
            data['options'] = options
        return self.put(f'/v1/sys/audit/{path}', data)
    
    def disable_audit_device(self, path: str) -> APIResponse:
        """Disable an audit device."""
        return self.delete(f'/v1/sys/audit/{path}')
    
    # ============ Leases ============
    
    def list_leases(self, prefix: str) -> APIResponse:
        """List leases by prefix."""
        return self.list(f'/v1/sys/leases/lookup/{prefix}')
    
    def lookup_lease(self, lease_id: str) -> APIResponse:
        """Look up a lease."""
        return self.put('/v1/sys/leases/lookup', {'lease_id': lease_id})
    
    def renew_lease(self, lease_id: str, increment: int = None) -> APIResponse:
        """Renew a lease."""
        data = {'lease_id': lease_id}
        if increment:
            data['increment'] = increment
        return self.put('/v1/sys/leases/renew', data)
    
    def revoke_lease(self, lease_id: str) -> APIResponse:
        """Revoke a lease."""
        return self.put('/v1/sys/leases/revoke', {'lease_id': lease_id})
    
    # ============ Wrapping ============
    
    def wrap(self, data: Dict, ttl: str = "5m") -> APIResponse:
        """Wrap data in a response-wrapping token."""
        headers = self._get_headers()
        headers['X-Vault-Wrap-TTL'] = ttl
        return self._make_request('POST', '/v1/sys/wrapping/wrap', 
                                   data=data, headers=headers)
    
    def unwrap(self, token: str = None) -> APIResponse:
        """Unwrap a wrapped secret."""
        headers = self._get_headers()
        if token:
            headers['X-Vault-Token'] = token
        return self.post('/v1/sys/wrapping/unwrap')
    
    def lookup_wrap(self, token: str) -> APIResponse:
        """Look up wrapping token properties."""
        return self.post('/v1/sys/wrapping/lookup', {'token': token})
    
    def rewrap(self, token: str) -> APIResponse:
        """Rewrap a wrapped secret."""
        return self.post('/v1/sys/wrapping/rewrap', {'token': token})
    
    # ============ Tools ============
    
    def random(self, bytes_count: int = 32, format: str = "base64") -> APIResponse:
        """Generate random bytes."""
        return self.post('/v1/sys/tools/random', {
            'bytes': bytes_count,
            'format': format
        })
    
    def hash(self, input_data: str, algorithm: str = "sha2-256",
             format: str = "base64") -> APIResponse:
        """Hash data."""
        return self.post('/v1/sys/tools/hash', {
            'input': input_data,
            'algorithm': algorithm,
            'format': format
        })
    
    # ============ Generic API Access ============
    
    def api_read(self, path: str) -> APIResponse:
        """Generic read from any API path."""
        if not path.startswith('/'):
            path = '/' + path
        if not path.startswith('/v1'):
            path = '/v1' + path
        return self.get(path)
    
    def api_write(self, path: str, data: Dict = None) -> APIResponse:
        """Generic write to any API path."""
        if not path.startswith('/'):
            path = '/' + path
        if not path.startswith('/v1'):
            path = '/v1' + path
        return self.post(path, data)
    
    def api_list(self, path: str) -> APIResponse:
        """Generic list from any API path."""
        if not path.startswith('/'):
            path = '/' + path
        if not path.startswith('/v1'):
            path = '/v1' + path
        return self.list(path)
    
    def api_delete(self, path: str) -> APIResponse:
        """Generic delete from any API path."""
        if not path.startswith('/'):
            path = '/' + path
        if not path.startswith('/v1'):
            path = '/v1' + path
        return self.delete(path)
    
    # ============ Schema Helpers ============
    
    def get_engine_type(self, mount_path: str) -> Optional[str]:
        """Determine the type of a secrets engine."""
        response = self.list_mounts()
        if response.ok and response.data:
            mounts = response.data.get('data', response.data)
            mount_key = mount_path.rstrip('/') + '/'
            if mount_key in mounts:
                return mounts[mount_key].get('type')
        return None
    
    def is_kv_v2(self, mount_path: str) -> bool:
        """Check if a mount is KV v2."""
        engine_type = self.get_engine_type(mount_path)
        if engine_type == 'kv':
            # Check options for version
            response = self.list_mounts()
            if response.ok and response.data:
                mounts = response.data.get('data', response.data)
                mount_key = mount_path.rstrip('/') + '/'
                if mount_key in mounts:
                    options = mounts[mount_key].get('options', {})
                    return options.get('version') == '2'
        return False
