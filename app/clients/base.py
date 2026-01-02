"""
Base HTTP Client for OpenTongchi
Provides common HTTP functionality for all API clients.
"""

import json
import urllib.request
import urllib.error
import urllib.parse
import ssl
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class APIResponse:
    """Represents an API response."""
    status_code: int
    data: Any
    headers: Dict[str, str]
    error: Optional[str] = None
    
    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class BaseHTTPClient:
    """Base HTTP client with common functionality."""
    
    def __init__(self, base_url: str, token: str = "", 
                 namespace: str = "", skip_verify: bool = False):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.namespace = namespace
        self.skip_verify = skip_verify
        
        # Create SSL context
        if skip_verify:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE
        else:
            self._ssl_context = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get default headers for requests."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        return headers
    
    def _make_request(self, method: str, path: str, data: Any = None,
                      headers: Dict[str, str] = None, 
                      params: Dict[str, str] = None) -> APIResponse:
        """Make an HTTP request."""
        # Build URL
        url = f"{self.base_url}{path}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"
        
        # Prepare headers
        req_headers = self._get_headers()
        if headers:
            req_headers.update(headers)
        
        # Prepare body
        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')
        
        # Create request
        request = urllib.request.Request(
            url,
            data=body,
            headers=req_headers,
            method=method
        )
        
        try:
            if self._ssl_context:
                response = urllib.request.urlopen(request, context=self._ssl_context, timeout=30)
            else:
                response = urllib.request.urlopen(request, timeout=30)
            
            response_data = response.read().decode('utf-8')
            response_headers = dict(response.getheaders())
            
            try:
                parsed_data = json.loads(response_data) if response_data else None
            except json.JSONDecodeError:
                parsed_data = response_data
            
            return APIResponse(
                status_code=response.status,
                data=parsed_data,
                headers=response_headers
            )
        
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ""
            try:
                error_data = json.loads(error_body) if error_body else None
            except json.JSONDecodeError:
                error_data = error_body
            
            return APIResponse(
                status_code=e.code,
                data=error_data,
                headers=dict(e.headers) if e.headers else {},
                error=str(e)
            )
        
        except urllib.error.URLError as e:
            return APIResponse(
                status_code=0,
                data=None,
                headers={},
                error=f"Connection error: {e.reason}"
            )
        
        except Exception as e:
            return APIResponse(
                status_code=0,
                data=None,
                headers={},
                error=str(e)
            )
    
    def get(self, path: str, params: Dict[str, str] = None,
            headers: Dict[str, str] = None) -> APIResponse:
        """Make a GET request."""
        return self._make_request('GET', path, headers=headers, params=params)
    
    def post(self, path: str, data: Any = None,
             headers: Dict[str, str] = None) -> APIResponse:
        """Make a POST request."""
        return self._make_request('POST', path, data=data, headers=headers)
    
    def put(self, path: str, data: Any = None,
            headers: Dict[str, str] = None) -> APIResponse:
        """Make a PUT request."""
        return self._make_request('PUT', path, data=data, headers=headers)
    
    def delete(self, path: str, headers: Dict[str, str] = None) -> APIResponse:
        """Make a DELETE request."""
        return self._make_request('DELETE', path, headers=headers)
    
    def list(self, path: str, params: Dict[str, str] = None) -> APIResponse:
        """Make a LIST request (GET with list=true)."""
        params = params or {}
        params['list'] = 'true'
        return self.get(path, params=params)
