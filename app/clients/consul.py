"""
Consul Client for OpenTongchi
"""

from typing import Dict, Any, Optional, List
from .base import BaseHTTPClient, APIResponse


class ConsulClient(BaseHTTPClient):
    """Client for Consul API."""
    
    def __init__(self, settings):
        super().__init__(
            base_url=settings.address,
            token=settings.token,
            namespace=settings.namespace
        )
        self.settings = settings
        self.datacenter = settings.datacenter
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers including Consul token."""
        headers = super()._get_headers()
        if self.token:
            headers['X-Consul-Token'] = self.token
        if self.namespace:
            headers['X-Consul-Namespace'] = self.namespace
        return headers
    
    def _add_dc_param(self, params: Dict = None) -> Dict:
        """Add datacenter parameter if set."""
        params = params or {}
        if self.datacenter:
            params['dc'] = self.datacenter
        return params
    
    # ============ Health & Status ============
    
    def agent_self(self) -> APIResponse:
        """Get agent info."""
        return self.get('/v1/agent/self')
    
    def is_healthy(self) -> bool:
        """Check if Consul is healthy."""
        response = self.agent_self()
        return response.ok
    
    def leader(self) -> APIResponse:
        """Get cluster leader."""
        return self.get('/v1/status/leader')
    
    def peers(self) -> APIResponse:
        """Get cluster peers."""
        return self.get('/v1/status/peers')
    
    # ============ Catalog ============
    
    def catalog_datacenters(self) -> APIResponse:
        """List all datacenters."""
        return self.get('/v1/catalog/datacenters')
    
    def catalog_nodes(self) -> APIResponse:
        """List all nodes."""
        params = self._add_dc_param()
        return self.get('/v1/catalog/nodes', params=params)
    
    def catalog_node(self, node: str) -> APIResponse:
        """Get node info."""
        params = self._add_dc_param()
        return self.get(f'/v1/catalog/node/{node}', params=params)
    
    def catalog_services(self) -> APIResponse:
        """List all services."""
        params = self._add_dc_param()
        return self.get('/v1/catalog/services', params=params)
    
    def catalog_service(self, service: str) -> APIResponse:
        """Get service instances."""
        params = self._add_dc_param()
        return self.get(f'/v1/catalog/service/{service}', params=params)
    
    # ============ Health ============
    
    def health_node(self, node: str) -> APIResponse:
        """Get health checks for a node."""
        params = self._add_dc_param()
        return self.get(f'/v1/health/node/{node}', params=params)
    
    def health_service(self, service: str, passing_only: bool = False) -> APIResponse:
        """Get health for a service."""
        params = self._add_dc_param()
        if passing_only:
            params['passing'] = 'true'
        return self.get(f'/v1/health/service/{service}', params=params)
    
    def health_checks(self, service: str) -> APIResponse:
        """Get health checks for a service."""
        params = self._add_dc_param()
        return self.get(f'/v1/health/checks/{service}', params=params)
    
    def health_state(self, state: str = 'any') -> APIResponse:
        """Get checks in a specific state."""
        params = self._add_dc_param()
        return self.get(f'/v1/health/state/{state}', params=params)
    
    # ============ KV Store ============
    
    def kv_get(self, key: str, recurse: bool = False, 
               keys: bool = False) -> APIResponse:
        """Get a KV entry."""
        params = self._add_dc_param()
        if recurse:
            params['recurse'] = 'true'
        if keys:
            params['keys'] = 'true'
        return self.get(f'/v1/kv/{key}', params=params)
    
    def kv_put(self, key: str, value: str, 
               cas: int = None, flags: int = None) -> APIResponse:
        """Put a KV entry."""
        params = self._add_dc_param()
        if cas is not None:
            params['cas'] = str(cas)
        if flags is not None:
            params['flags'] = str(flags)
        
        # KV uses raw body, not JSON
        headers = self._get_headers()
        headers['Content-Type'] = 'text/plain'
        return self._make_request('PUT', f'/v1/kv/{key}', 
                                   data=value, headers=headers, params=params)
    
    def kv_delete(self, key: str, recurse: bool = False) -> APIResponse:
        """Delete a KV entry."""
        params = self._add_dc_param()
        if recurse:
            params['recurse'] = 'true'
        return self.delete(f'/v1/kv/{key}')
    
    def kv_list(self, prefix: str = "") -> APIResponse:
        """List KV keys."""
        params = self._add_dc_param({'keys': 'true'})
        path = f'/v1/kv/{prefix}' if prefix else '/v1/kv/'
        return self.get(path, params=params)
    
    # ============ Agent ============
    
    def agent_checks(self) -> APIResponse:
        """List agent checks."""
        return self.get('/v1/agent/checks')
    
    def agent_services(self) -> APIResponse:
        """List agent services."""
        return self.get('/v1/agent/services')
    
    def agent_service(self, service_id: str) -> APIResponse:
        """Get agent service."""
        return self.get(f'/v1/agent/service/{service_id}')
    
    def agent_register_service(self, service: Dict) -> APIResponse:
        """Register a service with the agent."""
        return self.put('/v1/agent/service/register', service)
    
    def agent_deregister_service(self, service_id: str) -> APIResponse:
        """Deregister a service."""
        return self.put(f'/v1/agent/service/deregister/{service_id}')
    
    def agent_maintenance(self, enable: bool, reason: str = "") -> APIResponse:
        """Enable/disable agent maintenance mode."""
        params = {'enable': str(enable).lower()}
        if reason:
            params['reason'] = reason
        return self.put('/v1/agent/maintenance', params=params)
    
    # ============ Sessions ============
    
    def session_list(self) -> APIResponse:
        """List all sessions."""
        params = self._add_dc_param()
        return self.get('/v1/session/list', params=params)
    
    def session_info(self, session_id: str) -> APIResponse:
        """Get session info."""
        params = self._add_dc_param()
        return self.get(f'/v1/session/info/{session_id}', params=params)
    
    def session_create(self, data: Dict = None) -> APIResponse:
        """Create a session."""
        params = self._add_dc_param()
        return self.put('/v1/session/create', data or {})
    
    def session_destroy(self, session_id: str) -> APIResponse:
        """Destroy a session."""
        params = self._add_dc_param()
        return self.put(f'/v1/session/destroy/{session_id}')
    
    # ============ ACL ============
    
    def acl_bootstrap(self) -> APIResponse:
        """Bootstrap ACL."""
        return self.put('/v1/acl/bootstrap')
    
    def acl_token_list(self) -> APIResponse:
        """List ACL tokens."""
        return self.get('/v1/acl/tokens')
    
    def acl_token_read(self, accessor_id: str) -> APIResponse:
        """Read ACL token."""
        return self.get(f'/v1/acl/token/{accessor_id}')
    
    def acl_token_create(self, token: Dict) -> APIResponse:
        """Create ACL token."""
        return self.put('/v1/acl/token', token)
    
    def acl_token_delete(self, accessor_id: str) -> APIResponse:
        """Delete ACL token."""
        return self.delete(f'/v1/acl/token/{accessor_id}')
    
    def acl_policy_list(self) -> APIResponse:
        """List ACL policies."""
        return self.get('/v1/acl/policies')
    
    def acl_policy_read(self, policy_id: str) -> APIResponse:
        """Read ACL policy."""
        return self.get(f'/v1/acl/policy/{policy_id}')
    
    def acl_policy_create(self, policy: Dict) -> APIResponse:
        """Create ACL policy."""
        return self.put('/v1/acl/policy', policy)
    
    def acl_policy_delete(self, policy_id: str) -> APIResponse:
        """Delete ACL policy."""
        return self.delete(f'/v1/acl/policy/{policy_id}')
    
    # ============ Connect ============
    
    def connect_ca_roots(self) -> APIResponse:
        """Get Connect CA roots."""
        return self.get('/v1/connect/ca/roots')
    
    def connect_ca_configuration(self) -> APIResponse:
        """Get Connect CA configuration."""
        return self.get('/v1/connect/ca/configuration')
    
    def connect_intentions(self) -> APIResponse:
        """List Connect intentions."""
        return self.get('/v1/connect/intentions')
    
    # ============ Namespaces (Enterprise) ============
    
    def namespace_list(self) -> APIResponse:
        """List namespaces."""
        return self.get('/v1/namespaces')
    
    def namespace_read(self, name: str) -> APIResponse:
        """Read namespace."""
        return self.get(f'/v1/namespace/{name}')
    
    # ============ Helpers ============
    
    def get_service_health_status(self, service: str) -> str:
        """Get overall health status for a service."""
        response = self.health_service(service)
        if not response.ok:
            return 'unknown'
        
        services = response.data or []
        if not services:
            return 'unknown'
        
        # Check all checks
        all_passing = True
        any_critical = False
        
        for svc in services:
            checks = svc.get('Checks', [])
            for check in checks:
                status = check.get('Status', '')
                if status == 'critical':
                    any_critical = True
                elif status != 'passing':
                    all_passing = False
        
        if any_critical:
            return 'critical'
        elif all_passing:
            return 'passing'
        else:
            return 'warning'
