"""
OpenTofu/Terraform Client for OpenTongchi
Handles both local workspaces and HCP Terraform (Terraform Cloud).
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from .base import BaseHTTPClient, APIResponse


class OpenTofuClient:
    """Client for local OpenTofu/Terraform operations."""
    
    def __init__(self, settings):
        self.settings = settings
        self.home_dir = Path(settings.home_dir).expanduser()
        self.binary_path = settings.binary_path or 'tofu'
        self.logs_dir = self.home_dir / '.logs'
        
        # Ensure directories exist
        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def _run_command(self, workspace_dir: Path, *args, 
                     capture_output: bool = True) -> Dict:
        """Run a tofu/terraform command in a workspace directory."""
        cmd = [self.binary_path] + list(args)
        
        try:
            if capture_output:
                result = subprocess.run(
                    cmd,
                    cwd=workspace_dir,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minute timeout
                )
                
                return {
                    'success': result.returncode == 0,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'returncode': result.returncode
                }
            else:
                # Start process in background
                process = subprocess.Popen(
                    cmd,
                    cwd=workspace_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return {
                    'success': True,
                    'process': process
                }
        
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Command timed out'}
        except FileNotFoundError:
            return {'success': False, 'error': f'Binary not found: {self.binary_path}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _save_log(self, workspace_name: str, action: str, output: str):
        """Save command output to log file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = self.logs_dir / workspace_name / f'{action}_{timestamp}.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(output)
        return log_file
    
    # ============ Workspace Management ============
    
    def list_workspaces(self) -> List[Dict]:
        """List all local workspaces."""
        workspaces = []
        
        if not self.home_dir.exists():
            return workspaces
        
        for item in self.home_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                # Check if it's a valid workspace
                if (item / 'main.tf').exists() or (item / '.terraform').exists():
                    workspace = {
                        'name': item.name,
                        'path': str(item),
                        'status': self._get_workspace_status(item),
                        'last_modified': datetime.fromtimestamp(
                            item.stat().st_mtime
                        ).isoformat()
                    }
                    workspaces.append(workspace)
        
        return workspaces
    
    def _get_workspace_status(self, workspace_dir: Path) -> str:
        """Get the status of a workspace."""
        # Check for .terraform directory
        if not (workspace_dir / '.terraform').exists():
            return 'not_initialized'
        
        # Check for tfstate
        state_file = workspace_dir / 'terraform.tfstate'
        if not state_file.exists():
            return 'initialized'
        
        # Try to check state
        try:
            state = json.loads(state_file.read_text())
            if state.get('resources'):
                return 'applied'
            return 'initialized'
        except:
            return 'unknown'
    
    def get_workspace_status_emoji(self, status: str) -> str:
        """Get status emoji for a workspace."""
        status_map = {
            'not_initialized': '⚪',
            'initialized': '🟡',
            'applied': '🟢',
            'error': '🔴',
            'unknown': '⚪',
        }
        return status_map.get(status, '⚪')
    
    # ============ Terraform Commands ============
    
    def init(self, workspace_name: str, upgrade: bool = False) -> Dict:
        """Initialize a workspace."""
        workspace_dir = self.home_dir / workspace_name
        
        args = ['init']
        if upgrade:
            args.append('-upgrade')
        args.append('-no-color')
        
        result = self._run_command(workspace_dir, *args)
        
        if result.get('stdout') or result.get('stderr'):
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            self._save_log(workspace_name, 'init', output)
        
        return result
    
    def plan(self, workspace_name: str, out_file: str = None,
             var_file: str = None, vars: Dict = None) -> Dict:
        """Run terraform plan."""
        workspace_dir = self.home_dir / workspace_name
        
        args = ['plan', '-no-color']
        
        if out_file:
            args.extend(['-out', out_file])
        if var_file:
            args.extend(['-var-file', var_file])
        if vars:
            for key, value in vars.items():
                args.extend(['-var', f'{key}={value}'])
        
        result = self._run_command(workspace_dir, *args)
        
        if result.get('stdout') or result.get('stderr'):
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            self._save_log(workspace_name, 'plan', output)
        
        return result
    
    def apply(self, workspace_name: str, auto_approve: bool = False,
              plan_file: str = None, var_file: str = None,
              vars: Dict = None) -> Dict:
        """Run terraform apply."""
        workspace_dir = self.home_dir / workspace_name
        
        args = ['apply', '-no-color']
        
        if auto_approve:
            args.append('-auto-approve')
        if plan_file:
            args.append(plan_file)
        if var_file:
            args.extend(['-var-file', var_file])
        if vars:
            for key, value in vars.items():
                args.extend(['-var', f'{key}={value}'])
        
        result = self._run_command(workspace_dir, *args)
        
        if result.get('stdout') or result.get('stderr'):
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            self._save_log(workspace_name, 'apply', output)
        
        return result
    
    def destroy(self, workspace_name: str, 
                auto_approve: bool = False) -> Dict:
        """Run terraform destroy."""
        workspace_dir = self.home_dir / workspace_name
        
        args = ['destroy', '-no-color']
        
        if auto_approve:
            args.append('-auto-approve')
        
        result = self._run_command(workspace_dir, *args)
        
        if result.get('stdout') or result.get('stderr'):
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            self._save_log(workspace_name, 'destroy', output)
        
        return result
    
    def refresh(self, workspace_name: str) -> Dict:
        """Run terraform refresh."""
        workspace_dir = self.home_dir / workspace_name
        
        result = self._run_command(workspace_dir, 'refresh', '-no-color')
        
        if result.get('stdout') or result.get('stderr'):
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            self._save_log(workspace_name, 'refresh', output)
        
        return result
    
    def output(self, workspace_name: str, json_format: bool = True) -> Dict:
        """Get terraform outputs."""
        workspace_dir = self.home_dir / workspace_name
        
        args = ['output']
        if json_format:
            args.append('-json')
        
        result = self._run_command(workspace_dir, *args)
        
        if result.get('success') and json_format and result.get('stdout'):
            try:
                result['data'] = json.loads(result['stdout'])
            except json.JSONDecodeError:
                pass
        
        return result
    
    def state_list(self, workspace_name: str) -> Dict:
        """List resources in state."""
        workspace_dir = self.home_dir / workspace_name
        return self._run_command(workspace_dir, 'state', 'list')
    
    def state_show(self, workspace_name: str, address: str) -> Dict:
        """Show a resource in state."""
        workspace_dir = self.home_dir / workspace_name
        return self._run_command(workspace_dir, 'state', 'show', address)
    
    def validate(self, workspace_name: str) -> Dict:
        """Validate terraform configuration."""
        workspace_dir = self.home_dir / workspace_name
        return self._run_command(workspace_dir, 'validate', '-json')
    
    def fmt(self, workspace_name: str, check: bool = False) -> Dict:
        """Format terraform files."""
        workspace_dir = self.home_dir / workspace_name
        
        args = ['fmt']
        if check:
            args.append('-check')
        
        return self._run_command(workspace_dir, *args)
    
    # ============ Logs ============
    
    def list_logs(self, workspace_name: str) -> List[Dict]:
        """List logs for a workspace."""
        logs = []
        log_dir = self.logs_dir / workspace_name
        
        if log_dir.exists():
            for log_file in sorted(log_dir.iterdir(), reverse=True):
                if log_file.suffix == '.log':
                    logs.append({
                        'name': log_file.name,
                        'path': str(log_file),
                        'size': log_file.stat().st_size,
                        'modified': datetime.fromtimestamp(
                            log_file.stat().st_mtime
                        ).isoformat()
                    })
        
        return logs
    
    def read_log(self, workspace_name: str, log_name: str) -> str:
        """Read a log file."""
        log_file = self.logs_dir / workspace_name / log_name
        if log_file.exists():
            return log_file.read_text()
        return ""


