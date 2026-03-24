"""
Settings Manager for OpenTongchi
Handles all configuration, environment variables, and persistent settings.
Secrets are stored securely using the system keyring (KDE Wallet, GNOME Keyring, etc.)
"""

import os
import json
from pathlib import Path
from typing import Any, Optional, Dict, List
from dataclasses import dataclass, field, asdict, fields
from PySide6.QtCore import QSettings

# Try to import keyring for secure secret storage
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Default addresses for services
DEFAULT_VAULT_ADDR = "http://127.0.0.1:8200"
DEFAULT_CONSUL_ADDR = "http://127.0.0.1:8500"
DEFAULT_NOMAD_ADDR = "http://127.0.0.1:4646"
DEFAULT_BOUNDARY_ADDR = "http://127.0.0.1:9200"
DEFAULT_WAYPOINT_ADDR = "http://127.0.0.1:9701"

# Service name for keyring
KEYRING_SERVICE = "opentongchi"

# Fields that should be stored securely in keyring
SECRET_FIELDS = {
    'openbao': ['token'],
    'opentofu': [],
    'hcp': ['client_id', 'client_secret', 'hcp_terraform_token'],
    'consul': ['token'],
    'nomad': ['token'],
    'boundary': ['token', 'password'],
    'waypoint': ['token'],
}


class SecretStore:
    """Secure storage for secrets using system keyring."""
    
    def __init__(self):
        self._available = KEYRING_AVAILABLE
        self._cache: Dict[str, str] = {}  # In-memory cache for session
        
        if self._available:
            try:
                # Test keyring availability
                keyring.get_keyring()
            except Exception:
                self._available = False
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def _make_key(self, section: str, field: str) -> str:
        """Create a keyring key from section and field."""
        return f"{section}.{field}"
    
    def get_secret(self, section: str, field: str) -> str:
        """Retrieve a secret from keyring."""
        key = self._make_key(section, field)
        
        # Check cache first
        if key in self._cache:
            return self._cache[key]
        
        if not self._available:
            return ""
        
        try:
            value = keyring.get_password(KEYRING_SERVICE, key)
            if value:
                self._cache[key] = value
                return value
        except Exception:
            pass
        
        return ""
    
    def set_secret(self, section: str, field: str, value: str):
        """Store a secret in keyring."""
        key = self._make_key(section, field)
        
        # Update cache
        if value:
            self._cache[key] = value
        elif key in self._cache:
            del self._cache[key]
        
        if not self._available:
            return
        
        try:
            if value:
                keyring.set_password(KEYRING_SERVICE, key, value)
            else:
                # Delete empty secrets
                try:
                    keyring.delete_password(KEYRING_SERVICE, key)
                except keyring.errors.PasswordDeleteError:
                    pass
        except Exception:
            pass
    
    def delete_secret(self, section: str, field: str):
        """Delete a secret from keyring."""
        key = self._make_key(section, field)
        
        if key in self._cache:
            del self._cache[key]
        
        if not self._available:
            return
        
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except Exception:
            pass
    
    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()


# Global secret store instance
_secret_store: Optional[SecretStore] = None


def get_secret_store() -> SecretStore:
    """Get the global secret store instance."""
    global _secret_store
    if _secret_store is None:
        _secret_store = SecretStore()
    return _secret_store


@dataclass
class OpenBaoSettings:
    """OpenBao (Vault) settings."""
    address: str = DEFAULT_VAULT_ADDR
    token: str = ""  # Stored in keyring
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
    binary_path: str = "tofu"
    
    def load_from_env(self):
        """Load settings from environment variables."""
        default_home = str(Path.home() / "opentofu")
        self.home_dir = os.environ.get('TOFU_HOME', os.environ.get('TF_HOME', default_home))
        # Try to find tofu or terraform binary
        if not self.binary_path or self.binary_path == "tofu":
            for binary in ['tofu', 'terraform']:
                if os.system(f'which {binary} > /dev/null 2>&1') == 0:
                    self.binary_path = binary
                    break


