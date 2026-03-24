"""
HCP (HashiCorp Cloud Platform) Client for OpenTongchi
OAuth2 auth via HCP IdP, API at HCP Cloud API.
All endpoints are configurable for EU region or self-hosted deployments.
HCP Terraform uses separate TFE token (supports app.terraform.io, EU, or Terraform Enterprise).

All cloud-API sub-clients share an HCPAuthClient and accept org_id/project_id
dynamically so the menu can browse multiple orgs and projects.
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Optional, List
from .base import BaseHTTPClient, APIResponse


# ============================================================
# OAuth2 token helper
# ============================================================

class HCPAuthClient:
    """OAuth2 client_credentials flow against HCP IdP."""

    DEFAULT_AUTH_URL = "https://auth.idp.hashicorp.com"
    AUDIENCE = "https://api.hashicorp.cloud"

    def __init__(self, client_id: str, client_secret: str,
                 auth_url: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = f"{(auth_url or self.DEFAULT_AUTH_URL).rstrip('/')}/oauth2/token"
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    @property
    def access_token(self) -> str:
        if not self._access_token or time.time() >= self._token_expiry - 60:
            self._refresh_token()
        return self._access_token or ""

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _refresh_token(self):
        if not self.is_configured:
            return
        body = urllib.parse.urlencode({
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials',
            'audience': self.AUDIENCE,
        }).encode('utf-8')
        request = urllib.request.Request(
            self.token_url, data=body,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST')
        try:
            response = urllib.request.urlopen(request, timeout=15)
            data = json.loads(response.read().decode('utf-8'))
            self._access_token = data.get('access_token', '')
            self._token_expiry = time.time() + data.get('expires_in', 3600)
        except Exception as e:
            self._access_token = None
            self._token_expiry = 0
            raise RuntimeError(f"HCP auth failed: {e}")

    def invalidate(self):
        self._access_token = None
        self._token_expiry = 0


# ============================================================
# Base cloud-API client (shared by all services)
# ============================================================

class HCPCloudClient(BaseHTTPClient):
    """Base client for HCP Cloud API endpoints."""

    DEFAULT_API_URL = "https://api.cloud.hashicorp.com"

    def __init__(self, auth: HCPAuthClient, api_url: str = ""):
        super().__init__(base_url=(api_url or self.DEFAULT_API_URL).rstrip('/'))
        self.auth = auth

    def _get_headers(self) -> Dict[str, str]:
        headers = super()._get_headers()
        token = self.auth.access_token
        if token:
            headers['Authorization'] = f'Bearer {token}'
        return headers

    def get(self, path: str, params: Dict[str, str] = None,
            headers: Dict[str, str] = None) -> APIResponse:
        """GET with default pagination (100 items) for HCP APIs."""
        params = dict(params or {})
        if 'pagination.page_size' not in params:
            params['pagination.page_size'] = '100'
        return super().get(path, params=params, headers=headers)

    def get_all_pages(self, path: str, list_key: str,
                      params: Dict[str, str] = None,
                      headers: Dict[str, str] = None) -> APIResponse:
        """GET all pages for a paginated HCP endpoint.

        Follows ``pagination.next_page_token`` until exhausted and
        merges items under *list_key* into a single APIResponse.
        """
        params = dict(params or {})
        all_items: List[Any] = []
        last_resp: Optional[APIResponse] = None

        while True:
            resp = self.get(path, params=params, headers=headers)
            last_resp = resp
            if not resp.ok:
                return resp

            data = resp.data or {}
            page_items = data.get(list_key, []) if isinstance(data, dict) else []
            if isinstance(page_items, list):
                all_items.extend(page_items)

            # Check for next page
            pagination = data.get('pagination', {}) if isinstance(data, dict) else {}
            next_token = pagination.get('next_page_token', '') if isinstance(pagination, dict) else ''
            if not next_token:
                break
            params = dict(params)  # don't mutate caller's dict
            params['pagination.next_page_token'] = next_token

        # Return a merged response with all items under the original key
        merged_data = dict(last_resp.data) if isinstance(last_resp.data, dict) else {}
        merged_data[list_key] = all_items
        merged_data.pop('pagination', None)
        return APIResponse(
            status_code=last_resp.status_code,
            data=merged_data,
            headers=last_resp.headers,
        )


# ============================================================
# Resource Manager  (orgs + projects)
# ============================================================

class HCPResourceManagerClient(HCPCloudClient):
    """List / manage HCP organizations and projects."""

    RM = "/resource-manager/2019-12-10"

    def list_organizations(self) -> APIResponse:
        return self.get_all_pages(f"{self.RM}/organizations", 'organizations')

    def get_organization(self, org_id: str) -> APIResponse:
        return self.get(f"{self.RM}/organizations/{org_id}")

    def list_projects(self, org_id: str) -> APIResponse:
        # HCP projects are scoped to an org via query param
        return self.get_all_pages(f"{self.RM}/projects", 'projects', params={
            'scope.id': org_id,
            'scope.type': 'ORGANIZATION',
        })

    def get_project(self, project_id: str) -> APIResponse:
        return self.get(f"{self.RM}/projects/{project_id}")

    def create_project(self, org_id: str, name: str,
                       description: str = "") -> APIResponse:
        data = {
            'name': name,
            'description': description,
            'parent': {
                'type': 'ORGANIZATION',
                'id': org_id,
            },
        }
        return self.post(f"{self.RM}/projects", data)

    def delete_project(self, project_id: str) -> APIResponse:
        return self.delete(f"{self.RM}/projects/{project_id}")


# ============================================================
# HCP Vault Secrets
# ============================================================

class HCPVaultSecretsClient(HCPCloudClient):
    V = "2023-11-28"

    def _p(self, org_id: str, project_id: str) -> str:
        return f"/secrets/{self.V}/organizations/{org_id}/projects/{project_id}"

    def list_apps(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/apps")

    def create_app(self, org_id: str, project_id: str,
                   name: str, description: str = "") -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/apps",
                         {'name': name, 'description': description})

    def get_app(self, org_id: str, project_id: str, app_name: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/apps/{app_name}")

    def delete_app(self, org_id: str, project_id: str, app_name: str) -> APIResponse:
        return self.delete(f"{self._p(org_id, project_id)}/apps/{app_name}")

    def list_secrets(self, org_id: str, project_id: str,
                     app_name: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/apps/{app_name}/secrets")

    def open_secret(self, org_id: str, project_id: str,
                    app_name: str, secret_name: str) -> APIResponse:
        return self.get(
            f"{self._p(org_id, project_id)}/apps/{app_name}/secrets/{secret_name}:open")

    def create_secret(self, org_id: str, project_id: str,
                      app_name: str, name: str, value: str) -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/apps/{app_name}/secrets",
                         {'name': name, 'value': value})

    def delete_secret(self, org_id: str, project_id: str,
                      app_name: str, secret_name: str) -> APIResponse:
        return self.delete(
            f"{self._p(org_id, project_id)}/apps/{app_name}/secrets/{secret_name}")

    def list_integrations(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/integrations")

    def get_usage(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/usage")


# ============================================================
# HCP Vault Dedicated
# ============================================================

class HCPVaultDedicatedClient(HCPCloudClient):
    V = "2020-11-25"

    def _p(self, org_id: str, project_id: str) -> str:
        return f"/vault/{self.V}/organizations/{org_id}/projects/{project_id}"

    def list_clusters(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/clusters")

    def get_cluster(self, org_id: str, project_id: str,
                    cluster_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/clusters/{cluster_id}")

    def create_cluster(self, org_id: str, project_id: str,
                       cluster_id: str, hvn_id: str,
                       tier: str = "DEV",
                       public_endpoint: bool = False,
                       min_version: str = "") -> APIResponse:
        data = {
            'id': cluster_id,
            'config': {
                'tier': tier.upper(),
                'network_config': {'network_id': hvn_id},
            },
        }
        if public_endpoint:
            data['config']['network_config']['public_endpoint'] = True
        if min_version:
            data['min_vault_version'] = min_version
        return self.post(f"{self._p(org_id, project_id)}/clusters", data)

    def delete_cluster(self, org_id: str, project_id: str,
                       cluster_id: str) -> APIResponse:
        return self.delete(f"{self._p(org_id, project_id)}/clusters/{cluster_id}")

    def seal_cluster(self, org_id: str, project_id: str,
                     cluster_id: str) -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/clusters/{cluster_id}/seal")

    def unseal_cluster(self, org_id: str, project_id: str,
                       cluster_id: str) -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/clusters/{cluster_id}/unseal")

    def lock_cluster(self, org_id: str, project_id: str,
                     cluster_id: str) -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/clusters/{cluster_id}/lock")

    def unlock_cluster(self, org_id: str, project_id: str,
                       cluster_id: str) -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/clusters/{cluster_id}/unlock")

    def get_admin_token(self, org_id: str, project_id: str,
                        cluster_id: str) -> APIResponse:
        return self.post(
            f"{self._p(org_id, project_id)}/clusters/{cluster_id}/admintoken")

    def list_snapshots(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/snapshots")

    def get_utilization(self, org_id: str, project_id: str,
                        cluster_id: str) -> APIResponse:
        return self.get(
            f"{self._p(org_id, project_id)}/clusters/{cluster_id}/utilization")

    def get_client_counts(self, org_id: str, project_id: str,
                          cluster_id: str) -> APIResponse:
        return self.get(
            f"{self._p(org_id, project_id)}/clusters/{cluster_id}/clientcounts")

    def get_replication_status(self, org_id: str, project_id: str,
                               cluster_id: str) -> APIResponse:
        return self.get(
            f"{self._p(org_id, project_id)}/clusters/{cluster_id}/replicationstatus")

    @staticmethod
    def status_emoji(state: str) -> str:
        m = {'RUNNING': '🟢', 'CREATING': '🔄', 'PENDING': '⏳',
             'RESTORING': '🔄', 'UPDATING': '🔄', 'DELETING': '🗑️',
             'SEALED': '🔒', 'FAILED': '🔴', 'LOCKING': '🔒'}
        return m.get(state, '⚪')


# ============================================================
# HCP Packer
# ============================================================

class HCPPackerClient(HCPCloudClient):
    V = "2023-01-01"

    def _p(self, org_id: str, project_id: str) -> str:
        return f"/packer/{self.V}/organizations/{org_id}/projects/{project_id}"

    def list_buckets(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/buckets")

    def get_bucket(self, org_id: str, project_id: str,
                   bucket_name: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/buckets/{bucket_name}")

    def create_bucket(self, org_id: str, project_id: str,
                      bucket_name: str, description: str = "") -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/buckets",
                         {'name': bucket_name, 'description': description})

    def delete_bucket(self, org_id: str, project_id: str,
                      bucket_name: str) -> APIResponse:
        return self.delete(f"{self._p(org_id, project_id)}/buckets/{bucket_name}")

    def list_versions(self, org_id: str, project_id: str,
                      bucket_name: str) -> APIResponse:
        return self.get(
            f"{self._p(org_id, project_id)}/buckets/{bucket_name}/versions")

    def list_channels(self, org_id: str, project_id: str,
                      bucket_name: str) -> APIResponse:
        return self.get(
            f"{self._p(org_id, project_id)}/buckets/{bucket_name}/channels")

    def create_channel(self, org_id: str, project_id: str,
                       bucket_name: str, channel_name: str,
                       version_fingerprint: str = None) -> APIResponse:
        data = {'name': channel_name}
        if version_fingerprint:
            data['version_fingerprint'] = version_fingerprint
        return self.post(
            f"{self._p(org_id, project_id)}/buckets/{bucket_name}/channels", data)

    def delete_channel(self, org_id: str, project_id: str,
                       bucket_name: str, channel_name: str) -> APIResponse:
        return self.delete(
            f"{self._p(org_id, project_id)}/buckets/{bucket_name}/channels/{channel_name}")


# ============================================================
# HCP Boundary
# ============================================================

class HCPBoundaryClient(HCPCloudClient):
    V = "2021-12-21"

    def _p(self, org_id: str, project_id: str) -> str:
        return f"/boundary/{self.V}/organizations/{org_id}/projects/{project_id}"

    def list_clusters(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/clusters")

    def get_cluster(self, org_id: str, project_id: str,
                    cluster_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/clusters/{cluster_id}")

    def create_cluster(self, org_id: str, project_id: str,
                       cluster_id: str, tier: str = "STANDARD") -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/clusters",
                         {'id': cluster_id, 'tier': tier.upper()})

    def delete_cluster(self, org_id: str, project_id: str,
                       cluster_id: str) -> APIResponse:
        return self.delete(f"{self._p(org_id, project_id)}/clusters/{cluster_id}")

    @staticmethod
    def status_emoji(state: str) -> str:
        m = {'RUNNING': '🟢', 'CREATING': '🔄', 'PENDING': '⏳',
             'UPDATING': '🔄', 'DELETING': '🗑️', 'FAILED': '🔴'}
        return m.get(state, '⚪')


# ============================================================
# HCP Consul Dedicated
# ============================================================

class HCPConsulClient(HCPCloudClient):
    V = "2021-02-04"

    def _p(self, org_id: str, project_id: str) -> str:
        return f"/consul/{self.V}/organizations/{org_id}/projects/{project_id}"

    def list_clusters(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/clusters")

    def get_cluster(self, org_id: str, project_id: str,
                    cluster_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/clusters/{cluster_id}")

    def create_cluster(self, org_id: str, project_id: str,
                       cluster_id: str, hvn_id: str,
                       tier: str = "DEVELOPMENT",
                       num_servers: int = 1,
                       connect_enabled: bool = True) -> APIResponse:
        data = {
            'id': cluster_id,
            'config': {
                'tier': tier.upper(),
                'capacity_config': {'num_servers': num_servers},
                'network_config': {'network': hvn_id},
                'consul_config': {'connect_enabled': connect_enabled},
            },
        }
        return self.post(f"{self._p(org_id, project_id)}/clusters", data)

    def delete_cluster(self, org_id: str, project_id: str,
                       cluster_id: str) -> APIResponse:
        return self.delete(f"{self._p(org_id, project_id)}/clusters/{cluster_id}")

    def list_snapshots(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/snapshots")

    def get_client_config(self, org_id: str, project_id: str,
                          cluster_id: str) -> APIResponse:
        return self.get(
            f"{self._p(org_id, project_id)}/clusters/{cluster_id}/agent-config")

    @staticmethod
    def status_emoji(state: str) -> str:
        m = {'RUNNING': '🟢', 'CREATING': '🔄', 'PENDING': '⏳',
             'UPDATING': '🔄', 'DELETING': '🗑️', 'FAILED': '🔴'}
        return m.get(state, '⚪')


# ============================================================
# HCP Waypoint
# ============================================================

class HCPWaypointClient(HCPCloudClient):
    V = "2023-08-18"

    def _p(self, org_id: str, project_id: str) -> str:
        return f"/waypoint/{self.V}/organizations/{org_id}/projects/{project_id}"

    def list_templates(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/templates")

    def get_template(self, org_id: str, project_id: str,
                     template_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/templates/{template_id}")

    def create_template(self, org_id: str, project_id: str,
                        name: str, summary: str = "") -> APIResponse:
        return self.post(f"{self._p(org_id, project_id)}/templates",
                         {'name': name, 'summary': summary})

    def delete_template(self, org_id: str, project_id: str,
                        template_id: str) -> APIResponse:
        return self.delete(f"{self._p(org_id, project_id)}/templates/{template_id}")

    def list_applications(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/applications")

    def list_actions(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/actions")

    def list_action_runs(self, org_id: str, project_id: str,
                         action_id: str = None) -> APIResponse:
        params = {}
        if action_id:
            params['action_id'] = action_id
        return self.get(f"{self._p(org_id, project_id)}/action-runs", params=params)

    def list_add_on_definitions(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/add-on-definitions")

    def list_add_ons(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/add-ons")


# ============================================================
# HCP Network (HVN)
# ============================================================

class HCPNetworkClient(HCPCloudClient):
    V = "2020-09-07"

    def _p(self, org_id: str, project_id: str) -> str:
        return f"/network/{self.V}/organizations/{org_id}/projects/{project_id}"

    def list_hvns(self, org_id: str, project_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/hvns")

    def get_hvn(self, org_id: str, project_id: str, hvn_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/hvns/{hvn_id}")

    def create_hvn(self, org_id: str, project_id: str,
                   hvn_id: str, cloud_provider: str = "aws",
                   region: str = "us-west-2",
                   cidr_block: str = "172.25.16.0/20") -> APIResponse:
        data = {
            'id': hvn_id, 'cloud_provider': cloud_provider.upper(),
            'region': region, 'cidr_block': cidr_block,
        }
        return self.post(f"{self._p(org_id, project_id)}/hvns", data)

    def delete_hvn(self, org_id: str, project_id: str,
                   hvn_id: str) -> APIResponse:
        return self.delete(f"{self._p(org_id, project_id)}/hvns/{hvn_id}")

    def list_peerings(self, org_id: str, project_id: str,
                      hvn_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/hvns/{hvn_id}/peerings")

    def list_routes(self, org_id: str, project_id: str,
                    hvn_id: str) -> APIResponse:
        return self.get(f"{self._p(org_id, project_id)}/hvns/{hvn_id}/routes")

    @staticmethod
    def status_emoji(state: str) -> str:
        m = {'ACTIVE': '🟢', 'CREATING': '🔄', 'PENDING': '⏳',
             'DELETING': '🗑️', 'FAILED': '🔴'}
        return m.get(state, '⚪')


# ============================================================
# HCP Terraform (app.terraform.io — TFE bearer token)
# ============================================================

class HCPTerraformClient(BaseHTTPClient):
    """HCP Terraform / Terraform Cloud / Terraform Enterprise API client."""

    DEFAULT_URL = "https://app.terraform.io"

    def __init__(self, settings):
        base_url = (settings.hcp_terraform_url or self.DEFAULT_URL).rstrip('/')
        super().__init__(base_url=base_url,
                         token=settings.hcp_terraform_token)
        self.org = settings.hcp_terraform_org

    def _get_headers(self) -> Dict[str, str]:
        headers = super()._get_headers()
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        headers['Content-Type'] = 'application/vnd.api+json'
        return headers

    # -- Organizations --
    def list_organizations(self) -> APIResponse:
        return self.get('/api/v2/organizations')

    def get_organization(self, org: str = None) -> APIResponse:
        return self.get(f'/api/v2/organizations/{org or self.org}')

    def update_organization(self, org: str = None, email: str = None,
                           policy: str = None) -> APIResponse:
        data = {'data': {'type': 'organizations', 'attributes': {}}}
        if email:
            data['data']['attributes']['email'] = email
        if policy:
            data['data']['attributes']['collaborator-auth-policy'] = policy
        return self.patch(f'/api/v2/organizations/{org or self.org}', data)

    def get_entitlements(self, org: str = None) -> APIResponse:
        return self.get(f'/api/v2/organizations/{org or self.org}/entitlement-set')

    # -- Projects --
    def list_projects(self, org: str = None) -> APIResponse:
        return self.get(f'/api/v2/organizations/{org or self.org}/projects')

    def create_project(self, name: str, org: str = None,
                       description: str = None) -> APIResponse:
        data = {'data': {'type': 'projects', 'attributes': {'name': name}}}
        if description:
            data['data']['attributes']['description'] = description
        return self.post(f'/api/v2/organizations/{org or self.org}/projects', data)

    def delete_project(self, project_id: str) -> APIResponse:
        return self.delete(f'/api/v2/projects/{project_id}')

    # -- Workspaces --
    def list_workspaces(self, org: str = None) -> APIResponse:
        return self.get(f'/api/v2/organizations/{org or self.org}/workspaces')

    def get_workspace_by_id(self, ws_id: str) -> APIResponse:
        return self.get(f'/api/v2/workspaces/{ws_id}')

    def create_workspace(self, name: str, org: str = None,
                         auto_apply: bool = False,
                         description: str = None) -> APIResponse:
        data = {'data': {'type': 'workspaces',
                'attributes': {'name': name, 'auto-apply': auto_apply}}}
        if description:
            data['data']['attributes']['description'] = description
        return self.post(f'/api/v2/organizations/{org or self.org}/workspaces', data)

    def delete_workspace(self, ws_name: str, org: str = None) -> APIResponse:
        return self.delete(
            f'/api/v2/organizations/{org or self.org}/workspaces/{ws_name}')

    def lock_workspace(self, ws_id: str, reason: str = "") -> APIResponse:
        return self.post(f'/api/v2/workspaces/{ws_id}/actions/lock',
                         {'reason': reason})

    def unlock_workspace(self, ws_id: str) -> APIResponse:
        return self.post(f'/api/v2/workspaces/{ws_id}/actions/unlock')

    # -- Runs --
    def list_runs(self, ws_id: str) -> APIResponse:
        return self.get(f'/api/v2/workspaces/{ws_id}/runs')

    def get_run(self, run_id: str) -> APIResponse:
        return self.get(f'/api/v2/runs/{run_id}')

    def create_run(self, ws_id: str, message: str = None,
                   is_destroy: bool = False,
                   auto_apply: bool = False) -> APIResponse:
        data = {'data': {'type': 'runs',
                'attributes': {'is-destroy': is_destroy, 'auto-apply': auto_apply},
                'relationships': {'workspace': {'data': {'type': 'workspaces',
                                                         'id': ws_id}}}}}
        if message:
            data['data']['attributes']['message'] = message
        return self.post('/api/v2/runs', data)

    def apply_run(self, run_id: str, comment: str = None) -> APIResponse:
        return self.post(f'/api/v2/runs/{run_id}/actions/apply',
                         {'comment': comment} if comment else {})

    def discard_run(self, run_id: str) -> APIResponse:
        return self.post(f'/api/v2/runs/{run_id}/actions/discard')

    def cancel_run(self, run_id: str) -> APIResponse:
        return self.post(f'/api/v2/runs/{run_id}/actions/cancel')

    # -- State Versions --
    def list_state_versions(self, ws_id: str) -> APIResponse:
        return self.get(f'/api/v2/workspaces/{ws_id}/state-versions')

    # -- Variables --
    def list_variables(self, ws_id: str) -> APIResponse:
        return self.get(f'/api/v2/workspaces/{ws_id}/vars')

    def create_variable(self, ws_id: str, key: str, value: str,
                        category: str = 'terraform',
                        sensitive: bool = False, hcl: bool = False) -> APIResponse:
        data = {'data': {'type': 'vars', 'attributes': {
            'key': key, 'value': value, 'category': category,
            'sensitive': sensitive, 'hcl': hcl}}}
        return self.post(f'/api/v2/workspaces/{ws_id}/vars', data)

    def delete_variable(self, var_id: str) -> APIResponse:
        return self.delete(f'/api/v2/vars/{var_id}')

    # -- Variable Sets --
    def list_variable_sets(self, org: str = None) -> APIResponse:
        return self.get(f'/api/v2/organizations/{org or self.org}/varsets')

    def get_variable_set(self, vs_id: str) -> APIResponse:
        return self.get(f'/api/v2/varsets/{vs_id}')

    def create_variable_set(self, name: str, org: str = None,
                            description: str = None,
                            global_set: bool = False) -> APIResponse:
        data = {'data': {'type': 'varsets',
                'attributes': {'name': name, 'global': global_set}}}
        if description:
            data['data']['attributes']['description'] = description
        return self.post(f'/api/v2/organizations/{org or self.org}/varsets', data)

    def delete_variable_set(self, vs_id: str) -> APIResponse:
        return self.delete(f'/api/v2/varsets/{vs_id}')

    def list_varset_variables(self, vs_id: str) -> APIResponse:
        return self.get(f'/api/v2/varsets/{vs_id}/relationships/vars')

    def create_varset_variable(self, vs_id: str, key: str, value: str,
                               category: str = 'terraform',
                               sensitive: bool = False,
                               hcl: bool = False) -> APIResponse:
        data = {'data': {'type': 'vars', 'attributes': {
            'key': key, 'value': value, 'category': category,
            'sensitive': sensitive, 'hcl': hcl}}}
        return self.post(f'/api/v2/varsets/{vs_id}/relationships/vars', data)

    # -- Teams --
    def list_teams(self, org: str = None) -> APIResponse:
        return self.get(f'/api/v2/organizations/{org or self.org}/teams')

    def get_team(self, team_id: str) -> APIResponse:
        return self.get(f'/api/v2/teams/{team_id}')

    # -- Helpers --
    @staticmethod
    def ws_emoji(ws: Dict) -> str:
        if ws.get('attributes', {}).get('locked'):
            return '🔒'
        if ws.get('relationships', {}).get('latest-run', {}).get('data'):
            return '🟢'
        return '⚪'

    @staticmethod
    def run_emoji(status: str) -> str:
        m = {'pending': '⏳', 'plan_queued': '🔄', 'planning': '🔄',
             'planned': '📋', 'confirmed': '✅', 'apply_queued': '🔄',
             'applying': '🔄', 'applied': '🟢', 'discarded': '🗑️',
             'errored': '🔴', 'canceled': '🚫', 'force_canceled': '🚫'}
        return m.get(status, '⚪')

    def delete_with_body(self, path: str, data: Any = None) -> APIResponse:
        return self._make_request('DELETE', path, data)
