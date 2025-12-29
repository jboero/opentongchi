"""Consul client and menu handling"""

import base64
from typing import Dict, List, Optional, Any

from PyQt6.QtWidgets import QMenu, QMessageBox
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt, QObject, pyqtSignal

from .http_client import ConsulClient, ApiError
from .dialogs import JsonTableDialog, CrudDialog, KeyValueTableWidget


class ConsulApiClient(ConsulClient):
    """Extended Consul API client"""
    
    def get_leader(self) -> str:
        """Get cluster leader"""
        return self.get("/v1/status/leader")
    
    def get_peers(self) -> List[str]:
        """Get cluster peers"""
        return self.get("/v1/status/peers")
    
    def list_services(self) -> Dict:
        """List all services"""
        return self.get("/v1/catalog/services")
    
    def get_service(self, name: str) -> List[Dict]:
        """Get service instances"""
        return self.get(f"/v1/catalog/service/{name}")
    
    def get_service_health(self, name: str) -> List[Dict]:
        """Get service health"""
        return self.get(f"/v1/health/service/{name}")
    
    def list_nodes(self) -> List[Dict]:
        """List all nodes"""
        return self.get("/v1/catalog/nodes")
    
    def get_node(self, name: str) -> Dict:
        """Get node details"""
        return self.get(f"/v1/catalog/node/{name}")
    
    def list_kv(self, prefix: str = "") -> List[str]:
        """List KV keys"""
        try:
            params = {"keys": "true"}
            result = self.get(f"/v1/kv/{prefix}", params=params)
            return result if isinstance(result, list) else []
        except ApiError as e:
            if e.status_code == 404:
                return []
            raise
    
    def get_kv(self, key: str) -> Optional[Dict]:
        """Get KV value"""
        try:
            result = self.get(f"/v1/kv/{key}")
            if result and isinstance(result, list) and len(result) > 0:
                item = result[0]
                # Decode base64 value
                if "Value" in item and item["Value"]:
                    item["DecodedValue"] = base64.b64decode(item["Value"]).decode("utf-8")
                return item
            return None
        except ApiError as e:
            if e.status_code == 404:
                return None
            raise
    
    def put_kv(self, key: str, value: str) -> bool:
        """Put KV value"""
        result = self.request("PUT", f"/v1/kv/{key}", data=None, 
                             headers={"Content-Type": "text/plain"})
        return result
    
    def delete_kv(self, key: str) -> bool:
        """Delete KV value"""
        self.delete(f"/v1/kv/{key}")
        return True
    
    def list_datacenters(self) -> List[str]:
        """List datacenters"""
        return self.get("/v1/catalog/datacenters")
    
    def list_namespaces(self) -> List[Dict]:
        """List namespaces (Enterprise only)"""
        try:
            return self.get("/v1/namespaces")
        except ApiError:
            return []
    
    def get_agent_self(self) -> Dict:
        """Get local agent info"""
        return self.get("/v1/agent/self")
    
    def list_agent_checks(self) -> Dict:
        """List local agent checks"""
        return self.get("/v1/agent/checks")
    
    def list_agent_services(self) -> Dict:
        """List local agent services"""
        return self.get("/v1/agent/services")


