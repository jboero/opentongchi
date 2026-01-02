"""
Nomad Client for OpenTongchi
"""

from typing import Dict, Any, Optional, List
from .base import BaseHTTPClient, APIResponse


class NomadClient(BaseHTTPClient):
    """Client for Nomad API."""
    
    def __init__(self, settings):
        super().__init__(
            base_url=settings.address,
            token=settings.token,
            namespace=settings.namespace
        )
        self.settings = settings
        self.region = settings.region
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers including Nomad token."""
        headers = super()._get_headers()
        if self.token:
            headers['X-Nomad-Token'] = self.token
        return headers
    
    def _add_params(self, params: Dict = None) -> Dict:
        """Add common parameters."""
        params = params or {}
        if self.namespace:
            params['namespace'] = self.namespace
        if self.region:
            params['region'] = self.region
        return params
    
    # ============ Status ============
    
    def agent_self(self) -> APIResponse:
        """Get agent info."""
        return self.get('/v1/agent/self')
    
    def is_healthy(self) -> bool:
        """Check if Nomad is healthy."""
        response = self.agent_self()
        return response.ok
    
    def leader(self) -> APIResponse:
        """Get cluster leader."""
        return self.get('/v1/status/leader')
    
    def peers(self) -> APIResponse:
        """Get cluster peers."""
        return self.get('/v1/status/peers')
    
    # ============ Jobs ============
    
    def job_list(self, prefix: str = None) -> APIResponse:
        """List all jobs."""
        params = self._add_params()
        if prefix:
            params['prefix'] = prefix
        return self.get('/v1/jobs', params=params)
    
    def job_read(self, job_id: str) -> APIResponse:
        """Read a job."""
        params = self._add_params()
        return self.get(f'/v1/job/{job_id}', params=params)
    
    def job_versions(self, job_id: str) -> APIResponse:
        """Get job versions."""
        params = self._add_params()
        return self.get(f'/v1/job/{job_id}/versions', params=params)
    
    def job_allocations(self, job_id: str) -> APIResponse:
        """Get job allocations."""
        params = self._add_params()
        return self.get(f'/v1/job/{job_id}/allocations', params=params)
    
    def job_evaluations(self, job_id: str) -> APIResponse:
        """Get job evaluations."""
        params = self._add_params()
        return self.get(f'/v1/job/{job_id}/evaluations', params=params)
    
    def job_summary(self, job_id: str) -> APIResponse:
        """Get job summary."""
        params = self._add_params()
        return self.get(f'/v1/job/{job_id}/summary', params=params)
    
    def job_register(self, job_spec: Dict) -> APIResponse:
        """Register (create/update) a job."""
        params = self._add_params()
        return self.post('/v1/jobs', {'Job': job_spec})
    
    def job_update(self, job_id: str, job_spec: Dict) -> APIResponse:
        """Update a job."""
        params = self._add_params()
        return self.post(f'/v1/job/{job_id}', {'Job': job_spec})
    
    def job_stop(self, job_id: str, purge: bool = False) -> APIResponse:
        """Stop a job."""
        params = self._add_params()
        if purge:
            params['purge'] = 'true'
        return self.delete(f'/v1/job/{job_id}')
    
    def job_force_periodic(self, job_id: str) -> APIResponse:
        """Force a periodic job to run."""
        params = self._add_params()
        return self.post(f'/v1/job/{job_id}/periodic/force')
    
    def job_dispatch(self, job_id: str, meta: Dict = None, 
                     payload: str = None) -> APIResponse:
        """Dispatch a parameterized job."""
        params = self._add_params()
        data = {}
        if meta:
            data['Meta'] = meta
        if payload:
            data['Payload'] = payload
        return self.post(f'/v1/job/{job_id}/dispatch', data)
    
    def job_scale(self, job_id: str, group: str, count: int,
                  message: str = None) -> APIResponse:
        """Scale a job task group."""
        params = self._add_params()
        data = {
            'Count': count,
            'Target': {group: {'Count': count}}
        }
        if message:
            data['Message'] = message
        return self.post(f'/v1/job/{job_id}/scale', data)
    
    # ============ Allocations ============
    
    def allocation_list(self, prefix: str = None) -> APIResponse:
        """List allocations."""
        params = self._add_params()
        if prefix:
            params['prefix'] = prefix
        return self.get('/v1/allocations', params=params)
    
    def allocation_read(self, alloc_id: str) -> APIResponse:
        """Read an allocation."""
        params = self._add_params()
        return self.get(f'/v1/allocation/{alloc_id}', params=params)
    
    def allocation_stop(self, alloc_id: str) -> APIResponse:
        """Stop an allocation."""
        params = self._add_params()
        return self.post(f'/v1/allocation/{alloc_id}/stop')
    
    def allocation_logs(self, alloc_id: str, task: str, 
                        log_type: str = 'stdout') -> APIResponse:
        """Get allocation logs."""
        params = self._add_params({
            'task': task,
            'type': log_type,
            'plain': 'true'
        })
        return self.get(f'/v1/client/fs/logs/{alloc_id}', params=params)
    
    # ============ Nodes ============
    
    def node_list(self, prefix: str = None) -> APIResponse:
        """List nodes."""
        params = self._add_params()
        if prefix:
            params['prefix'] = prefix
        return self.get('/v1/nodes', params=params)
    
    def node_read(self, node_id: str) -> APIResponse:
        """Read a node."""
        params = self._add_params()
        return self.get(f'/v1/node/{node_id}', params=params)
    
    def node_allocations(self, node_id: str) -> APIResponse:
        """Get node allocations."""
        params = self._add_params()
        return self.get(f'/v1/node/{node_id}/allocations', params=params)
    
    def node_drain(self, node_id: str, enable: bool = True,
                   deadline: str = None) -> APIResponse:
        """Set node drain mode."""
        params = self._add_params()
        data = {'DrainSpec': None}
        if enable:
            data['DrainSpec'] = {'Deadline': deadline or '1h'}
        return self.post(f'/v1/node/{node_id}/drain', data)
    
    def node_eligibility(self, node_id: str, eligible: bool) -> APIResponse:
        """Set node scheduling eligibility."""
        params = self._add_params()
        eligibility = 'eligible' if eligible else 'ineligible'
        return self.post(f'/v1/node/{node_id}/eligibility', 
                         {'Eligibility': eligibility})
    
    # ============ Evaluations ============
    
    def evaluation_list(self) -> APIResponse:
        """List evaluations."""
        params = self._add_params()
        return self.get('/v1/evaluations', params=params)
    
    def evaluation_read(self, eval_id: str) -> APIResponse:
        """Read an evaluation."""
        params = self._add_params()
        return self.get(f'/v1/evaluation/{eval_id}', params=params)
    
    def evaluation_allocations(self, eval_id: str) -> APIResponse:
        """Get evaluation allocations."""
        params = self._add_params()
        return self.get(f'/v1/evaluation/{eval_id}/allocations', params=params)
    
    # ============ Deployments ============
    
    def deployment_list(self) -> APIResponse:
        """List deployments."""
        params = self._add_params()
        return self.get('/v1/deployments', params=params)
    
    def deployment_read(self, deploy_id: str) -> APIResponse:
        """Read a deployment."""
        params = self._add_params()
        return self.get(f'/v1/deployment/{deploy_id}', params=params)
    
    def deployment_fail(self, deploy_id: str) -> APIResponse:
        """Fail a deployment."""
        params = self._add_params()
        return self.post(f'/v1/deployment/fail/{deploy_id}')
    
    def deployment_promote(self, deploy_id: str, all_groups: bool = True,
                           groups: List[str] = None) -> APIResponse:
        """Promote a deployment."""
        params = self._add_params()
        data = {'DeploymentID': deploy_id, 'All': all_groups}
        if groups:
            data['Groups'] = groups
        return self.post(f'/v1/deployment/promote/{deploy_id}', data)
    
    # ============ Namespaces ============
    
    def namespace_list(self) -> APIResponse:
        """List namespaces."""
        return self.get('/v1/namespaces')
    
    def namespace_read(self, name: str) -> APIResponse:
        """Read a namespace."""
        return self.get(f'/v1/namespace/{name}')
    
    def namespace_create(self, namespace: Dict) -> APIResponse:
        """Create a namespace."""
        return self.post('/v1/namespace', namespace)
    
    def namespace_delete(self, name: str) -> APIResponse:
        """Delete a namespace."""
        return self.delete(f'/v1/namespace/{name}')
    
    # ============ Scaling ============
    
    def scaling_policies(self) -> APIResponse:
        """List scaling policies."""
        params = self._add_params()
        return self.get('/v1/scaling/policies', params=params)
    
    def scaling_policy(self, policy_id: str) -> APIResponse:
        """Read a scaling policy."""
        params = self._add_params()
        return self.get(f'/v1/scaling/policy/{policy_id}', params=params)
    
    # ============ Variables ============
    
    def variable_list(self, prefix: str = None) -> APIResponse:
        """List variables."""
        params = self._add_params()
        if prefix:
            params['prefix'] = prefix
        return self.get('/v1/vars', params=params)
    
    def variable_read(self, path: str) -> APIResponse:
        """Read a variable."""
        params = self._add_params()
        return self.get(f'/v1/var/{path}', params=params)
    
    def variable_create(self, path: str, items: Dict) -> APIResponse:
        """Create a variable."""
        params = self._add_params()
        return self.put(f'/v1/var/{path}', {'Path': path, 'Items': items})
    
    def variable_delete(self, path: str) -> APIResponse:
        """Delete a variable."""
        params = self._add_params()
        return self.delete(f'/v1/var/{path}')
    
    # ============ Helpers ============
    
    def get_job_status_emoji(self, status: str) -> str:
        """Get status emoji for a job."""
        status_map = {
            'running': '🟢',
            'pending': '🟡',
            'dead': '⚪',
            'failed': '🔴',
        }
        return status_map.get(status.lower(), '⚪')
    
    def get_alloc_status_emoji(self, client_status: str) -> str:
        """Get status emoji for an allocation."""
        status_map = {
            'running': '🟢',
            'pending': '🟡',
            'complete': '✅',
            'failed': '🔴',
            'lost': '⚫',
        }
        return status_map.get(client_status.lower(), '⚪')
    
    def get_node_status_emoji(self, status: str, eligible: bool) -> str:
        """Get status emoji for a node."""
        if not eligible:
            return '🟠'
        status_map = {
            'ready': '🟢',
            'initializing': '🟡',
            'down': '🔴',
        }
        return status_map.get(status.lower(), '⚪')