class HCPTerraformClient(BaseHTTPClient):
    """Client for HCP Terraform (Terraform Cloud) API."""
    
    def __init__(self, settings):
        super().__init__(
            base_url='https://app.terraform.io',
            token=settings.hcp_token
        )
        self.settings = settings
        self.org = settings.hcp_org
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers including HCP token."""
        headers = super()._get_headers()
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        headers['Content-Type'] = 'application/vnd.api+json'
        return headers
    
    # ============ Organizations ============
    
    def list_organizations(self) -> APIResponse:
        """List organizations."""
        return self.get('/api/v2/organizations')
    
    def get_organization(self, org_name: str = None) -> APIResponse:
        """Get organization details."""
        org = org_name or self.org
        return self.get(f'/api/v2/organizations/{org}')
    
    # ============ Workspaces ============
    
    def list_workspaces(self, org_name: str = None) -> APIResponse:
        """List workspaces in an organization."""
        org = org_name or self.org
        return self.get(f'/api/v2/organizations/{org}/workspaces')
    
    def get_workspace(self, workspace_name: str, 
                      org_name: str = None) -> APIResponse:
        """Get workspace details."""
        org = org_name or self.org
        return self.get(f'/api/v2/organizations/{org}/workspaces/{workspace_name}')
    
    def get_workspace_by_id(self, workspace_id: str) -> APIResponse:
        """Get workspace by ID."""
        return self.get(f'/api/v2/workspaces/{workspace_id}')
    
    def create_workspace(self, name: str, org_name: str = None,
                         auto_apply: bool = False,
                         description: str = None) -> APIResponse:
        """Create a workspace."""
        org = org_name or self.org
        data = {
            'data': {
                'type': 'workspaces',
                'attributes': {
                    'name': name,
                    'auto-apply': auto_apply
                }
            }
        }
        if description:
            data['data']['attributes']['description'] = description
        return self.post(f'/api/v2/organizations/{org}/workspaces', data)
    
    def delete_workspace(self, workspace_name: str, 
                         org_name: str = None) -> APIResponse:
        """Delete a workspace."""
        org = org_name or self.org
        return self.delete(f'/api/v2/organizations/{org}/workspaces/{workspace_name}')
    
    def lock_workspace(self, workspace_id: str, reason: str = "") -> APIResponse:
        """Lock a workspace."""
        return self.post(f'/api/v2/workspaces/{workspace_id}/actions/lock',
                         {'reason': reason})
    
    def unlock_workspace(self, workspace_id: str) -> APIResponse:
        """Unlock a workspace."""
        return self.post(f'/api/v2/workspaces/{workspace_id}/actions/unlock')
    
    # ============ Runs ============
    
    def list_runs(self, workspace_id: str) -> APIResponse:
        """List runs for a workspace."""
        return self.get(f'/api/v2/workspaces/{workspace_id}/runs')
    
    def get_run(self, run_id: str) -> APIResponse:
        """Get run details."""
        return self.get(f'/api/v2/runs/{run_id}')
    
    def create_run(self, workspace_id: str, message: str = None,
                   is_destroy: bool = False,
                   auto_apply: bool = False) -> APIResponse:
        """Create a new run."""
        data = {
            'data': {
                'type': 'runs',
                'attributes': {
                    'is-destroy': is_destroy,
                    'auto-apply': auto_apply
                },
                'relationships': {
                    'workspace': {
                        'data': {
                            'type': 'workspaces',
                            'id': workspace_id
                        }
                    }
                }
            }
        }
        if message:
            data['data']['attributes']['message'] = message
        return self.post('/api/v2/runs', data)
    
    def apply_run(self, run_id: str, comment: str = None) -> APIResponse:
        """Apply a run."""
        data = {}
        if comment:
            data['comment'] = comment
        return self.post(f'/api/v2/runs/{run_id}/actions/apply', data)
    
    def discard_run(self, run_id: str, comment: str = None) -> APIResponse:
        """Discard a run."""
        data = {}
        if comment:
            data['comment'] = comment
        return self.post(f'/api/v2/runs/{run_id}/actions/discard', data)
    
    def cancel_run(self, run_id: str, comment: str = None) -> APIResponse:
        """Cancel a run."""
        data = {}
        if comment:
            data['comment'] = comment
        return self.post(f'/api/v2/runs/{run_id}/actions/cancel', data)
    
    # ============ State Versions ============
    
    def list_state_versions(self, workspace_id: str) -> APIResponse:
        """List state versions for a workspace."""
        return self.get(f'/api/v2/workspaces/{workspace_id}/state-versions')
    
    def get_current_state_version(self, workspace_id: str) -> APIResponse:
        """Get current state version for a workspace."""
        return self.get(f'/api/v2/workspaces/{workspace_id}/current-state-version')
    
    # ============ Variables ============
    
    def list_variables(self, workspace_id: str) -> APIResponse:
        """List variables for a workspace."""
        return self.get(f'/api/v2/workspaces/{workspace_id}/vars')
    
    def create_variable(self, workspace_id: str, key: str, value: str,
                        category: str = 'terraform',
                        sensitive: bool = False,
                        hcl: bool = False) -> APIResponse:
        """Create a variable."""
        data = {
            'data': {
                'type': 'vars',
                'attributes': {
                    'key': key,
                    'value': value,
                    'category': category,
                    'sensitive': sensitive,
                    'hcl': hcl
                }
            }
        }
        return self.post(f'/api/v2/workspaces/{workspace_id}/vars', data)
    
    def update_variable(self, variable_id: str, value: str = None,
                        sensitive: bool = None) -> APIResponse:
        """Update a variable."""
        data = {
            'data': {
                'type': 'vars',
                'attributes': {}
            }
        }
        if value is not None:
            data['data']['attributes']['value'] = value
        if sensitive is not None:
            data['data']['attributes']['sensitive'] = sensitive
        return self.patch(f'/api/v2/vars/{variable_id}', data)
    
    def delete_variable(self, variable_id: str) -> APIResponse:
        """Delete a variable."""
        return self.delete(f'/api/v2/vars/{variable_id}')
    
    # ============ Helpers ============
    
    def get_workspace_status_emoji(self, workspace: Dict) -> str:
        """Get status emoji for a workspace."""
        attrs = workspace.get('attributes', {})
        
        # Check if locked
        if attrs.get('locked'):
            return '🔒'
        
        # Check latest run status
        latest_run = workspace.get('relationships', {}).get(
            'latest-run', {}).get('data')
        if not latest_run:
            return '⚪'
        
        # Would need to fetch run status for accurate emoji
        return '🟢'
    
    def get_run_status_emoji(self, status: str) -> str:
        """Get status emoji for a run."""
        status_map = {
            'pending': '⏳',
            'plan_queued': '🔄',
            'planning': '🔄',
            'planned': '📋',
            'cost_estimating': '💰',
            'cost_estimated': '💰',
            'policy_checking': '📜',
            'policy_override': '⚠️',
            'policy_soft_failed': '⚠️',
            'policy_checked': '✅',
            'confirmed': '✅',
            'apply_queued': '🔄',
            'applying': '🔄',
            'applied': '🟢',
            'discarded': '🗑️',
            'errored': '🔴',
            'canceled': '🚫',
            'force_canceled': '🚫',
        }
        return status_map.get(status, '⚪')