class ConsulMenuBuilder(QObject):
    """Builds dynamic menus for Consul"""
    
    status_changed = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.client: Optional[ConsulApiClient] = None
        self._loading_menus: set = set()
    
    def get_client(self) -> ConsulApiClient:
        if self.client is None or self.client.base_url != self.config.consul.address:
            self.client = ConsulApiClient(
                self.config.consul.address,
                self.config.consul.token,
                self.config.consul.namespace,
                self.config.consul.skip_verify
            )
        else:
            self.client.token = self.config.consul.token
            self.client.namespace = self.config.consul.namespace
        return self.client
    
    def get_status_emoji(self) -> str:
        """Get status emoji based on cluster health"""
        try:
            client = self.get_client()
            leader = client.get_leader()
            if leader:
                return "🟢"
            return "🔴"
        except Exception:
            return "⚪"
    
    def get_service_status_emoji(self, health_checks: List[Dict]) -> str:
        """Get status emoji for a service"""
        if not health_checks:
            return "⚪"
        
        statuses = set()
        for check in health_checks:
            for c in check.get("Checks", []):
                statuses.add(c.get("Status", "unknown"))
        
        if "critical" in statuses:
            return "🔴"
        if "warning" in statuses:
            return "🟡"
        if "passing" in statuses:
            return "🟢"
        return "⚪"
    
    def build_menu(self, parent_menu: QMenu) -> QMenu:
        menu = parent_menu.addMenu("🔍 Consul")
        
        status = self.get_status_emoji()
        status_action = menu.addAction(f"{status} Status")
        status_action.triggered.connect(self.show_status)
        
        menu.addSeparator()
        
        # Services
        services_menu = menu.addMenu("🌐 Services")
        services_menu.aboutToShow.connect(lambda: self.populate_services_menu(services_menu))
        
        # Nodes
        nodes_menu = menu.addMenu("🖥️ Nodes")
        nodes_menu.aboutToShow.connect(lambda: self.populate_nodes_menu(nodes_menu))
        
        # KV Store
        kv_menu = menu.addMenu("📦 KV Store")
        kv_menu.aboutToShow.connect(lambda: self.populate_kv_menu(kv_menu))
        
        menu.addSeparator()
        
        # Agent
        agent_menu = menu.addMenu("🤖 Agent")
        self.build_agent_menu(agent_menu)
        
        # Datacenters
        dc_menu = menu.addMenu("🏢 Datacenters")
        dc_menu.aboutToShow.connect(lambda: self.populate_dc_menu(dc_menu))
        
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
    
    def populate_services_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            services = client.list_services()
            menu.clear()
            
            for service_name, tags in sorted(services.items()):
                # Get health for status emoji
                try:
                    health = client.get_service_health(service_name)
                    emoji = self.get_service_status_emoji(health)
                except Exception:
                    emoji = "⚪"
                
                service_menu = menu.addMenu(f"{emoji} {service_name}")
                service_menu.aboutToShow.connect(
                    lambda m=service_menu, n=service_name: self.populate_service_details_menu(m, n)
                )
            
            if not services:
                empty_action = menu.addAction("No services found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_service_details_menu(self, menu: QMenu, service_name: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            instances = client.get_service(service_name)
            health = client.get_service_health(service_name)
            menu.clear()
            
            # Health overview action
            health_action = menu.addAction("📊 Health Overview")
            health_action.triggered.connect(lambda: self.show_service_health(service_name, health))
            menu.addSeparator()
            
            # List instances
            for instance in instances:
                node = instance.get("Node", "unknown")
                address = instance.get("Address", "")
                port = instance.get("ServicePort", "")
                
                instance_action = menu.addAction(f"🖥️ {node} ({address}:{port})")
                instance_action.triggered.connect(
                    lambda checked, i=instance: self.show_instance_details(i)
                )
            
            if not instances:
                empty_action = menu.addAction("No instances")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_nodes_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            nodes = client.list_nodes()
            menu.clear()
            
            for node in sorted(nodes, key=lambda x: x.get("Node", "")):
                node_name = node.get("Node", "unknown")
                address = node.get("Address", "")
                node_action = menu.addAction(f"🖥️ {node_name} ({address})")
                node_action.triggered.connect(
                    lambda checked, n=node_name: self.show_node_details(n)
                )
            
            if not nodes:
                empty_action = menu.addAction("No nodes found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_kv_menu(self, menu: QMenu, prefix: str = ""):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            keys = client.list_kv(prefix)
            menu.clear()
            
            # Add "New..." action
            new_action = menu.addAction("➕ New Key...")
            new_action.triggered.connect(lambda: self.create_new_kv(prefix))
            menu.addSeparator()
            
            # Build tree structure
            tree = {}
            prefix_len = len(prefix)
            
            for key in keys:
                # Get relative path
                rel_key = key[prefix_len:] if key.startswith(prefix) else key
                parts = rel_key.strip("/").split("/")
                
                if len(parts) == 1 and parts[0]:
                    # Leaf node
                    tree[parts[0]] = {"__is_leaf__": True, "__full_key__": key}
                elif len(parts) > 1:
                    # Directory
                    dir_name = parts[0] + "/"
                    if dir_name not in tree:
                        tree[dir_name] = {"__is_leaf__": False, "__full_key__": prefix + dir_name}
            
            for name, info in sorted(tree.items()):
                if info["__is_leaf__"]:
                    key_action = menu.addAction(f"🔑 {name}")
                    key_action.triggered.connect(
                        lambda checked, k=info["__full_key__"]: self.view_kv(k)
                    )
                else:
                    dir_menu = menu.addMenu(f"📁 {name}")
                    dir_menu.aboutToShow.connect(
                        lambda m=dir_menu, p=info["__full_key__"]: self.populate_kv_menu(m, p)
                    )
            
            if not keys:
                empty_action = menu.addAction("(empty)")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def build_agent_menu(self, menu: QMenu):
        self_action = menu.addAction("ℹ️ Agent Info")
        self_action.triggered.connect(self.show_agent_info)
        
        checks_action = menu.addAction("✅ Checks")
        checks_action.triggered.connect(self.show_agent_checks)
        
        services_action = menu.addAction("🌐 Services")
        services_action.triggered.connect(self.show_agent_services)
    
    def populate_dc_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            dcs = client.list_datacenters()
            menu.clear()
            
            for dc in sorted(dcs):
                dc_action = menu.addAction(f"🏢 {dc}")
                # Could add actions to switch datacenter
            
            if not dcs:
                empty_action = menu.addAction("No datacenters found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def show_status(self):
        try:
            client = self.get_client()
            leader = client.get_leader()
            peers = client.get_peers()
            
            status = {
                "Leader": leader,
                "Peers": peers,
                "Peer Count": len(peers) if peers else 0
            }
            
            dialog = JsonTableDialog("🔍 Consul Status", status, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get status: {e}")
    
    def show_service_health(self, name: str, health: List[Dict]):
        """Show service health details"""
        health_data = {}
        for i, h in enumerate(health):
            node = h.get("Node", {}).get("Node", f"instance_{i}")
            checks = h.get("Checks", [])
            for check in checks:
                check_name = check.get("Name", "unknown")
                health_data[f"{node}/{check_name}"] = check.get("Status", "unknown")
        
        dialog = JsonTableDialog(f"📊 {name} Health", health_data, readonly=True)
        dialog.exec()
    
    def show_instance_details(self, instance: Dict):
        dialog = JsonTableDialog("🖥️ Instance Details", instance, readonly=True)
        dialog.exec()
    
    def show_node_details(self, node_name: str):
        try:
            client = self.get_client()
            node = client.get_node(node_name)
            dialog = JsonTableDialog(f"🖥️ Node: {node_name}", node, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get node: {e}")
    
    def view_kv(self, key: str):
        try:
            client = self.get_client()
            kv = client.get_kv(key)
            
            if kv:
                # Show the decoded value prominently
                display_data = {
                    "Key": key,
                    "Value": kv.get("DecodedValue", kv.get("Value", "")),
                    "CreateIndex": kv.get("CreateIndex"),
                    "ModifyIndex": kv.get("ModifyIndex"),
                    "Flags": kv.get("Flags", 0)
                }
                
                dialog = CrudDialog(f"🔑 {key}", display_data, is_new=False)
                dialog.saved.connect(lambda d: self.save_kv(key, d.get("Value", "")))
                dialog.deleted.connect(lambda: self.delete_kv(key))
                dialog.exec()
            else:
                QMessageBox.information(None, "Not Found", f"Key '{key}' not found")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get KV: {e}")
    
    def save_kv(self, key: str, value: str):
        try:
            client = self.get_client()
            # Use raw PUT request for KV
            import json
            from urllib.request import Request, urlopen
            
            url = f"{client.base_url}/v1/kv/{key}"
            headers = {"X-Consul-Token": client.token} if client.token else {}
            if client.namespace:
                headers["X-Consul-Namespace"] = client.namespace
            
            req = Request(url, data=value.encode(), headers=headers, method="PUT")
            urlopen(req)
            
            QMessageBox.information(None, "Success", "KV saved successfully")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to save KV: {e}")
    
    def delete_kv(self, key: str):
        try:
            client = self.get_client()
            client.delete_kv(key)
            QMessageBox.information(None, "Success", "KV deleted successfully")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to delete KV: {e}")
    
    def create_new_kv(self, prefix: str = ""):
        from PyQt6.QtWidgets import QInputDialog
        
        key, ok = QInputDialog.getText(None, "New Key", "Enter key name:", text=prefix)
        if ok and key:
            value, ok = QInputDialog.getMultiLineText(None, "New Key", "Enter value:")
            if ok:
                self.save_kv(key, value)
    
    def show_agent_info(self):
        try:
            client = self.get_client()
            info = client.get_agent_self()
            dialog = JsonTableDialog("🤖 Agent Info", info, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get agent info: {e}")
    
    def show_agent_checks(self):
        try:
            client = self.get_client()
            checks = client.list_agent_checks()
            dialog = JsonTableDialog("✅ Agent Checks", checks, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get checks: {e}")
    
    def show_agent_services(self):
        try:
            client = self.get_client()
            services = client.list_agent_services()
            dialog = JsonTableDialog("🌐 Agent Services", services, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get services: {e}")
