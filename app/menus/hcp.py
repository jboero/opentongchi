"""HCP (HashiCorp Cloud Platform) Menu Builder for OpenTongchi.

Flat menu structure with org/project selectors at the top (like Vault namespaces).
Select org → select project → all services listed flat below.

  ☁️ HCP
    🏢 Organization: <name>   ← click to switch
    📂 Project: <name>        ← click to switch
    ─────
    🏛️ Vault Dedicated
    📦 Packer Registry
    🚪 Boundary
    🔍 Consul Dedicated
    🧭 Waypoint
    🌐 Network (HVN)

  🏗️ Terraform Cloud          ← separate root-level menu
"""

from typing import Dict, Optional
from PySide6.QtWidgets import QMenu, QMessageBox, QInputDialog
from PySide6.QtCore import QObject, Signal
from app.clients.hcp import (
    HCPAuthClient, HCPResourceManagerClient,
    HCPTerraformClient,
    HCPVaultDedicatedClient,
    HCPPackerClient, HCPBoundaryClient, HCPConsulClient,
    HCPWaypointClient, HCPNetworkClient,
)
from app.async_menu import AsyncMenu
from app.dialogs import JsonEditorDialog, CrudDialog


class HCPMenuBuilder(QObject):
    notification = Signal(str, str)
    context_changed = Signal()  # emitted when org/project selection changes

    def __init__(self, settings, process_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.process_manager = process_manager
        # Cached org/project context (populated from settings or picker)
        self._current_org_id = ""
        self._current_org_name = ""
        self._current_project_id = ""
        self._current_project_name = ""
        self._auth: Optional[HCPAuthClient] = None
        self._rm = None
        self._tf = None
        self._vd = None
        self._pk = None
        self._bd = None
        self._co = None
        self._wp = None
        self._nw = None

    # ---- lazy client accessors ----
    @property
    def auth(self) -> HCPAuthClient:
        if not self._auth:
            s = self.settings.hcp
            self._auth = HCPAuthClient(s.client_id, s.client_secret,
                                       auth_url=s.hcp_auth_url)
        return self._auth

    def _c(self, cls, attr):
        v = getattr(self, attr)
        if not v:
            v = cls(self.auth, api_url=self.settings.hcp.hcp_api_url)
            setattr(self, attr, v)
        return v

    @property
    def rm(self): return self._c(HCPResourceManagerClient, '_rm')
    @property
    def vd(self): return self._c(HCPVaultDedicatedClient, '_vd')
    @property
    def pk(self): return self._c(HCPPackerClient, '_pk')
    @property
    def bd(self): return self._c(HCPBoundaryClient, '_bd')
    @property
    def co(self): return self._c(HCPConsulClient, '_co')
    @property
    def wp(self): return self._c(HCPWaypointClient, '_wp')
    @property
    def nw(self): return self._c(HCPNetworkClient, '_nw')

    @property
    def tf(self) -> HCPTerraformClient:
        if not self._tf:
            self._tf = HCPTerraformClient(self.settings.hcp)
        return self._tf

    @property
    def o(self) -> str:
        """Current organization ID."""
        return self._current_org_id or self.settings.hcp.organization_id

    @property
    def p(self) -> str:
        """Current project ID."""
        return self._current_project_id or self.settings.hcp.project_id

    def refresh_client(self):
        if self._auth:
            self._auth.invalidate()
        for a in ('_auth','_rm','_tf','_vd','_pk','_bd','_co','_wp','_nw'):
            setattr(self, a, None)

    # ================================================================
    # build_menu — root
    # ================================================================
    def build_menu(self) -> QMenu:
        menu = QMenu("☁️ HCP")
        s = self.settings.hcp
        has_cloud = bool(s.client_id and s.client_secret)
        has_tf = bool(s.hcp_terraform_token)

        if not has_cloud and not has_tf:
            na = menu.addAction("⚠️ Not Configured — set HCP credentials in Settings")
            na.setEnabled(False)
            return menu

        if has_cloud:
            # ---- Org dropdown (shows current, lists all to switch) ----
            org_label = self._current_org_name or self.settings.hcp.organization_name or self.settings.hcp.organization_id or "(not set)"
            org_menu = AsyncMenu(f"🏢 Organization: {org_label}", self._load_org_choices)
            org_menu.set_item_callback(self._do_switch_org)
            menu.addMenu(org_menu)

            # ---- Project dropdown (shows current, lists all to switch) ----
            proj_label = self._current_project_name or self.settings.hcp.project_name or self.settings.hcp.project_id or "(not set)"
            proj_menu = AsyncMenu(f"📂 Project: {proj_label}", self._load_project_choices)
            proj_menu.set_item_callback(self._do_switch_project)
            proj_menu.set_new_item_callback(self._create_project, "➕ New Project...")
            menu.addMenu(proj_menu)

            menu.addSeparator()

            if self.o and self.p:
                # All services flat under current org+project
                menu.addMenu(self._svc_vault_dedicated())
                menu.addMenu(self._svc_packer())
                menu.addMenu(self._svc_boundary())
                menu.addMenu(self._svc_consul())
                menu.addMenu(self._svc_waypoint())
                menu.addSeparator()
                menu.addMenu(self._svc_network())
            else:
                hint = menu.addAction("⚠️ Select an Organization and Project above")
                hint.setEnabled(False)

            menu.addSeparator()

        return menu

    def build_tf_menu(self) -> QMenu:
        """Build the Terraform Cloud menu (intended for root-level placement)."""
        if not self.settings.hcp.hcp_terraform_token:
            m = QMenu("🏗️ Terraform Cloud")
            na = m.addAction("⚠️ Not Configured — set TFE token in Settings")
            na.setEnabled(False)
            return m
        return self._build_tf_menu()

    # ================================================================
    # Org / Project dropdown loaders + switch callbacks
    # ================================================================
    def _load_org_choices(self) -> list:
        """Load orgs as clickable menu items.
        HCP resource-manager response wraps each org as
        {"organization": {id, name, ...}, "role_id": ...}.
        """
        r = self.rm.list_organizations()
        if not r.ok:
            raise Exception(r.error or "Failed to list organizations")
        orgs = self._extract_list(r.data, 'organizations')
        items = []
        for o in orgs:
            name = o.get('name', o.get('id', '?'))
            oid = o.get('id', '')
            current = " ✓" if oid == self.o else ""
            items.append((f"🏢 {name}{current}", {'id': oid, 'name': name}))
        if not items:
            return [("⚠️ No organizations found (check service principal permissions)", None)]
        return items

    def _do_switch_org(self, data):
        """Switch to selected organization."""
        if data is None:
            return
        oid = data.get('id', '')
        oname = data.get('name', '')
        if oid == self._current_org_id:
            return
        self._current_org_id = oid
        self._current_org_name = oname
        self.settings.hcp.organization_id = oid
        self.settings.hcp.organization_name = oname
        # Reset project when org changes
        self._current_project_id = ""
        self._current_project_name = ""
        self.settings.hcp.project_id = ""
        self.settings.hcp.project_name = ""
        self.settings.save()
        self.notification.emit("Organization Selected", f"Switched to {oname}")
        self.context_changed.emit()

    def _load_project_choices(self) -> list:
        """Load projects for current org as clickable menu items.
        HCP resource-manager wraps each project as {"project": {id, name, ...}}.
        """
        if not self.o:
            return [("⚠️ Select an organization first", None)]
        r = self.rm.list_projects(self.o)
        if not r.ok:
            raise Exception(r.error or "Failed to list projects")
        projects = self._extract_list(r.data, 'projects')
        items = []
        for p in projects:
            name = p.get('name', p.get('id', '?'))
            pid = p.get('id', '')
            current = " ✓" if pid == self.p else ""
            items.append((f"📂 {name}{current}", {'id': pid, 'name': name}))
        if not items:
            return [("⚠️ No projects found", None)]
        return items

    def _do_switch_project(self, data):
        """Switch to selected project."""
        if data is None:
            return
        pid = data.get('id', '')
        pname = data.get('name', '')
        if pid == self._current_project_id:
            return
        self._current_project_id = pid
        self._current_project_name = pname
        self.settings.hcp.project_id = pid
        self.settings.hcp.project_name = pname
        self.settings.save()
        self.notification.emit("Project Selected", f"Switched to {pname}")
        self.context_changed.emit()

    def _create_project(self):
        """Create a new HCP project in the current organization."""
        if not self.o:
            QMessageBox.warning(None, "Error", "Select an organization first.")
            return
        d = CrudDialog("New HCP Project", {'name': '', 'description': ''})
        if d.exec():
            name = d.data.get('name', '')
            desc = d.data.get('description', '')
            if name:
                self._notify_result(
                    self.rm.create_project(self.o, name, desc),
                    "Project Created", name)

    # ================================================================
    # Vault Dedicated
    # ================================================================
    def _svc_vault_dedicated(self) -> AsyncMenu:
        m = AsyncMenu("🏛️ Vault Dedicated", self._load_vd_clusters)
        m.set_submenu_factory(self._vd_cluster_sub)
        m.set_new_item_callback(self._create_vd_cluster, "➕ New Cluster...")
        def _vd_footer(menu):
            sn = AsyncMenu("📸 Snapshots", self._load_vd_snapshots)
            sn.set_item_callback(lambda d: self._show_json("Snapshot", d))
            menu.addMenu(sn)
        m.set_footer_builder(_vd_footer)
        return m

    def _load_vd_clusters(self) -> list:
        r = self.vd.list_clusters(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        items = []
        for c in (r.data or {}).get('clusters', []):
            cid = c.get('id', '?')
            state = c.get('state', '?')
            e = HCPVaultDedicatedClient.status_emoji(state)
            tier = c.get('config', {}).get('tier', '')
            items.append({'text': f"{e} {cid} ({tier})", 'data': c, 'is_submenu': True})
        return items

    def _vd_cluster_sub(self, title, data) -> QMenu:
        cid = data.get('id', '')
        state = data.get('state', '')
        m = QMenu(title)
        m.addAction(f"ℹ️ Details (state: {state})").triggered.connect(
            lambda: self._show_json(f"Cluster: {cid}", data))
        m.addSeparator()
        m.addAction("🔑 Admin Token").triggered.connect(
            lambda: self._show_api(self.vd.get_admin_token, self.o, self.p, cid))
        m.addAction("📊 Utilization").triggered.connect(
            lambda: self._show_api(self.vd.get_utilization, self.o, self.p, cid))
        m.addAction("👥 Client Counts").triggered.connect(
            lambda: self._show_api(self.vd.get_client_counts, self.o, self.p, cid))
        m.addAction("🔄 Replication").triggered.connect(
            lambda: self._show_api(self.vd.get_replication_status, self.o, self.p, cid))
        m.addSeparator()
        if state == 'SEALED':
            m.addAction("🔓 Unseal").triggered.connect(
                lambda: self._action_confirm("Unseal", cid,
                    lambda: self.vd.unseal_cluster(self.o, self.p, cid)))
        elif state == 'RUNNING':
            m.addAction("🔒 Seal").triggered.connect(
                lambda: self._action_confirm("Seal", cid,
                    lambda: self.vd.seal_cluster(self.o, self.p, cid)))
        m.addSeparator()
        m.addAction("🗑️ Delete Cluster").triggered.connect(
            lambda: self._del_confirm("Delete Vault Cluster", cid,
                lambda: self.vd.delete_cluster(self.o, self.p, cid)))
        return m

    def _load_vd_snapshots(self) -> list:
        r = self.vd.list_snapshots(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"📸 {s.get('snapshot_id','?')}", s)
                for s in (r.data or {}).get('snapshots', [])]

    def _create_vd_cluster(self):
        d = CrudDialog("New Vault Dedicated Cluster", {
            'cluster_id': '', 'hvn_id': '',
            'tier': 'DEV', 'public_endpoint': False})
        if d.exec():
            self._notify_result(
                self.vd.create_cluster(self.o, self.p,
                    cluster_id=d.data['cluster_id'], hvn_id=d.data['hvn_id'],
                    tier=d.data.get('tier', 'DEV'),
                    public_endpoint=d.data.get('public_endpoint', False)),
                "Cluster Creating", d.data['cluster_id'])

    # ================================================================
    # Packer
    # ================================================================
    def _svc_packer(self) -> AsyncMenu:
        m = AsyncMenu("📦 Packer Registry", self._load_pk_buckets)
        m.set_submenu_factory(self._pk_bucket_sub)
        m.set_new_item_callback(self._create_pk_bucket, "➕ New Bucket...")
        return m

    def _load_pk_buckets(self) -> list:
        r = self.pk.list_buckets(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        return [{'text': f"🪣 {b.get('name','?')}", 'data': b, 'is_submenu': True}
                for b in (r.data or {}).get('buckets', [])]

    def _pk_bucket_sub(self, title, data) -> QMenu:
        bn = data.get('name', '')
        m = QMenu(title)
        m.addAction("ℹ️ Details").triggered.connect(
            lambda: self._show_json(f"Bucket: {bn}", data))
        m.addSeparator()
        ver = AsyncMenu("📋 Versions", lambda: self._load_pk_versions(bn))
        ver.set_item_callback(lambda d: self._show_json("Version", d))
        m.addMenu(ver)
        ch = AsyncMenu("📡 Channels", lambda: self._load_pk_channels(bn))
        ch.set_item_callback(lambda d: self._show_json("Channel", d))
        ch.set_new_item_callback(lambda: self._create_pk_channel(bn), "➕ New Channel...")
        m.addMenu(ch)
        m.addSeparator()
        m.addAction("🗑️ Delete Bucket").triggered.connect(
            lambda: self._del_confirm("Delete Bucket", bn,
                lambda: self.pk.delete_bucket(self.o, self.p, bn)))
        return m

    def _load_pk_versions(self, bn) -> list:
        r = self.pk.list_versions(self.o, self.p, bn)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"📋 {v.get('name','') or v.get('fingerprint','?')[:12]}", v)
                for v in (r.data or {}).get('versions', [])[:20]]

    def _load_pk_channels(self, bn) -> list:
        r = self.pk.list_channels(self.o, self.p, bn)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"📡 {c.get('name','?')}", c)
                for c in (r.data or {}).get('channels', [])]

    def _create_pk_bucket(self):
        name, ok = QInputDialog.getText(None, "New Bucket", "Bucket name:")
        if ok and name:
            self._notify_result(
                self.pk.create_bucket(self.o, self.p, name), "Bucket Created", name)

    def _create_pk_channel(self, bn):
        name, ok = QInputDialog.getText(None, "New Channel", "Channel name:")
        if ok and name:
            self._notify_result(
                self.pk.create_channel(self.o, self.p, bn, name),
                "Channel Created", name)

    # ================================================================
    # Boundary
    # ================================================================
    def _svc_boundary(self) -> AsyncMenu:
        m = AsyncMenu("🚪 Boundary", self._load_bd_clusters)
        m.set_submenu_factory(self._bd_cluster_sub)
        m.set_new_item_callback(self._create_bd_cluster, "➕ New Cluster...")
        return m

    def _load_bd_clusters(self) -> list:
        r = self.bd.list_clusters(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        items = []
        for c in (r.data or {}).get('clusters', []):
            cid = c.get('id', '?')
            state = c.get('state', '?')
            items.append({'text': f"{HCPBoundaryClient.status_emoji(state)} {cid}",
                          'data': c, 'is_submenu': True})
        return items

    def _bd_cluster_sub(self, title, data) -> QMenu:
        cid = data.get('id', '')
        url = data.get('cluster_url', '')
        m = QMenu(title)
        m.addAction("ℹ️ Details").triggered.connect(
            lambda: self._show_json(f"Cluster: {cid}", data))
        if url:
            u = m.addAction(f"🌐 {url}")
            u.setEnabled(False)
        m.addSeparator()
        m.addAction("🗑️ Delete Cluster").triggered.connect(
            lambda: self._del_confirm("Delete Boundary Cluster", cid,
                lambda: self.bd.delete_cluster(self.o, self.p, cid)))
        return m

    def _create_bd_cluster(self):
        d = CrudDialog("New Boundary Cluster", {
            'cluster_id': '', 'tier': 'STANDARD'})
        if d.exec():
            self._notify_result(
                self.bd.create_cluster(self.o, self.p,
                    d.data['cluster_id'], tier=d.data.get('tier', 'STANDARD')),
                "Cluster Creating", d.data['cluster_id'])

    # ================================================================
    # Consul
    # ================================================================
    def _svc_consul(self) -> AsyncMenu:
        m = AsyncMenu("🔍 Consul Dedicated", self._load_co_clusters)
        m.set_submenu_factory(self._co_cluster_sub)
        m.set_new_item_callback(self._create_co_cluster, "➕ New Cluster...")
        def _co_footer(menu):
            sn = AsyncMenu("📸 Snapshots", self._load_co_snapshots)
            sn.set_item_callback(lambda d: self._show_json("Snapshot", d))
            menu.addMenu(sn)
        m.set_footer_builder(_co_footer)
        return m

    def _load_co_clusters(self) -> list:
        r = self.co.list_clusters(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        items = []
        for c in (r.data or {}).get('clusters', []):
            cid = c.get('id', '?')
            state = c.get('state', '?')
            items.append({'text': f"{HCPConsulClient.status_emoji(state)} {cid}",
                          'data': c, 'is_submenu': True})
        return items

    def _co_cluster_sub(self, title, data) -> QMenu:
        cid = data.get('id', '')
        m = QMenu(title)
        m.addAction("ℹ️ Details").triggered.connect(
            lambda: self._show_json(f"Cluster: {cid}", data))
        m.addAction("⚙️ Agent Config").triggered.connect(
            lambda: self._show_api(self.co.get_client_config, self.o, self.p, cid))
        m.addSeparator()
        m.addAction("🗑️ Delete Cluster").triggered.connect(
            lambda: self._del_confirm("Delete Consul Cluster", cid,
                lambda: self.co.delete_cluster(self.o, self.p, cid)))
        return m

    def _load_co_snapshots(self) -> list:
        r = self.co.list_snapshots(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"📸 {s.get('id','?')}", s)
                for s in (r.data or {}).get('snapshots', [])]

    def _create_co_cluster(self):
        d = CrudDialog("New Consul Dedicated Cluster", {
            'cluster_id': '', 'hvn_id': '',
            'tier': 'DEVELOPMENT', 'num_servers': 1,
            'connect_enabled': True})
        if d.exec():
            self._notify_result(
                self.co.create_cluster(self.o, self.p,
                    cluster_id=d.data['cluster_id'], hvn_id=d.data['hvn_id'],
                    tier=d.data.get('tier', 'DEVELOPMENT'),
                    num_servers=int(d.data.get('num_servers', 1)),
                    connect_enabled=d.data.get('connect_enabled', True)),
                "Cluster Creating", d.data['cluster_id'])

    # ================================================================
    # Waypoint
    # ================================================================
    def _svc_waypoint(self) -> AsyncMenu:
        m = AsyncMenu("🧭 Waypoint", self._load_wp_templates)
        m.set_submenu_factory(self._wp_template_sub)
        m.set_new_item_callback(self._create_wp_template, "➕ New Template...")
        def _wp_footer(menu):
            apps = AsyncMenu("📱 Applications", self._load_wp_apps)
            apps.set_item_callback(lambda d: self._show_json("Application", d))
            menu.addMenu(apps)
            acts = AsyncMenu("⚡ Actions", self._load_wp_actions)
            acts.set_item_callback(lambda d: self._show_json("Action", d))
            menu.addMenu(acts)
            addons = AsyncMenu("🧩 Add-on Definitions", self._load_wp_addons)
            addons.set_item_callback(lambda d: self._show_json("Add-on Def", d))
            menu.addMenu(addons)
        m.set_footer_builder(_wp_footer)
        return m

    def _load_wp_templates(self) -> list:
        r = self.wp.list_templates(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        return [{'text': f"📐 {t.get('name','?')}", 'data': t, 'is_submenu': True}
                for t in (r.data or {}).get('templates', [])]

    def _wp_template_sub(self, title, data) -> QMenu:
        tid = data.get('id', '')
        name = data.get('name', '')
        m = QMenu(title)
        m.addAction("ℹ️ Details").triggered.connect(
            lambda: self._show_json(f"Template: {name}", data))
        m.addSeparator()
        m.addAction("🗑️ Delete").triggered.connect(
            lambda: self._del_confirm("Delete Template", name,
                lambda: self.wp.delete_template(self.o, self.p, tid)))
        return m

    def _load_wp_apps(self) -> list:
        r = self.wp.list_applications(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"📱 {a.get('name','?')}", a)
                for a in (r.data or {}).get('applications', [])]

    def _load_wp_actions(self) -> list:
        r = self.wp.list_actions(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"⚡ {a.get('name','?')}", a)
                for a in (r.data or {}).get('actions', [])]

    def _load_wp_addons(self) -> list:
        r = self.wp.list_add_on_definitions(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"🧩 {d.get('name','?')}", d)
                for d in (r.data or {}).get('add_on_definitions', [])]

    def _create_wp_template(self):
        name, ok = QInputDialog.getText(None, "New Template", "Template name:")
        if ok and name:
            self._notify_result(
                self.wp.create_template(self.o, self.p, name),
                "Template Created", name)

    # ================================================================
    # Network (HVN)
    # ================================================================
    def _svc_network(self) -> AsyncMenu:
        m = AsyncMenu("🌐 Network (HVN)", self._load_hvns)
        m.set_submenu_factory(self._hvn_sub)
        m.set_new_item_callback(self._create_hvn, "➕ New HVN...")
        return m

    def _load_hvns(self) -> list:
        r = self.nw.list_hvns(self.o, self.p)
        if not r.ok: raise Exception(r.error or "Failed")
        items = []
        for h in (r.data or {}).get('hvns', []):
            hid = h.get('id', '?')
            state = h.get('state', '?')
            e = HCPNetworkClient.status_emoji(state)
            prov = h.get('cloud_provider', '')
            reg = h.get('region', '')
            items.append({'text': f"{e} {hid} ({prov}/{reg})",
                          'data': h, 'is_submenu': True})
        return items

    def _hvn_sub(self, title, data) -> QMenu:
        hid = data.get('id', '')
        m = QMenu(title)
        m.addAction("ℹ️ Details").triggered.connect(
            lambda: self._show_json(f"HVN: {hid}", data))
        m.addSeparator()
        peer = AsyncMenu("🔗 Peerings", lambda: self._load_peers(hid))
        peer.set_item_callback(lambda d: self._show_json("Peering", d))
        m.addMenu(peer)
        routes = AsyncMenu("🛤️ Routes", lambda: self._load_routes(hid))
        routes.set_item_callback(lambda d: self._show_json("Route", d))
        m.addMenu(routes)
        m.addSeparator()
        m.addAction("🗑️ Delete HVN").triggered.connect(
            lambda: self._del_confirm("Delete HVN", hid,
                lambda: self.nw.delete_hvn(self.o, self.p, hid)))
        return m

    def _load_peers(self, hid) -> list:
        r = self.nw.list_peerings(self.o, self.p, hid)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"🔗 {x.get('id','?')}", x)
                for x in (r.data or {}).get('peerings', [])]

    def _load_routes(self, hid) -> list:
        r = self.nw.list_routes(self.o, self.p, hid)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"🛤️ {x.get('id','?')}", x)
                for x in (r.data or {}).get('routes', [])]

    def _create_hvn(self):
        d = CrudDialog("New HashiCorp Virtual Network", {
            'id': '', 'cloud_provider': 'aws',
            'region': 'us-west-2', 'cidr_block': '172.25.16.0/20'})
        if d.exec():
            self._notify_result(
                self.nw.create_hvn(self.o, self.p,
                    hvn_id=d.data['id'],
                    cloud_provider=d.data.get('cloud_provider', 'aws'),
                    region=d.data.get('region', 'us-west-2'),
                    cidr_block=d.data.get('cidr_block', '172.25.16.0/20')),
                "HVN Creating", d.data['id'])

    # ================================================================
    # Terraform Orgs (TFE token — flat org list, fka Terraform Cloud)
    # ================================================================
    def _build_tf_menu(self) -> QMenu:
        m = AsyncMenu("🏗️ Terraform Cloud", self._load_tf_orgs)
        m.set_submenu_factory(self._tf_org_sub)
        return m

    def _load_tf_orgs(self) -> list:
        r = self.tf.list_organizations()
        if not r.ok: raise Exception(r.error or "Failed")
        return [{'text': f"🏢 {o.get('attributes',{}).get('name', o.get('id',''))}",
                 'data': o, 'is_submenu': True}
                for o in (r.data or {}).get('data', [])]

    def _tf_org_sub(self, title, data) -> QMenu:
        org = data.get('attributes', {}).get('name', data.get('id', ''))
        m = QMenu(title)
        m.addAction("ℹ️ Info").triggered.connect(
            lambda: self._show_api(self.tf.get_organization, org))
        m.addSeparator()

        proj = AsyncMenu("📂 Projects", lambda: self._load_tf_projects(org))
        proj.set_item_callback(lambda d: self._show_json("Project", d))
        proj.set_new_item_callback(
            lambda: self._create_tf_project(org), "➕ New Project...")
        m.addMenu(proj)

        ws = AsyncMenu("📁 Workspaces", lambda: self._load_tf_ws(org))
        ws.set_submenu_factory(self._tf_ws_sub)
        ws.set_new_item_callback(
            lambda: self._create_tf_ws(org), "➕ New Workspace...")
        m.addMenu(ws)

        vs = AsyncMenu("📦 Variable Sets", lambda: self._load_tf_varsets(org))
        vs.set_item_callback(lambda d: self._show_json("Variable Set", d))
        vs.set_new_item_callback(
            lambda: self._create_tf_varset(org), "➕ New Variable Set...")
        m.addMenu(vs)

        tm = AsyncMenu("👥 Teams", lambda: self._load_tf_teams(org))
        tm.set_item_callback(lambda d: self._show_json("Team", d))
        m.addMenu(tm)
        return m

    # -- TF data loaders --
    def _load_tf_projects(self, org) -> list:
        r = self.tf.list_projects(org)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"📂 {p.get('attributes',{}).get('name','?')} "
                 f"({p.get('attributes',{}).get('workspace-count',0)} ws)", p)
                for p in (r.data or {}).get('data', [])]

    def _load_tf_ws(self, org) -> list:
        r = self.tf.list_workspaces(org)
        if not r.ok: raise Exception(r.error or "Failed")
        items = []
        for ws in (r.data or {}).get('data', []):
            a = ws.get('attributes', {})
            e = HCPTerraformClient.ws_emoji(ws)
            lock = '🔒' if a.get('locked') else ''
            items.append({'text': f"{e} {lock} {a.get('name','?')}",
                          'data': ws, 'is_submenu': True})
        return items

    def _tf_ws_sub(self, title, data) -> QMenu:
        ws_id = data.get('id', '')
        name = data.get('attributes', {}).get('name', '')
        locked = data.get('attributes', {}).get('locked', False)
        m = QMenu(title)
        m.addAction("ℹ️ Details").triggered.connect(
            lambda: self._show_api(self.tf.get_workspace_by_id, ws_id))
        m.addSeparator()
        if locked:
            m.addAction("🔓 Unlock").triggered.connect(
                lambda: self._action_notify(
                    self.tf.unlock_workspace(ws_id), "Unlocked"))
        else:
            m.addAction("🔒 Lock").triggered.connect(
                lambda: self._tf_lock(ws_id))
        m.addSeparator()

        va = AsyncMenu("🔐 Variables", lambda: self._load_tf_vars(ws_id))
        va.set_item_callback(lambda d: self._show_tf_var(d))
        va.set_new_item_callback(
            lambda: self._create_tf_var(ws_id), "➕ New Variable...")
        m.addMenu(va)

        ru = AsyncMenu("🚀 Runs", lambda: self._load_tf_runs(ws_id))
        ru.set_item_callback(
            lambda d: self._show_api(self.tf.get_run, d.get('id', '')))
        m.addMenu(ru)

        sv = AsyncMenu("📊 State Versions", lambda: self._load_tf_sv(ws_id))
        sv.set_item_callback(lambda d: self._show_json("State Version", d))
        m.addMenu(sv)

        m.addSeparator()
        m.addAction("▶️ Start Run").triggered.connect(
            lambda: self._tf_run(ws_id))
        m.addAction("💥 Destroy Run").triggered.connect(
            lambda: self._tf_destroy_run(ws_id))
        m.addSeparator()
        m.addAction("🗑️ Delete Workspace").triggered.connect(
            lambda: self._del_confirm("Delete Workspace", name,
                lambda: self.tf.delete_workspace(name)))
        return m

    def _load_tf_varsets(self, org) -> list:
        r = self.tf.list_variable_sets(org)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"{'🌐' if vs.get('attributes',{}).get('global') else '📦'} "
                 f"{vs.get('attributes',{}).get('name','?')}", vs)
                for vs in (r.data or {}).get('data', [])]

    def _load_tf_teams(self, org) -> list:
        r = self.tf.list_teams(org)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"👥 {t.get('attributes',{}).get('name','?')}", t)
                for t in (r.data or {}).get('data', [])]

    def _load_tf_vars(self, ws_id) -> list:
        r = self.tf.list_variables(ws_id)
        if not r.ok: raise Exception(r.error or "Failed")
        items = []
        for v in (r.data or {}).get('data', []):
            a = v.get('attributes', {})
            si = '🔒' if a.get('sensitive') else '🔓'
            ci = '🌍' if a.get('category') == 'env' else '📝'
            items.append((f"{si} {ci} {a.get('key','?')}", v))
        return items

    def _load_tf_runs(self, ws_id) -> list:
        r = self.tf.list_runs(ws_id)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"{HCPTerraformClient.run_emoji(run.get('attributes',{}).get('status','?'))} "
                 f"{run.get('attributes',{}).get('status','?')}", run)
                for run in (r.data or {}).get('data', [])[:10]]

    def _load_tf_sv(self, ws_id) -> list:
        r = self.tf.list_state_versions(ws_id)
        if not r.ok: raise Exception(r.error or "Failed")
        return [(f"📊 v{v.get('attributes',{}).get('serial',0)} "
                 f"({v.get('attributes',{}).get('created-at','')[:10]})", v)
                for v in (r.data or {}).get('data', [])[:10]]

    def _show_tf_var(self, var):
        a = var.get('attributes', {})
        self._show_json(f"Variable: {a.get('key','')}", {
            'key': a.get('key', ''), 'category': a.get('category', ''),
            'sensitive': a.get('sensitive', False),
            'value': '(sensitive)' if a.get('sensitive') else a.get('value', ''),
            'hcl': a.get('hcl', False)}, readonly=True)

    # -- TF actions --
    def _create_tf_project(self, org):
        name, ok = QInputDialog.getText(None, "New Project", "Project name:")
        if ok and name:
            self._notify_result(
                self.tf.create_project(name, org), "Project Created", name)

    def _create_tf_ws(self, org):
        d = CrudDialog("New Workspace", {
            'name': '', 'description': '', 'auto_apply': False})
        if d.exec():
            self._notify_result(
                self.tf.create_workspace(
                    d.data.get('name', ''), org,
                    auto_apply=d.data.get('auto_apply', False),
                    description=d.data.get('description')),
                "Workspace Created", d.data.get('name', ''))

    def _create_tf_varset(self, org):
        d = CrudDialog("New Variable Set", {
            'name': '', 'description': '', 'global': False})
        if d.exec():
            self._notify_result(
                self.tf.create_variable_set(
                    d.data.get('name', ''), org,
                    description=d.data.get('description'),
                    global_set=d.data.get('global', False)),
                "Variable Set Created", d.data.get('name', ''))

    def _create_tf_var(self, ws_id):
        d = CrudDialog("New Variable", {
            'key': '', 'value': '', 'category': 'terraform',
            'sensitive': False, 'hcl': False})
        if d.exec():
            self._notify_result(
                self.tf.create_variable(
                    ws_id, d.data.get('key', ''), d.data.get('value', ''),
                    category=d.data.get('category', 'terraform'),
                    sensitive=d.data.get('sensitive', False),
                    hcl=d.data.get('hcl', False)),
                "Variable Created", d.data.get('key', ''))

    def _tf_lock(self, ws_id):
        reason, ok = QInputDialog.getText(None, "Lock", "Reason:")
        if ok:
            self._action_notify(
                self.tf.lock_workspace(ws_id, reason), "Locked")

    def _tf_run(self, ws_id):
        msg, ok = QInputDialog.getText(None, "Start Run", "Message (optional):")
        if ok:
            self._notify_result(
                self.tf.create_run(ws_id, message=msg or None),
                "Run Started", "Plan/Apply")

    def _tf_destroy_run(self, ws_id):
        reply = QMessageBox.warning(None, "Destroy Run",
            "⚠️ Start a DESTROY run?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._notify_result(
                self.tf.create_run(ws_id, is_destroy=True),
                "Destroy Run Started", "")

    # ================================================================
    # Helpers
    # ================================================================
    def _show_json(self, title, data, readonly=True):
        JsonEditorDialog(title, data, readonly=readonly).exec()

    def _show_api(self, fn, *args):
        r = fn(*args)
        if r.ok:
            self._show_json(str(args[-1]) if args else "Result", r.data)
        else:
            QMessageBox.warning(None, "Error", f"API error: {r.error}")

    def _notify_result(self, r, ok_title, name):
        if r.ok:
            self.notification.emit(ok_title, f"{name}" if name else ok_title)
        else:
            QMessageBox.warning(None, "Error", f"Failed: {r.error}")

    def _action_notify(self, r, label):
        if r.ok:
            self.notification.emit(label, label)

    def _del_confirm(self, title, name, fn):
        reply = QMessageBox.warning(None, title,
            f"⚠️ {title}: '{name}'?\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            r = fn()
            self._notify_result(r, title.replace('Delete ', 'Deleted '), name)

    def _action_confirm(self, verb, name, fn):
        reply = QMessageBox.warning(None, verb,
            f"{verb} '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            r = fn()
            self._notify_result(r, f"{verb} complete", name)

    @staticmethod
    def _extract_list(data, key: str) -> list:
        """Extract a list from an HCP API response, trying common envelope patterns.
        HCP APIs may wrap results as {key: [...]}, {"data": [...]}, or just [...].
        """
        if not data:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Try the expected key first
            if key in data and isinstance(data[key], list):
                return data[key]
            # Try 'data' (JSON:API style)
            if 'data' in data and isinstance(data['data'], list):
                return data['data']
            # Try any key that holds a list
            for v in data.values():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    return v
        return []
