"""HTTP client for API calls to infrastructure services"""

import json
import ssl
from typing import Optional, Dict, Any, Callable
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin, urlencode

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool


class ApiError(Exception):
    """API error with status code and message"""
    def __init__(self, message: str, status_code: int = 0, response: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class HttpClient:
    """Synchronous HTTP client for API calls"""
    
    def __init__(self, base_url: str, token: str = "", 
                 namespace: str = "", skip_verify: bool = False):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.namespace = namespace
        self.skip_verify = skip_verify
        
        # Create SSL context
        if skip_verify:
            self.ssl_context = ssl.create_default_context()
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE
        else:
            self.ssl_context = None
    
    def _build_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build request headers"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["X-Vault-Token"] = self.token  # Works for OpenBao
        if self.namespace:
            headers["X-Vault-Namespace"] = self.namespace
        if extra_headers:
            headers.update(extra_headers)
        return headers
    
    def request(self, method: str, path: str, data: Optional[Dict] = None,
                params: Optional[Dict] = None, headers: Optional[Dict] = None,
                timeout: int = 30) -> Dict[str, Any]:
        """Make an HTTP request"""
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        
        if params:
            url = f"{url}?{urlencode(params)}"
        
        req_headers = self._build_headers(headers)
        body = json.dumps(data).encode() if data else None
        
        request = Request(url, data=body, headers=req_headers, method=method)
        
        try:
            if self.skip_verify:
                response = urlopen(request, timeout=timeout, context=self.ssl_context)
            else:
                response = urlopen(request, timeout=timeout)
            
            content = response.read().decode()
            if content:
                return json.loads(content)
            return {}
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise ApiError(f"HTTP {e.code}: {e.reason}", e.code, error_body)
        except URLError as e:
            raise ApiError(f"Connection error: {e.reason}")
        except json.JSONDecodeError:
            return {"raw": content}
    
    def get(self, path: str, params: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        return self.request("GET", path, params=params, **kwargs)
    
    def post(self, path: str, data: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        return self.request("POST", path, data=data, **kwargs)
    
    def put(self, path: str, data: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        return self.request("PUT", path, data=data, **kwargs)
    
    def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        return self.request("DELETE", path, **kwargs)
    
    def list(self, path: str, **kwargs) -> Dict[str, Any]:
        """LIST request (used by Vault/OpenBao)"""
        return self.request("LIST", path, **kwargs)


class AsyncRequestSignals(QObject):
    """Signals for async requests"""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class AsyncRequest(QRunnable):
    """Async HTTP request runner"""
    
    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = AsyncRequestSignals()
    
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


class AsyncHttpClient(HttpClient):
    """HTTP client with async support via Qt thread pool"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.thread_pool = QThreadPool.globalInstance()
    
    def async_request(self, method: str, path: str, 
                      on_success: Callable, on_error: Callable,
                      **kwargs):
        """Make an async HTTP request"""
        request = AsyncRequest(self.request, method, path, **kwargs)
        request.signals.finished.connect(on_success)
        request.signals.error.connect(on_error)
        self.thread_pool.start(request)
    
    def async_get(self, path: str, on_success: Callable, on_error: Callable, **kwargs):
        self.async_request("GET", path, on_success, on_error, **kwargs)
    
    def async_post(self, path: str, on_success: Callable, on_error: Callable, **kwargs):
        self.async_request("POST", path, on_success, on_error, **kwargs)
    
    def async_list(self, path: str, on_success: Callable, on_error: Callable, **kwargs):
        self.async_request("LIST", path, on_success, on_error, **kwargs)


class ConsulClient(HttpClient):
    """HTTP client specialized for Consul API"""
    
    def _build_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["X-Consul-Token"] = self.token
        if self.namespace:
            headers["X-Consul-Namespace"] = self.namespace
        if extra_headers:
            headers.update(extra_headers)
        return headers


class NomadClient(HttpClient):
    """HTTP client specialized for Nomad API"""
    
    def __init__(self, *args, region: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.region = region
    
    def _build_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["X-Nomad-Token"] = self.token
        if extra_headers:
            headers.update(extra_headers)
        return headers
    
    def request(self, method: str, path: str, data: Optional[Dict] = None,
                params: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        # Add namespace and region to params
        params = params or {}
        if self.namespace:
            params["namespace"] = self.namespace
        if self.region:
            params["region"] = self.region
        return super().request(method, path, data=data, params=params, **kwargs)


class TerraformCloudClient(HttpClient):
    """HTTP client for Terraform Cloud / HCP Terraform API"""
    
    def __init__(self, token: str = "", organization: str = ""):
        super().__init__("https://app.terraform.io", token)
        self.organization = organization
    
    def _build_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra_headers:
            headers.update(extra_headers)
        return headers
