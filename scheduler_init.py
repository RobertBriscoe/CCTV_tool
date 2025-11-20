# scheduler_init.py
"""
FDOT Snapshot/Reboot Tool - MIMS bootstrap & scheduler
------------------------------------------------------

This module provides:
- MIMS client creation and authentication
- Ticket creation for camera reboots
- Scheduler engine for automated jobs (optional)

Key functions:
- create_mims_client(username=None, password=None) -> MIMSClient
- create_reboot_ticket(...) -> (bool, Any)
- create_scheduler(...) -> SchedulerEngine (optional)
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Tuple, List
import logging
import os
import time
import threading

# Import your MIMS client
from mims_client import MIMSClient, MIMSTokenManager

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger("scheduler_init")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

# -----------------------------------------------------------------------------
# Defaults (FDOT D3 internal)
# -----------------------------------------------------------------------------
DEFAULT_BASE = os.getenv("MIMS_BASE_URL", "http://172.60.1.42:8080").rstrip("/")
DEFAULT_GROUP_ID = int(os.getenv("MIMS_GROUP_ID", "1024"))   # TransCore Network Team
DEFAULT_ISSUE_ID = int(os.getenv("MIMS_ISSUE_ID", "11"))     # "Other"
DEFAULT_WEATHER_ID = int(os.getenv("MIMS_WEATHER_ID", "2"))  # "Sunny"

# -----------------------------------------------------------------------------
# MIMS Client Factory
# -----------------------------------------------------------------------------
def create_mims_client(username: Optional[str] = None,
                       password: Optional[str] = None) -> Optional[MIMSClient]:
    """
    Build a MIMS client for the FDOT environment.
    - Prefers per-operator login (username/password) via MIMSTokenManager
    - Falls back to static token (MIMS_TOKEN) if creds not supplied
    - Uses HTTP base: http://172.60.1.42:8080 by default
    
    Returns:
        MIMSClient instance or None if creation fails
    """
    base = os.getenv("MIMS_BASE_URL", "http://172.60.1.42:8080").rstrip("/")
    verify = os.getenv("MIMS_VERIFY", "false").lower() == "true"

    try:
        # Per-operator login
        if username and password:
            logger.info(f"Creating MIMS client for operator: {username}")
            tm = MIMSTokenManager(
                base_url=base, 
                username=username, 
                password=password,
                verify=verify
            )
            return MIMSClient(
                base_url=base, 
                token=None, 
                token_manager=tm,
                verify=verify
            )

        # Fallback: static token
        static_token = os.getenv("MIMS_TOKEN")
        if static_token:
            logger.info("Creating MIMS client with static token")
            return MIMSClient(
                base_url=base, 
                token=static_token, 
                token_manager=None,
                verify=verify
            )
        
        logger.warning("No MIMS credentials provided (username/password or MIMS_TOKEN)")
        return None
        
    except Exception as e:
        logger.error(f"Failed to create MIMS client: {e}")
        return None

# -----------------------------------------------------------------------------
# Ticket Creation for Camera Reboots
# -----------------------------------------------------------------------------
def create_reboot_ticket(
    mims_client: MIMSClient,
    camera_name: str,
    cam_ip: str,
    operator: str,
    outcome: str,  # "success" or "failure"
    reason: str,
    submitting_group_id: int = DEFAULT_GROUP_ID,
    issue_id: int = DEFAULT_ISSUE_ID,
    weather_id: int = DEFAULT_WEATHER_ID
) -> Tuple[bool, Any]:
    """
    Create a MIMS ticket when an operator reboots a camera.

    Parameters
    ----------
    mims_client : MIMSClient
        An authenticated client (created via create_mims_client).
    camera_name : str
        Human-friendly name (e.g., "CCTV-I10-088.9-WB").
    cam_ip : str
        IP for exact matching in MIMS assets (preferred).
    operator : str
        MIMS username performing the action.
    outcome : str
        "success" or "failure"
    reason : str
        Why reboot was performed
    submitting_group_id, issue_id, weather_id : int
        IDs for ticket fields (defaults set for D3).

    Returns
    -------
    (success: bool, result: dict|str)
        True + response JSON on success; False + error dict on failure.
    """
    try:
        # Convert outcome to boolean
        reboot_ok = (outcome.lower() == "success")

        logger.info(f"Creating MIMS ticket for {camera_name} ({cam_ip}) - {outcome}")

        # Find the asset id (try IP first, then name)
        asset_id = mims_client.lookup_asset_id(ip=cam_ip)
        if not asset_id:
            logger.warning(f"IP lookup failed for {cam_ip}, trying name lookup...")
            asset_id = mims_client.lookup_asset_id(name=camera_name)

        # CHECK FOR EXISTING OPEN TICKETS BEFORE CREATING A NEW ONE
        logger.info(f"Checking for existing open tickets for {camera_name}...")
        existing_tickets = mims_client.get_open_tickets_for_camera(camera_name, asset_id)

        if existing_tickets:
            ticket_ids = [str(t.get('id', 'unknown')) for t in existing_tickets]
            logger.warning(f"Skipping ticket creation - {len(existing_tickets)} open ticket(s) already exist for {camera_name}: {', '.join(ticket_ids)}")
            return True, {
                "skipped": True,
                "message": f"Open ticket(s) already exist for {camera_name}",
                "existing_tickets": ticket_ids,
                "count": len(existing_tickets)
            }

        if not asset_id:
            # Camera not registered in MIMS - create ticket without asset
            logger.warning(f"Asset not found in MIMS for {camera_name} ({cam_ip}) - creating ticket without asset linkage")
            ok, result = mims_client.create_reboot_ticket_without_asset(
                camera_name=camera_name,
                camera_ip=cam_ip,
                outcome=outcome,
                reason=reason,
                submitting_group_id=submitting_group_id,
                issue_id=issue_id,
                weather_id=weather_id,
                operator=operator
            )
        else:
            logger.info(f"Found asset ID {asset_id} for {camera_name}")
            # Create the ticket with asset linkage
            ok, result = mims_client.create_reboot_ticket_for_asset(
                asset_id=asset_id,
                camera_name=camera_name,
                outcome=outcome,
                reason=reason,
                submitting_group_id=submitting_group_id,
                issue_id=issue_id,
                weather_id=weather_id,
                operator=operator
            )
        
        if ok:
            logger.info(f"✓ MIMS ticket created for {camera_name}: {result}")
        else:
            logger.error(f"✗ MIMS ticket creation failed for {camera_name}: {result}")
        
        return ok, result
        
    except Exception as e:
        logger.error(f"Exception creating MIMS ticket for {camera_name}: {e}")
        import traceback
        traceback.print_exc()
        return False, {"error": str(e)}

# -----------------------------------------------------------------------------
# Handle Camera Reboot (Wrapper for scheduler_engine.py)
# -----------------------------------------------------------------------------
def handle_camera_reboot(
    mims_client: MIMSClient,
    camera_name: str,
    cam_ip: str,
    operator: str,
    reboot_result: Dict[str, Any]
) -> Tuple[bool, Any]:
    """
    Wrapper that converts reboot_result dict to create_reboot_ticket call.
    
    Parameters
    ----------
    reboot_result : dict
        Example: {"ok": True, "reason": "Poor Video Quality"}
    """
    outcome = "success" if reboot_result.get("ok") else "failure"
    reason = reboot_result.get("reason") or "Manual reboot"
    
    return create_reboot_ticket(
        mims_client=mims_client,
        camera_name=camera_name,
        cam_ip=cam_ip,
        operator=operator,
        outcome=outcome,
        reason=reason
    )

# -----------------------------------------------------------------------------
# Scheduler Engine (Optional)
# -----------------------------------------------------------------------------
class SchedulerEngine:
    """
    Background scheduler for automated CCTV capture jobs.
    Polls database every 30 seconds for scheduled jobs.
    """
    
    def __init__(self, db_manager, storage_config, email_config):
        self.db_manager = db_manager
        self.storage_config = storage_config
        self.email_config = email_config
        self.running = False
        self.thread = None
        logger.info("Scheduler engine created")
    
    def start(self):
        """Start the scheduler in background thread"""
        if self.running:
            logger.warning("Scheduler already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler engine started")
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Scheduler engine stopped")
    
    def _run_loop(self):
        """Main scheduler loop"""
        logger.info("Scheduler loop started")
        
        while self.running:
            try:
                # Check for jobs to run
                # TODO: Implement job checking and execution
                # For now, just sleep
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                time.sleep(30)


def create_scheduler(db_manager, storage_config, email_config) -> Optional[SchedulerEngine]:
    """
    Create and start the scheduler engine.
    
    Parameters
    ----------
    db_manager : FDOTDatabaseManager
        Database manager for job storage
    storage_config : dict
        Storage configuration
    email_config : dict
        Email configuration
    
    Returns
    -------
    SchedulerEngine or None
    """
    try:
        scheduler = SchedulerEngine(db_manager, storage_config, email_config)
        scheduler.start()
        return scheduler
    except Exception as e:
        logger.error(f"Failed to create scheduler: {e}")
        return None


def start_threshold_monitor(db_manager, mims_client, threshold_n=3, window_hours=24):
    """
    Start threshold monitor for automatic ticket creation.
    
    Parameters
    ----------
    db_manager : FDOTDatabaseManager
        Database manager
    mims_client : MIMSClient
        MIMS client for ticket creation
    threshold_n : int
        Number of failures before creating ticket
    window_hours : int
        Time window for failure counting
    
    Returns
    -------
    Monitor thread or None
    """
    if not mims_client:
        logger.warning("No MIMS client provided, threshold monitor disabled")
        return None
    
    # TODO: Implement threshold monitoring
    logger.info(f"Threshold monitor would start with N={threshold_n}, window={window_hours}h")
    return None


# -----------------------------------------------------------------------------
# Backward Compatibility Shims
# -----------------------------------------------------------------------------
def build_reboot_ticket_payload(
    asset_id: int,
    camera_name: str,
    outcome: str,
    reason: str,
    submitting_group_id: int = DEFAULT_GROUP_ID,
    issue_id: int = DEFAULT_ISSUE_ID,
    weather_id: int = DEFAULT_WEATHER_ID,
    are_assets_operational: Optional[bool] = None,
    operator: Optional[str] = None,
) -> dict:
    """Build a ticket payload dict (for testing/debugging)"""
    if are_assets_operational is None:
        are_assets_operational = (outcome == "success")
    
    op_note = f" by {operator}" if operator else ""
    issue_comment = f"CCTV reboot {outcome}{op_note}: {reason} ({camera_name})"
    
    return {
        "submittingGroupId": submitting_group_id,
        "assetIds": [asset_id],
        "areAssetsOperational": are_assets_operational,
        "issueDescriptionId": issue_id,
        "issueComment": issue_comment,
        "weatherConditionId": weather_id,
        "generalComment": "Automated entry from Snapshot/Reboot Tool",
    }


def create_reboot_failure_ticket(
    mims_client: MIMSClient,
    camera_name: str,
    cam_ip: Optional[str],
    reboot_reason: str,
    operator: Optional[str] = None,
) -> Tuple[bool, Any]:
    """Legacy helper for FAILURE path (backward compatibility)"""
    return create_reboot_ticket(
        mims_client=mims_client,
        camera_name=camera_name,
        cam_ip=cam_ip,
        operator=operator or "system",
        outcome="failure",
        reason=reboot_reason
    )


# -----------------------------------------------------------------------------
# Test/Debug
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("Testing scheduler_init.py...")
    
    # Test 1: Create MIMS client
    print("\n1. Testing MIMS client creation...")
    user = input("MIMS Username: ").strip()
    pw = input("MIMS Password: ").strip()
    
    mims = create_mims_client(username=user, password=pw)
    if mims:
        print("✓ MIMS client created")
        
        # Test 2: Asset lookup
        print("\n2. Testing asset lookup...")
        test_ip = "10.164.244.68"  # CCTV-I10-012.4-EB
        test_name = "CCTV-I10-012.4-EB"
        
        asset_id = mims.lookup_asset_id(ip=test_ip)
        if asset_id:
            print(f"✓ Found asset by IP: {asset_id}")
            
            # Test 3: Create ticket
            print("\n3. Testing ticket creation...")
            ok, result = create_reboot_ticket(
                mims_client=mims,
                camera_name=test_name,
                cam_ip=test_ip,
                operator=user,
                outcome="success",
                reason="Test from console"
            )
            
            if ok:
                print(f"✓ Ticket created: {result}")
            else:
                print(f"✗ Ticket failed: {result}")
        else:
            print(f"✗ Asset not found for {test_ip}")
    else:
        print("✗ Failed to create MIMS client")