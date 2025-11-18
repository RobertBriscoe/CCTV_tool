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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("health_monitor")


class HealthCheckManager:
    """Manages camera health checks and status tracking"""

    def __init__(self, camera_config: Dict, db_config: Dict):
        """
        Initialize health check manager

        Args:
            camera_config: Dictionary of camera configurations
            db_config: Database configuration
        """
        self.camera_config = camera_config
        self.db_config = db_config
        self.health_cache = {}  # In-memory cache for quick access
        self.lock = threading.Lock()
        self.running = False
        self.check_thread = None
        self.check_interval = int(os.getenv('HEALTH_CHECK_INTERVAL', '300'))  # 5 minutes default

        logger.info(f"HealthCheckManager initialized with {len(camera_config)} cameras")
        logger.info(f"Health check interval: {self.check_interval} seconds")

    def get_db_connection(self):
        """Create database connection"""
        try:
            conn_str = (
                f"DRIVER={{{self.db_config['driver']}}};"
                f"SERVER={self.db_config['server']};"
                f"DATABASE={self.db_config['database']};"
                f"UID={self.db_config['username']};"
                f"PWD={self.db_config['password']};"
                f"PORT=1433;"
                f"TDS_Version=7.4;"
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
        # Try different snapshot URLs for different camera vendors
        snapshot_urls = [
            "/jpegpull/snapshot",              # Cohu cameras (ONVIF GetSnapshotUri)
            "/axis-cgi/jpg/image.cgi",         # Axis cameras
            "/snapshot.jpg",                    # Generic
            "/cgi-bin/snapshot.cgi",           # Generic CGI
            "/jpg/image.jpg",                  # Axis alternative
        ]

        for path in snapshot_urls:
            try:
                url = f"http://{ip}{path}"
                response = requests.get(url, auth=(username, password), timeout=3)

                # Check if we got a valid image (>3KB and image content type)
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '').lower()
                    if len(response.content) > 3000 and 'image' in content_type:
                        logger.debug(f"Snapshot success for {ip} using {path}")

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
                logger.debug(f"Snapshot test failed for {ip}{path}: {e}")
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