@dataclass
class HCPSettings:
    """HCP (HashiCorp Cloud Platform) settings.
    
    Cloud services auth: OAuth2 client_credentials with client_id/client_secret.
    HCP Terraform auth: separate TFE bearer token against app.terraform.io.
    """
    # OAuth2 service principal credentials for HCP Cloud API
    client_id: str = ""        # Stored in keyring
    client_secret: str = ""    # Stored in keyring
    organization_id: str = ""
    organization_name: str = ""
    project_id: str = ""
    project_name: str = ""
    # Endpoint URLs (configurable for EU region or self-hosted)
    hcp_api_url: str = "https://api.cloud.hashicorp.com"
    hcp_auth_url: str = "https://auth.idp.hashicorp.com"
    # HCP Terraform (app.terraform.io) — separate token
    hcp_terraform_url: str = "https://app.terraform.io"
    hcp_terraform_token: str = ""  # Stored in keyring
    hcp_terraform_org: str = ""

    def load_from_env(self):
        """Load settings from environment variables."""
        self.client_id = os.environ.get('HCP_CLIENT_ID', self.client_id)
        self.client_secret = os.environ.get('HCP_CLIENT_SECRET', self.client_secret)
        self.organization_id = os.environ.get('HCP_ORGANIZATION_ID',
                                               os.environ.get('ORGANIZATION_ID', self.organization_id))
        self.project_id = os.environ.get('HCP_PROJECT_ID',
                                          os.environ.get('PROJECT_ID', self.project_id))
        self.hcp_api_url = os.environ.get('HCP_API_URL', self.hcp_api_url)
        self.hcp_auth_url = os.environ.get('HCP_AUTH_URL', self.hcp_auth_url)
        self.hcp_terraform_url = os.environ.get('TFE_ADDRESS',
                                                 os.environ.get('TFE_URL', self.hcp_terraform_url))
        self.hcp_terraform_token = os.environ.get('TFE_TOKEN',
                                                   os.environ.get('TFC_TOKEN', self.hcp_terraform_token))
        self.hcp_terraform_org = os.environ.get('TFE_ORG', self.hcp_terraform_org)


@dataclass
class ConsulSettings:
    """Consul settings."""
    address: str = DEFAULT_CONSUL_ADDR
    token: str = ""  # Stored in keyring
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
    token: str = ""  # Stored in keyring
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
    token: str = ""  # Stored in keyring
    auth_method_id: str = ""
    login_name: str = ""
    password: str = ""  # Stored in keyring
    scope_id: str = "global"
    binary_path: str = "boundary"
    
    def load_from_env(self):
        """Load settings from environment variables."""
        self.address = os.environ.get('BOUNDARY_ADDR', self.address)
        self.token = os.environ.get('BOUNDARY_TOKEN', self.token)
        self.auth_method_id = os.environ.get('BOUNDARY_AUTH_METHOD_ID', self.auth_method_id)
        self.login_name = os.environ.get('BOUNDARY_LOGIN_NAME', self.login_name)
        self.password = os.environ.get('BOUNDARY_PASSWORD', self.password)
        self.scope_id = os.environ.get('BOUNDARY_SCOPE_ID', self.scope_id)


@dataclass
class WaypointSettings:
    """Waypoint settings."""
    address: str = DEFAULT_WAYPOINT_ADDR
    token: str = ""  # Stored in keyring
    
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
    # Sound notification settings
    sounds_enabled: bool = False
    sound_success: str = "system"  # "system", "none", or path to file
    sound_error: str = "system"    # "system", "none", or path to file
    
    def load_from_env(self):
        """Load settings from environment variables."""
        self.namespace = os.environ.get('HASHICORP_NAMESPACE', self.namespace)
        default_cache = str(Path.home() / ".cache" / "opentongchi")
        self.cache_dir = os.environ.get('OPENTONGCHI_CACHE', default_cache)


