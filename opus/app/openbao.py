"""OpenBao (Vault) client and menu handling"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from PyQt6.QtWidgets import QMenu, QMessageBox, QInputDialog
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer

from .http_client import HttpClient, ApiError
from .dialogs import ViewSecretDialog, NewSecretDialog, CrudDialog, JsonTableDialog


class OpenBaoClient(HttpClient):
    """Client for OpenBao/Vault API"""
    
    def __init__(self, address: str, token: str = "", 
                 namespace: str = "", skip_verify: bool = False):
        super().__init__(address, token, namespace, skip_verify)
    
    def _build_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["X-Vault-Token"] = self.token
        if self.namespace:
            headers["X-Vault-Namespace"] = self.namespace
        if extra_headers:
            headers.update(extra_headers)
        return headers
    
    def get_health(self) -> Dict:
        """Get server health status"""
        try:
            return self.get("/v1/sys/health")
        except ApiError as e:
            if e.status_code in (429, 472, 473, 501, 503):
                return json.loads(e.response) if e.response else {}
            raise
    
    def get_seal_status(self) -> Dict:
        return self.get("/v1/sys/seal-status")
    
    def lookup_self(self) -> Dict:
        return self.get("/v1/auth/token/lookup-self")
    
    def renew_self(self) -> Dict:
        return self.post("/v1/auth/token/renew-self")
    
    def get_openapi_schema(self) -> Dict:
        return self.get("/v1/sys/internal/specs/openapi")
    
    def list_secrets(self, path: str) -> List[str]:
        try:
            result = self.list(f"/v1/{path}")
            return result.get("data", {}).get("keys", [])
        except ApiError:
            return []
    
    def read_secret(self, path: str) -> Dict:
        result = self.get(f"/v1/{path}")
        if "data" in result and "data" in result["data"]:
            return result["data"]["data"]
        return result.get("data", result)
    
    def write_secret(self, path: str, data: Dict) -> Dict:
        if "/data/" in path:
            return self.post(f"/v1/{path}", {"data": data})
        return self.post(f"/v1/{path}", data)
    
    def delete_secret(self, path: str) -> Dict:
        return self.delete(f"/v1/{path}")
    
    def list_mounts(self) -> Dict:
        result = self.get("/v1/sys/mounts")
        return result.get("data", result)
    
    def list_auth_methods(self) -> Dict:
        result = self.get("/v1/sys/auth")
        return result.get("data", result)
    
    def list_policies(self) -> List[str]:
        result = self.get("/v1/sys/policies/acl")
        return result.get("data", {}).get("keys", [])
    
    def read_policy(self, name: str) -> Dict:
        return self.get(f"/v1/sys/policies/acl/{name}")
    
    def write_policy(self, name: str, policy: str) -> Dict:
        return self.put(f"/v1/sys/policies/acl/{name}", {"policy": policy})
    
    def delete_policy(self, name: str) -> Dict:
        return self.delete(f"/v1/sys/policies/acl/{name}")
    
    def list_leases(self, prefix: str = "") -> List[str]:
        try:
            result = self.list(f"/v1/sys/leases/lookup/{prefix}")
            return result.get("data", {}).get("keys", [])
        except ApiError:
            return []
    
    def renew_lease(self, lease_id: str, increment: int = 0) -> Dict:
        data = {"lease_id": lease_id}
        if increment:
            data["increment"] = increment
        return self.put("/v1/sys/leases/renew", data)


class SchemaCache:
    """Cache for OpenAPI schema"""
    
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.schema: Optional[Dict] = None
    
    def cache_file(self, address: str) -> Path:
        safe_name = address.replace("://", "_").replace("/", "_").replace(":", "_")
        return self.cache_dir / f"openbao_schema_{safe_name}.json"
    
    def load(self, address: str) -> Optional[Dict]:
        cache_file = self.cache_file(address)
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    self.schema = json.load(f)
                    return self.schema
            except Exception:
                pass
        return None
    
    def save(self, address: str, schema: Dict):
        self.schema = schema
        cache_file = self.cache_file(address)
        with open(cache_file, "w") as f:
            json.dump(schema, f)
    
    def clear(self, address: str):
        cache_file = self.cache_file(address)
        if cache_file.exists():
            cache_file.unlink()
        self.schema = None


class OpenBaoMenuBuilder(QObject):
    """Builds dynamic menus for OpenBao"""
    
    status_changed = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.client: Optional[OpenBaoClient] = None
        self.schema_cache: Optional[SchemaCache] = None
        self._loading_menus: set = set()
    
    def get_client(self) -> OpenBaoClient:
        if self.client is None or self.client.base_url != self.config.openbao.address:
            self.client = OpenBaoClient(
                self.config.openbao.address,
                self.config.openbao.token,
                self.config.openbao.namespace,
                self.config.openbao.skip_verify
            )
        else:
            self.client.token = self.config.openbao.token
            self.client.namespace = self.config.openbao.namespace
        return self.client
    
    def get_schema_cache(self) -> SchemaCache:
        if self.schema_cache is None:
            self.schema_cache = SchemaCache(self.config.schema_cache_dir)
        return self.schema_cache
    
    def get_status_emoji(self) -> str:
        try:
            client = self.get_client()
            health = client.get_health()
            if health.get("sealed", False):
                return "🟡"
            if health.get("standby", False):
                return "🟠"
            if health.get("initialized", False):
                return "🟢"
            return "🔴"
        except Exception:
            return "⚪"
    
    def build_menu(self, parent_menu: QMenu) -> QMenu:
        menu = parent_menu.addMenu("🔐 OpenBao")
        
        status = self.get_status_emoji()
        status_action = menu.addAction(f"{status} Status")
        status_action.triggered.connect(self.show_status)
        
        menu.addSeparator()
        
        secrets_menu = menu.addMenu("🗝️ Secrets")
        secrets_menu.aboutToShow.connect(lambda: self.populate_mounts_menu(secrets_menu))
        
        auth_menu = menu.addMenu("🔑 Auth Methods")
        auth_menu.aboutToShow.connect(lambda: self.populate_auth_menu(auth_menu))
        
        policies_menu = menu.addMenu("📜 Policies")
        policies_menu.aboutToShow.connect(lambda: self.populate_policies_menu(policies_menu))
        
        sys_menu = menu.addMenu("⚙️ System")
        self.build_system_menu(sys_menu)
        
        tools_menu = menu.addMenu("🔧 Tools")
        self.build_tools_menu(tools_menu)
        
        menu.addSeparator()
        
        schema_menu = menu.addMenu("📋 API Schema")
        schema_menu.aboutToShow.connect(lambda: self.populate_schema_menu(schema_menu))
        
        refresh_action = menu.addAction("🔄 Refresh Schema")
        refresh_action.triggered.connect(self.refresh_schema)
        
        return menu
    
    def set_menu_loading(self, menu: QMenu, loading: bool):
        menu_id = id(menu)
        if loading:
            self._loading_menus.add(menu_id)
            menu.setCursor(QCursor(Qt.CursorShape.WaitCursor))
            if menu.isEmpty():
                loading_action = menu.addAction("⏳ Loading...")
                loading_action.setEnabled(False)
        else:
            self._loading_menus.discard(menu_id)
            menu.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
    
    def populate_mounts_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            mounts = client.list_mounts()
            menu.clear()
            for mount_path, mount_info in sorted(mounts.items()):
                mount_type = mount_info.get("type", "unknown")
                mount_menu = menu.addMenu(f"📁 {mount_path} ({mount_type})")
                mount_menu.aboutToShow.connect(
                    lambda m=mount_menu, p=mount_path, t=mount_type: 
                    self.populate_secrets_menu(m, p, t)
                )
            if not mounts:
                no_mounts = menu.addAction("No mounts found")
                no_mounts.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_secrets_menu(self, menu: QMenu, mount_path: str, mount_type: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            if mount_type in ("kv", "kv-v2"):
                list_path = f"{mount_path}metadata/"
            else:
                list_path = mount_path
            secrets = client.list_secrets(list_path)
            menu.clear()
            new_action = menu.addAction("➕ New...")
            new_action.triggered.connect(lambda: self.create_new_secret(mount_path, mount_type))
            menu.addSeparator()
            for secret in sorted(secrets):
                if secret.endswith("/"):
                    folder_menu = menu.addMenu(f"📁 {secret}")
                    folder_path = f"{list_path}{secret}"
                    folder_menu.aboutToShow.connect(
                        lambda m=folder_menu, p=folder_path, t=mount_type, r=mount_path:
                        self.populate_secrets_submenu(m, p, t, r)
                    )
                else:
                    secret_action = menu.addAction(f"🔑 {secret}")
                    if mount_type == "kv-v2":
                        secret_path = f"{mount_path}data/{secret}"
                    else:
                        secret_path = f"{mount_path}{secret}"
                    secret_action.triggered.connect(lambda checked, p=secret_path: self.view_secret(p))
            if not secrets:
                empty_action = menu.addAction("(empty)")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_secrets_submenu(self, menu: QMenu, path: str, mount_type: str, mount_root: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            secrets = client.list_secrets(path)
            menu.clear()
            new_action = menu.addAction("➕ New...")
            relative_path = path.replace(f"{mount_root}metadata/", "")
            new_action.triggered.connect(lambda: self.create_new_secret(mount_root, mount_type, relative_path))
            menu.addSeparator()
            for secret in sorted(secrets):
                if secret.endswith("/"):
                    folder_menu = menu.addMenu(f"📁 {secret}")
                    folder_path = f"{path}{secret}"
                    folder_menu.aboutToShow.connect(
                        lambda m=folder_menu, p=folder_path, t=mount_type, r=mount_root:
                        self.populate_secrets_submenu(m, p, t, r)
                    )
                else:
                    secret_action = menu.addAction(f"🔑 {secret}")
                    if mount_type == "kv-v2":
                        data_path = path.replace("/metadata/", "/data/") + secret
                    else:
                        data_path = path + secret
                    secret_action.triggered.connect(lambda checked, p=data_path: self.view_secret(p))
            if not secrets:
                empty_action = menu.addAction("(empty)")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_auth_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            auth_methods = client.list_auth_methods()
            menu.clear()
            for path, info in sorted(auth_methods.items()):
                auth_type = info.get("type", "unknown")
                emoji = self.get_auth_emoji(auth_type)
                auth_action = menu.addAction(f"{emoji} {path} ({auth_type})")
                auth_action.triggered.connect(lambda checked, p=path, i=info: self.show_auth_details(p, i))
            if not auth_methods:
                empty_action = menu.addAction("No auth methods found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def get_auth_emoji(self, auth_type: str) -> str:
        emojis = {
            "token": "🎫", "userpass": "👤", "ldap": "🏢", "github": "🐙",
            "aws": "☁️", "gcp": "🌐", "azure": "🔷", "kubernetes": "☸️",
            "jwt": "📄", "oidc": "🔗", "approle": "🤖", "cert": "📜",
        }
        return emojis.get(auth_type, "🔐")
    
    def populate_policies_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            policies = client.list_policies()
            menu.clear()
            new_action = menu.addAction("➕ New Policy...")
            new_action.triggered.connect(self.create_new_policy)
            menu.addSeparator()
            for policy in sorted(policies):
                policy_action = menu.addAction(f"📜 {policy}")
                policy_action.triggered.connect(lambda checked, p=policy: self.view_policy(p))
            if not policies:
                empty_action = menu.addAction("No policies found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def build_system_menu(self, menu: QMenu):
        seal_action = menu.addAction("🔒 Seal Status")
        seal_action.triggered.connect(self.show_seal_status)
        token_action = menu.addAction("🎫 Token Info")
        token_action.triggered.connect(self.show_token_info)
        menu.addSeparator()
        leases_menu = menu.addMenu("📄 Leases")
        leases_menu.aboutToShow.connect(lambda: self.populate_leases_menu(leases_menu))
        audit_action = menu.addAction("📝 Audit Devices")
        audit_action.triggered.connect(self.show_audit_devices)
    
    def build_tools_menu(self, menu: QMenu):
        random_action = menu.addAction("🎲 Generate Random")
        random_action.triggered.connect(self.generate_random)
        hash_action = menu.addAction("#️⃣ Hash Data")
        hash_action.triggered.connect(self.hash_data)
        menu.addSeparator()
        transit_menu = menu.addMenu("🔐 Transit")
        transit_menu.aboutToShow.connect(lambda: self.populate_transit_menu(transit_menu))
    
    def populate_schema_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            cache = self.get_schema_cache()
            schema = cache.load(self.config.openbao.address)
            if not schema:
                client = self.get_client()
                schema = client.get_openapi_schema()
                cache.save(self.config.openbao.address, schema)
            menu.clear()
            paths = schema.get("paths", {})
            categories = {}
            for path, methods in paths.items():
                parts = path.strip("/").split("/")
                category = parts[1] if len(parts) > 1 else "root"
                if category not in categories:
                    categories[category] = {}
                categories[category][path] = methods
            for category in sorted(categories.keys()):
                cat_menu = menu.addMenu(f"📂 {category}")
                self.build_category_menu(cat_menu, categories[category])
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def build_category_menu(self, menu: QMenu, paths: Dict):
        tree = {}
        for path, methods in paths.items():
            parts = path.strip("/").split("/")[2:]
            current = tree
            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {"__methods__": None, "__children__": {}}
                if i == len(parts) - 1:
                    current[part]["__methods__"] = methods
                current = current[part]["__children__"]
        
        def build_tree_menu(parent_menu: QMenu, tree_node: Dict, current_path: str):
            for name, node in sorted(tree_node.items()):
                full_path = f"{current_path}/{name}"
                if node["__children__"]:
                    submenu = parent_menu.addMenu(f"📁 {name}")
                    if node["__methods__"]:
                        method_names = [m.upper() for m in node["__methods__"].keys() if m != "parameters"]
                        action = submenu.addAction(f"🔗 [{', '.join(method_names)}]")
                        action.triggered.connect(lambda checked, p=full_path, m=node["__methods__"]: self.show_endpoint_dialog(p, m))
                        submenu.addSeparator()
                    build_tree_menu(submenu, node["__children__"], full_path)
                elif node["__methods__"]:
                    method_names = [m.upper() for m in node["__methods__"].keys() if m != "parameters"]
                    action = parent_menu.addAction(f"🔗 {name} [{', '.join(method_names)}]")
                    action.triggered.connect(lambda checked, p=full_path, m=node["__methods__"]: self.show_endpoint_dialog(p, m))
        
        base_path = list(paths.keys())[0].rsplit("/", 1)[0] if paths else ""
        build_tree_menu(menu, tree, base_path)
    
    def populate_leases_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            leases = client.list_leases()
            menu.clear()
            for lease in sorted(leases):
                if lease.endswith("/"):
                    lease_menu = menu.addMenu(f"📁 {lease}")
                    lease_menu.aboutToShow.connect(lambda m=lease_menu, p=lease: self.populate_lease_submenu(m, p))
                else:
                    lease_action = menu.addAction(f"📄 {lease}")
                    lease_action.triggered.connect(lambda checked, l=lease: self.show_lease_details(l))
            if not leases:
                empty_action = menu.addAction("No leases found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_lease_submenu(self, menu: QMenu, prefix: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            leases = client.list_leases(prefix)
            menu.clear()
            for lease in sorted(leases):
                if lease.endswith("/"):
                    lease_menu = menu.addMenu(f"📁 {lease}")
                    lease_menu.aboutToShow.connect(lambda m=lease_menu, p=f"{prefix}{lease}": self.populate_lease_submenu(m, p))
                else:
                    lease_action = menu.addAction(f"📄 {lease}")
                    lease_action.triggered.connect(lambda checked, l=f"{prefix}{lease}": self.show_lease_details(l))
            if not leases:
                empty_action = menu.addAction("(empty)")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_transit_menu(self, menu: QMenu):
        menu.clear()
        encrypt_action = menu.addAction("🔒 Encrypt")
        decrypt_action = menu.addAction("🔓 Decrypt")
        keys_menu = menu.addMenu("🔑 Keys")
    
    def show_status(self):
        try:
            client = self.get_client()
            health = client.get_health()
            dialog = JsonTableDialog("🔐 OpenBao Status", health, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get status: {e}")
    
    def show_seal_status(self):
        try:
            client = self.get_client()
            status = client.get_seal_status()
            dialog = JsonTableDialog("🔒 Seal Status", status, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get seal status: {e}")
    
    def show_token_info(self):
        try:
            client = self.get_client()
            info = client.lookup_self()
            dialog = JsonTableDialog("🎫 Token Info", info.get("data", info), readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get token info: {e}")
    
    def view_secret(self, path: str):
        try:
            client = self.get_client()
            data = client.read_secret(path)
            dialog = ViewSecretDialog(path, data)
            dialog.secret_updated.connect(lambda p, d: self.save_secret(p, d))
            dialog.secret_deleted.connect(lambda p: self.delete_secret(p))
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to read secret: {e}")
    
    def save_secret(self, path: str, data: Dict):
        try:
            client = self.get_client()
            client.write_secret(path, data)
            QMessageBox.information(None, "Success", "Secret saved successfully")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to save secret: {e}")
    
    def delete_secret(self, path: str):
        try:
            client = self.get_client()
            client.delete_secret(path)
            QMessageBox.information(None, "Success", "Secret deleted successfully")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to delete secret: {e}")
    
    def create_new_secret(self, mount_path: str, mount_type: str, prefix: str = ""):
        dialog = NewSecretDialog(f"{mount_path}{prefix}")
        if dialog.exec():
            path = dialog.get_path()
            data = dialog.get_data()
            if mount_type == "kv-v2" and "/data/" not in path:
                parts = path.split("/", 1)
                if len(parts) > 1:
                    path = f"{parts[0]}/data/{parts[1]}"
            self.save_secret(path, data)
    
    def view_policy(self, name: str):
        try:
            client = self.get_client()
            policy_data = client.read_policy(name)
            dialog = CrudDialog(f"📜 Policy: {name}", policy_data.get("data", policy_data), is_new=False)
            dialog.saved.connect(lambda d: self.save_policy(name, d.get("policy", "")))
            dialog.deleted.connect(lambda: self.delete_policy_action(name))
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to read policy: {e}")
    
    def create_new_policy(self):
        dialog = CrudDialog("📜 New Policy", {"name": "", "policy": ""}, is_new=True)
        dialog.saved.connect(lambda d: self.save_policy(d.get("name", ""), d.get("policy", "")))
        dialog.exec()
    
    def save_policy(self, name: str, policy: str):
        try:
            client = self.get_client()
            client.write_policy(name, policy)
            QMessageBox.information(None, "Success", "Policy saved successfully")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to save policy: {e}")
    
    def delete_policy_action(self, name: str):
        try:
            client = self.get_client()
            client.delete_policy(name)
            QMessageBox.information(None, "Success", "Policy deleted successfully")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to delete policy: {e}")
    
    def show_auth_details(self, path: str, info: Dict):
        dialog = JsonTableDialog(f"🔑 Auth: {path}", info, readonly=True)
        dialog.exec()
    
    def show_audit_devices(self):
        try:
            client = self.get_client()
            result = client.get("/v1/sys/audit")
            dialog = JsonTableDialog("📝 Audit Devices", result.get("data", result), readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get audit devices: {e}")
    
    def show_lease_details(self, lease_id: str):
        try:
            client = self.get_client()
            result = client.put("/v1/sys/leases/lookup", {"lease_id": lease_id})
            dialog = JsonTableDialog(f"📄 Lease: {lease_id}", result.get("data", result), readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get lease details: {e}")
    
    def show_endpoint_dialog(self, path: str, methods: Dict):
        info = {"path": path}
        for method, details in methods.items():
            if method != "parameters":
                info[f"{method.upper()}_summary"] = details.get("summary", "")
        dialog = JsonTableDialog(f"🔗 {path}", info, readonly=True)
        dialog.exec()
    
    def generate_random(self):
        try:
            client = self.get_client()
            result = client.post("/v1/sys/tools/random", {"bytes": 32, "format": "base64"})
            data = result.get("data", result)
            dialog = JsonTableDialog("🎲 Random Data", data, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to generate random: {e}")
    
    def hash_data(self):
        text, ok = QInputDialog.getText(None, "Hash Data", "Enter text to hash:")
        if ok and text:
            try:
                client = self.get_client()
                result = client.post("/v1/sys/tools/hash", {"input": text})
                data = result.get("data", result)
                dialog = JsonTableDialog("#️⃣ Hash Result", data, readonly=True)
                dialog.exec()
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to hash: {e}")
    
    def refresh_schema(self):
        try:
            cache = self.get_schema_cache()
            cache.clear(self.config.openbao.address)
            client = self.get_client()
            schema = client.get_openapi_schema()
            cache.save(self.config.openbao.address, schema)
            QMessageBox.information(None, "Success", "Schema refreshed successfully")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to refresh schema: {e}")
