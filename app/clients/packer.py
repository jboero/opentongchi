"""
Packer Client for OpenTongchi
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


class PackerClient:
    """Client for Packer operations."""
    
    def __init__(self, settings):
        self.settings = settings
        self.home_dir = Path(settings.home_dir).expanduser()
        self.binary_path = settings.binary_path or 'packer'
        self.logs_dir = self.home_dir / '.logs'
        
        # Ensure directories exist
        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def _run_command(self, template_dir: Path, *args,
                     capture_output: bool = True) -> Dict:
        """Run a packer command in a template directory."""
        cmd = [self.binary_path] + list(args)
        
        try:
            if capture_output:
                result = subprocess.run(
                    cmd,
                    cwd=template_dir,
                    capture_output=True,
                    text=True,
                    timeout=1800  # 30 minute timeout for builds
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
                    cwd=template_dir,
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
    
    def _save_log(self, template_name: str, action: str, output: str) -> Path:
        """Save command output to log file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = self.logs_dir / template_name / f'{action}_{timestamp}.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(output)
        return log_file
    
    # ============ Template Management ============
    
    def list_templates(self) -> List[Dict]:
        """List all Packer templates."""
        templates = []
        
        if not self.home_dir.exists():
            return templates
        
        for item in self.home_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                template_files = list(item.glob('*.pkr.hcl')) + \
                                 list(item.glob('*.pkr.json')) + \
                                 list(item.glob('*.json'))
                
                if template_files:
                    template = {
                        'name': item.name,
                        'path': str(item),
                        'files': [f.name for f in template_files],
                        'last_modified': datetime.fromtimestamp(
                            item.stat().st_mtime
                        ).isoformat()
                    }
                    templates.append(template)
        
        return templates
    
    def get_template_info(self, template_name: str) -> Dict:
        """Get information about a template."""
        template_dir = self.home_dir / template_name
        
        if not template_dir.exists():
            return {'error': 'Template not found'}
        
        template_files = list(template_dir.glob('*.pkr.hcl')) + \
                         list(template_dir.glob('*.pkr.json')) + \
                         list(template_dir.glob('*.json'))
        
        var_files = list(template_dir.glob('*.pkrvars.hcl')) + \
                    list(template_dir.glob('*.auto.pkrvars.hcl'))
        
        return {
            'name': template_name,
            'path': str(template_dir),
            'template_files': [f.name for f in template_files],
            'variable_files': [f.name for f in var_files],
            'last_modified': datetime.fromtimestamp(
                template_dir.stat().st_mtime
            ).isoformat()
        }
    
    # ============ Packer Commands ============
    
    def init(self, template_name: str, upgrade: bool = False) -> Dict:
        """Initialize a template (install plugins)."""
        template_dir = self.home_dir / template_name
        
        args = ['init']
        if upgrade:
            args.append('-upgrade')
        args.append('.')
        
        result = self._run_command(template_dir, *args)
        
        if result.get('stdout') or result.get('stderr'):
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            self._save_log(template_name, 'init', output)
        
        return result
    
    def validate(self, template_name: str, 
                 var_file: str = None, vars: Dict = None) -> Dict:
        """Validate a template."""
        template_dir = self.home_dir / template_name
        
        args = ['validate']
        
        if var_file:
            args.extend(['-var-file', var_file])
        if vars:
            for key, value in vars.items():
                args.extend(['-var', f'{key}={value}'])
        
        args.append('.')
        
        result = self._run_command(template_dir, *args)
        
        if result.get('stdout') or result.get('stderr'):
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            self._save_log(template_name, 'validate', output)
        
        return result
    
    def inspect(self, template_name: str) -> Dict:
        """Inspect a template."""
        template_dir = self.home_dir / template_name
        
        # Find the main template file
        template_files = list(template_dir.glob('*.pkr.hcl'))
        if not template_files:
            template_files = list(template_dir.glob('*.json'))
        
        if not template_files:
            return {'success': False, 'error': 'No template files found'}
        
        result = self._run_command(template_dir, 'inspect', '.')
        return result
    
    def fmt(self, template_name: str, check: bool = False,
            recursive: bool = True) -> Dict:
        """Format template files."""
        template_dir = self.home_dir / template_name
        
        args = ['fmt']
        if check:
            args.append('-check')
        if recursive:
            args.append('-recursive')
        args.append('.')
        
        return self._run_command(template_dir, *args)
    
    def build(self, template_name: str, 
              only: List[str] = None,
              except_builds: List[str] = None,
              var_file: str = None,
              vars: Dict = None,
              force: bool = False,
              on_error: str = 'cleanup') -> Dict:
        """
        Build images from a template.
        Returns immediately with process info for background execution.
        """
        template_dir = self.home_dir / template_name
        
        args = ['build', '-color=false']
        
        if only:
            args.extend(['-only', ','.join(only)])
        if except_builds:
            args.extend(['-except', ','.join(except_builds)])
        if var_file:
            args.extend(['-var-file', var_file])
        if vars:
            for key, value in vars.items():
                args.extend(['-var', f'{key}={value}'])
        if force:
            args.append('-force')
        if on_error:
            args.extend(['-on-error', on_error])
        
        args.append('.')
        
        # For builds, we want to capture output to a log file
        result = self._run_command(template_dir, *args)
        
        if result.get('stdout') or result.get('stderr'):
            output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
            log_file = self._save_log(template_name, 'build', output)
            result['log_file'] = str(log_file)
        
        return result
    
    def build_async(self, template_name: str,
                    only: List[str] = None,
                    var_file: str = None,
                    vars: Dict = None) -> subprocess.Popen:
        """
        Start a build in the background.
        Returns the subprocess for monitoring.
        """
        template_dir = self.home_dir / template_name
        
        cmd = [self.binary_path, 'build', '-color=false']
        
        if only:
            cmd.extend(['-only', ','.join(only)])
        if var_file:
            cmd.extend(['-var-file', var_file])
        if vars:
            for key, value in vars.items():
                cmd.extend(['-var', f'{key}={value}'])
        
        cmd.append('.')
        
        # Create log file for output
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = self.logs_dir / template_name / f'build_{timestamp}.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        log_handle = open(log_file, 'w')
        
        process = subprocess.Popen(
            cmd,
            cwd=template_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        return process
    
    # ============ Logs ============
    
    def list_logs(self, template_name: str) -> List[Dict]:
        """List logs for a template."""
        logs = []
        log_dir = self.logs_dir / template_name
        
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
    
    def read_log(self, template_name: str, log_name: str) -> str:
        """Read a log file."""
        log_file = self.logs_dir / template_name / log_name
        if log_file.exists():
            return log_file.read_text()
        return ""
    
    # ============ Plugin Management ============
    
    def plugins_installed(self) -> Dict:
        """List installed plugins."""
        result = subprocess.run(
            [self.binary_path, 'plugins', 'installed'],
            capture_output=True,
            text=True
        )
        
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'plugins': result.stdout.strip().split('\n') if result.stdout else []
        }
    
    def plugins_install(self, plugin: str) -> Dict:
        """Install a plugin."""
        result = subprocess.run(
            [self.binary_path, 'plugins', 'install', plugin],
            capture_output=True,
            text=True
        )
        
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
    
    # ============ Helpers ============
    
    def get_template_status(self, template_name: str) -> str:
        """Get status of a template (based on last build)."""
        logs = self.list_logs(template_name)
        
        if not logs:
            return 'never_built'
        
        # Check most recent build log
        latest_log = logs[0]
        if 'build' in latest_log['name']:
            content = self.read_log(template_name, latest_log['name'])
            if 'error' in content.lower() or 'failed' in content.lower():
                return 'failed'
            elif 'successfully' in content.lower() or 'Build finished' in content.lower():
                return 'success'
        
        return 'unknown'
    
    def get_status_emoji(self, status: str) -> str:
        """Get status emoji."""
        status_map = {
            'success': '🟢',
            'failed': '🔴',
            'building': '🔄',
            'never_built': '⚪',
            'unknown': '⚪',
        }
        return status_map.get(status, '⚪')