class SettingsManager:
    """Manages all application settings with persistence.
    
    Secrets (tokens, passwords) are stored in the system keyring.
    Other settings are stored in QSettings.
    """
    
    def __init__(self):
        self.qsettings = QSettings("OpenTongchi", "OpenTongchi")
        self.secret_store = get_secret_store()
        
        # Initialize all settings objects
        self.global_settings = GlobalSettings()
        self.openbao = OpenBaoSettings()
        self.opentofu = OpenTofuSettings()
        self.hcp = HCPSettings()
        self.consul = ConsulSettings()
        self.nomad = NomadSettings()
        self.boundary = BoundarySettings()
        self.waypoint = WaypointSettings()
        self.packer = PackerSettings()
        
        # Load from environment first
        self._load_from_env()
        
        # Then load persisted settings (overrides env for non-secrets)
        self._load_persisted()
        
        # Load secrets from keyring
        self._load_secrets()
        
        # Migrate any old secrets from QSettings to keyring
        self._migrate_secrets_to_keyring()
        
        # Ensure cache directory exists
        Path(self.global_settings.cache_dir).mkdir(parents=True, exist_ok=True)
    
    def _load_from_env(self):
        """Load all settings from environment variables."""
        self.global_settings.load_from_env()
        self.openbao.load_from_env()
        self.opentofu.load_from_env()
        self.hcp.load_from_env()
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
    
    def _get_non_secret_dict(self, section: str, obj: Any) -> Dict:
        """Get a dictionary of non-secret fields from an object."""
        secret_fields = SECRET_FIELDS.get(section, [])
        result = {}
        for f in fields(obj):
            if f.name not in secret_fields:
                result[f.name] = getattr(obj, f.name)
        return result
    
    def _load_persisted(self):
        """Load non-secret settings from persistent storage."""
        # Global settings (no secrets)
        if self.qsettings.contains("global"):
            data = json.loads(self.qsettings.value("global", "{}"))
            for key, value in data.items():
                if hasattr(self.global_settings, key):
                    setattr(self.global_settings, key, value)
        
        # Product-specific settings (excluding secrets)
        for name, obj in [
            ("openbao", self.openbao),
            ("opentofu", self.opentofu),
            ("hcp", self.hcp),
            ("consul", self.consul),
            ("nomad", self.nomad),
            ("boundary", self.boundary),
            ("waypoint", self.waypoint),
            ("packer", self.packer),
        ]:
            secret_fields = SECRET_FIELDS.get(name, [])
            if self.qsettings.contains(name):
                data = json.loads(self.qsettings.value(name, "{}"))
                for key, value in data.items():
                    # Skip secret fields - they're loaded from keyring
                    if key in secret_fields:
                        continue
                    if hasattr(obj, key):
                        setattr(obj, key, value)
    
    def _load_secrets(self):
        """Load secrets from keyring."""
        for section, secret_fields in SECRET_FIELDS.items():
            obj = getattr(self, section, None)
            if obj is None:
                continue
            
            for field_name in secret_fields:
                # Only load from keyring if not already set from env
                current_value = getattr(obj, field_name, "")
                if not current_value:
                    secret_value = self.secret_store.get_secret(section, field_name)
                    if secret_value:
                        setattr(obj, field_name, secret_value)
    
    def _save_secrets(self):
        """Save secrets to keyring."""
        for section, secret_fields in SECRET_FIELDS.items():
            obj = getattr(self, section, None)
            if obj is None:
                continue
            
            for field_name in secret_fields:
                value = getattr(obj, field_name, "")
                self.secret_store.set_secret(section, field_name, value)
    
    def _migrate_secrets_to_keyring(self):
        """Migrate any secrets stored in QSettings to keyring.
        
        This handles upgrades from older versions that stored secrets in plain text.
        """
        if not self.secret_store.is_available:
            return
        
        migrated = False
        for section, secret_fields in SECRET_FIELDS.items():
            if self.qsettings.contains(section):
                try:
                    data = json.loads(self.qsettings.value(section, "{}"))
                    for field_name in secret_fields:
                        if field_name in data and data[field_name]:
                            # Move to keyring if not already there
                            existing = self.secret_store.get_secret(section, field_name)
                            if not existing:
                                self.secret_store.set_secret(section, field_name, data[field_name])
                            # Clear from QSettings data
                            data[field_name] = ""
                            migrated = True
                    if migrated:
                        # Re-save without secrets
                        self.qsettings.setValue(section, json.dumps(data))
                except Exception:
                    pass
        
        if migrated:
            self.qsettings.sync()
    
    def save(self):
        """Save all settings to persistent storage.
        
        Non-secret settings go to QSettings.
        Secrets go to the system keyring.
        """
        # Save non-secret settings to QSettings
        self.qsettings.setValue("global", json.dumps(asdict(self.global_settings)))
        
        for name, obj in [
            ("openbao", self.openbao),
            ("opentofu", self.opentofu),
            ("hcp", self.hcp),
            ("consul", self.consul),
            ("nomad", self.nomad),
            ("boundary", self.boundary),
            ("waypoint", self.waypoint),
            ("packer", self.packer),
        ]:
            # Save non-secret fields to QSettings
            non_secret_data = self._get_non_secret_dict(name, obj)
            self.qsettings.setValue(name, json.dumps(non_secret_data))
        
        self.qsettings.sync()
        
        # Save secrets to keyring
        self._save_secrets()
    
    def get_cache_path(self, filename: str) -> Path:
        """Get path for a cache file."""
        return Path(self.global_settings.cache_dir) / filename
    
    def get_effective_namespace(self) -> str:
        """Get the effective global namespace."""
        return self.global_settings.namespace
    
    def is_keyring_available(self) -> bool:
        """Check if secure keyring storage is available."""
        return self.secret_store.is_available
