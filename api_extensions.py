"""
API Extensions for Advanced Features
Provides REST API endpoints for camera groups, SLA, downtime, maintenance, and search/filter
"""

from flask import jsonify, request
import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)


def register_advanced_apis(app, cameras, db_manager, group_manager=None, downtime_tracker=None, maintenance_scheduler=None):
    """
    Register all advanced feature API endpoints

    Args:
        app: Flask application
        cameras: Camera configuration dict
        db_manager: Database manager instance
        group_manager: CameraGroupManager instance (optional)
        downtime_tracker: DowntimeTracker instance (optional)
        maintenance_scheduler: MaintenanceScheduler instance (optional)
    """

    # ==========================================================================
    # CAMERA GROUPS APIs
    # ==========================================================================

    @app.route('/api/groups/list', methods=['GET'])
    def api_list_groups():
        """Get all camera groups"""
        try:
            if group_manager:
                groups = group_manager.get_all_groups()
                summary = group_manager.get_group_summary()

                return jsonify({
                    'success': True,
                    'groups': groups,
                    'summary': summary
                })
            else:
                # Fallback: derive groups dynamically
                groups = _derive_groups_from_cameras(cameras)
                return jsonify({
                    'success': True,
                    'groups': groups,
                    'summary': {
                        'total_cameras': len(cameras),
                        'highways': {'count': len(groups['highway'])},
                        'counties': {'count': len(groups['county'])}
                    }
                })

        except Exception as e:
            logger.error(f"Error listing groups: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/groups/<group_type>/<group_name>', methods=['GET'])
    def api_get_group_cameras(group_type, group_name):
        """Get cameras in a specific group"""
        try:
            if group_manager:
                camera_list = group_manager.get_cameras_in_group(group_type, group_name)
            else:
                groups = _derive_groups_from_cameras(cameras)
                camera_list = groups.get(group_type, {}).get(group_name, [])

            return jsonify({
                'success': True,
                'group_type': group_type,
                'group_name': group_name,
                'cameras': camera_list,
                'count': len(camera_list)
            })

        except Exception as e:
            logger.error(f"Error getting group cameras: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # ==========================================================================
    # SEARCH & FILTER APIs
    # ==========================================================================

    @app.route('/api/cameras/search', methods=['GET'])
    def api_search_cameras():
        """Search and filter cameras"""
        try:
            query = request.args.get('q', '').lower()
            status_filter = request.args.get('status', None)
            highway_filter = request.args.get('highway', None)
            county_filter = request.args.get('county', None)

            results = []

            # Get current health status for all cameras
            cursor = db_manager.conn.cursor()
            cursor.execute("""
                SELECT camera_name, current_status, response_time_ms,
                       last_check_time, consecutive_failures
                FROM camera_health_summary
            """)

            health_status = {}
            for row in cursor.fetchall():
                health_status[row[0]] = {
                    'status': row[1],
                    'response_time': row[2],
                    'last_check': row[3].isoformat() if row[3] else None,
                    'consecutive_failures': row[4]
                }
            cursor.close()

            # Filter cameras
            for camera_key, camera_data in cameras.items():
                camera_name = camera_data.get('name', '')
                camera_ip = camera_data.get('ip', '')

                # Text search
                if query and query not in camera_name.lower() and query not in camera_ip:
                    continue

                # Status filter
                status = health_status.get(camera_name, {}).get('status', 'unknown')
                if status_filter and status != status_filter:
                    continue

                # Highway filter
                if highway_filter:
                    highway = _extract_highway(camera_name)
                    if highway != highway_filter:
                        continue

                # County filter
                if county_filter:
                    county = _extract_county_from_ip(camera_ip)
                    if county != county_filter:
                        continue

                # Add to results
                results.append({
                    'name': camera_name,
                    'ip': camera_ip,
                    'status': status,
                    'response_time': health_status.get(camera_name, {}).get('response_time'),
                    'consecutive_failures': health_status.get(camera_name, {}).get('consecutive_failures', 0),
                    'highway': _extract_highway(camera_name),
                    'county': _extract_county_from_ip(camera_ip)
                })

            return jsonify({
                'success': True,
                'query': query,
                'filters': {
                    'status': status_filter,
                    'highway': highway_filter,
                    'county': county_filter
                },
                'total_results': len(results),
                'cameras': results
            })

        except Exception as e:
            logger.error(f"Error searching cameras: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # ==========================================================================
    # DOWNTIME & SLA APIs
    # ==========================================================================

    @app.route('/api/downtime/stats/<camera_name>', methods=['GET'])
    def api_get_downtime_stats(camera_name):
        """Get downtime statistics for a camera"""
        try:
            days = int(request.args.get('days', 30))

            if downtime_tracker:
                stats = downtime_tracker.get_camera_downtime_stats(camera_name, days)
            else:
                stats = _calculate_downtime_from_health_log(db_manager, camera_name, days)

            return jsonify({
                'success': True,
                'camera_name': camera_name,
                'stats': stats
            })

        except Exception as e:
            logger.error(f"Error getting downtime stats: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/sla/compliance', methods=['GET'])
    def api_get_sla_compliance():
        """Get SLA compliance for all cameras"""
        try:
            days = int(request.args.get('days', 30))
            target = float(request.args.get('target', 95.0))

            if downtime_tracker:
                compliance = downtime_tracker.get_sla_compliance(days, target)
            else:
                compliance = _calculate_sla_from_health_log(db_manager, days, target)

            # Calculate summary
            meeting_sla = sum(1 for c in compliance if c.get('meets_sla', False))
            failing_sla = len(compliance) - meeting_sla

            return jsonify({
                'success': True,
                'days_analyzed': days,
                'target_uptime': target,
                'total_cameras': len(compliance),
                'meeting_sla': meeting_sla,
                'failing_sla': failing_sla,
                'compliance': compliance
            })

        except Exception as e:
            logger.error(f"Error getting SLA compliance: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # ==========================================================================
    # MAINTENANCE APIs
    # ==========================================================================

    @app.route('/api/maintenance/upcoming', methods=['GET'])
    def api_get_upcoming_maintenance():
        """Get upcoming maintenance schedules"""
        try:
            days = int(request.args.get('days', 7))

            if maintenance_scheduler:
                schedules = maintenance_scheduler.get_upcoming_maintenance(days)
            else:
                # Fallback: return empty list
                schedules = []

            return jsonify({
                'success': True,
                'days_ahead': days,
                'total_schedules': len(schedules),
                'schedules': schedules
            })

        except Exception as e:
            logger.error(f"Error getting maintenance schedules: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/maintenance/check/<camera_name>', methods=['GET'])
    def api_check_maintenance_window(camera_name):
        """Check if camera is in maintenance window"""
        try:
            if maintenance_scheduler:
                in_maintenance, info = maintenance_scheduler.is_in_maintenance(camera_name)
            else:
                in_maintenance, info = False, None

            return jsonify({
                'success': True,
                'camera_name': camera_name,
                'in_maintenance': in_maintenance,
                'maintenance_info': info
            })

        except Exception as e:
            logger.error(f"Error checking maintenance window: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    # ==========================================================================
    # STATISTICS & SUMMARY APIs
    # ==========================================================================

    @app.route('/api/stats/summary', methods=['GET'])
    def api_get_system_summary():
        """Get comprehensive system summary"""
        try:
            cursor = db_manager.conn.cursor()

            # Get status counts
            cursor.execute("""
                SELECT current_status, COUNT(*) as count
                FROM camera_health_summary
                GROUP BY current_status
            """)

            status_counts = {}
            for row in cursor.fetchall():
                status_counts[row[0]] = row[1]

            # Get average response time
            cursor.execute("""
                SELECT AVG(CAST(response_time_ms AS FLOAT)) as avg_response
                FROM camera_health_summary
                WHERE response_time_ms IS NOT NULL AND current_status = 'online'
            """)

            avg_response = cursor.fetchone()[0] or 0

            cursor.close()

            # Group summary
            if group_manager:
                group_summary = group_manager.get_group_summary()
            else:
                groups = _derive_groups_from_cameras(cameras)
                group_summary = {
                    'highways': {'count': len(groups['highway'])},
                    'counties': {'count': len(groups['county'])}
                }

            return jsonify({
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'cameras': {
                    'total': len(cameras),
                    'online': status_counts.get('online', 0),
                    'offline': status_counts.get('offline', 0),
                    'degraded': status_counts.get('degraded', 0),
                    'unknown': status_counts.get('unknown', 0)
                },
                'performance': {
                    'avg_response_time_ms': round(avg_response, 2)
                },
                'groups': group_summary
            })

        except Exception as e:
            logger.error(f"Error getting system summary: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    logger.info("✓ Advanced API endpoints registered")


# ==========================================================================
# HELPER FUNCTIONS
# ==========================================================================

def _derive_groups_from_cameras(cameras: Dict) -> Dict[str, Dict[str, List]]:
    """Derive camera groups from camera names and IPs"""
    highway_groups = {}
    county_groups = {}

    for camera_key, camera_data in cameras.items():
        camera_name = camera_data.get('name', '')
        camera_ip = camera_data.get('ip', '')

        # Extract highway
        highway = _extract_highway(camera_name)
        if highway:
            if highway not in highway_groups:
                highway_groups[highway] = []
            highway_groups[highway].append(camera_name)

        # Extract county
        county = _extract_county_from_ip(camera_ip)
        if county:
            if county not in county_groups:
                county_groups[county] = []
            county_groups[county].append(camera_name)

    return {
        'highway': highway_groups,
        'county': county_groups
    }


def _extract_highway(camera_name: str) -> str:
    """Extract highway from camera name"""
    patterns = [r'CCTV-(I|US|SR)[\-]?(\d+)']
    for pattern in patterns:
        match = re.search(pattern, camera_name, re.IGNORECASE)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
    return None


def _extract_county_from_ip(ip: str) -> str:
    """Extract county from IP subnet"""
    if not ip:
        return 'Unknown'

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


def _calculate_downtime_from_health_log(db_manager, camera_name: str, days: int) -> Dict:
    """Calculate downtime from health log (fallback if downtime tracker not available)"""
    try:
        cursor = db_manager.conn.cursor()

        # Count offline periods
        cursor.execute("""
            SELECT COUNT(*) as offline_checks
            FROM camera_health_log
            WHERE camera_name = ?
                AND status = 'offline'
                AND check_timestamp >= DATEADD(DAY, ?, GETDATE())
        """, camera_name, -days)

        offline_checks = cursor.fetchone()[0] or 0

        # Assuming 5-minute checks, calculate downtime
        downtime_minutes = offline_checks * 5
        total_minutes = days * 1440
        uptime_pct = 100.0 - (downtime_minutes * 100.0 / total_minutes)

        cursor.close()

        return {
            'camera_name': camera_name,
            'days_analyzed': days,
            'offline_checks': offline_checks,
            'estimated_downtime_minutes': downtime_minutes,
            'uptime_percentage': round(uptime_pct, 2)
        }

    except Exception as e:
        logger.error(f"Error calculating downtime: {e}")
        return {'camera_name': camera_name, 'error': str(e)}


def _calculate_sla_from_health_log(db_manager, days: int, target: float) -> List[Dict]:
    """Calculate SLA from health log (fallback)"""
    try:
        cursor = db_manager.conn.cursor()

        cursor.execute("""
            SELECT
                camera_name,
                COUNT(*) as total_checks,
                SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_checks
            FROM camera_health_log
            WHERE check_timestamp >= DATEADD(DAY, ?, GETDATE())
            GROUP BY camera_name
        """, -days)

        results = []
        for row in cursor.fetchall():
            total = row[1]
            online = row[2]
            uptime_pct = (online * 100.0 / total) if total > 0 else 0

            results.append({
                'camera_name': row[0],
                'total_checks': total,
                'online_checks': online,
                'uptime_percentage': round(uptime_pct, 2),
                'meets_sla': uptime_pct >= target,
                'target_uptime': target
            })

        cursor.close()
        return sorted(results, key=lambda x: x['uptime_percentage'])

    except Exception as e:
        logger.error(f"Error calculating SLA: {e}")
        return []
