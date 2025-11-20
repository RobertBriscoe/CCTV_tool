"""
MIMS Client for FDOT Snapshot/Reboot Tool - DIAGNOSTIC VERSION
---------------------------------------------------------------
This version includes extensive logging to diagnose MIMS API responses
"""

import os
import time
import logging
from typing import Optional, Tuple, Any, Dict
import requests
import json

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
MIMS_BASE_URL = "http://172.60.1.42:8080"
TOKEN_ENDPOINT = "/oauth2/token"
TICKET_ENDPOINT = "/api/troubleTicket"

DEFAULT_GROUP_ID = 1024  # TransCore Network Team
DEFAULT_ISSUE_ID = 11    # "Other"
DEFAULT_WEATHER_ID = 2   # "Sunny"

# -----------------------------------------------------------------------------
# LOGGING (Windows-safe)
# -----------------------------------------------------------------------------
logger = logging.getLogger("mims_client")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)  # Set to DEBUG for diagnostic

# -----------------------------------------------------------------------------
# TOKEN MANAGER
# -----------------------------------------------------------------------------
class MIMSTokenManager:
    """Handles login and JWT token refresh."""

    def __init__(self, base_url: str, username: str, password: str, 
                 verify: bool = True, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify = verify
        self.timeout = timeout
        self._token: Optional[str] = None
        self._expiry: float = 0

    def get_token(self) -> str:
        """Return a valid token (login if expired)."""
        if self._token and time.time() < self._expiry:
            logger.debug(f"Using cached token (expires in {self._expiry - time.time():.0f}s)")
            return self._token
        
        logger.info(f"Fetching new token from {self.base_url}{TOKEN_ENDPOINT}")
        return self._login()

    def _login(self) -> str:
        """Authenticate against /oauth2/token and cache the JWT."""
        url = f"{self.base_url}{TOKEN_ENDPOINT}"
        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password
        }
        
        try:
            logger.info(f"Authenticating as {self.username}...")
            r = requests.post(url, data=payload, verify=self.verify, timeout=self.timeout)
            
            logger.debug(f"Token response status: {r.status_code}")
            r.raise_for_status()
            
            data = r.json()
            self._token = data.get("access_token")
            if not self._token:
                raise RuntimeError("No access_token in MIMS response")

            expires_in = int(data.get("expires_in", 3600))
            self._expiry = time.time() + expires_in - 60
            
            logger.info(f"[OK] Token acquired; expires in {expires_in}s")
            return self._token

        except requests.RequestException as e:
            logger.error(f"MIMS login failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text[:500]}")
            raise

