"""Nomad Menu Builder for OpenTongchi"""

from typing import Dict, Optional
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog
from PySide6.QtCore import QObject, Signal, QTimer
from app.clients.nomad import NomadClient
from app.async_menu import AsyncMenu
from app.dialogs import JsonEditorDialog, CrudDialog


class NomadMenuBuilder(QObject):
    notification = Signal(str, str)
    job_status_changed = Signal(str, str)  # job_id, new_status
    
    def __init__(self, settings, process_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        self._client: Optional[NomadClient] = None
        self._refresh_timer: Optional[QTimer] = None
        self._job_states: Dict[str, str] = {}
    
    @property
    def client(self) -> NomadClient:
        if self._client is None:
            self._client = NomadClient(self.settings.nomad)
        return self._client
    
    def refresh_client(self):
        self._client = None
    
    def start_monitoring(self):
        if self._refresh_timer is None:
            self._refresh_timer = QTimer(self)
            self._refresh_timer.timeout.connect(self._check_job_status)
        interval = self.settings.nomad.refresh_interval_seconds * 1000
        self._refresh_timer.start(interval)
    
    def stop_monitoring(self):
        if self._refresh_timer:
            self._refresh_timer.stop()
    
    def _check_job_status(self):
        """Check for job status changes and emit alerts."""
        try:
            response = self.client.job_list()
            if response.ok and response.data:
                for job in response.data:
                    job_id = job.get('ID', '')
                    status = job.get('Status', '')
                    old_status = self._job_states.get(job_id)
                    
                    if old_status and old_status != status:
                        self.job_status_changed.emit(job_id, status)
                        if status == 'dead':
                            self.notification.emit("Job Failed", f"Job {job_id} is now {status}")
                    
                    self._job_states[job_id] = status
        except Exception:
            pass
    
    def build_menu(self) -> QMenu:
        menu = QMenu("📦 Nomad")
        
        if not self.settings.nomad.address:
            not_configured = menu.addAction("⚠️ Not Configured")
            not_configured.setEnabled(False)
            return menu
        
        self._add_status_menu(menu)
        menu.addSeparator()
        
        # Jobs
        jobs_menu = self._create_jobs_menu()
        menu.addMenu(jobs_menu)
        
        # Allocations
        allocs_menu = self._create_allocations_menu()
        menu.addMenu(allocs_menu)
        
        # Nodes
        nodes_menu = self._create_nodes_menu()
        menu.addMenu(nodes_menu)
        
        # Deployments
        deployments_menu = self._create_deployments_menu()
        menu.addMenu(deployments_menu)
        
        menu.addSeparator()
        
        # Namespaces
        ns_menu = self._create_namespaces_menu()
        menu.addMenu(ns_menu)
        
        # Variables
        vars_menu = self._create_variables_menu()
        menu.addMenu(vars_menu)
        
        return menu
    
    def _add_status_menu(self, menu: QMenu):
        try:
            if self.client.is_healthy():
                status = menu.addAction("🟢 Connected")
            else:
                status = menu.addAction("🔴 Disconnected")
        except Exception:
            status = menu.addAction("⚪ Unknown")
        status.setEnabled(False)
    
    def _create_jobs_menu(self) -> QMenu:
        menu = AsyncMenu("📋 Jobs", self._load_jobs)
        menu.set_submenu_factory(self._create_job_submenu)
        menu.set_new_item_callback(self._create_job, "➕ New Job...")
        return menu
    
    def _load_jobs(self) -> list:
        response = self.client.job_list()
        if not response.ok:
            raise Exception(response.error or "Failed to list jobs")
        
        jobs = response.data or []
        items = []
        
        for job in jobs:
            job_id = job.get('ID', 'unknown')
            status = job.get('Status', 'unknown')
            job_type = job.get('Type', '')
            emoji = self.client.get_job_status_emoji(status)
            
            items.append({
                'text': f"{emoji} {job_id} ({job_type})",
                'data': job,
                'is_submenu': True
            })
        return items
    
    def _create_job_submenu(self, title: str, data: Dict) -> QMenu:
        job_id = data.get('ID', '')
        menu = QMenu(title)
        
        # Info
        info = menu.addAction("ℹ️ Job Details")
        info.triggered.connect(lambda: self._show_job(job_id))
        
        summary = menu.addAction("📊 Summary")
        summary.triggered.connect(lambda: self._show_job_summary(job_id))
        
        menu.addSeparator()
        
        # Allocations submenu
        allocs = AsyncMenu("📋 Allocations", lambda: self._load_job_allocations(job_id))
        allocs.set_item_callback(self._show_allocation)
        menu.addMenu(allocs)
        
        # Versions
        versions = menu.addAction("📜 Versions")
        versions.triggered.connect(lambda: self._show_job_versions(job_id))
        
        menu.addSeparator()
        
        # Actions
        stop = menu.addAction("⏹️ Stop Job")
        stop.triggered.connect(lambda: self._stop_job(job_id))
        
        restart = menu.addAction("🔄 Restart Job")
        restart.triggered.connect(lambda: self._restart_job(job_id))
        
        if data.get('Periodic'):
            force = menu.addAction("▶️ Force Periodic Run")
            force.triggered.connect(lambda: self._force_periodic(job_id))
        
        if data.get('ParameterizedJob'):
            dispatch = menu.addAction("🚀 Dispatch")
            dispatch.triggered.connect(lambda: self._dispatch_job(job_id))
        
        menu.addSeparator()
        
        edit = menu.addAction("✏️ Edit Job")
        edit.triggered.connect(lambda: self._edit_job(job_id))
        
        return menu
    
    def _create_allocations_menu(self) -> QMenu:
        menu = AsyncMenu("📦 Allocations", self._load_allocations)
        menu.set_item_callback(self._show_allocation)
        return menu
    
    def _load_allocations(self) -> list:
        response = self.client.allocation_list()
        if not response.ok:
            raise Exception(response.error or "Failed to list allocations")
        
        allocs = response.data or []
        items = []
        
        for alloc in allocs[:50]:  # Limit to 50
            alloc_id = alloc.get('ID', '')[:8]
            job_id = alloc.get('JobID', '')
            client_status = alloc.get('ClientStatus', '')
            emoji = self.client.get_alloc_status_emoji(client_status)
            
            items.append((f"{emoji} {alloc_id}... ({job_id})", alloc))
        return items
    
    def _load_job_allocations(self, job_id: str) -> list:
        response = self.client.job_allocations(job_id)
        if not response.ok:
            raise Exception(response.error or "Failed to list allocations")
        
        allocs = response.data or []
        items = []
        
        for alloc in allocs:
            alloc_id = alloc.get('ID', '')[:8]
            client_status = alloc.get('ClientStatus', '')
            emoji = self.client.get_alloc_status_emoji(client_status)
            
            items.append((f"{emoji} {alloc_id}... ({client_status})", alloc))
        return items
    
    def _create_nodes_menu(self) -> QMenu:
        menu = AsyncMenu("🖥️ Nodes", self._load_nodes)
        menu.set_submenu_factory(self._create_node_submenu)
        return menu
    
    def _load_nodes(self) -> list:
        response = self.client.node_list()
        if not response.ok:
            raise Exception(response.error or "Failed to list nodes")
        
        nodes = response.data or []
        items = []
        
        for node in nodes:
            node_id = node.get('ID', '')[:8]
            name = node.get('Name', 'unknown')
            status = node.get('Status', '')
            eligible = node.get('SchedulingEligibility', '') == 'eligible'
            emoji = self.client.get_node_status_emoji(status, eligible)
            
            items.append({
                'text': f"{emoji} {name} ({node_id}...)",
                'data': node,
                'is_submenu': True
            })
        return items
    
    def _create_node_submenu(self, title: str, data: Dict) -> QMenu:
        node_id = data.get('ID', '')
        menu = QMenu(title)
        
        info = menu.addAction("ℹ️ Node Details")
        info.triggered.connect(lambda: self._show_node(node_id))
        
        allocs = AsyncMenu("📦 Allocations", lambda: self._load_node_allocations(node_id))
        menu.addMenu(allocs)
        
        menu.addSeparator()
        
        drain = menu.addAction("💧 Enable Drain")
        drain.triggered.connect(lambda: self._drain_node(node_id, True))
        
        undrain = menu.addAction("🚫💧 Disable Drain")
        undrain.triggered.connect(lambda: self._drain_node(node_id, False))
        
        return menu
    
    def _load_node_allocations(self, node_id: str) -> list:
        response = self.client.node_allocations(node_id)
        if not response.ok:
            raise Exception(response.error or "Failed to list allocations")
        
        allocs = response.data or []
        return [(f"📦 {a.get('ID', '')[:8]}... ({a.get('JobID', '')})", a) for a in allocs]
    
    def _create_deployments_menu(self) -> QMenu:
        menu = AsyncMenu("🚀 Deployments", self._load_deployments)
        menu.set_item_callback(self._show_deployment)
        return menu
    
    def _load_deployments(self) -> list:
        response = self.client.deployment_list()
        if not response.ok:
            raise Exception(response.error or "Failed to list deployments")
        
        deployments = response.data or []
        items = []
        
        for deploy in deployments[:20]:
            deploy_id = deploy.get('ID', '')[:8]
            job_id = deploy.get('JobID', '')
            status = deploy.get('Status', '')
            
            emoji = {'successful': '🟢', 'failed': '🔴', 'running': '🔄'}.get(status, '⚪')
            items.append((f"{emoji} {deploy_id}... ({job_id})", deploy))
        return items
    
    def _create_namespaces_menu(self) -> QMenu:
        menu = AsyncMenu("📂 Namespaces", self._load_namespaces)
        menu.set_item_callback(self._show_namespace)
        return menu
    
    def _load_namespaces(self) -> list:
        response = self.client.namespace_list()
        if not response.ok:
            raise Exception(response.error or "Failed to list namespaces")
        
        namespaces = response.data or []
        return [(f"📂 {ns.get('Name', 'unknown')}", ns) for ns in namespaces]
    
    def _create_variables_menu(self) -> QMenu:
        menu = AsyncMenu("🔐 Variables", self._load_variables)
        menu.set_item_callback(self._show_variable)
        menu.set_new_item_callback(self._create_variable, "➕ New Variable...")
        return menu
    
    def _load_variables(self) -> list:
        response = self.client.variable_list()
        if not response.ok:
            raise Exception(response.error or "Failed to list variables")
        
        variables = response.data or []
        return [(f"🔐 {v.get('Path', 'unknown')}", v) for v in variables]
    
    # Action handlers
    def _show_job(self, job_id: str):
        response = self.client.job_read(job_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Job: {job_id}", response.data, readonly=True)
            dialog.exec()
    
    def _show_job_summary(self, job_id: str):
        response = self.client.job_summary(job_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Summary: {job_id}", response.data, readonly=True)
            dialog.exec()
    
    def _show_job_versions(self, job_id: str):
        response = self.client.job_versions(job_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Versions: {job_id}", response.data, readonly=True)
            dialog.exec()
    
    def _show_allocation(self, alloc: Dict):
        alloc_id = alloc.get('ID', '')
        response = self.client.allocation_read(alloc_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Allocation: {alloc_id[:8]}...", response.data, readonly=True)
            dialog.exec()
    
    def _show_node(self, node_id: str):
        response = self.client.node_read(node_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Node: {node_id[:8]}...", response.data, readonly=True)
            dialog.exec()
    
    def _show_deployment(self, deploy: Dict):
        deploy_id = deploy.get('ID', '')
        response = self.client.deployment_read(deploy_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Deployment: {deploy_id[:8]}...", response.data, readonly=True)
            dialog.exec()
    
    def _show_namespace(self, ns: Dict):
        dialog = JsonEditorDialog(f"Namespace: {ns.get('Name', '')}", ns, readonly=True)
        dialog.exec()
    
    def _show_variable(self, var: Dict):
        path = var.get('Path', '')
        response = self.client.variable_read(path)
        if response.ok:
            dialog = JsonEditorDialog(f"Variable: {path}", response.data)
            dialog.saved.connect(lambda d: self._save_variable(path, d))
            dialog.exec()
    
    def _stop_job(self, job_id: str):
        reply = QMessageBox.question(None, "Stop Job", f"Stop job {job_id}?")
        if reply == QMessageBox.StandardButton.Yes:
            response = self.client.job_stop(job_id)
            if response.ok:
                self.notification.emit("Job Stopped", f"Job {job_id} stopped")
    
    def _restart_job(self, job_id: str):
        response = self.client.job_read(job_id)
        if response.ok:
            job_spec = response.data
            response = self.client.job_register(job_spec)
            if response.ok:
                self.notification.emit("Job Restarted", f"Job {job_id} restarted")
    
    def _force_periodic(self, job_id: str):
        response = self.client.job_force_periodic(job_id)
        if response.ok:
            self.notification.emit("Periodic Run", f"Forced periodic run of {job_id}")
    
    def _dispatch_job(self, job_id: str):
        response = self.client.job_dispatch(job_id)
        if response.ok:
            self.notification.emit("Job Dispatched", f"Dispatched {job_id}")
    
    def _edit_job(self, job_id: str):
        response = self.client.job_read(job_id)
        if response.ok:
            dialog = JsonEditorDialog(f"Edit Job: {job_id}", response.data)
            dialog.saved.connect(lambda d: self._save_job(d))
            dialog.exec()
    
    def _save_job(self, job_spec: Dict):
        response = self.client.job_register(job_spec)
        if response.ok:
            self.notification.emit("Job Saved", "Job updated successfully")
    
    def _create_job(self):
        dialog = JsonEditorDialog("New Job", {
            'ID': '',
            'Name': '',
            'Type': 'service',
            'TaskGroups': []
        })
        dialog.saved.connect(lambda d: self._save_job(d))
        dialog.exec()
    
    def _drain_node(self, node_id: str, enable: bool):
        response = self.client.node_drain(node_id, enable)
        if response.ok:
            action = "enabled" if enable else "disabled"
            self.notification.emit("Node Drain", f"Drain {action} for node")
    
    def _create_variable(self):
        path, ok = QInputDialog.getText(None, "New Variable", "Variable path:")
        if ok and path:
            dialog = CrudDialog(f"New Variable: {path}", {'key': '', 'value': ''})
            dialog.saved.connect(lambda d: self._save_variable(path, {'Items': d}))
            dialog.exec()
    
    def _save_variable(self, path: str, data: Dict):
        items = data.get('Items', data)
        response = self.client.variable_create(path, items)
        if response.ok:
            self.notification.emit("Variable Saved", f"Variable {path} saved")
