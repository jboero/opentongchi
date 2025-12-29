"""Configuration management for OpenTongchi"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class OpenBaoConfig:
    """OpenBao (Vault) configuration"""
    address: str = ""
    token: str = ""
    namespace: str = ""
    skip_verify: bool = False
    token_renewal_enabled: bool = True
    token_renewal_interval: int = 300  # 5 minutes
    lease_renewal_enabled: bool = True
    lease_renewal_interval: int = 60  # 1 minute
    
    def __post_init__(self):
        # Load from environment if not set
        if not self.address:
            self.address = os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200")
        if not self.token:
            self.token = os.environ.get("VAULT_TOKEN", "")
        if not self.namespace:
            self.namespace = os.environ.get("HASHICORP_NAMESPACE", "")


@dataclass
class ConsulConfig:
    """Consul configuration"""
    address: str = ""
    token: str = ""
    namespace: str = ""
    datacenter: str = ""
    skip_verify: bool = False
    
    def __post_init__(self):
        if not self.address:
            self.address = os.environ.get("CONSUL_HTTP_ADDR", "http://127.0.0.1:8500")
        if not self.token:
            self.token = os.environ.get("CONSUL_HTTP_TOKEN", "")
        if not self.namespace:
            self.namespace = os.environ.get("HASHICORP_NAMESPACE", "")
        if not self.datacenter:
            self.datacenter = os.environ.get("CONSUL_DATACENTER", "")


@dataclass
class NomadConfig:
    """Nomad configuration"""
    address: str = ""
    token: str = ""
    namespace: str = ""
    region: str = ""
    skip_verify: bool = False
    refresh_interval: int = 10  # seconds
    alerts_enabled: bool = True
    
    def __post_init__(self):
        if not self.address:
            self.address = os.environ.get("NOMAD_ADDR", "http://127.0.0.1:4646")
        if not self.token:
            self.token = os.environ.get("NOMAD_TOKEN", "")
        if not self.namespace:
            self.namespace = os.environ.get("HASHICORP_NAMESPACE", "")
        if not self.region:
            self.region = os.environ.get("NOMAD_REGION", "")


@dataclass
class OpenTofuConfig:
    """OpenTofu/Terraform configuration"""
    local_directory: str = ""
    hcp_token: str = ""
    hcp_organization: str = ""
    
    def __post_init__(self):
        if not self.local_directory:
            self.local_directory = os.path.join(os.path.expanduser("~"), "opentofu")
        if not self.hcp_token:
            self.hcp_token = os.environ.get("TF_TOKEN_app_terraform_io", "")
            if not self.hcp_token:
                self.hcp_token = os.environ.get("TFE_TOKEN", "")
        if not self.hcp_organization:
            self.hcp_organization = os.environ.get("TF_CLOUD_ORGANIZATION", "")


@dataclass
class Config:
    """Main configuration container"""
    openbao: OpenBaoConfig = field(default_factory=OpenBaoConfig)
    consul: ConsulConfig = field(default_factory=ConsulConfig)
    nomad: NomadConfig = field(default_factory=NomadConfig)
    opentofu: OpenTofuConfig = field(default_factory=OpenTofuConfig)
    global_namespace: str = ""
    schema_cache_dir: str = ""
    
    def __post_init__(self):
        if not self.global_namespace:
            self.global_namespace = os.environ.get("HASHICORP_NAMESPACE", "")
        if not self.schema_cache_dir:
            self.schema_cache_dir = os.path.join(
                os.path.expanduser("~"), ".opentongchi", "cache"
            )
        
        # Apply global namespace to all products
        if self.global_namespace:
            self.openbao.namespace = self.global_namespace
            self.consul.namespace = self.global_namespace
            self.nomad.namespace = self.global_namespace
    
    @classmethod
    def config_path(cls) -> Path:
        """Get the configuration file path"""
        config_dir = Path.home() / ".opentongchi"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "config.json"
    
    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file"""
        config_file = cls.config_path()
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    data = json.load(f)
                
                config = cls()
                if "openbao" in data:
                    for k, v in data["openbao"].items():
                        if hasattr(config.openbao, k):
                            setattr(config.openbao, k, v)
                if "consul" in data:
                    for k, v in data["consul"].items():
                        if hasattr(config.consul, k):
                            setattr(config.consul, k, v)
                if "nomad" in data:
                    for k, v in data["nomad"].items():
                        if hasattr(config.nomad, k):
                            setattr(config.nomad, k, v)
                if "opentofu" in data:
                    for k, v in data["opentofu"].items():
                        if hasattr(config.opentofu, k):
                            setattr(config.opentofu, k, v)
                if "global_namespace" in data:
                    config.global_namespace = data["global_namespace"]
                if "schema_cache_dir" in data:
                    config.schema_cache_dir = data["schema_cache_dir"]
                
                return config
            except Exception:
                pass
        return cls()
    
    def save(self):
        """Save configuration to file"""
        config_file = self.config_path()
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "openbao": asdict(self.openbao),
            "consul": asdict(self.consul),
            "nomad": asdict(self.nomad),
            "opentofu": asdict(self.opentofu),
            "global_namespace": self.global_namespace,
            "schema_cache_dir": self.schema_cache_dir,
        }
        
        with open(config_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def set_global_namespace(self, namespace: str):
        """Set namespace across all products"""
        self.global_namespace = namespace
        self.openbao.namespace = namespace
        self.consul.namespace = namespace
        self.nomad.namespace = namespace