# -----------------------------------------------------------------------------
# MAIN CLIENT
# -----------------------------------------------------------------------------
class MIMSClient:
    """Wrapper for MIMS API calls with extensive diagnostic logging."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        token_manager: Optional[MIMSTokenManager] = None,
        verify: Optional[bool] = None,
        timeout: int = 10,
    ):
        self.base_url = base_url.rstrip("/")
        self._static_token = token
        self._tm = token_manager
        self.timeout = timeout
        
        if verify is None:
            self.verify = not self.base_url.lower().startswith("http://")
        else:
            self.verify = verify
        
        logger.info(f"MIMS client initialized: {self.base_url} (verify={self.verify})")

    def _auth_header(self) -> Dict[str, str]:
        """Get authorization header with current token."""
        tok = self._static_token or (self._tm.get_token() if self._tm else None)
        if not tok:
            raise RuntimeError("No MIMS token available (user not logged in).")
        return {
            "Authorization": f"Bearer {tok}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _headers(self) -> Dict[str, str]:
        """Alias for _auth_header."""
        return self._auth_header()

    def _request(self, method: str, path: str, **kwargs) -> Tuple[bool, Any]:
        """Make an authenticated request with EXTENSIVE diagnostic logging."""
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._auth_header())
        
        try:
            logger.info(f"=== MIMS REQUEST ===")
            logger.info(f"Method: {method}")
            logger.info(f"URL: {url}")
            logger.info(f"Headers: {json.dumps({k: v[:20] + '...' if k == 'Authorization' else v for k, v in headers.items()}, indent=2)}")
            
            r = requests.request(
                method, url, 
                headers=headers, 
                verify=self.verify, 
                timeout=self.timeout, 
                **kwargs
            )
            
            logger.info(f"=== MIMS RESPONSE ===")
            logger.info(f"Status Code: {r.status_code}")
            logger.info(f"Headers: {json.dumps(dict(r.headers), indent=2)}")
            logger.info(f"Body (first 1000 chars): {r.text[:1000]}")
            
            # Handle token expiration
            if r.status_code == 401 and self._tm:
                logger.warning("Token expired (401), refreshing...")
                self._tm._expiry = 0
                headers.update(self._auth_header())
                r = requests.request(
                    method, url, 
                    headers=headers, 
                    verify=self.verify, 
                    timeout=self.timeout, 
                    **kwargs
                )
                logger.info(f"Retry response status: {r.status_code}")
            
            r.raise_for_status()
            
            # Check content type
            content_type = r.headers.get("content-type", "").lower()
            logger.debug(f"Content-Type: {content_type}")
            
            if "application/json" in content_type:
                parsed = r.json()
                logger.info(f"Parsed JSON structure: {json.dumps(parsed, indent=2)[:500]}")
                return True, parsed
            else:
                logger.warning(f"Non-JSON response!")
                logger.warning(f"Content-Type: {content_type}")
                logger.warning(f"Full body: {r.text}")
                return False, {
                    "error": "Non-JSON response", 
                    "content_type": content_type, 
                    "body": r.text[:1000]
                }
            
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if hasattr(e, 'response') else None
            body = e.response.text if hasattr(e, 'response') else str(e)
            logger.error(f"HTTP Error {status}: {method} {url}")
            logger.error(f"Response body: {body[:1000]}")
            return False, {"status_code": status, "error": body}
            
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout: {method} {url} - {e}")
            return False, {"error": "Request timeout", "details": str(e)}
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {method} {url} - {e}")
            return False, {"error": "Connection failed", "details": str(e)}
            
        except Exception as e:
            logger.error(f"Unexpected error: {method} {url} - {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, {"error": str(e)}

    def lookup_asset_id(self, ip: Optional[str] = None, name: Optional[str] = None, 
                        page_size: int = 200) -> Optional[int]:
        """Find device asset id with flexible response format handling."""
        page = 1
        target_name = (name or "").strip().lower() if name else None
        target_ip = (ip or "").strip() if ip else None

        logger.info(f"Looking up asset: ip={target_ip}, name={target_name}")

        while page <= 5:
            ok, resp = self._request("GET", f"/api/device?pageNumber={page}&pageSize={page_size}")
            
            if not ok:
                logger.error(f"Asset lookup request failed on page {page}")
                logger.error(f"Error details: {resp}")
                return None
            
            # Handle BOTH response formats
            items = None
            total_count = None
            
            if isinstance(resp, list):
                # Response is a direct array
                logger.info(f"Response is a direct array of {len(resp)} devices")
                items = resp
                total_count = len(resp)
            elif isinstance(resp, dict):
                # Response is an object with items
                items = resp.get("items", [])
                total_count = resp.get("totalCount", len(items))
                logger.info(f"Response is a dict with {len(items)} items (total: {total_count})")
            else:
                logger.error(f"Unexpected response type: {type(resp)}")
                return None
            
            if not items:
                logger.warning(f"No devices found at page {page}")
                return None
                
            # Show samples
            if page == 1 and items:
                logger.info(f"Sample devices (showing first 3):")
                for d in items[:3]:
                    logger.info(f"  - {d.get('name')} at {d.get('address')} (id={d.get('id')})")
            
            # Search for match
            for d in items:
                dname = (d.get("name") or "").lower()
                daddr = (d.get("address") or "").strip()
                d_id = d.get("id")
                
                if target_ip and daddr == target_ip:
                    logger.info(f"[OK] Found by IP: {d.get('name')} (id={d_id})")
                    return d_id
                    
                if target_name and (dname == target_name or target_name in dname):
                    logger.info(f"[OK] Found by name: {d.get('name')} (id={d_id})")
                    return d_id
            
            # Check pagination
            if isinstance(resp, list):
                # No pagination metadata, assume this is all results
                logger.warning(f"Searched all devices in response, no match found")
                return None
            elif total_count and page * page_size >= total_count:
                logger.warning(f"Searched all {total_count} devices, no match found")
                return None
            
            page += 1

        logger.warning(f"Searched 5 pages, no match found")
        return None

    def get_open_tickets_for_camera(self, camera_name: str, asset_id: Optional[int] = None) -> list:
        """
        Query for existing open tickets for a camera.

        Args:
            camera_name: Camera name to search for in ticket comments
            asset_id: Optional asset ID to filter by

        Returns:
            List of open tickets matching the camera
        """
        logger.info(f"Querying open tickets for camera: {camera_name}")

        try:
            # Query tickets - try with various filters
            # First try: Get recent tickets and filter
            ok, resp = self._request("GET", "/api/troubleTicket?pageNumber=1&pageSize=100")

            if not ok:
                logger.error(f"Failed to query tickets: {resp}")
                return []

            # Handle response format
            tickets = []
            if isinstance(resp, list):
                tickets = resp
            elif isinstance(resp, dict):
                tickets = resp.get("items", [])
            else:
                logger.error(f"Unexpected response type: {type(resp)}")
                return []

            logger.info(f"Retrieved {len(tickets)} tickets from MIMS")

            # Filter for open tickets related to this camera
            open_tickets = []
            for ticket in tickets:
                # Check if ticket is closed/resolved
                status = ticket.get("status", "").lower()
                if status in ["closed", "resolved", "completed"]:
                    continue

                # Check if this ticket is for our camera
                # Match by asset ID if available
                if asset_id:
                    ticket_assets = ticket.get("assetIds", [])
                    if asset_id in ticket_assets:
                        logger.info(f"Found open ticket #{ticket.get('id')} for asset {asset_id}")
                        open_tickets.append(ticket)
                        continue

                # Match by camera name in comments
                issue_comment = ticket.get("issueComment", "").lower()
                general_comment = ticket.get("generalComment", "").lower()

                if camera_name.lower() in issue_comment or camera_name.lower() in general_comment:
                    logger.info(f"Found open ticket #{ticket.get('id')} mentioning '{camera_name}'")
                    open_tickets.append(ticket)

            if open_tickets:
                logger.info(f"Found {len(open_tickets)} open ticket(s) for {camera_name}")
            else:
                logger.info(f"No open tickets found for {camera_name}")

            return open_tickets

        except Exception as e:
            logger.error(f"Error querying tickets: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def create_ticket(self, payload: Dict[str, Any]) -> Tuple[bool, Any]:
        """Create a new trouble ticket."""
        logger.info(f"Creating MIMS ticket for assets: {payload.get('assetIds')}")
        return self._request("POST", "/api/troubleTicket", json=payload)

    def create_reboot_ticket_for_asset(
        self,
        asset_id: int,
        camera_name: str,
        outcome: str,
        reason: str,
        submitting_group_id: int = DEFAULT_GROUP_ID,
        issue_id: int = DEFAULT_ISSUE_ID,
        weather_id: int = DEFAULT_WEATHER_ID,
        are_assets_operational: Optional[bool] = None,
        operator: Optional[str] = None,
    ) -> Tuple[bool, Any]:
        """Create a reboot ticket."""
        if are_assets_operational is None:
            are_assets_operational = (outcome == "success")
            
        op_note = f" by {operator}" if operator else ""
        
        payload = {
            "submittingGroupId": submitting_group_id,
            "assetIds": [asset_id],
            "areAssetsOperational": are_assets_operational,
            "issueDescriptionId": issue_id,
            "issueComment": f"CCTV reboot {outcome}{op_note}: {reason} ({camera_name})",
            "weatherConditionId": weather_id,
            "generalComment": "Automated entry from Snapshot/Reboot Tool",
        }
        
        return self.create_ticket(payload)

    def create_reboot_ticket_without_asset(
        self,
        camera_name: str,
        camera_ip: str,
        outcome: str,
        reason: str,
        submitting_group_id: int = DEFAULT_GROUP_ID,
        issue_id: int = DEFAULT_ISSUE_ID,
        weather_id: int = DEFAULT_WEATHER_ID,
        are_assets_operational: Optional[bool] = None,
        operator: Optional[str] = None,
    ) -> Tuple[bool, Any]:
        """Create a reboot ticket for cameras not registered in MIMS."""
        if are_assets_operational is None:
            are_assets_operational = (outcome == "success")

        op_note = f" by {operator}" if operator else ""

        # Create ticket without asset linkage - put all info in comments
        payload = {
            "submittingGroupId": submitting_group_id,
            "assetIds": [],  # Empty - camera not in MIMS asset database
            "areAssetsOperational": are_assets_operational,
            "issueDescriptionId": issue_id,
            "issueComment": f"CCTV Camera: {camera_name} (IP: {camera_ip})\nReboot {outcome}{op_note}\nReason: {reason}",
            "weatherConditionId": weather_id,
            "generalComment": f"Automated entry from CCTV Tool - Camera not registered in MIMS asset database",
        }

        logger.warning(f"Creating ticket without asset linkage for {camera_name} ({camera_ip})")
        return self.create_ticket(payload)


# -----------------------------------------------------------------------------
# DIAGNOSTIC TEST
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("="*70)
    print("MIMS CLIENT DIAGNOSTIC TEST")
    print("="*70)
    
    user = input("\nMIMS Username: ").strip()
    pw = input("MIMS Password: ").strip()

    print("\n" + "="*70)
    print("Creating MIMS client...")
    print("="*70)
    
    tm = MIMSTokenManager(
        base_url=MIMS_BASE_URL,
        username=user,
        password=pw,
        verify=False
    )
    
    mims = MIMSClient(
        base_url=MIMS_BASE_URL,
        token=None,
        token_manager=tm,
        verify=False
    )

    try:
        # Test 1: Authentication
        print("\n" + "="*70)
        print("TEST 1: Authentication")
        print("="*70)
        token = tm.get_token()
        print(f"\n[OK] Token: {token[:30]}...")

        # Test 2: Raw device API call
        print("\n" + "="*70)
        print("TEST 2: Raw /api/device call (page 1, size 5)")
        print("="*70)
        ok, resp = mims._request("GET", "/api/device?pageNumber=1&pageSize=5")
        
        if ok:
            print(f"\n[OK] API call successful")
            print(f"\nResponse type: {type(resp)}")
            print(f"\nFull response structure:")
            print(json.dumps(resp, indent=2)[:2000])
        else:
            print(f"\n[ERROR] API call failed")
            print(f"Error: {resp}")

        # Test 3: Asset lookup
        print("\n" + "="*70)
        print("TEST 3: Asset Lookup")
        print("="*70)
        test_ip = input("\nEnter camera IP to test (or press Enter for 10.164.244.89): ").strip()
        if not test_ip:
            test_ip = "10.164.244.89"
        
        print(f"\nLooking up IP: {test_ip}")
        asset_id = mims.lookup_asset_id(ip=test_ip)
        
        if asset_id:
            print(f"\n[OK] Found asset ID: {asset_id}")
        else:
            print(f"\n[ERROR] Asset not found for IP: {test_ip}")
            print("\nTrying name lookup for 'CCTV-I10-016'...")
            asset_id = mims.lookup_asset_id(name="CCTV-I10-016")
            if asset_id:
                print(f"[OK] Found by name: {asset_id}")

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()