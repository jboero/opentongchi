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
                               description: str = None, config: Dict = None,
                               options: Dict = None, local: bool = False,
                               seal_wrap: bool = False) -> APIResponse:
        """Enable a secrets engine."""
        data = {'type': engine_type}
        if description:
            data['description'] = description
        if config:
            # Filter out None/empty values from config
            filtered_config = {k: v for k, v in config.items() if v}
            if filtered_config:
                data['config'] = filtered_config
        if options:
            # Filter out None/empty values from options
            filtered_options = {k: v for k, v in options.items() if v}
            if filtered_options:
                data['options'] = filtered_options
        if local:
            data['local'] = True
        if seal_wrap:
            data['seal_wrap'] = True
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
    
    def read_auth_method(self, path: str) -> APIResponse:
        """Read auth method configuration."""
        path = path.rstrip('/')
        return self.get(f'/v1/sys/auth/{path}')
    
    def enable_auth_method(self, path: str, method_type: str,
                           description: str = None,
                           options: Dict = None,
                           config: Dict = None) -> APIResponse:
        """Enable an auth method."""
        data = {'type': method_type}
        if description:
            data['description'] = description
        if options:
            data['options'] = options
        if config:
            data['config'] = config
        return self.post(f'/v1/sys/auth/{path}', data)
    
    def tune_auth_method(self, path: str, default_lease_ttl: str = None,
                         max_lease_ttl: str = None, description: str = None,
                         listing_visibility: str = None,
                         token_type: str = None) -> APIResponse:
        """Tune an auth method's configuration."""
        path = path.rstrip('/')
        data = {}
        if default_lease_ttl:
            data['default_lease_ttl'] = default_lease_ttl
        if max_lease_ttl:
            data['max_lease_ttl'] = max_lease_ttl
        if description:
            data['description'] = description
        if listing_visibility:
            data['listing_visibility'] = listing_visibility
        if token_type:
            data['token_type'] = token_type
        return self.post(f'/v1/sys/auth/{path}/tune', data)
    
    def disable_auth_method(self, path: str) -> APIResponse:
        """Disable an auth method."""
        path = path.rstrip('/')
        return self.delete(f'/v1/sys/auth/{path}')
    
    # ============ Userpass Auth ============
    
    def userpass_list_users(self, mount: str = "userpass") -> APIResponse:
        """List all userpass users."""
        return self.list(f'/v1/auth/{mount}/users')
    
    def userpass_read_user(self, mount: str, username: str) -> APIResponse:
        """Read a userpass user."""
        return self.get(f'/v1/auth/{mount}/users/{username}')
    
    def userpass_create_user(self, mount: str, username: str, password: str,
                              policies: List[str] = None, ttl: str = None,
                              max_ttl: str = None) -> APIResponse:
        """Create or update a userpass user."""
        data = {'password': password}
        if policies:
            data['policies'] = policies
        if ttl:
            data['ttl'] = ttl
        if max_ttl:
            data['max_ttl'] = max_ttl
        return self.post(f'/v1/auth/{mount}/users/{username}', data)
    
    def userpass_update_user(self, mount: str, username: str,
                              policies: List[str] = None, ttl: str = None,
                              max_ttl: str = None) -> APIResponse:
        """Update a userpass user (without changing password)."""
        data = {}
        if policies is not None:
            data['policies'] = policies
        if ttl:
            data['ttl'] = ttl
        if max_ttl:
            data['max_ttl'] = max_ttl
        return self.post(f'/v1/auth/{mount}/users/{username}', data)
    
    def userpass_update_password(self, mount: str, username: str, 
                                  password: str) -> APIResponse:
        """Update a user's password."""
        return self.post(f'/v1/auth/{mount}/users/{username}/password', 
                        {'password': password})
    
    def userpass_delete_user(self, mount: str, username: str) -> APIResponse:
        """Delete a userpass user."""
        return self.delete(f'/v1/auth/{mount}/users/{username}')
    
    # ============ AppRole Auth ============
    
    def approle_list_roles(self, mount: str = "approle") -> APIResponse:
        """List all AppRole roles."""
        return self.list(f'/v1/auth/{mount}/role')
    
    def approle_read_role(self, mount: str, role_name: str) -> APIResponse:
        """Read an AppRole role."""
        return self.get(f'/v1/auth/{mount}/role/{role_name}')
    
    def approle_create_role(self, mount: str, role_name: str,
                             bind_secret_id: bool = True,
                             secret_id_bound_cidrs: List[str] = None,
                             token_policies: List[str] = None,
                             token_ttl: str = None,
                             token_max_ttl: str = None) -> APIResponse:
        """Create or update an AppRole role."""
        data = {'bind_secret_id': bind_secret_id}
        if secret_id_bound_cidrs:
            data['secret_id_bound_cidrs'] = secret_id_bound_cidrs
        if token_policies:
            data['token_policies'] = token_policies
        if token_ttl:
            data['token_ttl'] = token_ttl
        if token_max_ttl:
            data['token_max_ttl'] = token_max_ttl
        return self.post(f'/v1/auth/{mount}/role/{role_name}', data)
    
    def approle_delete_role(self, mount: str, role_name: str) -> APIResponse:
        """Delete an AppRole role."""
        return self.delete(f'/v1/auth/{mount}/role/{role_name}')
    
    def approle_read_role_id(self, mount: str, role_name: str) -> APIResponse:
        """Read the RoleID for an AppRole."""
        return self.get(f'/v1/auth/{mount}/role/{role_name}/role-id')
    
    def approle_generate_secret_id(self, mount: str, role_name: str,
                                    metadata: Dict = None,
                                    cidr_list: List[str] = None,
                                    ttl: str = None) -> APIResponse:
        """Generate a new SecretID for an AppRole."""
        data = {}
        if metadata:
            data['metadata'] = json.dumps(metadata)
        if cidr_list:
            data['cidr_list'] = cidr_list
        if ttl:
            data['ttl'] = ttl
        return self.post(f'/v1/auth/{mount}/role/{role_name}/secret-id', data)
    
    def approle_list_secret_ids(self, mount: str, role_name: str) -> APIResponse:
        """List SecretID accessors for an AppRole."""
        return self.list(f'/v1/auth/{mount}/role/{role_name}/secret-id')
    
    def approle_destroy_secret_id(self, mount: str, role_name: str,
                                   secret_id: str) -> APIResponse:
        """Destroy a SecretID."""
        return self.post(f'/v1/auth/{mount}/role/{role_name}/secret-id/destroy',
                        {'secret_id': secret_id})
    
    # ============ Token Auth ============
    
    def token_list_roles(self) -> APIResponse:
        """List token roles."""
        return self.list('/v1/auth/token/roles')
    
    def token_read_role(self, role_name: str) -> APIResponse:
        """Read a token role."""
        return self.get(f'/v1/auth/token/roles/{role_name}')
    
    def token_create_role(self, role_name: str, allowed_policies: List[str] = None,
                          orphan: bool = False, renewable: bool = True,
                          token_period: str = None, token_explicit_max_ttl: str = None,
                          path_suffix: str = None) -> APIResponse:
        """Create or update a token role."""
        data = {'orphan': orphan, 'renewable': renewable}
        if allowed_policies:
            data['allowed_policies'] = allowed_policies
        if token_period:
            data['token_period'] = token_period
        if token_explicit_max_ttl:
            data['token_explicit_max_ttl'] = token_explicit_max_ttl
        if path_suffix:
            data['path_suffix'] = path_suffix
        return self.post(f'/v1/auth/token/roles/{role_name}', data)
    
    def token_delete_role(self, role_name: str) -> APIResponse:
        """Delete a token role."""
        return self.delete(f'/v1/auth/token/roles/{role_name}')
    
    # ============ LDAP Auth ============
    
    def ldap_read_config(self, mount: str = "ldap") -> APIResponse:
        """Read LDAP configuration."""
        return self.get(f'/v1/auth/{mount}/config')
    
    def ldap_write_config(self, mount: str, url: str, userdn: str = None,
                          groupdn: str = None, binddn: str = None,
                          bindpass: str = None, userattr: str = None,
                          groupattr: str = None, upndomain: str = None,
                          insecure_tls: bool = False) -> APIResponse:
        """Configure LDAP auth."""
        data = {'url': url, 'insecure_tls': insecure_tls}
        if userdn:
            data['userdn'] = userdn
        if groupdn:
            data['groupdn'] = groupdn
        if binddn:
            data['binddn'] = binddn
        if bindpass:
            data['bindpass'] = bindpass
        if userattr:
            data['userattr'] = userattr
        if groupattr:
            data['groupattr'] = groupattr
        if upndomain:
            data['upndomain'] = upndomain
        return self.post(f'/v1/auth/{mount}/config', data)
    
    def ldap_list_groups(self, mount: str = "ldap") -> APIResponse:
        """List LDAP groups."""
        return self.list(f'/v1/auth/{mount}/groups')
    
    def ldap_read_group(self, mount: str, name: str) -> APIResponse:
        """Read an LDAP group."""
        return self.get(f'/v1/auth/{mount}/groups/{name}')
    
    def ldap_write_group(self, mount: str, name: str, 
                         policies: List[str]) -> APIResponse:
        """Create or update an LDAP group."""
        return self.post(f'/v1/auth/{mount}/groups/{name}', 
                        {'policies': policies})
    
    def ldap_delete_group(self, mount: str, name: str) -> APIResponse:
        """Delete an LDAP group."""
        return self.delete(f'/v1/auth/{mount}/groups/{name}')
    
    def ldap_list_users(self, mount: str = "ldap") -> APIResponse:
        """List LDAP users with policies."""
        return self.list(f'/v1/auth/{mount}/users')
    
    def ldap_read_user(self, mount: str, username: str) -> APIResponse:
        """Read an LDAP user's policies."""
        return self.get(f'/v1/auth/{mount}/users/{username}')
    
    def ldap_write_user(self, mount: str, username: str,
                        policies: List[str] = None,
                        groups: List[str] = None) -> APIResponse:
        """Create or update an LDAP user's policies."""
        data = {}
        if policies:
            data['policies'] = policies
        if groups:
            data['groups'] = groups
        return self.post(f'/v1/auth/{mount}/users/{username}', data)
    
    def ldap_delete_user(self, mount: str, username: str) -> APIResponse:
        """Delete an LDAP user."""
        return self.delete(f'/v1/auth/{mount}/users/{username}')
    
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
    
    # ============ Namespaces ============
    
    def list_namespaces(self) -> APIResponse:
        """List all namespaces."""
        return self.list('/v1/sys/namespaces')
    
    def read_namespace(self, path: str) -> APIResponse:
        """Read namespace details."""
        return self.get(f'/v1/sys/namespaces/{path}')
    
    def create_namespace(self, path: str, custom_metadata: Dict = None) -> APIResponse:
        """Create a new namespace."""
        data = {}
        if custom_metadata:
            data['custom_metadata'] = custom_metadata
        return self.post(f'/v1/sys/namespaces/{path}', data if data else None)
    
    def delete_namespace(self, path: str) -> APIResponse:
        """Delete a namespace."""
        return self.delete(f'/v1/sys/namespaces/{path}')
    
    def lock_namespace(self, path: str) -> APIResponse:
        """Lock a namespace (API lock)."""
        return self.post(f'/v1/sys/namespaces/{path}/lock')
    
    def unlock_namespace(self, path: str, unlock_key: str) -> APIResponse:
        """Unlock a namespace."""
        return self.post(f'/v1/sys/namespaces/{path}/unlock', {'unlock_key': unlock_key})
    
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
    
    # ============ Transit Engine ============
    
    def transit_list_keys(self, mount: str = "transit") -> APIResponse:
        """List transit keys."""
        return self.list(f'/v1/{mount}/keys')
    
    def transit_read_key(self, mount: str, key_name: str) -> APIResponse:
        """Read transit key configuration."""
        return self.get(f'/v1/{mount}/keys/{key_name}')
    
    def transit_create_key(self, mount: str, key_name: str, 
                           key_type: str = "aes256-gcm96",
                           exportable: bool = False,
                           allow_plaintext_backup: bool = False) -> APIResponse:
        """Create a new transit key."""
        data = {
            'type': key_type,
            'exportable': exportable,
            'allow_plaintext_backup': allow_plaintext_backup
        }
        return self.post(f'/v1/{mount}/keys/{key_name}', data)
    
    def transit_delete_key(self, mount: str, key_name: str) -> APIResponse:
        """Delete a transit key (must be configured as deletable first)."""
        return self.delete(f'/v1/{mount}/keys/{key_name}')
    
    def transit_update_key_config(self, mount: str, key_name: str,
                                   deletion_allowed: bool = None,
                                   min_decryption_version: int = None,
                                   min_encryption_version: int = None) -> APIResponse:
        """Update transit key configuration."""
        data = {}
        if deletion_allowed is not None:
            data['deletion_allowed'] = deletion_allowed
        if min_decryption_version is not None:
            data['min_decryption_version'] = min_decryption_version
        if min_encryption_version is not None:
            data['min_encryption_version'] = min_encryption_version
        return self.post(f'/v1/{mount}/keys/{key_name}/config', data)
    
    def transit_rotate_key(self, mount: str, key_name: str) -> APIResponse:
        """Rotate a transit key."""
        return self.post(f'/v1/{mount}/keys/{key_name}/rotate')
    
    def transit_encrypt(self, mount: str, key_name: str, plaintext: str,
                        context: str = None, key_version: int = None) -> APIResponse:
        """Encrypt data using a transit key. Plaintext must be base64 encoded."""
        data = {'plaintext': plaintext}
        if context:
            data['context'] = context
        if key_version:
            data['key_version'] = key_version
        return self.post(f'/v1/{mount}/encrypt/{key_name}', data)
    
    def transit_decrypt(self, mount: str, key_name: str, ciphertext: str,
                        context: str = None) -> APIResponse:
        """Decrypt data using a transit key."""
        data = {'ciphertext': ciphertext}
        if context:
            data['context'] = context
        return self.post(f'/v1/{mount}/decrypt/{key_name}', data)
    
    def transit_rewrap(self, mount: str, key_name: str, ciphertext: str,
                       context: str = None, key_version: int = None) -> APIResponse:
        """Rewrap ciphertext with a new key version."""
        data = {'ciphertext': ciphertext}
        if context:
            data['context'] = context
        if key_version:
            data['key_version'] = key_version
        return self.post(f'/v1/{mount}/rewrap/{key_name}', data)
    
    def transit_sign(self, mount: str, key_name: str, input_data: str,
                     hash_algorithm: str = "sha2-256",
                     signature_algorithm: str = None,
                     prehashed: bool = False) -> APIResponse:
        """Sign data using a transit key."""
        data = {
            'input': input_data,
            'hash_algorithm': hash_algorithm,
            'prehashed': prehashed
        }
        if signature_algorithm:
            data['signature_algorithm'] = signature_algorithm
        return self.post(f'/v1/{mount}/sign/{key_name}', data)
    
    def transit_verify(self, mount: str, key_name: str, input_data: str,
                       signature: str, hash_algorithm: str = "sha2-256",
                       prehashed: bool = False) -> APIResponse:
        """Verify a signature using a transit key."""
        data = {
            'input': input_data,
            'signature': signature,
            'hash_algorithm': hash_algorithm,
            'prehashed': prehashed
        }
        return self.post(f'/v1/{mount}/verify/{key_name}', data)
    
    def transit_generate_hmac(self, mount: str, key_name: str, input_data: str,
                              algorithm: str = "sha2-256") -> APIResponse:
        """Generate HMAC for data."""
        return self.post(f'/v1/{mount}/hmac/{key_name}', {
            'input': input_data,
            'algorithm': algorithm
        })
    
    def transit_generate_data_key(self, mount: str, key_name: str,
                                   key_type: str = "plaintext",
                                   bits: int = 256,
                                   context: str = None) -> APIResponse:
        """Generate a data key (wrapped or plaintext)."""
        data = {'bits': bits}
        if context:
            data['context'] = context
        return self.post(f'/v1/{mount}/datakey/{key_type}/{key_name}', data)
    
    def transit_export_key(self, mount: str, key_name: str,
                           key_type: str = "encryption-key",
                           version: str = None) -> APIResponse:
        """Export a transit key (if exportable)."""
        path = f'/v1/{mount}/export/{key_type}/{key_name}'
        if version:
            path += f'/{version}'
        return self.get(path)
    
    # ============ PKI Engine ============
    
    def pki_list_roles(self, mount: str = "pki") -> APIResponse:
        """List PKI roles."""
        return self.list(f'/v1/{mount}/roles')
    
    def pki_read_role(self, mount: str, role_name: str) -> APIResponse:
        """Read PKI role configuration."""
        return self.get(f'/v1/{mount}/roles/{role_name}')
    
    def pki_create_role(self, mount: str, role_name: str,
                        allowed_domains: List[str] = None,
                        allow_subdomains: bool = True,
                        allow_any_name: bool = False,
                        max_ttl: str = "72h",
                        ttl: str = "24h",
                        key_type: str = "rsa",
                        key_bits: int = 2048) -> APIResponse:
        """Create a PKI role."""
        data = {
            'allow_subdomains': allow_subdomains,
            'allow_any_name': allow_any_name,
            'max_ttl': max_ttl,
            'ttl': ttl,
            'key_type': key_type,
            'key_bits': key_bits
        }
        if allowed_domains:
            data['allowed_domains'] = allowed_domains
        return self.post(f'/v1/{mount}/roles/{role_name}', data)
    
    def pki_delete_role(self, mount: str, role_name: str) -> APIResponse:
        """Delete a PKI role."""
        return self.delete(f'/v1/{mount}/roles/{role_name}')
    
    def pki_issue_cert(self, mount: str, role_name: str, common_name: str,
                       alt_names: str = None, ip_sans: str = None,
                       ttl: str = None, format: str = "pem") -> APIResponse:
        """Issue a certificate."""
        data = {
            'common_name': common_name,
            'format': format
        }
        if alt_names:
            data['alt_names'] = alt_names
        if ip_sans:
            data['ip_sans'] = ip_sans
        if ttl:
            data['ttl'] = ttl
        return self.post(f'/v1/{mount}/issue/{role_name}', data)
    
    def pki_sign_csr(self, mount: str, role_name: str, csr: str,
                     common_name: str = None, ttl: str = None) -> APIResponse:
        """Sign a CSR."""
        data = {'csr': csr}
        if common_name:
            data['common_name'] = common_name
        if ttl:
            data['ttl'] = ttl
        return self.post(f'/v1/{mount}/sign/{role_name}', data)
    
    def pki_generate_root(self, mount: str, common_name: str,
                          key_type: str = "rsa", key_bits: int = 2048,
                          ttl: str = "87600h", issuer_name: str = None) -> APIResponse:
        """Generate a root CA certificate."""
        data = {
            'common_name': common_name,
            'key_type': key_type,
            'key_bits': key_bits,
            'ttl': ttl
        }
        if issuer_name:
            data['issuer_name'] = issuer_name
        return self.post(f'/v1/{mount}/root/generate/internal', data)
    
    def pki_generate_intermediate(self, mount: str, common_name: str,
                                   key_type: str = "rsa", 
                                   key_bits: int = 2048) -> APIResponse:
        """Generate an intermediate CA CSR."""
        data = {
            'common_name': common_name,
            'key_type': key_type,
            'key_bits': key_bits
        }
        return self.post(f'/v1/{mount}/intermediate/generate/internal', data)
    
    def pki_set_signed_intermediate(self, mount: str, certificate: str) -> APIResponse:
        """Set signed intermediate certificate."""
        return self.post(f'/v1/{mount}/intermediate/set-signed', {
            'certificate': certificate
        })
    
    def pki_read_ca_cert(self, mount: str = "pki", format: str = "pem") -> APIResponse:
        """Read CA certificate."""
        if format == "der":
            return self.get(f'/v1/{mount}/ca')
        return self.get(f'/v1/{mount}/ca/pem')
    
    def pki_read_crl(self, mount: str = "pki") -> APIResponse:
        """Read CRL."""
        return self.get(f'/v1/{mount}/crl/pem')
    
    def pki_list_certs(self, mount: str = "pki") -> APIResponse:
        """List issued certificates by serial number."""
        return self.list(f'/v1/{mount}/certs')
    
    def pki_read_cert(self, mount: str, serial: str) -> APIResponse:
        """Read a certificate by serial number."""
        return self.get(f'/v1/{mount}/cert/{serial}')
    
    def pki_revoke_cert(self, mount: str, serial: str) -> APIResponse:
        """Revoke a certificate by serial number."""
        return self.post(f'/v1/{mount}/revoke', {'serial_number': serial})
    
    def pki_tidy(self, mount: str, tidy_cert_store: bool = True,
                 tidy_revoked_certs: bool = True,
                 safety_buffer: str = "72h") -> APIResponse:
        """Tidy up the certificate store."""
        return self.post(f'/v1/{mount}/tidy', {
            'tidy_cert_store': tidy_cert_store,
            'tidy_revoked_certs': tidy_revoked_certs,
            'safety_buffer': safety_buffer
        })
    
    def pki_list_issuers(self, mount: str = "pki") -> APIResponse:
        """List PKI issuers."""
        return self.list(f'/v1/{mount}/issuers')
    
    def pki_read_issuer(self, mount: str, issuer_ref: str) -> APIResponse:
        """Read issuer details."""
        return self.get(f'/v1/{mount}/issuer/{issuer_ref}')
    
    # ============ Identity - Entities ============
    
    def identity_list_entities(self) -> APIResponse:
        """List all entities by ID."""
        return self.list('/v1/identity/entity/id')
    
    def identity_list_entities_by_name(self) -> APIResponse:
        """List all entities by name."""
        return self.list('/v1/identity/entity/name')
    
    def identity_read_entity(self, entity_id: str) -> APIResponse:
        """Read an entity by ID."""
        return self.get(f'/v1/identity/entity/id/{entity_id}')
    
    def identity_read_entity_by_name(self, name: str) -> APIResponse:
        """Read an entity by name."""
        return self.get(f'/v1/identity/entity/name/{name}')
    
    def identity_create_entity(self, name: str, policies: List[str] = None,
                                metadata: Dict = None, disabled: bool = False) -> APIResponse:
        """Create a new entity."""
        data = {'name': name, 'disabled': disabled}
        if policies:
            data['policies'] = policies
        if metadata:
            data['metadata'] = metadata
        return self.post('/v1/identity/entity', data)
    
    def identity_update_entity(self, entity_id: str, name: str = None,
                                policies: List[str] = None, metadata: Dict = None,
                                disabled: bool = None) -> APIResponse:
        """Update an entity by ID."""
        data = {}
        if name is not None:
            data['name'] = name
        if policies is not None:
            data['policies'] = policies
        if metadata is not None:
            data['metadata'] = metadata
        if disabled is not None:
            data['disabled'] = disabled
        return self.post(f'/v1/identity/entity/id/{entity_id}', data)
    
    def identity_delete_entity(self, entity_id: str) -> APIResponse:
        """Delete an entity by ID."""
        return self.delete(f'/v1/identity/entity/id/{entity_id}')
    
    def identity_delete_entity_by_name(self, name: str) -> APIResponse:
        """Delete an entity by name."""
        return self.delete(f'/v1/identity/entity/name/{name}')
    
    def identity_merge_entities(self, to_entity_id: str, from_entity_ids: List[str],
                                 force: bool = False) -> APIResponse:
        """Merge multiple entities into one."""
        return self.post('/v1/identity/entity/merge', {
            'to_entity_id': to_entity_id,
            'from_entity_ids': from_entity_ids,
            'force': force
        })
    
    # ============ Identity - Entity Aliases ============
    
    def identity_list_entity_aliases(self) -> APIResponse:
        """List all entity aliases by ID."""
        return self.list('/v1/identity/entity-alias/id')
    
    def identity_read_entity_alias(self, alias_id: str) -> APIResponse:
        """Read an entity alias by ID."""
        return self.get(f'/v1/identity/entity-alias/id/{alias_id}')
    
    def identity_create_entity_alias(self, name: str, canonical_id: str,
                                      mount_accessor: str, custom_metadata: Dict = None) -> APIResponse:
        """Create an entity alias."""
        data = {
            'name': name,
            'canonical_id': canonical_id,
            'mount_accessor': mount_accessor
        }
        if custom_metadata:
            data['custom_metadata'] = custom_metadata
        return self.post('/v1/identity/entity-alias', data)
    
    def identity_update_entity_alias(self, alias_id: str, name: str = None,
                                      canonical_id: str = None, mount_accessor: str = None,
                                      custom_metadata: Dict = None) -> APIResponse:
        """Update an entity alias."""
        data = {}
        if name is not None:
            data['name'] = name
        if canonical_id is not None:
            data['canonical_id'] = canonical_id
        if mount_accessor is not None:
            data['mount_accessor'] = mount_accessor
        if custom_metadata is not None:
            data['custom_metadata'] = custom_metadata
        return self.post(f'/v1/identity/entity-alias/id/{alias_id}', data)
    
    def identity_delete_entity_alias(self, alias_id: str) -> APIResponse:
        """Delete an entity alias."""
        return self.delete(f'/v1/identity/entity-alias/id/{alias_id}')
    
    # ============ Identity - Groups ============
    
    def identity_list_groups(self) -> APIResponse:
        """List all groups by ID."""
        return self.list('/v1/identity/group/id')
    
    def identity_list_groups_by_name(self) -> APIResponse:
        """List all groups by name."""
        return self.list('/v1/identity/group/name')
    
    def identity_read_group(self, group_id: str) -> APIResponse:
        """Read a group by ID."""
        return self.get(f'/v1/identity/group/id/{group_id}')
    
    def identity_read_group_by_name(self, name: str) -> APIResponse:
        """Read a group by name."""
        return self.get(f'/v1/identity/group/name/{name}')
    
    def identity_create_group(self, name: str, group_type: str = "internal",
                               policies: List[str] = None, metadata: Dict = None,
                               member_entity_ids: List[str] = None,
                               member_group_ids: List[str] = None) -> APIResponse:
        """Create a new group."""
        data = {'name': name, 'type': group_type}
        if policies:
            data['policies'] = policies
        if metadata:
            data['metadata'] = metadata
        if member_entity_ids:
            data['member_entity_ids'] = member_entity_ids
        if member_group_ids:
            data['member_group_ids'] = member_group_ids
        return self.post('/v1/identity/group', data)
    
    def identity_update_group(self, group_id: str, name: str = None,
                               policies: List[str] = None, metadata: Dict = None,
                               member_entity_ids: List[str] = None,
                               member_group_ids: List[str] = None) -> APIResponse:
        """Update a group by ID."""
        data = {}
        if name is not None:
            data['name'] = name
        if policies is not None:
            data['policies'] = policies
        if metadata is not None:
            data['metadata'] = metadata
        if member_entity_ids is not None:
            data['member_entity_ids'] = member_entity_ids
        if member_group_ids is not None:
            data['member_group_ids'] = member_group_ids
        return self.post(f'/v1/identity/group/id/{group_id}', data)
    
    def identity_delete_group(self, group_id: str) -> APIResponse:
        """Delete a group by ID."""
        return self.delete(f'/v1/identity/group/id/{group_id}')
    
    def identity_delete_group_by_name(self, name: str) -> APIResponse:
        """Delete a group by name."""
        return self.delete(f'/v1/identity/group/name/{name}')
    
    # ============ Identity - Group Aliases ============
    
    def identity_list_group_aliases(self) -> APIResponse:
        """List all group aliases by ID."""
        return self.list('/v1/identity/group-alias/id')
    
    def identity_read_group_alias(self, alias_id: str) -> APIResponse:
        """Read a group alias by ID."""
        return self.get(f'/v1/identity/group-alias/id/{alias_id}')
    
    def identity_create_group_alias(self, name: str, canonical_id: str,
                                     mount_accessor: str) -> APIResponse:
        """Create a group alias."""
        return self.post('/v1/identity/group-alias', {
            'name': name,
            'canonical_id': canonical_id,
            'mount_accessor': mount_accessor
        })
    
    def identity_delete_group_alias(self, alias_id: str) -> APIResponse:
        """Delete a group alias."""
        return self.delete(f'/v1/identity/group-alias/id/{alias_id}')
    
    # ============ Identity - Lookup ============
    
    def identity_lookup_entity(self, name: str = None, entity_id: str = None,
                                alias_id: str = None, alias_name: str = None,
                                alias_mount_accessor: str = None) -> APIResponse:
        """Lookup an entity by various criteria."""
        data = {}
        if name:
            data['name'] = name
        if entity_id:
            data['id'] = entity_id
        if alias_id:
            data['alias_id'] = alias_id
        if alias_name:
            data['alias_name'] = alias_name
        if alias_mount_accessor:
            data['alias_mount_accessor'] = alias_mount_accessor
        return self.post('/v1/identity/lookup/entity', data)
    
    def identity_lookup_group(self, name: str = None, group_id: str = None,
                               alias_id: str = None, alias_name: str = None,
                               alias_mount_accessor: str = None) -> APIResponse:
        """Lookup a group by various criteria."""
        data = {}
        if name:
            data['name'] = name
        if group_id:
            data['id'] = group_id
        if alias_id:
            data['alias_id'] = alias_id
        if alias_name:
            data['alias_name'] = alias_name
        if alias_mount_accessor:
            data['alias_mount_accessor'] = alias_mount_accessor
        return self.post('/v1/identity/lookup/group', data)
    
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

    # ==================== Database Secrets Engine ====================
    
    def db_list_connections(self, mount: str = "database") -> APIResponse:
        """List database connections."""
        return self._request("GET", f"/{mount}/config", list_request=True)
    
    def db_read_connection(self, mount: str, name: str) -> APIResponse:
        """Read database connection configuration."""
        return self._request("GET", f"/{mount}/config/{name}")
    
    def db_create_connection(self, mount: str, name: str, plugin_name: str,
                              connection_url: str, allowed_roles: List[str] = None,
                              username: str = None, password: str = None,
                              verify_connection: bool = True,
                              **kwargs) -> APIResponse:
        """Create or update a database connection."""
        data = {
            "plugin_name": plugin_name,
            "connection_url": connection_url,
            "verify_connection": verify_connection,
        }
        if allowed_roles:
            data["allowed_roles"] = allowed_roles
        if username:
            data["username"] = username
        if password:
            data["password"] = password
        data.update(kwargs)
        return self._request("POST", f"/{mount}/config/{name}", data=data)
    
    def db_delete_connection(self, mount: str, name: str) -> APIResponse:
        """Delete a database connection."""
        return self._request("DELETE", f"/{mount}/config/{name}")
    
    def db_reset_connection(self, mount: str, name: str) -> APIResponse:
        """Reset a database connection (close and reconnect)."""
        return self._request("POST", f"/{mount}/reset/{name}")
    
    def db_rotate_root(self, mount: str, name: str) -> APIResponse:
        """Rotate the root credentials for a database connection."""
        return self._request("POST", f"/{mount}/rotate-root/{name}")
    
    def db_list_roles(self, mount: str = "database") -> APIResponse:
        """List database roles."""
        return self._request("GET", f"/{mount}/roles", list_request=True)
    
    def db_read_role(self, mount: str, role_name: str) -> APIResponse:
        """Read a database role."""
        return self._request("GET", f"/{mount}/roles/{role_name}")
    
    def db_create_role(self, mount: str, role_name: str, db_name: str,
                       creation_statements: List[str],
                       revocation_statements: List[str] = None,
                       rollback_statements: List[str] = None,
                       renew_statements: List[str] = None,
                       default_ttl: str = None, max_ttl: str = None,
                       **kwargs) -> APIResponse:
        """Create or update a database role."""
        data = {
            "db_name": db_name,
            "creation_statements": creation_statements,
        }
        if revocation_statements:
            data["revocation_statements"] = revocation_statements
        if rollback_statements:
            data["rollback_statements"] = rollback_statements
        if renew_statements:
            data["renew_statements"] = renew_statements
        if default_ttl:
            data["default_ttl"] = default_ttl
        if max_ttl:
            data["max_ttl"] = max_ttl
        data.update(kwargs)
        return self._request("POST", f"/{mount}/roles/{role_name}", data=data)
    
    def db_delete_role(self, mount: str, role_name: str) -> APIResponse:
        """Delete a database role."""
        return self._request("DELETE", f"/{mount}/roles/{role_name}")
    
    def db_list_static_roles(self, mount: str = "database") -> APIResponse:
        """List static database roles."""
        return self._request("GET", f"/{mount}/static-roles", list_request=True)
    
    def db_read_static_role(self, mount: str, role_name: str) -> APIResponse:
        """Read a static database role."""
        return self._request("GET", f"/{mount}/static-roles/{role_name}")
    
    def db_create_static_role(self, mount: str, role_name: str, db_name: str,
                               username: str, rotation_period: str,
                               rotation_statements: List[str] = None,
                               **kwargs) -> APIResponse:
        """Create or update a static database role."""
        data = {
            "db_name": db_name,
            "username": username,
            "rotation_period": rotation_period,
        }
        if rotation_statements:
            data["rotation_statements"] = rotation_statements
        data.update(kwargs)
        return self._request("POST", f"/{mount}/static-roles/{role_name}", data=data)
    
    def db_delete_static_role(self, mount: str, role_name: str) -> APIResponse:
        """Delete a static database role."""
        return self._request("DELETE", f"/{mount}/static-roles/{role_name}")
    
    def db_generate_creds(self, mount: str, role_name: str) -> APIResponse:
        """Generate credentials for a database role."""
        return self._request("GET", f"/{mount}/creds/{role_name}")
    
    def db_get_static_creds(self, mount: str, role_name: str) -> APIResponse:
        """Get credentials for a static database role."""
        return self._request("GET", f"/{mount}/static-creds/{role_name}")
    
    def db_rotate_static_role(self, mount: str, role_name: str) -> APIResponse:
        """Rotate credentials for a static database role."""
        return self._request("POST", f"/{mount}/rotate-role/{role_name}")

    # ==================== SSH Secrets Engine ====================
    
    def ssh_read_ca(self, mount: str = "ssh") -> APIResponse:
        """Read the SSH CA public key."""
        return self._request("GET", f"/{mount}/config/ca")
    
    def ssh_configure_ca(self, mount: str, private_key: str = None,
                          public_key: str = None, generate_signing_key: bool = True,
                          key_type: str = "ssh-rsa", key_bits: int = 0) -> APIResponse:
        """Configure the SSH CA."""
        data = {"generate_signing_key": generate_signing_key}
        if private_key:
            data["private_key"] = private_key
        if public_key:
            data["public_key"] = public_key
        if key_type:
            data["key_type"] = key_type
        if key_bits:
            data["key_bits"] = key_bits
        return self._request("POST", f"/{mount}/config/ca", data=data)
    
    def ssh_delete_ca(self, mount: str = "ssh") -> APIResponse:
        """Delete the SSH CA configuration."""
        return self._request("DELETE", f"/{mount}/config/ca")
    
    def ssh_read_zeroaddress(self, mount: str = "ssh") -> APIResponse:
        """Read the zero-address configuration."""
        return self._request("GET", f"/{mount}/config/zeroaddress")
    
    def ssh_configure_zeroaddress(self, mount: str, roles: List[str]) -> APIResponse:
        """Configure zero-address roles."""
        return self._request("POST", f"/{mount}/config/zeroaddress", data={"roles": roles})
    
    def ssh_delete_zeroaddress(self, mount: str = "ssh") -> APIResponse:
        """Delete the zero-address configuration."""
        return self._request("DELETE", f"/{mount}/config/zeroaddress")
    
    def ssh_list_roles(self, mount: str = "ssh") -> APIResponse:
        """List SSH roles."""
        return self._request("GET", f"/{mount}/roles", list_request=True)
    
    def ssh_read_role(self, mount: str, role_name: str) -> APIResponse:
        """Read an SSH role."""
        return self._request("GET", f"/{mount}/roles/{role_name}")
    
    def ssh_create_role(self, mount: str, role_name: str, key_type: str,
                        default_user: str = None, allowed_users: str = None,
                        allowed_domains: str = None, cidr_list: str = None,
                        allowed_extensions: str = None,
                        default_extensions: Dict = None,
                        allowed_user_key_lengths: Dict = None,
                        ttl: str = None, max_ttl: str = None,
                        algorithm_signer: str = None,
                        allow_user_certificates: bool = True,
                        allow_host_certificates: bool = False,
                        **kwargs) -> APIResponse:
        """Create or update an SSH role."""
        data = {"key_type": key_type}
        if default_user:
            data["default_user"] = default_user
        if allowed_users:
            data["allowed_users"] = allowed_users
        if allowed_domains:
            data["allowed_domains"] = allowed_domains
        if cidr_list:
            data["cidr_list"] = cidr_list
        if allowed_extensions:
            data["allowed_extensions"] = allowed_extensions
        if default_extensions:
            data["default_extensions"] = default_extensions
        if allowed_user_key_lengths:
            data["allowed_user_key_lengths"] = allowed_user_key_lengths
        if ttl:
            data["ttl"] = ttl
        if max_ttl:
            data["max_ttl"] = max_ttl
        if algorithm_signer:
            data["algorithm_signer"] = algorithm_signer
        if key_type == "ca":
            data["allow_user_certificates"] = allow_user_certificates
            data["allow_host_certificates"] = allow_host_certificates
        data.update(kwargs)
        return self._request("POST", f"/{mount}/roles/{role_name}", data=data)
    
    def ssh_delete_role(self, mount: str, role_name: str) -> APIResponse:
        """Delete an SSH role."""
        return self._request("DELETE", f"/{mount}/roles/{role_name}")
    
    def ssh_sign_key(self, mount: str, role_name: str, public_key: str,
                     valid_principals: str = None, cert_type: str = "user",
                     ttl: str = None, extensions: Dict = None,
                     critical_options: Dict = None) -> APIResponse:
        """Sign an SSH public key."""
        data = {"public_key": public_key, "cert_type": cert_type}
        if valid_principals:
            data["valid_principals"] = valid_principals
        if ttl:
            data["ttl"] = ttl
        if extensions:
            data["extensions"] = extensions
        if critical_options:
            data["critical_options"] = critical_options
        return self._request("POST", f"/{mount}/sign/{role_name}", data=data)
    
    def ssh_issue_credentials(self, mount: str, role_name: str,
                               key_type: str = "ssh-rsa", key_bits: int = 0,
                               ttl: str = None, valid_principals: str = None,
                               extensions: Dict = None,
                               critical_options: Dict = None) -> APIResponse:
        """Issue SSH credentials (key pair + certificate)."""
        data = {"key_type": key_type}
        if key_bits:
            data["key_bits"] = key_bits
        if ttl:
            data["ttl"] = ttl
        if valid_principals:
            data["valid_principals"] = valid_principals
        if extensions:
            data["extensions"] = extensions
        if critical_options:
            data["critical_options"] = critical_options
        return self._request("POST", f"/{mount}/issue/{role_name}", data=data)
    
    def ssh_verify_otp(self, mount: str, otp: str) -> APIResponse:
        """Verify an SSH OTP."""
        return self._request("POST", f"/{mount}/verify", data={"otp": otp})

    # ==================== System (sys) Endpoints ====================
    
    def sys_capabilities(self, paths: List[str], token: str = None) -> APIResponse:
        """Check capabilities for paths."""
        data = {"paths": paths}
        if token:
            data["token"] = token
        endpoint = "/sys/capabilities" if token else "/sys/capabilities-self"
        return self._request("POST", endpoint, data=data)
    
    def sys_internal_counters_activity(self) -> APIResponse:
        """Get client activity data."""
        return self._request("GET", "/sys/internal/counters/activity")
    
    def sys_internal_counters_tokens(self) -> APIResponse:
        """Get token count."""
        return self._request("GET", "/sys/internal/counters/tokens")
    
    def sys_internal_counters_entities(self) -> APIResponse:
        """Get entity count."""
        return self._request("GET", "/sys/internal/counters/entities")
    
    def sys_internal_specs_openapi(self) -> APIResponse:
        """Get OpenAPI spec."""
        return self._request("GET", "/sys/internal/specs/openapi")
    
    def sys_config_state_sanitized(self) -> APIResponse:
        """Get sanitized configuration."""
        return self._request("GET", "/sys/config/state/sanitized")
    
    def sys_host_info(self) -> APIResponse:
        """Get host information."""
        return self._request("GET", "/sys/host-info")
    
    def sys_in_flight_requests(self) -> APIResponse:
        """Get in-flight requests."""
        return self._request("GET", "/sys/in-flight-req")
    
    def sys_metrics(self, format: str = "prometheus") -> APIResponse:
        """Get metrics."""
        return self._request("GET", f"/sys/metrics?format={format}")
    
    def sys_pprof(self, profile: str = "profile") -> APIResponse:
        """Get pprof data (profile, heap, goroutine, etc.)."""
        return self._request("GET", f"/sys/pprof/{profile}")
    
    def sys_seal(self) -> APIResponse:
        """Seal the vault."""
        return self._request("PUT", "/sys/seal")
    
    def sys_unseal(self, key: str, reset: bool = False, migrate: bool = False) -> APIResponse:
        """Unseal the vault."""
        data = {"key": key, "reset": reset, "migrate": migrate}
        return self._request("PUT", "/sys/unseal", data=data)
    
    def sys_step_down(self) -> APIResponse:
        """Force the active node to step down."""
        return self._request("PUT", "/sys/step-down")
    
    def sys_generate_root_init(self, otp: str = None, pgp_key: str = None) -> APIResponse:
        """Initialize root token generation."""
        data = {}
        if otp:
            data["otp"] = otp
        if pgp_key:
            data["pgp_key"] = pgp_key
        return self._request("PUT", "/sys/generate-root/attempt", data=data)
    
    def sys_generate_root_update(self, key: str, nonce: str) -> APIResponse:
        """Update root token generation with unseal key."""
        return self._request("PUT", "/sys/generate-root/update", data={"key": key, "nonce": nonce})
    
    def sys_generate_root_cancel(self) -> APIResponse:
        """Cancel root token generation."""
        return self._request("DELETE", "/sys/generate-root/attempt")
    
    def sys_rekey_init(self, secret_shares: int, secret_threshold: int,
                       pgp_keys: List[str] = None, backup: bool = False) -> APIResponse:
        """Initialize rekey operation."""
        data = {
            "secret_shares": secret_shares,
            "secret_threshold": secret_threshold,
            "backup": backup,
        }
        if pgp_keys:
            data["pgp_keys"] = pgp_keys
        return self._request("PUT", "/sys/rekey/init", data=data)
    
    def sys_rekey_update(self, key: str, nonce: str) -> APIResponse:
        """Update rekey with unseal key."""
        return self._request("PUT", "/sys/rekey/update", data={"key": key, "nonce": nonce})
    
    def sys_rekey_cancel(self) -> APIResponse:
        """Cancel rekey operation."""
        return self._request("DELETE", "/sys/rekey/init")
    
    def sys_rekey_status(self) -> APIResponse:
        """Get rekey status."""
        return self._request("GET", "/sys/rekey/init")
    
    def sys_rekey_verify_status(self) -> APIResponse:
        """Get rekey verification status."""
        return self._request("GET", "/sys/rekey/verify")
    
    def sys_plugins_catalog(self) -> APIResponse:
        """List all registered plugins."""
        return self._request("GET", "/sys/plugins/catalog")
    
    def sys_plugins_catalog_type(self, plugin_type: str) -> APIResponse:
        """List plugins by type (auth, database, secret)."""
        return self._request("GET", f"/sys/plugins/catalog/{plugin_type}", list_request=True)
    
    def sys_plugins_read(self, plugin_type: str, name: str) -> APIResponse:
        """Read plugin info."""
        return self._request("GET", f"/sys/plugins/catalog/{plugin_type}/{name}")
    
    def sys_plugins_register(self, plugin_type: str, name: str, sha256: str,
                              command: str, args: List[str] = None,
                              env: List[str] = None) -> APIResponse:
        """Register a plugin."""
        data = {"sha256": sha256, "command": command}
        if args:
            data["args"] = args
        if env:
            data["env"] = env
        return self._request("PUT", f"/sys/plugins/catalog/{plugin_type}/{name}", data=data)
    
    def sys_plugins_deregister(self, plugin_type: str, name: str) -> APIResponse:
        """Deregister a plugin."""
        return self._request("DELETE", f"/sys/plugins/catalog/{plugin_type}/{name}")
    
    def sys_plugins_reload(self, plugin: str = None, mounts: List[str] = None) -> APIResponse:
        """Reload plugins."""
        data = {}
        if plugin:
            data["plugin"] = plugin
        if mounts:
            data["mounts"] = mounts
        return self._request("PUT", "/sys/plugins/reload/backend", data=data)
    
    def sys_tools_random(self, bytes_count: int = 32, format: str = "base64") -> APIResponse:
        """Generate random bytes."""
        return self._request("POST", f"/sys/tools/random/{bytes_count}", data={"format": format})
    
    def sys_tools_hash(self, input_data: str, algorithm: str = "sha2-256",
                       format: str = "base64") -> APIResponse:
        """Hash data."""
        return self._request("POST", f"/sys/tools/hash/{algorithm}",
                           data={"input": input_data, "format": format})
    
    def sys_license(self) -> APIResponse:
        """Get license info (Enterprise only)."""
        return self._request("GET", "/sys/license")
    
    def sys_replication_status(self) -> APIResponse:
        """Get replication status."""
        return self._request("GET", "/sys/replication/status")
    
    def sys_storage_raft_configuration(self) -> APIResponse:
        """Get Raft storage configuration."""
        return self._request("GET", "/sys/storage/raft/configuration")
    
    def sys_storage_raft_autopilot_state(self) -> APIResponse:
        """Get Raft autopilot state."""
        return self._request("GET", "/sys/storage/raft/autopilot/state")
    
    def sys_storage_raft_snapshot(self) -> APIResponse:
        """Take a Raft snapshot."""
        return self._request("GET", "/sys/storage/raft/snapshot")
    
    def sys_ha_status(self) -> APIResponse:
        """Get HA status."""
        return self._request("GET", "/sys/ha-status")
    
    def sys_key_status(self) -> APIResponse:
        """Get encryption key status."""
        return self._request("GET", "/sys/key-status")
    
    def sys_rotate(self) -> APIResponse:
        """Rotate the encryption key."""
        return self._request("PUT", "/sys/rotate")
    
    def sys_wrapping_lookup(self, token: str) -> APIResponse:
        """Look up wrapping token info."""
        return self._request("POST", "/sys/wrapping/lookup", data={"token": token})
    
    def sys_wrapping_rewrap(self, token: str) -> APIResponse:
        """Rewrap a wrapping token."""
        return self._request("POST", "/sys/wrapping/rewrap", data={"token": token})
    
    def sys_wrapping_unwrap(self, token: str = None) -> APIResponse:
        """Unwrap a wrapping token."""
        data = {"token": token} if token else {}
        return self._request("POST", "/sys/wrapping/unwrap", data=data)
    
    def sys_mounts_tune(self, path: str, default_lease_ttl: str = None,
                        max_lease_ttl: str = None, description: str = None,
                        audit_non_hmac_request_keys: List[str] = None,
                        audit_non_hmac_response_keys: List[str] = None,
                        listing_visibility: str = None,
                        passthrough_request_headers: List[str] = None) -> APIResponse:
        """Tune a secrets engine mount."""
        data = {}
        if default_lease_ttl:
            data["default_lease_ttl"] = default_lease_ttl
        if max_lease_ttl:
            data["max_lease_ttl"] = max_lease_ttl
        if description:
            data["description"] = description
        if audit_non_hmac_request_keys:
            data["audit_non_hmac_request_keys"] = audit_non_hmac_request_keys
        if audit_non_hmac_response_keys:
            data["audit_non_hmac_response_keys"] = audit_non_hmac_response_keys
        if listing_visibility:
            data["listing_visibility"] = listing_visibility
        if passthrough_request_headers:
            data["passthrough_request_headers"] = passthrough_request_headers
        return self._request("POST", f"/sys/mounts/{path}/tune", data=data)
    
    def sys_mounts_read_tune(self, path: str) -> APIResponse:
        """Read mount tune settings."""
        return self._request("GET", f"/sys/mounts/{path}/tune")
    
    # ==================== Database Secrets Engine ====================
    
    def database_list_connections(self, mount: str = "database") -> APIResponse:
        """List all database connections."""
        return self.api_list(f"{mount}/config")
    
    def database_read_connection(self, mount: str, name: str) -> APIResponse:
        """Read a database connection configuration."""
        return self.api_read(f"{mount}/config/{name}")
    
    def database_create_connection(self, mount: str, name: str, plugin_name: str,
                                   connection_url: str, allowed_roles: List[str] = None,
                                   username: str = None, password: str = None,
                                   **kwargs) -> APIResponse:
        """Create or update a database connection."""
        data = {
            'plugin_name': plugin_name,
            'connection_url': connection_url,
        }
        if allowed_roles:
            data['allowed_roles'] = allowed_roles
        if username:
            data['username'] = username
        if password:
            data['password'] = password
        data.update(kwargs)
        return self.api_write(f"{mount}/config/{name}", data)
    
    def database_delete_connection(self, mount: str, name: str) -> APIResponse:
        """Delete a database connection."""
        return self.api_delete(f"{mount}/config/{name}")
    
    def database_reset_connection(self, mount: str, name: str) -> APIResponse:
        """Reset a database connection (close and reopen)."""
        return self.api_write(f"{mount}/reset/{name}")
    
    def database_rotate_root(self, mount: str, name: str) -> APIResponse:
        """Rotate the root credentials for a database connection."""
        return self.api_write(f"{mount}/rotate-root/{name}")
    
    def database_list_roles(self, mount: str = "database") -> APIResponse:
        """List all database roles."""
        return self.api_list(f"{mount}/roles")
    
    def database_read_role(self, mount: str, role_name: str) -> APIResponse:
        """Read a database role."""
        return self.api_read(f"{mount}/roles/{role_name}")
    
    def database_create_role(self, mount: str, role_name: str, db_name: str,
                             creation_statements: List[str],
                             revocation_statements: List[str] = None,
                             rollback_statements: List[str] = None,
                             renew_statements: List[str] = None,
                             default_ttl: str = None, max_ttl: str = None,
                             **kwargs) -> APIResponse:
        """Create or update a database role."""
        data = {
            'db_name': db_name,
            'creation_statements': creation_statements,
        }
        if revocation_statements:
            data['revocation_statements'] = revocation_statements
        if rollback_statements:
            data['rollback_statements'] = rollback_statements
        if renew_statements:
            data['renew_statements'] = renew_statements
        if default_ttl:
            data['default_ttl'] = default_ttl
        if max_ttl:
            data['max_ttl'] = max_ttl
        data.update(kwargs)
        return self.api_write(f"{mount}/roles/{role_name}", data)
    
    def database_delete_role(self, mount: str, role_name: str) -> APIResponse:
        """Delete a database role."""
        return self.api_delete(f"{mount}/roles/{role_name}")
    
    def database_list_static_roles(self, mount: str = "database") -> APIResponse:
        """List all static database roles."""
        return self.api_list(f"{mount}/static-roles")
    
    def database_read_static_role(self, mount: str, role_name: str) -> APIResponse:
        """Read a static database role."""
        return self.api_read(f"{mount}/static-roles/{role_name}")
    
    def database_create_static_role(self, mount: str, role_name: str, db_name: str,
                                    username: str, rotation_period: str,
                                    rotation_statements: List[str] = None,
                                    **kwargs) -> APIResponse:
        """Create or update a static database role."""
        data = {
            'db_name': db_name,
            'username': username,
            'rotation_period': rotation_period,
        }
        if rotation_statements:
            data['rotation_statements'] = rotation_statements
        data.update(kwargs)
        return self.api_write(f"{mount}/static-roles/{role_name}", data)
    
    def database_delete_static_role(self, mount: str, role_name: str) -> APIResponse:
        """Delete a static database role."""
        return self.api_delete(f"{mount}/static-roles/{role_name}")
    
    def database_generate_creds(self, mount: str, role_name: str) -> APIResponse:
        """Generate credentials for a database role."""
        return self.api_read(f"{mount}/creds/{role_name}")
    
    def database_get_static_creds(self, mount: str, role_name: str) -> APIResponse:
        """Get credentials for a static database role."""
        return self.api_read(f"{mount}/static-creds/{role_name}")
    
    def database_rotate_static_role(self, mount: str, role_name: str) -> APIResponse:
        """Rotate credentials for a static database role."""
        return self.api_write(f"{mount}/rotate-role/{role_name}")
    
    # ==================== SSH Secrets Engine ====================
    
    def ssh_read_ca_config(self, mount: str = "ssh") -> APIResponse:
        """Read the SSH CA public key."""
        return self.api_read(f"{mount}/config/ca")
    
    def ssh_configure_ca(self, mount: str, private_key: str = None,
                         public_key: str = None, generate_signing_key: bool = True,
                         key_type: str = "ssh-rsa", key_bits: int = 0) -> APIResponse:
        """Configure the SSH CA."""
        data = {'generate_signing_key': generate_signing_key}
        if private_key:
            data['private_key'] = private_key
        if public_key:
            data['public_key'] = public_key
        if key_type:
            data['key_type'] = key_type
        if key_bits:
            data['key_bits'] = key_bits
        return self.api_write(f"{mount}/config/ca", data)
    
    def ssh_delete_ca(self, mount: str = "ssh") -> APIResponse:
        """Delete the SSH CA configuration."""
        return self.api_delete(f"{mount}/config/ca")
    
    def ssh_read_zeroaddress(self, mount: str = "ssh") -> APIResponse:
        """Read the zero-address configuration."""
        return self.api_read(f"{mount}/config/zeroaddress")
    
    def ssh_configure_zeroaddress(self, mount: str, roles: List[str]) -> APIResponse:
        """Configure zero-address roles."""
        return self.api_write(f"{mount}/config/zeroaddress", {'roles': roles})
    
    def ssh_delete_zeroaddress(self, mount: str = "ssh") -> APIResponse:
        """Delete the zero-address configuration."""
        return self.api_delete(f"{mount}/config/zeroaddress")
    
    def ssh_list_roles(self, mount: str = "ssh") -> APIResponse:
        """List all SSH roles."""
        return self.api_list(f"{mount}/roles")
    
    def ssh_read_role(self, mount: str, role_name: str) -> APIResponse:
        """Read an SSH role."""
        return self.api_read(f"{mount}/roles/{role_name}")
    
    def ssh_create_role(self, mount: str, role_name: str, key_type: str,
                        default_user: str = None, allowed_users: str = None,
                        allowed_domains: str = None, ttl: str = None,
                        max_ttl: str = None, allowed_extensions: str = None,
                        default_extensions: Dict = None,
                        allowed_critical_options: str = None,
                        allow_user_certificates: bool = True,
                        allow_host_certificates: bool = False,
                        allow_bare_domains: bool = False,
                        allow_subdomains: bool = False,
                        allow_user_key_ids: bool = False,
                        algorithm_signer: str = None,
                        **kwargs) -> APIResponse:
        """Create or update an SSH role."""
        data = {'key_type': key_type}
        if default_user:
            data['default_user'] = default_user
        if allowed_users:
            data['allowed_users'] = allowed_users
        if allowed_domains:
            data['allowed_domains'] = allowed_domains
        if ttl:
            data['ttl'] = ttl
        if max_ttl:
            data['max_ttl'] = max_ttl
        if allowed_extensions:
            data['allowed_extensions'] = allowed_extensions
        if default_extensions:
            data['default_extensions'] = default_extensions
        if allowed_critical_options:
            data['allowed_critical_options'] = allowed_critical_options
        if algorithm_signer:
            data['algorithm_signer'] = algorithm_signer
        data['allow_user_certificates'] = allow_user_certificates
        data['allow_host_certificates'] = allow_host_certificates
        data['allow_bare_domains'] = allow_bare_domains
        data['allow_subdomains'] = allow_subdomains
        data['allow_user_key_ids'] = allow_user_key_ids
        data.update(kwargs)
        return self.api_write(f"{mount}/roles/{role_name}", data)
    
    def ssh_delete_role(self, mount: str, role_name: str) -> APIResponse:
        """Delete an SSH role."""
        return self.api_delete(f"{mount}/roles/{role_name}")
    
    def ssh_sign_key(self, mount: str, role_name: str, public_key: str,
                     valid_principals: str = None, cert_type: str = "user",
                     ttl: str = None, extensions: Dict = None,
                     critical_options: Dict = None) -> APIResponse:
        """Sign an SSH public key."""
        data = {'public_key': public_key, 'cert_type': cert_type}
        if valid_principals:
            data['valid_principals'] = valid_principals
        if ttl:
            data['ttl'] = ttl
        if extensions:
            data['extensions'] = extensions
        if critical_options:
            data['critical_options'] = critical_options
        return self.api_write(f"{mount}/sign/{role_name}", data)
    
    def ssh_issue_credential(self, mount: str, role_name: str, 
                             cert_type: str = "user",
                             valid_principals: str = None,
                             key_type: str = "rsa",
                             key_bits: int = 0,
                             ttl: str = None,
                             extensions: Dict = None,
                             critical_options: Dict = None) -> APIResponse:
        """Issue an SSH credential (key pair + signed certificate)."""
        data = {'cert_type': cert_type, 'key_type': key_type}
        if valid_principals:
            data['valid_principals'] = valid_principals
        if key_bits:
            data['key_bits'] = key_bits
        if ttl:
            data['ttl'] = ttl
        if extensions:
            data['extensions'] = extensions
        if critical_options:
            data['critical_options'] = critical_options
        return self.api_write(f"{mount}/issue/{role_name}", data)
    
    # ==================== Extended System Endpoints ====================
    
    def sys_capabilities(self, token: str, paths: List[str]) -> APIResponse:
        """Check capabilities of a token on paths."""
        return self.api_write("sys/capabilities", {'token': token, 'paths': paths})
    
    def sys_capabilities_self(self, paths: List[str]) -> APIResponse:
        """Check capabilities of the current token on paths."""
        return self.api_write("sys/capabilities-self", {'paths': paths})
    
    def sys_internal_counters_activity(self) -> APIResponse:
        """Get client activity data."""
        return self.api_read("sys/internal/counters/activity")
    
    def sys_internal_counters_tokens(self) -> APIResponse:
        """Get token count data."""
        return self.api_read("sys/internal/counters/tokens")
    
    def sys_internal_counters_entities(self) -> APIResponse:
        """Get entity count data."""
        return self.api_read("sys/internal/counters/entities")
    
    def sys_host_info(self) -> APIResponse:
        """Get host information."""
        return self.api_read("sys/host-info")
    
    def sys_in_flight_req(self) -> APIResponse:
        """Get in-flight request information."""
        return self.api_read("sys/in-flight-req")
    
    def sys_init_status(self) -> APIResponse:
        """Get initialization status."""
        return self.api_read("sys/init")
    
    def sys_key_status(self) -> APIResponse:
        """Get encryption key status."""
        return self.api_read("sys/key-status")
    
    def sys_generate_root_status(self) -> APIResponse:
        """Get root token generation status."""
        return self.api_read("sys/generate-root/attempt")
    
    def sys_generate_root_init(self, otp: str = None, pgp_key: str = None) -> APIResponse:
        """Initialize root token generation."""
        data = {}
        if otp:
            data['otp'] = otp
        if pgp_key:
            data['pgp_key'] = pgp_key
        return self.api_write("sys/generate-root/attempt", data)
    
    def sys_generate_root_cancel(self) -> APIResponse:
        """Cancel root token generation."""
        return self.api_delete("sys/generate-root/attempt")
    
    def sys_generate_root_update(self, key: str, nonce: str) -> APIResponse:
        """Provide unseal key for root generation."""
        return self.api_write("sys/generate-root/update", {'key': key, 'nonce': nonce})
    
    def sys_rekey_init_status(self) -> APIResponse:
        """Get rekey initialization status."""
        return self.api_read("sys/rekey/init")
    
    def sys_rekey_init(self, secret_shares: int, secret_threshold: int,
                       pgp_keys: List[str] = None, backup: bool = False) -> APIResponse:
        """Initialize rekey operation."""
        data = {'secret_shares': secret_shares, 'secret_threshold': secret_threshold, 'backup': backup}
        if pgp_keys:
            data['pgp_keys'] = pgp_keys
        return self.api_write("sys/rekey/init", data)
    
    def sys_rekey_cancel(self) -> APIResponse:
        """Cancel rekey operation."""
        return self.api_delete("sys/rekey/init")
    
    def sys_rekey_update(self, key: str, nonce: str) -> APIResponse:
        """Provide unseal key for rekey operation."""
        return self.api_write("sys/rekey/update", {'key': key, 'nonce': nonce})
    
    def sys_rekey_verify_status(self) -> APIResponse:
        """Get rekey verification status."""
        return self.api_read("sys/rekey/verify")
    
    def sys_rekey_verify(self, key: str, nonce: str) -> APIResponse:
        """Provide new key for rekey verification."""
        return self.api_write("sys/rekey/verify", {'key': key, 'nonce': nonce})
    
    def sys_rekey_verify_cancel(self) -> APIResponse:
        """Cancel rekey verification."""
        return self.api_delete("sys/rekey/verify")
    
    def sys_rotate(self) -> APIResponse:
        """Rotate the encryption key."""
        return self.api_write("sys/rotate")
    
    def sys_seal(self) -> APIResponse:
        """Seal the vault."""
        return self.api_write("sys/seal")
    
    def sys_unseal(self, key: str = None, reset: bool = False, migrate: bool = False) -> APIResponse:
        """Unseal the vault."""
        data = {}
        if key:
            data['key'] = key
        if reset:
            data['reset'] = reset
        if migrate:
            data['migrate'] = migrate
        return self.api_write("sys/unseal", data)
    
    def sys_step_down(self) -> APIResponse:
        """Force the active node to step down."""
        return self.api_write("sys/step-down")
    
    def sys_ha_status(self) -> APIResponse:
        """Get HA status."""
        return self.api_read("sys/ha-status")
    
    def sys_replication_status(self) -> APIResponse:
        """Get replication status."""
        return self.api_read("sys/replication/status")
    
    def sys_storage_raft_config(self) -> APIResponse:
        """Get Raft storage configuration."""
        return self.api_read("sys/storage/raft/configuration")
    
    def sys_storage_raft_autopilot_state(self) -> APIResponse:
        """Get Raft autopilot state."""
        return self.api_read("sys/storage/raft/autopilot/state")
    
    def sys_storage_raft_autopilot_config(self) -> APIResponse:
        """Get Raft autopilot configuration."""
        return self.api_read("sys/storage/raft/autopilot/configuration")
    
    def sys_storage_raft_snapshot(self) -> APIResponse:
        """Take a Raft snapshot (returns binary)."""
        return self.api_read("sys/storage/raft/snapshot")
    
    def sys_storage_raft_remove_peer(self, server_id: str) -> APIResponse:
        """Remove a peer from Raft cluster."""
        return self.api_write("sys/storage/raft/remove-peer", {'server_id': server_id})
    
    def sys_plugins_catalog_list(self, plugin_type: str = None) -> APIResponse:
        """List all plugins or plugins of a specific type."""
        if plugin_type:
            return self.api_list(f"sys/plugins/catalog/{plugin_type}")
        return self.api_read("sys/plugins/catalog")
    
    def sys_plugins_catalog_read(self, plugin_type: str, name: str) -> APIResponse:
        """Read a plugin from the catalog."""
        return self.api_read(f"sys/plugins/catalog/{plugin_type}/{name}")
    
    def sys_plugins_reload(self, plugin: str = None, mounts: List[str] = None) -> APIResponse:
        """Reload a plugin or mounts."""
        data = {}
        if plugin:
            data['plugin'] = plugin
        if mounts:
            data['mounts'] = mounts
        return self.api_write("sys/plugins/reload/backend", data)
    
    def sys_tools_random(self, bytes_count: int = 32, format: str = "base64") -> APIResponse:
        """Generate random bytes."""
        return self.api_write(f"sys/tools/random/{bytes_count}", {'format': format})
    
    def sys_tools_hash(self, input_data: str, algorithm: str = "sha2-256",
                       format: str = "hex") -> APIResponse:
        """Hash data."""
        return self.api_write(f"sys/tools/hash/{algorithm}", {'input': input_data, 'format': format})
    
    def sys_config_auditing_request_headers(self) -> APIResponse:
        """List audited request headers."""
        return self.api_read("sys/config/auditing/request-headers")
    
    def sys_config_cors(self) -> APIResponse:
        """Read CORS configuration."""
        return self.api_read("sys/config/cors")
    
    def sys_config_cors_configure(self, enabled: bool, allowed_origins: List[str] = None,
                                  allowed_headers: List[str] = None) -> APIResponse:
        """Configure CORS."""
        data = {'enabled': enabled}
        if allowed_origins:
            data['allowed_origins'] = allowed_origins
        if allowed_headers:
            data['allowed_headers'] = allowed_headers
        return self.api_write("sys/config/cors", data)
    
    def sys_config_ui_headers(self) -> APIResponse:
        """List custom UI headers."""
        return self.api_list("sys/config/ui/headers")
    
    def sys_config_state_sanitized(self) -> APIResponse:
        """Get sanitized configuration state."""
        return self.api_read("sys/config/state/sanitized")
    
    def sys_internal_ui_mounts(self) -> APIResponse:
        """Get UI-visible mounts."""
        return self.api_read("sys/internal/ui/mounts")
    
    def sys_internal_ui_namespaces(self) -> APIResponse:
        """Get UI-visible namespaces."""
        return self.api_read("sys/internal/ui/namespaces")
    
    def sys_internal_specs_openapi(self) -> APIResponse:
        """Get OpenAPI spec."""
        return self.api_read("sys/internal/specs/openapi")
    
    def sys_metrics(self, format: str = "prometheus") -> APIResponse:
        """Get metrics."""
        return self.api_read(f"sys/metrics?format={format}")
    
    def sys_monitor(self, log_level: str = "info") -> APIResponse:
        """Stream logs (returns log data)."""
        return self.api_read(f"sys/monitor?log_level={log_level}")
    
    def sys_pprof_index(self) -> APIResponse:
        """Get pprof index."""
        return self.api_read("sys/pprof")
    
    def sys_quotas_rate_limit_list(self) -> APIResponse:
        """List rate limit quotas."""
        return self.api_list("sys/quotas/rate-limit")
    
    def sys_quotas_rate_limit_read(self, name: str) -> APIResponse:
        """Read a rate limit quota."""
        return self.api_read(f"sys/quotas/rate-limit/{name}")
    
    def sys_quotas_rate_limit_create(self, name: str, rate: float, 
                                      path: str = None, interval: str = None,
                                      block_interval: str = None) -> APIResponse:
        """Create or update a rate limit quota."""
        data = {'name': name, 'rate': rate}
        if path:
            data['path'] = path
        if interval:
            data['interval'] = interval
        if block_interval:
            data['block_interval'] = block_interval
        return self.api_write(f"sys/quotas/rate-limit/{name}", data)
    
    def sys_quotas_rate_limit_delete(self, name: str) -> APIResponse:
        """Delete a rate limit quota."""
        return self.api_delete(f"sys/quotas/rate-limit/{name}")
    
    def sys_quotas_lease_count_list(self) -> APIResponse:
        """List lease count quotas."""
        return self.api_list("sys/quotas/lease-count")
    
    def sys_quotas_lease_count_read(self, name: str) -> APIResponse:
        """Read a lease count quota."""
        return self.api_read(f"sys/quotas/lease-count/{name}")
    
    def sys_license(self) -> APIResponse:
        """Read license info (Enterprise only)."""
        return self.api_read("sys/license/status")
    
    def sys_mfa_method_list(self) -> APIResponse:
        """List MFA methods."""
        return self.api_list("sys/mfa/method")
    
    def sys_raw_read(self, path: str) -> APIResponse:
        """Read raw storage (requires root)."""
        return self.api_read(f"sys/raw/{path}")
    
    def sys_raw_list(self, path: str = "") -> APIResponse:
        """List raw storage (requires root)."""
        return self.api_list(f"sys/raw/{path}")
    
    def sys_remount(self, from_path: str, to_path: str) -> APIResponse:
        """Remount a secrets engine."""
        return self.api_write("sys/remount", {'from': from_path, 'to': to_path})
    
    def sys_remount_status(self, migration_id: str) -> APIResponse:
        """Get remount status."""
        return self.api_read(f"sys/remount/status/{migration_id}")
