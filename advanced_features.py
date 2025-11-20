"""
Advanced Features Module for CCTV Tool
Handles camera groups, downtime tracking, SLA reporting, maintenance scheduling, and map view
"""

import logging
import re
import os
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class CameraGroupManager:
    """
    Manages camera grouping by highway, county, and custom categories
    Automatically derives groups from camera names
    """

    def __init__(self, db_manager, cameras: Dict[str, Dict]):
        self.db = db_manager
        self.cameras = cameras
        self._highway_groups = {}
        self._county_groups = {}
        self._custom_groups = {}
        self._initialize_groups()

    def _initialize_groups(self):
        """Automatically derive groups from camera names"""
        logger.info("Initializing camera groups...")

        for camera_key, camera_data in self.cameras.items():
            camera_name = camera_data.get('name', '')

            # Extract highway from camera name (e.g., "CCTV-I10-012.4-EB" -> "I-10")
            highway = self._extract_highway(camera_name)
            if highway:
                if highway not in self._highway_groups:
                    self._highway_groups[highway] = []
                self._highway_groups[highway].append(camera_name)

            # Extract county from IP address subnet
            county = self._extract_county_from_ip(camera_data.get('ip', ''))
            if county:
                if county not in self._county_groups:
                    self._county_groups[county] = []
                self._county_groups[county].append(camera_name)

        logger.info(f"Grouped cameras: {len(self._highway_groups)} highways, {len(self._county_groups)} counties")

    def _extract_highway(self, camera_name: str) -> Optional[str]:
        """Extract highway name from camera name"""
        # Match patterns like I10, I-10, US98, US-98, SR20, SR-20
        patterns = [
            r'CCTV-(I|US|SR)[\-]?(\d+)',  # Match I10, I-10, US98, SR20, etc.
            r'CCTV-([A-Z]{2,3}[\-]?\d+)',  # General pattern
        ]

        for pattern in patterns:
            match = re.search(pattern, camera_name, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    return f"{match.group(1)}-{match.group(2)}"
                else:
                    return match.group(1)

        return None

    def _extract_county_from_ip(self, ip: str) -> Optional[str]:
        """Extract county from IP subnet"""
        # Map IP subnets to counties (based on your network)
        if not ip:
            return None

        subnet_map = {
            '10.161': 'Escambia',
            '10.162': 'Santa Rosa',
            '10.164': 'Okaloosa',
            '10.167': 'Walton',
            '10.169': 'Holmes',
            '10.170': 'Washington',
            '10.171': 'Bay',
            '10.172': 'Bay',
            '10.173': 'Gulf',
            '10.174': 'Calhoun',
            '10.175': 'Jackson',
        }

        for subnet, county in subnet_map.items():
            if ip.startswith(subnet):
                return county

        return 'Unknown'

    def get_all_groups(self) -> Dict[str, List[str]]:
        """Get all groups organized by type"""
        return {
            'highway': self._highway_groups,
            'county': self._county_groups,
            'custom': self._custom_groups
        }

    def get_cameras_in_group(self, group_type: str, group_name: str) -> List[str]:
        """Get list of cameras in a specific group"""
        if group_type == 'highway':
            return self._highway_groups.get(group_name, [])
        elif group_type == 'county':
            return self._county_groups.get(group_name, [])
        elif group_type == 'custom':
            return self._custom_groups.get(group_name, [])
        return []

    def get_group_summary(self) -> Dict[str, Any]:
        """Get summary of all groups"""
        return {
            'total_cameras': len(self.cameras),
            'highways': {
                'count': len(self._highway_groups),
                'groups': {name: len(cams) for name, cams in self._highway_groups.items()}
            },
            'counties': {
                'count': len(self._county_groups),
                'groups': {name: len(cams) for name, cams in self._county_groups.items()}
            },
            'custom': {
                'count': len(self._custom_groups),
                'groups': {name: len(cams) for name, cams in self._custom_groups.items()}
            }
        }


class DowntimeTracker:
    """
    Tracks camera downtime for SLA reporting
    Automatically starts/ends downtime records based on health status changes
    """

    def __init__(self, db_manager):
        self.db = db_manager
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure downtime tracking tables exist"""
        try:
            cursor = self.db.conn.cursor()

            # Check if table exists
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = 'camera_downtime_log'
            """)

            if cursor.fetchone()[0] == 0:
                logger.info("Creating camera_downtime_log table...")
                # Run migration SQL
                # This will be created by the migration script
                pass

            cursor.close()
        except Exception as e:
            logger.warning(f"Could not verify downtime tables: {e}")

    def start_downtime(self, camera_name: str, camera_ip: str,
                       status_before: str, status_during: str) -> Optional[int]:
        """Start tracking downtime for a camera"""
        try:
            cursor = self.db.conn.cursor()

            # Check if already tracking downtime
            cursor.execute("""
                SELECT id FROM camera_downtime_log
                WHERE camera_name = ? AND downtime_end IS NULL
            """, camera_name)

            existing = cursor.fetchone()
            if existing:
                logger.debug(f"Already tracking downtime for {camera_name}")
                return existing[0]

            # Start new downtime record
            cursor.execute("""
                INSERT INTO camera_downtime_log
                (camera_name, camera_ip, downtime_start, status_before, status_during)
                VALUES (?, ?, GETDATE(), ?, ?)
            """, camera_name, camera_ip, status_before, status_during)

            self.db.conn.commit()

            cursor.execute("SELECT @@IDENTITY")
            downtime_id = cursor.fetchone()[0]

            logger.info(f"Started downtime tracking for {camera_name} (ID: {downtime_id})")
            cursor.close()
            return int(downtime_id)

        except Exception as e:
            logger.error(f"Error starting downtime tracking: {e}")
            return None

    def end_downtime(self, camera_name: str, recovery_method: str = 'auto',
                     mims_ticket_id: Optional[str] = None, notes: Optional[str] = None) -> bool:
        """End downtime tracking for a camera"""
        try:
            cursor = self.db.conn.cursor()

            cursor.execute("""
                UPDATE camera_downtime_log
                SET downtime_end = GETDATE(),
                    duration_minutes = DATEDIFF(MINUTE, downtime_start, GETDATE()),
                    recovery_method = ?,
                    mims_ticket_id = ?,
                    notes = ?,
                    updated_at = GETDATE()
                WHERE camera_name = ? AND downtime_end IS NULL
            """, recovery_method, mims_ticket_id, notes, camera_name)

            self.db.conn.commit()
            rows = cursor.rowcount

            if rows > 0:
                logger.info(f"Ended downtime tracking for {camera_name}")

            cursor.close()
            return rows > 0

        except Exception as e:
            logger.error(f"Error ending downtime tracking: {e}")
            return False

    def get_camera_downtime_stats(self, camera_name: str, days: int = 30) -> Dict[str, Any]:
        """Get downtime statistics for a camera"""
        try:
            cursor = self.db.conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total_incidents,
                    SUM(ISNULL(duration_minutes, 0)) as total_downtime_minutes,
                    AVG(ISNULL(duration_minutes, 0)) as avg_downtime_minutes,
                    MAX(ISNULL(duration_minutes, 0)) as max_downtime_minutes
                FROM camera_downtime_log
                WHERE camera_name = ?
                    AND downtime_start >= DATEADD(DAY, ?, GETDATE())
                    AND downtime_end IS NOT NULL
            """, camera_name, -days)

            row = cursor.fetchone()
            cursor.close()

            if row:
                # Calculate uptime percentage (assuming 1440 minutes per day)
                total_minutes = days * 1440
                downtime = row[1] or 0
                uptime_pct = 100.0 - (downtime * 100.0 / total_minutes)

                return {
                    'camera_name': camera_name,
                    'days_analyzed': days,
                    'total_incidents': row[0],
                    'total_downtime_minutes': row[1],
                    'avg_downtime_minutes': round(row[2], 2) if row[2] else 0,
                    'max_downtime_minutes': row[3] or 0,
                    'uptime_percentage': round(uptime_pct, 2)
                }

            return {'camera_name': camera_name, 'error': 'No data'}

        except Exception as e:
            logger.error(f"Error getting downtime stats: {e}")
            return {'camera_name': camera_name, 'error': str(e)}

    def get_sla_compliance(self, days: int = 30, target_uptime: float = 95.0) -> List[Dict[str, Any]]:
        """Get SLA compliance for all cameras"""
        try:
            cursor = self.db.conn.cursor()

            cursor.execute("""
                SELECT
                    camera_name,
                    COUNT(*) as total_incidents,
                    SUM(ISNULL(duration_minutes, 0)) as total_downtime_minutes,
                    100.0 - (SUM(ISNULL(duration_minutes, 0)) * 100.0 / ?) as uptime_percentage
                FROM camera_downtime_log
                WHERE downtime_start >= DATEADD(DAY, ?, GETDATE())
                    AND downtime_end IS NOT NULL
                GROUP BY camera_name
                ORDER BY uptime_percentage ASC
            """, days * 1440, -days)

            results = []
            for row in cursor.fetchall():
                uptime_pct = row[3]
                meets_sla = uptime_pct >= target_uptime

                results.append({
                    'camera_name': row[0],
                    'total_incidents': row[1],
                    'total_downtime_minutes': row[2],
                    'uptime_percentage': round(uptime_pct, 2),
                    'meets_sla': meets_sla,
                    'target_uptime': target_uptime
                })

            cursor.close()
            return results

        except Exception as e:
            logger.error(f"Error getting SLA compliance: {e}")
            return []


class MaintenanceScheduler:
    """
    Manages maintenance schedules and suppresses alerts during maintenance windows
    """

    def __init__(self, db_manager):
        self.db = db_manager

    def is_in_maintenance(self, camera_name: str, check_time: Optional[datetime] = None) -> Tuple[bool, Optional[Dict]]:
        """Check if camera is currently in a maintenance window"""
        if check_time is None:
            check_time = datetime.now()

        try:
            cursor = self.db.conn.cursor()

            cursor.execute("""
                SELECT id, description, scheduled_start, scheduled_end, maintenance_type
                FROM maintenance_schedule
                WHERE camera_name = ?
                    AND status IN ('scheduled', 'in-progress')
                    AND suppress_alerts = 1
                    AND ? BETWEEN scheduled_start AND scheduled_end
            """, camera_name, check_time)

            row = cursor.fetchone()
            cursor.close()

            if row:
                return True, {
                    'id': row[0],
                    'description': row[1],
                    'start': row[2],
                    'end': row[3],
                    'type': row[4]
                }

            return False, None

        except Exception as e:
            logger.error(f"Error checking maintenance window: {e}")
            return False, None

    def get_upcoming_maintenance(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get upcoming maintenance schedules"""
        try:
            cursor = self.db.conn.cursor()

            cursor.execute("""
                SELECT camera_name, maintenance_type, scheduled_start, scheduled_end,
                       description, technician, status
                FROM maintenance_schedule
                WHERE scheduled_start >= GETDATE()
                    AND scheduled_start <= DATEADD(DAY, ?, GETDATE())
                    AND status IN ('scheduled', 'in-progress')
                ORDER BY scheduled_start ASC
            """, days)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'camera_name': row[0],
                    'type': row[1],
                    'start': row[2].isoformat() if row[2] else None,
                    'end': row[3].isoformat() if row[3] else None,
                    'description': row[4],
                    'technician': row[5],
                    'status': row[6]
                })

            cursor.close()
            return results

        except Exception as e:
            logger.error(f"Error getting upcoming maintenance: {e}")
            return []


# Utility functions for camera name parsing
def parse_camera_name(camera_name: str) -> Dict[str, Any]:
    """
    Parse camera name to extract components
    Example: "CCTV-I10-012.4-EB" -> {"highway": "I-10", "milepost": 12.4, "direction": "EB"}
    """
    result = {
        'highway': None,
        'milepost': None,
        'direction': None,
        'raw_name': camera_name
    }

    # Pattern: CCTV-{HIGHWAY}-{MILEPOST}-{DIRECTION}
    pattern = r'CCTV-(I|US|SR)[\-]?(\d+)[\-](\d+\.?\d*)[\-]([A-Z]{1,2})'
    match = re.search(pattern, camera_name, re.IGNORECASE)

    if match:
        result['highway'] = f"{match.group(1)}-{match.group(2)}"
        result['milepost'] = float(match.group(3))
        result['direction'] = match.group(4)

    return result
