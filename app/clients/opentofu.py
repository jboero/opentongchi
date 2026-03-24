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


