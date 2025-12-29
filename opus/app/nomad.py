"""Nomad client and menu handling"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from PyQt6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer

from .http_client import NomadClient, ApiError
from .dialogs import JsonTableDialog, JobDialog


class NomadApiClient(NomadClient):
    """Extended Nomad API client"""
    
    def get_agent_self(self) -> Dict:
        """Get agent info"""
        return self.get("/v1/agent/self")
    
    def list_jobs(self) -> List[Dict]:
        """List all jobs"""
        return self.get("/v1/jobs")
    
    def get_job(self, job_id: str) -> Dict:
        """Get job details"""
        return self.get(f"/v1/job/{job_id}")
    
    def submit_job(self, job_spec: Dict) -> Dict:
        """Submit a job"""
        return self.post("/v1/jobs", {"Job": job_spec})
    
    def stop_job(self, job_id: str, purge: bool = False) -> Dict:
        """Stop a job"""
        params = {"purge": "true"} if purge else {}
        return self.delete(f"/v1/job/{job_id}", params=params)
    
    def list_allocations(self, job_id: Optional[str] = None) -> List[Dict]:
        """List allocations"""
        if job_id:
            return self.get(f"/v1/job/{job_id}/allocations")
        return self.get("/v1/allocations")
    
    def get_allocation(self, alloc_id: str) -> Dict:
        """Get allocation details"""
        return self.get(f"/v1/allocation/{alloc_id}")
    
    def list_nodes(self) -> List[Dict]:
        """List all nodes"""
        return self.get("/v1/nodes")
    
    def get_node(self, node_id: str) -> Dict:
        """Get node details"""
        return self.get(f"/v1/node/{node_id}")
    
    def list_deployments(self) -> List[Dict]:
        """List deployments"""
        return self.get("/v1/deployments")
    
    def get_deployment(self, deployment_id: str) -> Dict:
        """Get deployment details"""
        return self.get(f"/v1/deployment/{deployment_id}")
    
    def list_namespaces(self) -> List[Dict]:
        """List namespaces"""
        try:
            return self.get("/v1/namespaces")
        except ApiError:
            return []
    
    def list_evaluations(self) -> List[Dict]:
        """List evaluations"""
        return self.get("/v1/evaluations")
    
    def get_leader(self) -> str:
        """Get cluster leader"""
        return self.get("/v1/status/leader")
    
    def get_peers(self) -> List[str]:
        """Get cluster peers"""
        return self.get("/v1/status/peers")


class NomadMenuBuilder(QObject):
    """Builds dynamic menus for Nomad"""
    
    status_changed = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    alert = pyqtSignal(str, str)  # title, message
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.client: Optional[NomadApiClient] = None
        self._loading_menus: set = set()
        self._previous_jobs: Dict[str, str] = {}  # job_id -> status
        self._refresh_timer: Optional[QTimer] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
    
    def get_client(self) -> NomadApiClient:
        if self.client is None or self.client.base_url != self.config.nomad.address:
            self.client = NomadApiClient(
                self.config.nomad.address,
                self.config.nomad.token,
                self.config.nomad.namespace,
                self.config.nomad.skip_verify,
                region=self.config.nomad.region
            )
        else:
            self.client.token = self.config.nomad.token
            self.client.namespace = self.config.nomad.namespace
            self.client.region = self.config.nomad.region
        return self.client
    
    def start_refresh_timer(self):
        """Start the automatic refresh timer"""
        if self._refresh_timer is None:
            self._refresh_timer = QTimer()
            self._refresh_timer.timeout.connect(self.check_job_changes)
        
        interval = self.config.nomad.refresh_interval * 1000
        self._refresh_timer.start(interval)
    
    def stop_refresh_timer(self):
        """Stop the automatic refresh timer"""
        if self._refresh_timer:
            self._refresh_timer.stop()
    
    def check_job_changes(self):
        """Check for job status changes and emit alerts"""
        if not self.config.nomad.alerts_enabled:
            return
        
        try:
            client = self.get_client()
            jobs = client.list_jobs()
            
            for job in jobs:
                job_id = job.get("ID", "")
                status = job.get("Status", "")
                
                if job_id in self._previous_jobs:
                    prev_status = self._previous_jobs[job_id]
                    if prev_status != status:
                        # Status changed
                        if status == "dead":
                            self.emit_alert(f"Job Failed: {job_id}", 
                                          f"Job {job_id} status changed from {prev_status} to {status}")
                        elif status == "running" and prev_status != "running":
                            self.emit_alert(f"Job Started: {job_id}",
                                          f"Job {job_id} is now running")
                
                self._previous_jobs[job_id] = status
            
            # Check for removed jobs
            current_ids = {job.get("ID") for job in jobs}
            removed = set(self._previous_jobs.keys()) - current_ids
            for job_id in removed:
                self.emit_alert(f"Job Removed: {job_id}", f"Job {job_id} has been removed")
                del self._previous_jobs[job_id]
                
        except Exception:
            pass  # Silently ignore refresh errors
    
    def emit_alert(self, title: str, message: str):
        """Emit an alert"""
        self.alert.emit(title, message)
        if self.tray_icon:
            self.tray_icon.showMessage(title, message, 
                                       QSystemTrayIcon.MessageIcon.Warning, 5000)
    
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
    
    def get_job_status_emoji(self, status: str) -> str:
        """Get emoji for job status"""
        emojis = {
            "running": "🟢",
            "pending": "🟡",
            "dead": "🔴",
            "stopped": "⚪",
        }
        return emojis.get(status.lower(), "⚪")
    
    def get_alloc_status_emoji(self, client_status: str) -> str:
        """Get emoji for allocation status"""
        emojis = {
            "running": "🟢",
            "pending": "🟡",
            "complete": "🔵",
            "failed": "🔴",
            "lost": "⚫",
        }
        return emojis.get(client_status.lower(), "⚪")
    
    def get_node_status_emoji(self, status: str, eligibility: str) -> str:
        """Get emoji for node status"""
        if status != "ready":
            return "🔴"
        if eligibility != "eligible":
            return "🟡"
        return "🟢"
    
    def build_menu(self, parent_menu: QMenu) -> QMenu:
        menu = parent_menu.addMenu("📦 Nomad")
        
        status = self.get_status_emoji()
        status_action = menu.addAction(f"{status} Status")
        status_action.triggered.connect(self.show_status)
        
        menu.addSeparator()
        
        # Jobs
        jobs_menu = menu.addMenu("📋 Jobs")
        jobs_menu.aboutToShow.connect(lambda: self.populate_jobs_menu(jobs_menu))
        
        # Allocations
        allocs_menu = menu.addMenu("📊 Allocations")
        allocs_menu.aboutToShow.connect(lambda: self.populate_allocations_menu(allocs_menu))
        
        # Nodes
        nodes_menu = menu.addMenu("🖥️ Nodes")
        nodes_menu.aboutToShow.connect(lambda: self.populate_nodes_menu(nodes_menu))
        
        # Deployments
        deployments_menu = menu.addMenu("🚀 Deployments")
        deployments_menu.aboutToShow.connect(lambda: self.populate_deployments_menu(deployments_menu))
        
        menu.addSeparator()
        
        # Namespaces
        ns_menu = menu.addMenu("🏷️ Namespaces")
        ns_menu.aboutToShow.connect(lambda: self.populate_namespaces_menu(ns_menu))
        
        # Evaluations
        evals_menu = menu.addMenu("📝 Evaluations")
        evals_menu.aboutToShow.connect(lambda: self.populate_evaluations_menu(evals_menu))
        
        menu.addSeparator()
        
        # New Job
        new_job_action = menu.addAction("➕ New Job...")
        new_job_action.triggered.connect(self.create_new_job)
        
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
    
    def populate_jobs_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            jobs = client.list_jobs()
            menu.clear()
            
            # Add "New..." action
            new_action = menu.addAction("➕ New Job...")
            new_action.triggered.connect(self.create_new_job)
            menu.addSeparator()
            
            for job in sorted(jobs, key=lambda x: x.get("Name", "")):
                job_id = job.get("ID", "unknown")
                job_name = job.get("Name", job_id)
                status = job.get("Status", "unknown")
                emoji = self.get_job_status_emoji(status)
                
                job_menu = menu.addMenu(f"{emoji} {job_name}")
                job_menu.aboutToShow.connect(
                    lambda m=job_menu, j=job_id: self.populate_job_details_menu(m, j)
                )
            
            if not jobs:
                empty_action = menu.addAction("No jobs found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_job_details_menu(self, menu: QMenu, job_id: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            job = client.get_job(job_id)
            menu.clear()
            
            # Job info
            status = job.get("Status", "unknown")
            job_type = job.get("Type", "unknown")
            priority = job.get("Priority", 50)
            
            info_action = menu.addAction(f"ℹ️ {status} | {job_type} | Priority: {priority}")
            info_action.setEnabled(False)
            
            menu.addSeparator()
            
            # View details
            view_action = menu.addAction("👁️ View Details")
            view_action.triggered.connect(lambda: self.view_job(job_id))
            
            # Edit
            edit_action = menu.addAction("✏️ Edit")
            edit_action.triggered.connect(lambda: self.edit_job(job_id, job))
            
            menu.addSeparator()
            
            # Allocations submenu
            allocs_menu = menu.addMenu("📊 Allocations")
            allocs_menu.aboutToShow.connect(
                lambda m=allocs_menu, j=job_id: self.populate_job_allocations_menu(m, j)
            )
            
            menu.addSeparator()
            
            # Stop job
            stop_action = menu.addAction("⏹️ Stop")
            stop_action.triggered.connect(lambda: self.stop_job(job_id))
            
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_job_allocations_menu(self, menu: QMenu, job_id: str):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            allocs = client.list_allocations(job_id)
            menu.clear()
            
            for alloc in sorted(allocs, key=lambda x: x.get("CreateTime", 0), reverse=True):
                alloc_id = alloc.get("ID", "unknown")[:8]
                client_status = alloc.get("ClientStatus", "unknown")
                node_name = alloc.get("NodeName", "unknown")
                emoji = self.get_alloc_status_emoji(client_status)
                
                alloc_action = menu.addAction(f"{emoji} {alloc_id} on {node_name}")
                alloc_action.triggered.connect(
                    lambda checked, a=alloc.get("ID"): self.view_allocation(a)
                )
            
            if not allocs:
                empty_action = menu.addAction("No allocations")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_allocations_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            allocs = client.list_allocations()
            menu.clear()
            
            # Group by job
            by_job = {}
            for alloc in allocs:
                job_id = alloc.get("JobID", "unknown")
                if job_id not in by_job:
                    by_job[job_id] = []
                by_job[job_id].append(alloc)
            
            for job_id in sorted(by_job.keys()):
                job_allocs = by_job[job_id]
                job_menu = menu.addMenu(f"📋 {job_id}")
                
                for alloc in sorted(job_allocs, key=lambda x: x.get("CreateTime", 0), reverse=True):
                    alloc_id = alloc.get("ID", "unknown")[:8]
                    client_status = alloc.get("ClientStatus", "unknown")
                    emoji = self.get_alloc_status_emoji(client_status)
                    
                    alloc_action = job_menu.addAction(f"{emoji} {alloc_id} ({client_status})")
                    alloc_action.triggered.connect(
                        lambda checked, a=alloc.get("ID"): self.view_allocation(a)
                    )
            
            if not allocs:
                empty_action = menu.addAction("No allocations found")
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
            
            for node in sorted(nodes, key=lambda x: x.get("Name", "")):
                node_id = node.get("ID", "unknown")
                node_name = node.get("Name", node_id[:8])
                status = node.get("Status", "unknown")
                eligibility = node.get("SchedulingEligibility", "unknown")
                emoji = self.get_node_status_emoji(status, eligibility)
                
                node_action = menu.addAction(f"{emoji} {node_name}")
                node_action.triggered.connect(
                    lambda checked, n=node_id: self.view_node(n)
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
    
    def populate_deployments_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            deployments = client.list_deployments()
            menu.clear()
            
            for deployment in sorted(deployments, key=lambda x: x.get("CreateIndex", 0), reverse=True)[:20]:
                dep_id = deployment.get("ID", "unknown")[:8]
                job_id = deployment.get("JobID", "unknown")
                status = deployment.get("Status", "unknown")
                
                emoji = "🟢" if status == "successful" else "🟡" if status == "running" else "🔴"
                
                dep_action = menu.addAction(f"{emoji} {job_id} ({status})")
                dep_action.triggered.connect(
                    lambda checked, d=deployment.get("ID"): self.view_deployment(d)
                )
            
            if not deployments:
                empty_action = menu.addAction("No deployments found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_namespaces_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            namespaces = client.list_namespaces()
            menu.clear()
            
            for ns in sorted(namespaces, key=lambda x: x.get("Name", "")):
                ns_name = ns.get("Name", "unknown")
                ns_action = menu.addAction(f"🏷️ {ns_name}")
                ns_action.triggered.connect(
                    lambda checked, n=ns: self.view_namespace(n)
                )
            
            if not namespaces:
                empty_action = menu.addAction("No namespaces found")
                empty_action.setEnabled(False)
        except Exception as e:
            menu.clear()
            error_action = menu.addAction(f"🔴 Error: {str(e)[:50]}")
            error_action.setEnabled(False)
        finally:
            self.set_menu_loading(menu, False)
    
    def populate_evaluations_menu(self, menu: QMenu):
        if id(menu) in self._loading_menus:
            return
        menu.clear()
        self.set_menu_loading(menu, True)
        try:
            client = self.get_client()
            evals = client.list_evaluations()
            menu.clear()
            
            for eval_item in sorted(evals, key=lambda x: x.get("CreateIndex", 0), reverse=True)[:20]:
                eval_id = eval_item.get("ID", "unknown")[:8]
                job_id = eval_item.get("JobID", "unknown")
                status = eval_item.get("Status", "unknown")
                
                emoji = "🟢" if status == "complete" else "🟡" if status == "pending" else "🔴"
                
                eval_action = menu.addAction(f"{emoji} {eval_id} for {job_id}")
                eval_action.triggered.connect(
                    lambda checked, e=eval_item: self.view_evaluation(e)
                )
            
            if not evals:
                empty_action = menu.addAction("No evaluations found")
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
            agent = client.get_agent_self()
            
            status = {
                "Leader": leader,
                "Peers": peers,
                "Peer Count": len(peers) if peers else 0,
                "Server Name": agent.get("config", {}).get("Name", "unknown"),
                "Region": agent.get("config", {}).get("Region", "unknown"),
                "Datacenter": agent.get("config", {}).get("Datacenter", "unknown"),
            }
            
            dialog = JsonTableDialog("📦 Nomad Status", status, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get status: {e}")
    
    def view_job(self, job_id: str):
        try:
            client = self.get_client()
            job = client.get_job(job_id)
            dialog = JsonTableDialog(f"📋 Job: {job_id}", job, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get job: {e}")
    
    def edit_job(self, job_id: str, job_data: Dict):
        dialog = JobDialog(job_id, job_data, is_new=False)
        dialog.job_submitted.connect(self.submit_job)
        dialog.job_stopped.connect(self.stop_job)
        dialog.exec()
    
    def create_new_job(self):
        dialog = JobDialog(is_new=True)
        dialog.job_submitted.connect(self.submit_job)
        dialog.exec()
    
    def submit_job(self, job_spec: Dict):
        try:
            client = self.get_client()
            result = client.submit_job(job_spec)
            eval_id = result.get("EvalID", "unknown")
            QMessageBox.information(None, "Success", f"Job submitted. Evaluation ID: {eval_id}")
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to submit job: {e}")
    
    def stop_job(self, job_id: str):
        reply = QMessageBox.question(
            None, "Confirm Stop",
            f"Are you sure you want to stop job '{job_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                client = self.get_client()
                client.stop_job(job_id)
                QMessageBox.information(None, "Success", f"Job '{job_id}' stopped")
            except Exception as e:
                QMessageBox.warning(None, "Error", f"Failed to stop job: {e}")
    
    def view_allocation(self, alloc_id: str):
        try:
            client = self.get_client()
            alloc = client.get_allocation(alloc_id)
            dialog = JsonTableDialog(f"📊 Allocation: {alloc_id[:8]}", alloc, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get allocation: {e}")
    
    def view_node(self, node_id: str):
        try:
            client = self.get_client()
            node = client.get_node(node_id)
            dialog = JsonTableDialog(f"🖥️ Node: {node.get('Name', node_id[:8])}", node, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get node: {e}")
    
    def view_deployment(self, deployment_id: str):
        try:
            client = self.get_client()
            deployment = client.get_deployment(deployment_id)
            dialog = JsonTableDialog(f"🚀 Deployment: {deployment_id[:8]}", deployment, readonly=True)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(None, "Error", f"Failed to get deployment: {e}")
    
    def view_namespace(self, ns: Dict):
        dialog = JsonTableDialog(f"🏷️ Namespace: {ns.get('Name', 'unknown')}", ns, readonly=True)
        dialog.exec()
    
    def view_evaluation(self, eval_data: Dict):
        dialog = JsonTableDialog(f"📝 Evaluation: {eval_data.get('ID', 'unknown')[:8]}", 
                                eval_data, readonly=True)
        dialog.exec()
