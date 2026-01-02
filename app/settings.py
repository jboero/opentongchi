"""
Settings Manager for OpenTongchi
Handles all configuration, environment variables, and persistent settings.
"""

import os
import json
from pathlib import Path
from typing import Any, Optional, Dict
from dataclasses import dataclass, field, asdict
from PySide6.QtCore import QSettings

# Default addresses for services
DEFAULT_VAULT_ADDR = "http://127.0.0.1:8200"
DEFAULT_CONSUL_ADDR = "http://127.0.0.1:8500"
DEFAULT_NOMAD_ADDR = "http://127.0.0.1:4646"
DEFAULT_BOUNDARY_ADDR = "http://127.0.0.1:9200"
DEFAULT_WAYPOINT_ADDR = "http://127.0.0.1:9701"


@dataclass
class OpenBaoSettings:
    """OpenBao (Vault) settings."""
    address: str = DEFAULT_VAULT_ADDR
    token: str = ""
    namespace: str = ""
    skip_verify: bool = False
    auto_renew_token: bool = True
    renew_interval_seconds: int = 300
    
    def load_from_env(self):
        """Load settings from environment variables."""
        self.address = os.environ.get('VAULT_ADDR', os.environ.get('BAO_ADDR', self.address))
        self.token = os.environ.get('VAULT_TOKEN', os.environ.get('BAO_TOKEN', self.token))
        self.namespace = os.environ.get('VAULT_NAMESPACE', os.environ.get('BAO_NAMESPACE', 
                                        os.environ.get('HASHICORP_NAMESPACE', self.namespace)))
        self.skip_verify = os.environ.get('VAULT_SKIP_VERIFY', '').lower() in ('true', '1', 'yes')


@dataclass
class OpenTofuSettings:
    """OpenTofu (Terraform) settings."""
    home_dir: str = ""
    hcp_token: str = ""
    hcp_org: str = ""
    binary_path: str = "tofu"
    
    def load_from_env(self):
        """Load settings from environment variables."""
        default_home = str(Path.home() / "opentofu")
        self.home_dir = os.environ.get('TOFU_HOME', os.environ.get('TF_HOME', default_home))
        self.hcp_token = os.environ.get('TFE_TOKEN', os.environ.get('TFC_TOKEN', self.hcp_token))
        self.hcp_org = os.environ.get('TFE_ORG', self.hcp_org)
        # Try to find tofu or terraform binary
        if not self.binary_path or self.binary_path == "tofu":
            for binary in ['tofu', 'terraform']:
                if os.system(f'which {binary} > /dev/null 2>&1') == 0:
                    self.binary_path = binary
                    break


@dataclass
class ConsulSettings:
    """Consul settings."""
    address: str = DEFAULT_CONSUL_ADDR
    token: str = ""
    namespace: str = ""
    datacenter: str = ""
    
    def load_from_env(self):
        """Load settings from environment variables."""
        self.address = os.environ.get('CONSUL_HTTP_ADDR', os.environ.get('CONSUL_ADDR', self.address))
        self.token = os.environ.get('CONSUL_HTTP_TOKEN', os.environ.get('CONSUL_TOKEN', self.token))
        self.namespace = os.environ.get('CONSUL_NAMESPACE', 
                                        os.environ.get('HASHICORP_NAMESPACE', self.namespace))
        self.datacenter = os.environ.get('CONSUL_DATACENTER', self.datacenter)


@dataclass
class NomadSettings:
    """Nomad settings."""
    address: str = DEFAULT_NOMAD_ADDR
    token: str = ""
    namespace: str = ""
    region: str = ""
    refresh_interval_seconds: int = 10
    
    def load_from_env(self):
        """Load settings from environment variables."""
        self.address = os.environ.get('NOMAD_ADDR', self.address)
        self.token = os.environ.get('NOMAD_TOKEN', self.token)
        self.namespace = os.environ.get('NOMAD_NAMESPACE', 
                                        os.environ.get('HASHICORP_NAMESPACE', self.namespace))
        self.region = os.environ.get('NOMAD_REGION', self.region)


@dataclass
class BoundarySettings:
    """Boundary settings."""
    address: str = DEFAULT_BOUNDARY_ADDR
    token: str = ""
    auth_method_id: str = ""
    binary_path: str = "boundary"
    
    def load_from_env(self):
        """Load settings from environment variables."""
        self.address = os.environ.get('BOUNDARY_ADDR', self.address)
        self.token = os.environ.get('BOUNDARY_TOKEN', self.token)
        self.auth_method_id = os.environ.get('BOUNDARY_AUTH_METHOD_ID', self.auth_method_id)


