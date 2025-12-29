"""OpenTofu/Terraform client and menu handling"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from PyQt6.QtWidgets import QMenu, QMessageBox
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt, QObject, pyqtSignal

from .http_client import TerraformCloudClient, ApiError
from .dialogs import JsonTableDialog


class HCPTerraformClient(TerraformCloudClient):
    """Extended HCP Terraform / Terraform Cloud API client"""
    
    def list_organizations(self) -> List[Dict]:
        result = self.get("/api/v2/organizations")
        return result.get("data", [])
    
    def get_organization(self, org_name: str) -> Dict:
        result = self.get(f"/api/v2/organizations/{org_name}")
        return result.get("data", {})
    
    def list_workspaces(self, org_name: str) -> List[Dict]:
        result = self.get(f"/api/v2/organizations/{org_name}/workspaces")
        return result.get("data", [])
    
    def get_workspace(self, workspace_id: str) -> Dict:
        result = self.get(f"/api/v2/workspaces/{workspace_id}")
        return result.get("data", {})
    
    def list_runs(self, workspace_id: str) -> List[Dict]:
        result = self.get(f"/api/v2/workspaces/{workspace_id}/runs")
        return result.get("data", [])
    
    def list_state_versions(self, workspace_id: str) -> List[Dict]:
        result = self.get(f"/api/v2/workspaces/{workspace_id}/state-versions")
        return result.get("data", [])
    
    def list_variables(self, workspace_id: str) -> List[Dict]:
        result = self.get(f"/api/v2/workspaces/{workspace_id}/vars")
        return result.get("data", [])


class LocalWorkspaceScanner:
    """Scans local directories for OpenTofu/Terraform workspaces"""
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
    
    def find_workspaces(self) -> List[Dict]:
        workspaces = []
        if not self.base_dir.exists():
            return workspaces
        for item in self.base_dir.iterdir():
            if item.is_dir() and self.is_workspace(item):
                workspaces.append(self.get_workspace_info(item))
        return workspaces
    
    def is_workspace(self, directory: Path) -> bool:
        tf_files = list(directory.glob("*.tf")) + list(directory.glob("*.tofu"))
        return len(tf_files) > 0
    
    def get_workspace_info(self, directory: Path) -> Dict:
        info = {
            "name": directory.name,
            "path": str(directory),
            "has_state": False,
            "state_backend": "local",
            "status": "unknown",
            "initialized": (directory / ".terraform").exists(),
        }
        state_file = directory / "terraform.tfstate"
        if state_file.exists():
            info["has_state"] = True
            try:
                with open(state_file, "r") as f:
                    state = json.load(f)
                    info["terraform_version"] = state.get("terraform_version")
                    info["serial"] = state.get("serial", 0)
                    info["resource_count"] = len(state.get("resources", []))
            except Exception:
                pass
        for tf_file in directory.glob("*.tf"):
            try:
                content = tf_file.read_text()
                if "backend" in content:
                    for backend in ["s3", "gcs", "azurerm", "consul", "remote"]:
                        if backend in content:
                            info["state_backend"] = backend
                            break
            except Exception:
                pass
        if info["initialized"]:
            info["status"] = "ok" if info["has_state"] else "no_state"
        else:
            info["status"] = "not_initialized"
        return info
    
    def get_workspace_state(self, workspace_path: str) -> Optional[Dict]:
        state_file = Path(workspace_path) / "terraform.tfstate"
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return None
    
    def get_workspace_resources(self, workspace_path: str) -> List[Dict]:
        state = self.get_workspace_state(workspace_path)
        return state.get("resources", []) if state else []


class OpenTofuMenuBuilder(QObject):
    """Builds dynamic menus for OpenTofu"""
    
    status_changed = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.hcp_client: Optional[HCPTerraformClient] = None
        self.local_scanner: Optional[LocalWorkspaceScanner] = None
        self._loading_menus: set = set()
    
    def get_hcp_client(self) -> HCPTerraformClient:
        if self.hcp_client is None:
            self.hcp_client = HCPTerraformClient(
                self.config.opentofu.hcp_token,
                self.config.opentofu.hcp_organization
            )
        else:
            self.hcp_client.token = self.config.opentofu.hcp_token
        return self.hcp_client
    
    def get_local_scanner(self) -> LocalWorkspaceScanner:
        if self.local_scanner is None:
            self.local_scanner = LocalWorkspaceScanner(self.config.opentofu.local_directory)
        else:
            self.local_scanner.base_dir = Path(self.config.opentofu.local_directory)
        return self.local_scanner
    
    def get_status_emoji(self, status: str) -> str:
        emojis = {
            "ok": "🟢", "no_state": "🟡", "not_initialized": "⚪", "error": "🔴",
            "applied": "🟢", "planned": "🔵", "planning": "🟡", "applying": "🟡",
            "errored": "🔴", "canceled": "⚫", "pending": "🟡",
        }
        return emojis.get(status.lower(), "⚪")
    
    def build_menu(self, parent_menu: QMenu) -> QMenu:
        menu = parent_menu.addMenu("🏗️ OpenTofu")
        
        local_menu = menu.addMenu("📁 Local Workspaces")
        local_menu.aboutToShow.connect(lambda: self.populate_local_menu(local_menu))
        
        hcp_menu = menu.addMenu("☁️ HCP Terraform")
        hcp_menu.aboutToShow.connect(lambda: self.populate_hcp_menu(hcp_menu))
        
        return menu
    
    def set_menu_loading(self, menu: QMenu, loading: bool):
        menu_id = id(menu)
        if loading:
            self._loading_menus.add(menu_id)
            menu.setCursor(QCursor(Qt.CursorShape.WaitCursor))
            if menu.isEmpty():
                action = menu.addAction("⏳ Loading...")
                action.setEnabled(False)
        else:
            self._loading_menus.discard(menu_id)
            menu.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
    
    def populate_local_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            scanner = self.get_local_scanner()
            workspaces = scanner.find_workspaces()
            menu.clear()
            
            base_dir = self.config.opentofu.local_directory
            dir_action = menu.addAction(f"📂 {base_dir}")
            dir_action.setEnabled(False)
            menu.addSeparator()
            
            for ws in sorted(workspaces, key=lambda x: x.get("name", "")):
                emoji = self.get_status_emoji(ws.get("status", ""))
                ws_menu = menu.addMenu(f"{emoji} {ws.get('name', 'unknown')}")
                ws_menu.aboutToShow.connect(
                    lambda m=ws_menu, w=ws: self.populate_local_ws_menu(m, w)
                )
            
            if not workspaces:
                empty = menu.addAction("No workspaces found")
                empty.setEnabled(False)
        except Exception as e:
            menu.clear()
            err = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            err.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_local_ws_menu(self, menu: QMenu, ws: Dict):
        menu.clear()
        
        info = menu.addAction(f"ℹ️ Status: {ws.get('status', 'unknown')}")
        info.setEnabled(False)
        
        backend = menu.addAction(f"💾 Backend: {ws.get('state_backend', 'local')}")
        backend.setEnabled(False)
        
        init = menu.addAction(f"🔧 Initialized: {'Yes' if ws.get('initialized') else 'No'}")
        init.setEnabled(False)
        
        if ws.get("terraform_version"):
            ver = menu.addAction(f"📦 Version: {ws['terraform_version']}")
            ver.setEnabled(False)
        
        if ws.get("resource_count") is not None:
            res = menu.addAction(f"🗂️ Resources: {ws['resource_count']}")
            res.setEnabled(False)
        
        menu.addSeparator()
        
        if ws.get("has_state"):
            state_action = menu.addAction("📄 View State")
            state_action.triggered.connect(lambda: self.view_local_state(ws.get("path", "")))
            
            res_action = menu.addAction("🗂️ View Resources")
            res_action.triggered.connect(lambda: self.view_local_resources(ws.get("path", "")))
        
        path = menu.addAction(f"📁 {ws.get('path', '')}")
        path.setEnabled(False)
    
    def populate_hcp_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_hcp_client()
            if not client.token:
                menu.clear()
                no_token = menu.addAction("⚠️ No HCP token configured")
                no_token.setEnabled(False)
                return
            
            orgs = client.list_organizations()
            menu.clear()
            
            for org in sorted(orgs, key=lambda x: x.get("attributes", {}).get("name", "")):
                org_name = org.get("attributes", {}).get("name", "unknown")
                org_menu = menu.addMenu(f"🏢 {org_name}")
                org_menu.aboutToShow.connect(
                    lambda m=org_menu, o=org_name: self.populate_org_menu(m, o)
                )
            
            if not orgs:
                empty = menu.addAction("No organizations found")
                empty.setEnabled(False)
        except Exception as e:
            menu.clear()
            err = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            err.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_org_menu(self, menu: QMenu, org_name: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_hcp_client()
            workspaces = client.list_workspaces(org_name)
            menu.clear()
            
            for ws in sorted(workspaces, key=lambda x: x.get("attributes", {}).get("name", "")):
                ws_id = ws.get("id", "")
                attrs = ws.get("attributes", {})
                ws_name = attrs.get("name", "unknown")
                latest_run = attrs.get("latest-run", {})
                run_status = latest_run.get("status", "no_runs") if latest_run else "no_runs"
                emoji = self.get_status_emoji(run_status)
                
                ws_menu = menu.addMenu(f"{emoji} {ws_name}")
                ws_menu.aboutToShow.connect(
                    lambda m=ws_menu, w=ws_id, n=ws_name, o=org_name: 
                    self.populate_ws_menu(m, w, n, o)
                )
            
            if not workspaces:
                empty = menu.addAction("No workspaces found")
                empty.setEnabled(False)
        except Exception as e:
            menu.clear()
            err = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            err.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_ws_menu(self, menu: QMenu, ws_id: str, ws_name: str, org_name: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_hcp_client()
            workspace = client.get_workspace(ws_id)
            menu.clear()
            
            attrs = workspace.get("attributes", {})
            
            ver = menu.addAction(f"📦 Terraform: {attrs.get('terraform-version', 'unknown')}")
            ver.setEnabled(False)
            
            auto = menu.addAction(f"🔄 Auto-apply: {'Yes' if attrs.get('auto-apply') else 'No'}")
            auto.setEnabled(False)
            
            lock = menu.addAction(f"🔒 Locked: {'Yes' if attrs.get('locked') else 'No'}")
            lock.setEnabled(False)
            
            menu.addSeparator()
            
            runs_menu = menu.addMenu("🏃 Runs")
            runs_menu.aboutToShow.connect(lambda m=runs_menu, w=ws_id: self.populate_runs_menu(m, w))
            
            vars_menu = menu.addMenu("📝 Variables")
            vars_menu.aboutToShow.connect(lambda m=vars_menu, w=ws_id: self.populate_vars_menu(m, w))
            
            menu.addSeparator()
            
            details = menu.addAction("👁️ View Details")
            details.triggered.connect(lambda: self.view_ws_details(workspace))
        except Exception as e:
            menu.clear()
            err = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            err.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_runs_menu(self, menu: QMenu, ws_id: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_hcp_client()
            runs = client.list_runs(ws_id)
            menu.clear()
            
            for run in runs[:20]:
                run_id = run.get("id", "unknown")
                attrs = run.get("attributes", {})
                status = attrs.get("status", "unknown")
                emoji = self.get_status_emoji(status)
                
                action = menu.addAction(f"{emoji} {run_id[:8]} ({status})")
                action.triggered.connect(lambda checked, r=run: self.view_run(r))
            
            if not runs:
                empty = menu.addAction("No runs found")
                empty.setEnabled(False)
        except Exception as e:
            menu.clear()
            err = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            err.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_vars_menu(self, menu: QMenu, ws_id: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_hcp_client()
            variables = client.list_variables(ws_id)
            menu.clear()
            
            for var in sorted(variables, key=lambda x: x.get("attributes", {}).get("key", "")):
                attrs = var.get("attributes", {})
                key = attrs.get("key", "unknown")
                sensitive = attrs.get("sensitive", False)
                category = attrs.get("category", "terraform")
                
                emoji = "🔐" if sensitive else "📝"
                cat_emoji = "🌍" if category == "env" else "📦"
                
                action = menu.addAction(f"{emoji} {cat_emoji} {key}")
                action.triggered.connect(lambda checked, v=var: self.view_var(v))
            
            if not variables:
                empty = menu.addAction("No variables found")
                empty.setEnabled(False)
        except Exception as e:
            menu.clear()
            err = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            err.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def view_local_state(self, path: str):
        scanner = self.get_local_scanner()
        state = scanner.get_workspace_state(path)
        if state:
            summary = {
                "terraform_version": state.get("terraform_version"),
                "serial": state.get("serial"),
                "lineage": state.get("lineage"),
                "resource_count": len(state.get("resources", [])),
            }
            dialog = JsonTableDialog(f"📄 State: {Path(path).name}", summary, readonly=True)
            dialog.exec()
        else:
            QMessageBox.information(None, "No State", "No state file found")
    
    def view_local_resources(self, path: str):
        scanner = self.get_local_scanner()
        resources = scanner.get_workspace_resources(path)
        if resources:
            summary = {}
            for res in resources:
                key = f"{res.get('type', 'unknown')}.{res.get('name', 'unknown')}"
                summary[key] = {
                    "mode": res.get("mode", "managed"),
                    "provider": res.get("provider", ""),
                    "instances": len(res.get("instances", [])),
                }
            dialog = JsonTableDialog(f"🗂️ Resources: {Path(path).name}", summary, readonly=True)
            dialog.exec()
        else:
            QMessageBox.information(None, "No Resources", "No resources found")
    
    def view_ws_details(self, workspace: Dict):
        dialog = JsonTableDialog("🏗️ Workspace Details", workspace, readonly=True)
        dialog.exec()
    
    def view_run(self, run: Dict):
        dialog = JsonTableDialog("🏃 Run Details", run, readonly=True)
        dialog.exec()
    
    def view_var(self, var: Dict):
        attrs = var.get("attributes", {})
        display = {
            "key": attrs.get("key"),
            "category": attrs.get("category"),
            "sensitive": attrs.get("sensitive"),
            "hcl": attrs.get("hcl"),
            "description": attrs.get("description"),
            "value": attrs.get("value") if not attrs.get("sensitive") else "********",
        }
        dialog = JsonTableDialog("📝 Variable", display, readonly=True)
        dialog.exec()
