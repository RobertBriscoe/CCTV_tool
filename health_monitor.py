#!/usr/bin/env python3
"""
Camera Health Monitoring System
Tracks camera health status with ping tests, snapshot tests, and database logging
"""

import os
import time
import socket
import logging
import threading
import pyodbc
import requests
import smtplib
from requests.auth import HTTPDigestAuth
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("health_monitor")


class AlertManager:
    """Manages health alerts and notifications"""

    def __init__(self, email_config: Dict):
        """
        Initialize alert manager

        Args:
            email_config: Email configuration dictionary
        """
        self.email_config = email_config
        self.previous_status = {}  # Track previous status per camera
        self.last_alert_time = {}  # Track last offline alert time per camera
        self.alert_count_today = {}  # Track alert count per camera per day
        self.last_reset_date = datetime.now().date()  # Track when we last reset counts

        self.alert_cooldown = int(os.getenv('ALERT_COOLDOWN_MINUTES', '30'))  # 30 min default
        self.alert_threshold = int(os.getenv('ALERT_THRESHOLD_FAILURES', '3'))  # Alert after 3 failures
        self.max_daily_alerts = int(os.getenv('MAX_DAILY_ALERTS_PER_CAMERA', '3'))  # Max alerts per camera per day

        self.maintenance_emails = os.getenv('MAINTENANCE_EMAILS', '').split(',')
        self.maintenance_emails = [e.strip() for e in self.maintenance_emails if e.strip()]

        logger.info(f"AlertManager initialized (cooldown: {self.alert_cooldown}min, threshold: {self.alert_threshold}, daily limit: {self.max_daily_alerts})")

    def check_and_send_alerts(self, camera_name: str, camera_ip: str,
                               current_status: str, consecutive_failures: int):
        """
        Check if alert should be sent and send it

        ONLY sends alerts on state transitions:
        - When camera FIRST goes offline/degraded (online -> offline/degraded)
        - When camera recovers (offline/degraded -> online)

        Does NOT send repeated alerts while camera stays offline.

        Args:
            camera_name: Camera name
            camera_ip: Camera IP address
            current_status: Current health status (online/degraded/offline)
            consecutive_failures: Number of consecutive failures
        """
        previous = self.previous_status.get(camera_name, 'unknown')

        # Only alert on STATUS CHANGES, not every failed check
        if previous != current_status:
            # Camera TRANSITIONED to offline/degraded (first failure)
            if current_status in ['offline', 'degraded'] and previous not in ['offline', 'degraded', 'unknown']:
                if consecutive_failures >= self.alert_threshold:
                    logger.info(f"Camera {camera_name} transitioned from {previous} to {current_status} - sending alert")
                    self._send_offline_alert(camera_name, camera_ip, current_status, consecutive_failures)
                    self.last_alert_time[camera_name] = datetime.now()
                else:
                    logger.debug(f"Camera {camera_name} status changed but below threshold ({consecutive_failures}/{self.alert_threshold})")

            # Camera RECOVERED (came back online)
            elif current_status == 'online' and previous in ['offline', 'degraded']:
                logger.info(f"Camera {camera_name} recovered from {previous} - sending recovery alert")
                self._send_recovery_alert(camera_name, camera_ip)
        else:
            # Status unchanged - no alert needed
            if current_status in ['offline', 'degraded']:
                logger.debug(f"Camera {camera_name} still {current_status} (no alert, already notified)")

        # Update previous status
        self.previous_status[camera_name] = current_status

    def _can_send_alert(self, camera_name: str) -> bool:
        """
        Check if alert can be sent (cooldown + daily limit)

        Returns:
            True if alert can be sent, False otherwise
        """
        # Reset daily counters if it's a new day
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.alert_count_today = {}
            self.last_reset_date = today
            logger.debug("Reset daily alert counters")

        # Check daily limit
        count_today = self.alert_count_today.get(camera_name, 0)
        if count_today >= self.max_daily_alerts:
            logger.debug(f"Camera {camera_name} has reached daily alert limit ({count_today}/{self.max_daily_alerts})")
            return False

        # Check cooldown
        if camera_name in self.last_alert_time:
            elapsed = datetime.now() - self.last_alert_time[camera_name]
            if elapsed.total_seconds() < (self.alert_cooldown * 60):
                return False

        return True

    def _send_offline_alert(self, camera_name: str, camera_ip: str,
                            status: str, failures: int):
        """Send alert for offline/degraded camera"""
        if not self.maintenance_emails:
            logger.warning("No maintenance emails configured for alerts")
            return

        # Increment daily alert counter
        count_today = self.alert_count_today.get(camera_name, 0)
        count_today += 1
        self.alert_count_today[camera_name] = count_today

        subject = f"🔴 CCTV Alert: {camera_name} is {status.upper()}"

        # Add alert count to body if approaching limit
        alert_count_msg = ""
        if count_today >= self.max_daily_alerts - 1:
            alert_count_msg = f"\n⚠️  This is alert #{count_today} today for this camera (max {self.max_daily_alerts}/day).\n"

        body = f"""Camera Health Alert

Camera: {camera_name}
Status: {status.upper()}
Consecutive Failures: {failures}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{alert_count_msg}
This camera has failed {failures} consecutive health checks.

Please investigate and take appropriate action.

---
FDOT CCTV Operations Tool
Automated Health Monitoring System
"""

        self._send_email(self.maintenance_emails, subject, body)
        logger.info(f"Sent offline alert for {camera_name} (alert #{count_today} today)")

    def _send_recovery_alert(self, camera_name: str, camera_ip: str):
        """Send alert for camera recovery"""
        if not self.maintenance_emails:
            return

        subject = f"🟢 CCTV Recovery: {camera_name} is back ONLINE"
        body = f"""Camera Recovery Notice

Camera: {camera_name}
Status: ONLINE
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This camera has recovered and is now responding to health checks.

---
FDOT CCTV Operations Tool
Automated Health Monitoring System
"""

        self._send_email(self.maintenance_emails, subject, body)
        logger.info(f"Sent recovery alert for {camera_name}")

    def send_daily_summary(self, health_stats: Dict, problem_cameras: List[Dict]):
        """
        Send daily health summary email

        Args:
            health_stats: Dictionary with health statistics
            problem_cameras: List of cameras with issues
        """
        if not self.maintenance_emails:
            logger.warning("No maintenance emails configured for daily summary")
            return

        subject = f"📊 CCTV Daily Health Summary - {datetime.now().strftime('%Y-%m-%d')}"

        # Build summary body
        body = f"""CCTV Daily Health Summary
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

=== SYSTEM HEALTH ===
Total Cameras: {health_stats.get('total', 0)}
Online: {health_stats.get('online', 0)} ({health_stats.get('online_percentage', 0):.1f}%)
Degraded: {health_stats.get('degraded', 0)}
Offline: {health_stats.get('offline', 0)}
System Health: {health_stats.get('system_health_percentage', 0):.1f}%

"""

        if problem_cameras:
            body += "=== PROBLEM CAMERAS ===\n"
            for cam in problem_cameras:
                body += f"\n{cam.get('camera_name', 'Unknown')}\n"
                body += f"  Status: {cam.get('status', 'Unknown')}\n"
                body += f"  Consecutive Failures: {cam.get('consecutive_failures', 0)}\n"
                body += f"  Uptime: {cam.get('uptime_percentage', 0):.1f}%\n"
        else:
            body += "=== NO PROBLEM CAMERAS ===\nAll cameras are operating normally.\n"

        body += """
---
FDOT CCTV Operations Tool
Automated Health Monitoring System
"""

        self._send_email(self.maintenance_emails, subject, body)
        logger.info("Sent daily health summary")

    def _send_email(self, to_emails: List[str], subject: str, body: str) -> bool:
        """Send email using configured SMTP"""
        if not self.email_config.get('enabled', False):
            logger.info("Email disabled, skipping notification")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config.get('from_email', '')
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject
            msg['Date'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")

            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['smtp_username'], self.email_config['from_password'])
                server.send_message(msg)

            logger.info(f"Email sent to {', '.join(to_emails)}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class RemediationManager:
    """Manages automated camera remediation (auto-reboot with MIMS ticket)"""

    def __init__(self, reboot_callback=None):
        """
        Initialize remediation manager

        Args:
            reboot_callback: Function to call for rebooting camera
                            Signature: (camera_ip, camera_name, operator, reason) -> Dict
        """
        self.reboot_callback = reboot_callback
        self.cameras_under_remediation = {}  # camera_name -> remediation info
        self.last_ticket_time = {}  # camera_name -> last ticket timestamp
        self.auto_reboot_threshold = int(os.getenv('AUTO_REBOOT_THRESHOLD', '6'))  # 6 failures = 30 min
        self.auto_reboot_enabled = os.getenv('AUTO_REBOOT_ENABLED', 'true').lower() == 'true'
        self.ticket_cooldown_hours = int(os.getenv('TICKET_COOLDOWN_HOURS', '24'))  # 24 hours default

        logger.info(f"RemediationManager initialized (enabled: {self.auto_reboot_enabled}, threshold: {self.auto_reboot_threshold}, ticket cooldown: {self.ticket_cooldown_hours}h)")

    def check_and_remediate(self, camera_name: str, camera_ip: str,
                            status: str, consecutive_failures: int) -> bool:
        """
        Check if camera needs remediation and perform it

        Args:
            camera_name: Camera name
            camera_ip: Camera IP address
            status: Current status (online/degraded/offline)
            consecutive_failures: Number of consecutive failures

        Returns:
            True if remediation was performed, False otherwise
        """
        if not self.auto_reboot_enabled:
            return False

        # If camera is online, clear remediation state (but preserve ticket cooldown)
        if status == 'online':
            if camera_name in self.cameras_under_remediation:
                logger.info(f"Camera {camera_name} recovered - clearing remediation state")
                del self.cameras_under_remediation[camera_name]
            return False

        # Check if we're in ticket cooldown period
        if camera_name in self.last_ticket_time:
            elapsed = datetime.now() - self.last_ticket_time[camera_name]
            cooldown_seconds = self.ticket_cooldown_hours * 3600
            if elapsed.total_seconds() < cooldown_seconds:
                hours_remaining = (cooldown_seconds - elapsed.total_seconds()) / 3600
                logger.debug(f"Camera {camera_name} in ticket cooldown ({hours_remaining:.1f}h remaining)")
                return False

        # Check if already under remediation (already rebooted, waiting for maintenance)
        if camera_name in self.cameras_under_remediation:
            return False

        # Check if threshold reached for auto-reboot
        if consecutive_failures >= self.auto_reboot_threshold:
            return self._perform_remediation(camera_name, camera_ip, consecutive_failures)

        return False

    def _perform_remediation(self, camera_name: str, camera_ip: str,
                             consecutive_failures: int) -> bool:
        """
        Perform auto-reboot and create MIMS ticket

        Returns:
            True if remediation was performed
        """
        if not self.reboot_callback:
            logger.warning(f"Cannot remediate {camera_name} - no reboot callback configured")
            return False

        logger.info(f"Auto-remediating {camera_name} after {consecutive_failures} failures")

        # Record ticket creation time BEFORE attempting (prevents duplicate attempts)
        self.last_ticket_time[camera_name] = datetime.now()

        # Mark as under remediation BEFORE attempting reboot
        self.cameras_under_remediation[camera_name] = {
            'timestamp': datetime.now().isoformat(),
            'failures': consecutive_failures,
            'ip': camera_ip
        }

        try:
            # Perform reboot with MIMS ticket creation
            reason = f"Auto-remediation: Camera failed {consecutive_failures} consecutive health checks"
            result = self.reboot_callback(
                camera_ip=camera_ip,
                camera_name=camera_name,
                operator="CCTV Auto-Remediation System",
                reason=reason
            )

            if result.get('success'):
                logger.info(f"Auto-reboot successful for {camera_name}")
                if result.get('ticket_id'):
                    logger.info(f"MIMS ticket created: {result['ticket_id']}")
                    self.cameras_under_remediation[camera_name]['ticket_id'] = result['ticket_id']
            else:
                logger.error(f"Auto-reboot failed for {camera_name}: {result.get('message')}")
                # Still keep under remediation to prevent loops

            # Log the cooldown period
            logger.info(f"Camera {camera_name} entered ticket cooldown for {self.ticket_cooldown_hours} hours")

            return True

        except Exception as e:
            logger.error(f"Error during auto-remediation of {camera_name}: {e}")
            # Even on error, keep the cooldown to prevent spam
            return False

    def get_cameras_under_remediation(self) -> Dict:
        """Get all cameras currently under remediation"""
        return self.cameras_under_remediation.copy()

    def clear_remediation(self, camera_name: str, clear_ticket_cooldown: bool = False) -> bool:
        """
        Manually clear remediation state for a camera

        Args:
            camera_name: Camera name
            clear_ticket_cooldown: Also clear the ticket cooldown (allows new ticket creation)

        Returns:
            True if state was cleared
        """
        cleared = False

        if camera_name in self.cameras_under_remediation:
            del self.cameras_under_remediation[camera_name]
            logger.info(f"Cleared remediation state for {camera_name}")
            cleared = True

        if clear_ticket_cooldown and camera_name in self.last_ticket_time:
            del self.last_ticket_time[camera_name]
            logger.info(f"Cleared ticket cooldown for {camera_name}")
            cleared = True

        return cleared


class HealthCheckManager:
    """Manages camera health checks and status tracking"""

    def __init__(self, camera_config: Dict, db_config: Dict, email_config: Optional[Dict] = None,
                 reboot_callback=None):
        """
        Initialize health check manager

        Args:
            camera_config: Dictionary of camera configurations
            db_config: Database configuration
            email_config: Email configuration for alerts (optional)
            reboot_callback: Function to call for rebooting camera (optional)
        """
        self.camera_config = camera_config
        self.db_config = db_config
        self.health_cache = {}  # In-memory cache for quick access
        self.lock = threading.Lock()
        self.running = False
        self.check_thread = None
        self.check_interval = int(os.getenv('HEALTH_CHECK_INTERVAL', '300'))  # 5 minutes default

        # Initialize alert manager if email config provided
        self.alert_manager = None
        if email_config:
            self.alert_manager = AlertManager(email_config)
            logger.info("Alert manager enabled")

        # Initialize remediation manager
        self.remediation_manager = RemediationManager(reboot_callback)
        if reboot_callback:
            logger.info("Auto-remediation enabled")

        logger.info(f"HealthCheckManager initialized with {len(camera_config)} cameras")
        logger.info(f"Health check interval: {self.check_interval} seconds")

    def get_db_connection(self):
        """Create database connection"""
        try:
            conn_str = (
                f"DRIVER={{{self.db_config['driver']}}};"
                f"SERVER={self.db_config['server']},1433;"
                f"DATABASE={self.db_config['database']};"
                f"UID={self.db_config['username']};"
                f"PWD={self.db_config['password']};"
                f"TrustServerCertificate=yes;"
                f"Connection Timeout={self.db_config['timeout']};"
            )
            return pyodbc.connect(conn_str)
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return None

    def ensure_tables_exist(self):
        """Create health monitoring tables if they don't exist"""
        conn = self.get_db_connection()
        if not conn:
            logger.warning("Cannot create tables - no database connection")
            return False

        try:
            cursor = conn.cursor()

            # Create camera_health_summary table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_health_summary')
                BEGIN
                    CREATE TABLE camera_health_summary (
                        camera_name NVARCHAR(100) PRIMARY KEY,
                        camera_ip NVARCHAR(50) NOT NULL,
                        current_status NVARCHAR(20) NOT NULL,
                        last_check DATETIME2 NOT NULL,
                        last_online DATETIME2 NULL,
                        last_offline DATETIME2 NULL,
                        consecutive_failures INT NOT NULL DEFAULT 0,
                        total_checks INT NOT NULL DEFAULT 0,
                        successful_checks INT NOT NULL DEFAULT 0,
                        avg_response_time_ms INT NULL,
                        last_ping_ms INT NULL,
                        last_snapshot_ms INT NULL,
                        avg_ping_ms INT NULL,
                        avg_snapshot_ms INT NULL,
                        uptime_percentage DECIMAL(5,2) NULL,
                        updated_at DATETIME2 NOT NULL DEFAULT GETDATE()
                    )
                END
            """)
            conn.commit()

            # Create camera_health_log table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_health_log')
                BEGIN
                    CREATE TABLE camera_health_log (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        camera_name NVARCHAR(100) NOT NULL,
                        camera_ip NVARCHAR(50) NOT NULL,
                        check_timestamp DATETIME2 NOT NULL DEFAULT GETDATE(),
                        status NVARCHAR(20) NOT NULL,
                        response_time_ms INT NULL,
                        ping_response_ms INT NULL,
                        snapshot_response_ms INT NULL,
                        ping_success BIT NOT NULL DEFAULT 0,
                        snapshot_success BIT NOT NULL DEFAULT 0,
                        error_message NVARCHAR(500) NULL,
                        check_type NVARCHAR(20) NOT NULL DEFAULT 'auto'
                    )
                END
            """)
            conn.commit()

            # Add new response time columns to existing tables (migration)
            try:
                # Check and add columns to camera_health_summary if they don't exist
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('camera_health_summary') AND name = 'last_ping_ms')
                    BEGIN
                        ALTER TABLE camera_health_summary ADD last_ping_ms INT NULL
                    END
                """)
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('camera_health_summary') AND name = 'last_snapshot_ms')
                    BEGIN
                        ALTER TABLE camera_health_summary ADD last_snapshot_ms INT NULL
                    END
                """)
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('camera_health_summary') AND name = 'avg_ping_ms')
                    BEGIN
                        ALTER TABLE camera_health_summary ADD avg_ping_ms INT NULL
                    END
                """)
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('camera_health_summary') AND name = 'avg_snapshot_ms')
                    BEGIN
                        ALTER TABLE camera_health_summary ADD avg_snapshot_ms INT NULL
                    END
                """)

                # Check and add columns to camera_health_log if they don't exist
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('camera_health_log') AND name = 'ping_response_ms')
                    BEGIN
                        ALTER TABLE camera_health_log ADD ping_response_ms INT NULL
                    END
                """)
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('camera_health_log') AND name = 'snapshot_response_ms')
                    BEGIN
                        ALTER TABLE camera_health_log ADD snapshot_response_ms INT NULL
                    END
                """)
                conn.commit()
                logger.info("✓ Response time columns added/verified")
            except Exception as e:
                logger.warning(f"Could not add response time columns (may already exist): {e}")

            # Create reboot_history table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'reboot_history')
                BEGIN
                    CREATE TABLE reboot_history (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        camera_name NVARCHAR(100) NOT NULL,
                        camera_ip NVARCHAR(50) NOT NULL,
                        reboot_timestamp DATETIME2 NOT NULL DEFAULT GETDATE(),
                        operator NVARCHAR(100) NOT NULL,
                        reason NVARCHAR(500) NOT NULL,
                        outcome NVARCHAR(20) NOT NULL,
                        mims_ticket_id INT NULL,
                        reboot_type NVARCHAR(20) NOT NULL DEFAULT 'manual',
                        error_message NVARCHAR(500) NULL
                    )
                END
            """)
            conn.commit()

            cursor.close()
            conn.close()
            logger.info("Health monitoring tables verified/created")
            return True

        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            return False

    def ping_camera(self, ip: str, timeout: int = 2) -> Tuple[bool, int]:
        """
        Ping camera to check connectivity

        Args:
            ip: Camera IP address
            timeout: Ping timeout in seconds

        Returns:
            Tuple of (success: bool, response_time_ms: int)
        """
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, 80))  # Try HTTP port
            sock.close()
            response_time = int((time.time() - start_time) * 1000)

            return (result == 0, response_time)
        except Exception as e:
            logger.debug(f"Ping failed for {ip}: {e}")
            return (False, 0)

    def test_snapshot(self, ip: str, username: str = 'admin', password: str = 'Tampa234') -> Tuple[bool, int]:
        """
        Test if camera can provide snapshots - tries multiple vendors

        Args:
            ip: Camera IP address
            username: Camera username
            password: Camera password

        Returns:
            Tuple of (success: bool, response_time_ms: int)
        """
        start_time = time.time()

        # Define camera configurations to try (vendor, path, auth_type, user, pass)
        camera_configs = [
            # Cohu cameras - Basic auth
            ("Cohu", "/jpegpull/snapshot", "basic", username, password),
            # Axis cameras - Digest auth with root/root
            ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "root"),
            # Axis cameras - Digest auth with root/T@mpa234 (FDOT custom)
            ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "T@mpa234"),
            # Axis cameras - Digest auth with root/Service!1 (alternate)
            ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "Service!1"),
            # Axis cameras - Digest auth with FDOT credentials
            ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "FDOT", "FloridaD0t3!."),
            # Axis alternative paths
            ("Axis", "/jpg/image.jpg", "digest", "root", "root"),
            ("Axis", "/jpg/image.jpg", "digest", "root", "T@mpa234"),
            # Generic fallbacks
            ("Generic", "/snapshot.jpg", "basic", username, password),
            ("Generic", "/cgi-bin/snapshot.cgi", "basic", username, password),
        ]

        for vendor, path, auth_type, user, pwd in camera_configs:
            try:
                url = f"http://{ip}{path}"

                # Use appropriate auth type
                if auth_type == "digest":
                    auth = HTTPDigestAuth(user, pwd)
                else:
                    auth = (user, pwd)

                response = requests.get(url, auth=auth, timeout=3)

                # Check if we got a valid image (>3KB and image content type)
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '').lower()
                    if len(response.content) > 3000 and 'image' in content_type:
                        logger.debug(f"Snapshot success for {ip} using {vendor} ({path})")

                        # Save snapshot to disk (overwrite existing)
                        try:
                            snapshot_path = f"/var/cctv-tool-v2/static/snapshots/{ip}.jpg"
                            with open(snapshot_path, 'wb') as f:
                                f.write(response.content)
                            logger.debug(f"Snapshot saved to {snapshot_path}")
                        except Exception as save_error:
                            logger.warning(f"Failed to save snapshot for {ip}: {save_error}")

                        response_time = int((time.time() - start_time) * 1000)
                        return (True, response_time)

            except Exception as e:
                logger.debug(f"Snapshot test failed for {ip}{path} ({vendor}): {e}")
                continue

        return (False, 0)

    def check_camera_health(self, camera_name: str, camera_ip: str, check_type: str = 'auto') -> Dict:
        """
        Perform complete health check on a camera

        Args:
            camera_name: Camera name
            camera_ip: Camera IP address
            check_type: 'auto' or 'manual'

        Returns:
            Dictionary with health check results
        """
        start_time = time.time()

        # Perform ping test
        ping_success, response_time = self.ping_camera(camera_ip)

        # Perform snapshot test (only if ping succeeds)
        snapshot_success = False
        snapshot_time = 0
        ping_time = response_time
        if ping_success:
            snapshot_success, snapshot_time = self.test_snapshot(camera_ip)

        # Determine overall status
        if ping_success and snapshot_success:
            status = 'online'
        elif ping_success and not snapshot_success:
            status = 'degraded'
        else:
            status = 'offline'

        check_duration = int((time.time() - start_time) * 1000)

        result = {
            'camera_name': camera_name,
            'camera_ip': camera_ip,
            'status': status,
            'ping_success': ping_success,
            'snapshot_success': snapshot_success,
            'response_time_ms': response_time if ping_success else None,
            'ping_response_ms': ping_time,
            'snapshot_response_ms': snapshot_time if snapshot_success else None,
            'check_timestamp': datetime.now(),
            'check_type': check_type,
            'error_message': None if ping_success else 'Connection timeout'
        }

        logger.debug(f"Health check: {camera_name} ({camera_ip}) = {status} ({check_duration}ms)")

        return result

    def log_health_check(self, result: Dict) -> bool:
        """
        Log health check result to database

        Args:
            result: Health check result dictionary

        Returns:
            True if logged successfully
        """
        conn = self.get_db_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()

            # Insert into health log
            cursor.execute("""
                INSERT INTO camera_health_log
                (camera_name, camera_ip, check_timestamp, status, response_time_ms,
                 ping_response_ms, snapshot_response_ms,
                 ping_success, snapshot_success, error_message, check_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result['camera_name'],
                result['camera_ip'],
                result['check_timestamp'],
                result['status'],
                result['response_time_ms'],
                result['ping_response_ms'],
                result['snapshot_response_ms'],
                result['ping_success'],
                result['snapshot_success'],
                result['error_message'],
                result['check_type']
            ))

            # Update summary table
            cursor.execute("""
                MERGE camera_health_summary AS target
                USING (SELECT ? AS camera_name, ? AS camera_ip) AS source
                ON (target.camera_name = source.camera_name)
                WHEN MATCHED THEN
                    UPDATE SET
                        camera_ip = ?,
                        current_status = ?,
                        last_check = ?,
                        last_online = CASE WHEN ? = 'online' THEN ? ELSE target.last_online END,
                        last_offline = CASE WHEN ? = 'offline' THEN ? ELSE target.last_offline END,
                        consecutive_failures = CASE WHEN ? IN ('offline', 'degraded')
                            THEN target.consecutive_failures + 1 ELSE 0 END,
                        total_checks = target.total_checks + 1,
                        successful_checks = target.successful_checks + CASE WHEN ? = 'online' THEN 1 ELSE 0 END,
                        avg_response_time_ms = ?,
                        last_ping_ms = ?,
                        last_snapshot_ms = ?,
                        avg_ping_ms = CASE
                            WHEN target.avg_ping_ms IS NULL THEN ?
                            WHEN ? IS NOT NULL THEN (target.avg_ping_ms * 0.7 + ? * 0.3)
                            ELSE target.avg_ping_ms
                        END,
                        avg_snapshot_ms = CASE
                            WHEN target.avg_snapshot_ms IS NULL THEN ?
                            WHEN ? IS NOT NULL THEN (target.avg_snapshot_ms * 0.7 + ? * 0.3)
                            ELSE target.avg_snapshot_ms
                        END,
                        uptime_percentage = CAST(100.0 * (target.successful_checks + CASE WHEN ? = 'online' THEN 1 ELSE 0 END)
                            / (target.total_checks + 1) AS DECIMAL(5,2)),
                        updated_at = GETDATE()
                WHEN NOT MATCHED THEN
                    INSERT (camera_name, camera_ip, current_status, last_check, last_online, last_offline,
                            consecutive_failures, total_checks, successful_checks, avg_response_time_ms,
                            last_ping_ms, last_snapshot_ms, avg_ping_ms, avg_snapshot_ms, uptime_percentage)
                    VALUES (?, ?, ?, ?,
                            CASE WHEN ? = 'online' THEN ? ELSE NULL END,
                            CASE WHEN ? = 'offline' THEN ? ELSE NULL END,
                            CASE WHEN ? IN ('offline', 'degraded') THEN 1 ELSE 0 END,
                            1,
                            CASE WHEN ? = 'online' THEN 1 ELSE 0 END,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            CASE WHEN ? = 'online' THEN 100.0 ELSE 0.0 END);
            """, (
                result['camera_name'], result['camera_ip'],
                result['camera_ip'], result['status'], result['check_timestamp'],
                result['status'], result['check_timestamp'],
                result['status'], result['check_timestamp'],
                result['status'],
                result['status'],
                result['response_time_ms'],
                result['ping_response_ms'],
                result['snapshot_response_ms'],
                result['ping_response_ms'],
                result['ping_response_ms'], result['ping_response_ms'],
                result['snapshot_response_ms'],
                result['snapshot_response_ms'], result['snapshot_response_ms'],
                result['status'],
                result['camera_name'], result['camera_ip'], result['status'], result['check_timestamp'],
                result['status'], result['check_timestamp'],
                result['status'], result['check_timestamp'],
                result['status'],
                result['status'],
                result['response_time_ms'],
                result['ping_response_ms'],
                result['snapshot_response_ms'],
                result['ping_response_ms'],
                result['snapshot_response_ms'],
                result['status']
            ))

            conn.commit()
            cursor.close()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Failed to log health check: {e}")
            return False

    def get_all_camera_status(self) -> List[Dict]:
        """
        Get current health status for all cameras

        Returns:
            List of camera status dictionaries
        """
        # Return from cache if available
        with self.lock:
            if self.health_cache:
                return list(self.health_cache.values())

        # Otherwise query database
        conn = self.get_db_connection()
        if not conn:
            # Return unknown status for all cameras when DB not available
            results = []
            for camera_id, camera_data in self.camera_config.items():
                camera_name = camera_data.get('name', camera_id)
                camera_ip = camera_data.get('ip')
                if camera_ip:
                    results.append({
                        'camera_name': camera_name,
                        'camera_ip': camera_ip,
                        'status': 'unknown',
                        'last_check': None,
                        'consecutive_failures': 0,
                        'uptime_percentage': 0.0,
                        'avg_response_time_ms': None,
                        'last_ping_ms': None,
                        'last_snapshot_ms': None,
                        'avg_ping_ms': None,
                        'avg_snapshot_ms': None
                    })
            return results

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT camera_name, camera_ip, current_status, last_check,
                       consecutive_failures, uptime_percentage, avg_response_time_ms,
                       last_ping_ms, last_snapshot_ms, avg_ping_ms, avg_snapshot_ms
                FROM camera_health_summary
                ORDER BY camera_name
            """)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'camera_name': row[0],
                    'camera_ip': row[1],
                    'status': row[2],
                    'last_check': row[3].isoformat() if row[3] else None,
                    'consecutive_failures': row[4],
                    'uptime_percentage': float(row[5]) if row[5] else 0.0,
                    'avg_response_time_ms': row[6],
                    'last_ping_ms': row[7],
                    'last_snapshot_ms': row[8],
                    'avg_ping_ms': row[9],
                    'avg_snapshot_ms': row[10]
                })

            cursor.close()
            conn.close()

            # Update cache
            with self.lock:
                self.health_cache = {r['camera_name']: r for r in results}

            return results

        except Exception as e:
            logger.error(f"Failed to get camera status: {e}")
            # Return unknown status on error
            results = []
            for camera_id, camera_data in self.camera_config.items():
                camera_name = camera_data.get('name', camera_id)
                camera_ip = camera_data.get('ip')
                if camera_ip:
                    results.append({
                        'camera_name': camera_name,
                        'camera_ip': camera_ip,
                        'status': 'unknown',
                        'last_check': None,
                        'consecutive_failures': 0,
                        'uptime_percentage': 0.0,
                        'avg_response_time_ms': None,
                        'last_ping_ms': None,
                        'last_snapshot_ms': None,
                        'avg_ping_ms': None,
                        'avg_snapshot_ms': None
                    })
            return results

    def get_health_statistics(self) -> Dict:
        """
        Get overall system health statistics

        Returns:
            Dictionary with health metrics
        """
        statuses = self.get_all_camera_status()

        if not statuses:
            return {
                'total_cameras': len(self.camera_config),
                'online': 0,
                'offline': 0,
                'degraded': 0,
                'unknown': len(self.camera_config),
                'system_health_percentage': 0.0,
                'problem_cameras': 0
            }

        online = sum(1 for s in statuses if s['status'] == 'online')
        offline = sum(1 for s in statuses if s['status'] == 'offline')
        degraded = sum(1 for s in statuses if s['status'] == 'degraded')
        unknown = len(self.camera_config) - len(statuses)
        problem_cameras = sum(1 for s in statuses if s['consecutive_failures'] >= 3)

        total = len(self.camera_config)
        health_pct = (online / total * 100) if total > 0 else 0.0

        return {
            'total_cameras': total,
            'online': online,
            'offline': offline,
            'degraded': degraded,
            'unknown': unknown,
            'system_health_percentage': round(health_pct, 1),
            'problem_cameras': problem_cameras
        }

    def get_camera_history(self, camera_name: str, hours: int = 24) -> List[Dict]:
        """
        Get historical health data for a specific camera

        Args:
            camera_name: Camera name to get history for
            hours: Number of hours of history to retrieve (default 24)

        Returns:
            List of historical health check records
        """
        try:
            conn = pyodbc.connect(self.db_connection_string)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    check_timestamp,
                    status,
                    ping_response_ms,
                    snapshot_response_ms,
                    ping_success,
                    snapshot_success,
                    error_message
                FROM camera_health_log
                WHERE camera_name = ?
                AND check_timestamp >= DATEADD(hour, ?, GETDATE())
                ORDER BY check_timestamp ASC
            """, (camera_name, -hours))

            history = []
            for row in cursor.fetchall():
                history.append({
                    'timestamp': row.check_timestamp.isoformat() if row.check_timestamp else None,
                    'status': row.status,
                    'ping_ms': row.ping_response_ms,
                    'snapshot_ms': row.snapshot_response_ms,
                    'ping_success': bool(row.ping_success),
                    'snapshot_success': bool(row.snapshot_success),
                    'error': row.error_message
                })

            conn.close()
            return history

        except Exception as e:
            logger.error(f"Error getting camera history: {e}")
            return []

    def get_system_history(self, hours: int = 24, interval_minutes: int = 60) -> List[Dict]:
        """
        Get aggregated system health history over time

        Args:
            hours: Number of hours of history (default 24)
            interval_minutes: Aggregation interval in minutes (default 60)

        Returns:
            List of aggregated health statistics over time
        """
        try:
            conn = pyodbc.connect(self.db_connection_string)
            cursor = conn.cursor()

            # Aggregate by time intervals
            cursor.execute("""
                SELECT
                    DATEADD(minute,
                        (DATEDIFF(minute, '2000-01-01', check_timestamp) / ?) * ?,
                        '2000-01-01'
                    ) as time_bucket,
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_count,
                    SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) as offline_count,
                    SUM(CASE WHEN status = 'degraded' THEN 1 ELSE 0 END) as degraded_count,
                    AVG(CAST(ping_response_ms as FLOAT)) as avg_ping_ms,
                    AVG(CAST(snapshot_response_ms as FLOAT)) as avg_snapshot_ms
                FROM camera_health_log
                WHERE check_timestamp >= DATEADD(hour, ?, GETDATE())
                GROUP BY DATEADD(minute,
                    (DATEDIFF(minute, '2000-01-01', check_timestamp) / ?) * ?,
                    '2000-01-01'
                )
                ORDER BY time_bucket ASC
            """, (interval_minutes, interval_minutes, -hours, interval_minutes, interval_minutes))

            history = []
            for row in cursor.fetchall():
                total = row.online_count + row.offline_count + row.degraded_count
                health_pct = (row.online_count / total * 100) if total > 0 else 0

                history.append({
                    'timestamp': row.time_bucket.isoformat() if row.time_bucket else None,
                    'total_checks': row.total_checks,
                    'online': row.online_count,
                    'offline': row.offline_count,
                    'degraded': row.degraded_count,
                    'health_percentage': round(health_pct, 1),
                    'avg_ping_ms': round(row.avg_ping_ms, 1) if row.avg_ping_ms else None,
                    'avg_snapshot_ms': round(row.avg_snapshot_ms, 1) if row.avg_snapshot_ms else None
                })

            conn.close()
            return history

        except Exception as e:
            logger.error(f"Error getting system history: {e}")
            return []

    def export_health_csv(self, hours: int = 24) -> str:
        """
        Export health data as CSV format

        Args:
            hours: Number of hours of data to export (default 24)

        Returns:
            CSV formatted string
        """
        import csv
        from io import StringIO

        try:
            conn = pyodbc.connect(self.db_connection_string)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    camera_name,
                    camera_ip,
                    check_timestamp,
                    status,
                    ping_response_ms,
                    snapshot_response_ms,
                    ping_success,
                    snapshot_success,
                    error_message,
                    check_type
                FROM camera_health_log
                WHERE check_timestamp >= DATEADD(hour, ?, GETDATE())
                ORDER BY check_timestamp DESC
            """, (-hours,))

            output = StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'Camera Name', 'IP Address', 'Timestamp', 'Status',
                'Ping (ms)', 'Snapshot (ms)', 'Ping OK', 'Snapshot OK',
                'Error', 'Check Type'
            ])

            # Write data
            for row in cursor.fetchall():
                writer.writerow([
                    row.camera_name,
                    row.camera_ip,
                    row.check_timestamp.strftime('%Y-%m-%d %H:%M:%S') if row.check_timestamp else '',
                    row.status,
                    row.ping_response_ms or '',
                    row.snapshot_response_ms or '',
                    'Yes' if row.ping_success else 'No',
                    'Yes' if row.snapshot_success else 'No',
                    row.error_message or '',
                    row.check_type
                ])

            conn.close()
            return output.getvalue()

        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            return f"Error: {str(e)}"

    def check_all_cameras(self, check_type: str = 'auto'):
        """
        Run health checks on all cameras

        Args:
            check_type: 'auto' or 'manual'
        """
        logger.info(f"Starting {check_type} health check for {len(self.camera_config)} cameras")
        start_time = time.time()

        checked = 0
        for camera_id, camera_data in self.camera_config.items():
            camera_name = camera_data.get('name', camera_id)
            camera_ip = camera_data.get('ip')

            if not camera_ip:
                continue

            try:
                result = self.check_camera_health(camera_name, camera_ip, check_type)
                self.log_health_check(result)

                # Update cache (merge with existing data to preserve averages from database)
                with self.lock:
                    if camera_name not in self.health_cache:
                        self.health_cache[camera_name] = {}

                    self.health_cache[camera_name].update({
                        'camera_name': camera_name,
                        'camera_ip': camera_ip,
                        'status': result['status'],
                        'last_check': result['check_timestamp'].isoformat(),
                        'response_time_ms': result['response_time_ms'],
                        'ping_response_ms': result.get('ping_response_ms'),
                        'snapshot_response_ms': result.get('snapshot_response_ms')
                    })

                checked += 1

            except Exception as e:
                logger.error(f"Error checking {camera_name}: {e}")

        duration = time.time() - start_time
        logger.info(f"Health check completed: {checked}/{len(self.camera_config)} cameras in {duration:.1f}s")

        # Refresh cache from database to include averaged response times
        try:
            db_status = self.get_all_camera_status()
            if db_status:
                with self.lock:
                    for cam in db_status:
                        cam_name = cam.get('camera_name')
                        if cam_name and cam_name in self.health_cache:
                            # Update cache with database values that include averages
                            self.health_cache[cam_name].update({
                                'avg_ping_ms': cam.get('avg_ping_ms'),
                                'avg_snapshot_ms': cam.get('avg_snapshot_ms'),
                                'consecutive_failures': cam.get('consecutive_failures', 0),
                                'uptime_percentage': cam.get('uptime_percentage', 0.0)
                            })
                logger.info(f"Cache refreshed with averaged response times for {len(db_status)} cameras")

                # Check and send alerts for status changes
                if self.alert_manager:
                    for cam in db_status:
                        self.alert_manager.check_and_send_alerts(
                            cam.get('camera_name', ''),
                            cam.get('camera_ip', ''),
                            cam.get('status', 'unknown'),
                            cam.get('consecutive_failures', 0)
                        )

                # Check for auto-remediation
                if self.remediation_manager:
                    for cam in db_status:
                        self.remediation_manager.check_and_remediate(
                            cam.get('camera_name', ''),
                            cam.get('camera_ip', ''),
                            cam.get('status', 'unknown'),
                            cam.get('consecutive_failures', 0)
                        )
        except Exception as e:
            logger.error(f"Failed to refresh cache from database: {e}")

    def start_background_checks(self):
        """Start background health checking thread"""
        if self.running:
            logger.warning("Background health checks already running")
            return

        # Ensure tables exist
        self.ensure_tables_exist()

        # Load initial cache from database to get averaged response times
        try:
            db_status = self.get_all_camera_status()
            if db_status:
                with self.lock:
                    for cam in db_status:
                        cam_name = cam.get('camera_name')
                        if cam_name:
                            self.health_cache[cam_name] = cam
                logger.info(f"Initial cache loaded from database: {len(db_status)} cameras")
        except Exception as e:
            logger.warning(f"Could not load initial cache from database: {e}")

        self.running = True
        self.check_thread = threading.Thread(target=self._background_check_loop, daemon=True)
        self.check_thread.start()
        logger.info("Background health checks started")

    def stop_background_checks(self):
        """Stop background health checking thread"""
        self.running = False
        if self.check_thread:
            self.check_thread.join(timeout=5)
        logger.info("Background health checks stopped")

    def _background_check_loop(self):
        """Background thread loop for health checks"""
        logger.info(f"Background health check loop started (interval: {self.check_interval}s)")

        # Run initial check immediately
        try:
            self.check_all_cameras('auto')
        except Exception as e:
            logger.error(f"Initial health check failed: {e}")

        # Continue with periodic checks
        while self.running:
            try:
                time.sleep(self.check_interval)
                if self.running:  # Check again after sleep
                    self.check_all_cameras('auto')
            except Exception as e:
                logger.error(f"Background health check error: {e}")
                time.sleep(60)  # Wait a minute before retrying


# Import requests at module level
try:
    import requests
except ImportError:
    logger.warning("requests module not available - snapshot tests will fail")