@dataclass
class WaypointSettings:
    """Waypoint settings."""
    address: str = DEFAULT_WAYPOINT_ADDR
    token: str = ""
    
    def load_from_env(self):
        """Load settings from environment variables."""
        self.address = os.environ.get('WAYPOINT_ADDR', self.address)
        self.token = os.environ.get('WAYPOINT_TOKEN', self.token)


@dataclass
class PackerSettings:
    """Packer settings."""
    home_dir: str = ""
    binary_path: str = "packer"
    
    def load_from_env(self):
        """Load settings from environment variables."""
        default_home = str(Path.home() / "packer")
        self.home_dir = os.environ.get('PACKER_HOME', default_home)


@dataclass
class GlobalSettings:
    """Global application settings."""
    namespace: str = ""  # HASHICORP_NAMESPACE - applies to all products
    theme: str = "system"
    show_notifications: bool = True
    log_level: str = "INFO"
    cache_dir: str = ""
    
    def load_from_env(self):
        """Load settings from environment variables."""
        self.namespace = os.environ.get('HASHICORP_NAMESPACE', self.namespace)
        default_cache = str(Path.home() / ".cache" / "opentongchi")
        self.cache_dir = os.environ.get('OPENTONGCHI_CACHE', default_cache)


class SettingsManager:
    """Manages all application settings with persistence."""
    
    def __init__(self):
        self.qsettings = QSettings("OpenTongchi", "OpenTongchi")
        
        # Initialize all settings objects
        self.global_settings = GlobalSettings()
        self.openbao = OpenBaoSettings()
        self.opentofu = OpenTofuSettings()
        self.consul = ConsulSettings()
        self.nomad = NomadSettings()
        self.boundary = BoundarySettings()
        self.waypoint = WaypointSettings()
        self.packer = PackerSettings()
        
        # Load from environment first
        self._load_from_env()
        
        # Then load persisted settings (overrides env)
        self._load_persisted()
        
        # Ensure cache directory exists
        Path(self.global_settings.cache_dir).mkdir(parents=True, exist_ok=True)
    
    def _load_from_env(self):
        """Load all settings from environment variables."""
        self.global_settings.load_from_env()
        self.openbao.load_from_env()
        self.opentofu.load_from_env()
        self.consul.load_from_env()
        self.nomad.load_from_env()
        self.boundary.load_from_env()
        self.waypoint.load_from_env()
        self.packer.load_from_env()
        
        # Apply global namespace to products if not set
        if self.global_settings.namespace:
            if not self.openbao.namespace:
                self.openbao.namespace = self.global_settings.namespace
            if not self.consul.namespace:
                self.consul.namespace = self.global_settings.namespace
            if not self.nomad.namespace:
                self.nomad.namespace = self.global_settings.namespace
    
    def _load_persisted(self):
        """Load settings from persistent storage."""
        # Global settings
        if self.qsettings.contains("global"):
            data = json.loads(self.qsettings.value("global", "{}"))
            for key, value in data.items():
                if hasattr(self.global_settings, key):
                    setattr(self.global_settings, key, value)
        
        # Product-specific settings
        for name, obj in [
            ("openbao", self.openbao),
            ("opentofu", self.opentofu),
            ("consul", self.consul),
            ("nomad", self.nomad),
            ("boundary", self.boundary),
            ("waypoint", self.waypoint),
            ("packer", self.packer),
        ]:
            if self.qsettings.contains(name):
                data = json.loads(self.qsettings.value(name, "{}"))
                for key, value in data.items():
                    if hasattr(obj, key):
                        setattr(obj, key, value)
    
    def save(self):
        """Save all settings to persistent storage."""
        self.qsettings.setValue("global", json.dumps(asdict(self.global_settings)))
        self.qsettings.setValue("openbao", json.dumps(asdict(self.openbao)))
        self.qsettings.setValue("opentofu", json.dumps(asdict(self.opentofu)))
        self.qsettings.setValue("consul", json.dumps(asdict(self.consul)))
        self.qsettings.setValue("nomad", json.dumps(asdict(self.nomad)))
        self.qsettings.setValue("boundary", json.dumps(asdict(self.boundary)))
        self.qsettings.setValue("waypoint", json.dumps(asdict(self.waypoint)))
        self.qsettings.setValue("packer", json.dumps(asdict(self.packer)))
        self.qsettings.sync()
    
    def get_cache_path(self, filename: str) -> Path:
        """Get path for a cache file."""
        return Path(self.global_settings.cache_dir) / filename
    
    def get_effective_namespace(self) -> str:
        """Get the effective global namespace."""
        return self.global_settings.namespace
