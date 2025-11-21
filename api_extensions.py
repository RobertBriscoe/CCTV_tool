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

    @app.route('/api/groups/create', methods=['POST'])
    def api_create_group():
        """Create a new camera group"""
        try:
            data = request.get_json()
            group_name = data.get('group_name', '').strip()
            group_type = data.get('group_type', 'custom')
            description = data.get('description', '')

            # Validation
            if not group_name:
                return jsonify({'success': False, 'error': 'Group name is required'}), 400

            if group_type not in ['highway', 'county', 'custom']:
                return jsonify({'success': False, 'error': 'Invalid group type'}), 400

            # Check if group already exists
            cursor = db_manager.conn.cursor()
            cursor.execute("""
                SELECT id FROM camera_groups WHERE group_name = ?
            """, group_name)
            if cursor.fetchone():
                cursor.close()
                return jsonify({'success': False, 'error': 'Group already exists'}), 400

            # Create group
            cursor.execute("""
                INSERT INTO camera_groups (group_name, group_type, description)
                VALUES (?, ?, ?)
            """, group_name, group_type, description)
            db_manager.conn.commit()

            # Get the created group ID
            cursor.execute("SELECT @@IDENTITY as id")
            group_id = cursor.fetchone()[0]
            cursor.close()

            logger.info(f"Created camera group: {group_name} (ID: {group_id})")

            return jsonify({
                'success': True,
                'message': 'Group created successfully',
                'group': {
                    'id': group_id,
                    'group_name': group_name,
                    'group_type': group_type,
                    'description': description
                }
            })

        except Exception as e:
            logger.error(f"Error creating group: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/groups/db/list', methods=['GET'])
    def api_list_db_groups():
        """Get all groups from database"""
        try:
            cursor = db_manager.conn.cursor()

            # Get all groups with member counts
            cursor.execute("""
                SELECT
                    g.id,
                    g.group_name,
                    g.group_type,
                    g.description,
                    g.created_at,
                    g.updated_at,
                    COUNT(m.camera_name) as member_count
                FROM camera_groups g
                LEFT JOIN camera_group_members m ON g.id = m.group_id
                GROUP BY g.id, g.group_name, g.group_type, g.description, g.created_at, g.updated_at
                ORDER BY g.created_at DESC
            """)

            groups = []
            for row in cursor.fetchall():
                groups.append({
                    'id': row[0],
                    'group_name': row[1],
                    'group_type': row[2],
                    'description': row[3],
                    'created_at': row[4].isoformat() if row[4] else None,
                    'updated_at': row[5].isoformat() if row[5] else None,
                    'member_count': row[6]
                })

            cursor.close()

            return jsonify({
                'success': True,
                'groups': groups,
                'count': len(groups)
            })

        except Exception as e:
            logger.error(f"Error listing database groups: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/groups/<int:group_id>', methods=['GET'])
    def api_get_group(group_id):
        """Get details of a specific group"""
        try:
            cursor = db_manager.conn.cursor()

            # Get group details
            cursor.execute("""
                SELECT id, group_name, group_type, description, created_at, updated_at
                FROM camera_groups
                WHERE id = ?
            """, group_id)

            row = cursor.fetchone()
            if not row:
                cursor.close()
                return jsonify({'success': False, 'error': 'Group not found'}), 404

            group = {
                'id': row[0],
                'group_name': row[1],
                'group_type': row[2],
                'description': row[3],
                'created_at': row[4].isoformat() if row[4] else None,
                'updated_at': row[5].isoformat() if row[5] else None
            }

            # Get group members
            cursor.execute("""
                SELECT camera_name, added_at
                FROM camera_group_members
                WHERE group_id = ?
                ORDER BY camera_name
            """, group_id)

            members = []
            for member_row in cursor.fetchall():
                members.append({
                    'camera_name': member_row[0],
                    'added_at': member_row[1].isoformat() if member_row[1] else None
                })

            cursor.close()

            group['members'] = members
            group['member_count'] = len(members)

            return jsonify({
                'success': True,
                'group': group
            })

        except Exception as e:
            logger.error(f"Error getting group: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/groups/<int:group_id>', methods=['PUT'])
    def api_update_group(group_id):
        """Update a camera group"""
        try:
            data = request.get_json()
            group_name = data.get('group_name', '').strip()
            group_type = data.get('group_type')
            description = data.get('description')

            cursor = db_manager.conn.cursor()

            # Check if group exists
            cursor.execute("SELECT id FROM camera_groups WHERE id = ?", group_id)
            if not cursor.fetchone():
                cursor.close()
                return jsonify({'success': False, 'error': 'Group not found'}), 404

            # Build update query
            updates = []
            params = []

            if group_name:
                # Check for duplicate name
                cursor.execute("""
                    SELECT id FROM camera_groups WHERE group_name = ? AND id != ?
                """, group_name, group_id)
                if cursor.fetchone():
                    cursor.close()
                    return jsonify({'success': False, 'error': 'Group name already exists'}), 400
                updates.append("group_name = ?")
                params.append(group_name)

            if group_type:
                if group_type not in ['highway', 'county', 'custom']:
                    cursor.close()
                    return jsonify({'success': False, 'error': 'Invalid group type'}), 400
                updates.append("group_type = ?")
                params.append(group_type)

            if description is not None:
                updates.append("description = ?")
                params.append(description)

            if not updates:
                cursor.close()
                return jsonify({'success': False, 'error': 'No fields to update'}), 400

            updates.append("updated_at = GETDATE()")
            params.append(group_id)

            # Execute update
            query = f"UPDATE camera_groups SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, *params)
            db_manager.conn.commit()
            cursor.close()

            logger.info(f"Updated camera group ID: {group_id}")

            return jsonify({
                'success': True,
                'message': 'Group updated successfully'
            })

        except Exception as e:
            logger.error(f"Error updating group: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/groups/<int:group_id>', methods=['DELETE'])
    def api_delete_group(group_id):
        """Delete a camera group"""
        try:
            cursor = db_manager.conn.cursor()

            # Check if group exists
            cursor.execute("SELECT group_name FROM camera_groups WHERE id = ?", group_id)
            row = cursor.fetchone()
            if not row:
                cursor.close()
                return jsonify({'success': False, 'error': 'Group not found'}), 404

            group_name = row[0]

            # Delete group (cascade will handle members)
            cursor.execute("DELETE FROM camera_groups WHERE id = ?", group_id)
            db_manager.conn.commit()
            cursor.close()

            logger.info(f"Deleted camera group: {group_name} (ID: {group_id})")

            return jsonify({
                'success': True,
                'message': 'Group deleted successfully'
            })

        except Exception as e:
            logger.error(f"Error deleting group: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/groups/<int:group_id>/members', methods=['POST'])
    def api_add_group_members(group_id):
        """Add cameras to a group"""
        try:
            data = request.get_json()
            camera_names = data.get('cameras', [])

            if not camera_names:
                return jsonify({'success': False, 'error': 'No cameras specified'}), 400

            cursor = db_manager.conn.cursor()

            # Check if group exists
            cursor.execute("SELECT id FROM camera_groups WHERE id = ?", group_id)
            if not cursor.fetchone():
                cursor.close()
                return jsonify({'success': False, 'error': 'Group not found'}), 404

            added_count = 0
            skipped_count = 0

            for camera_name in camera_names:
                # Check if already a member
                cursor.execute("""
                    SELECT id FROM camera_group_members
                    WHERE group_id = ? AND camera_name = ?
                """, group_id, camera_name)

                if cursor.fetchone():
                    skipped_count += 1
                    continue

                # Add member
                cursor.execute("""
                    INSERT INTO camera_group_members (group_id, camera_name)
                    VALUES (?, ?)
                """, group_id, camera_name)
                added_count += 1

            db_manager.conn.commit()
            cursor.close()

            logger.info(f"Added {added_count} cameras to group ID: {group_id}")

            return jsonify({
                'success': True,
                'message': f'Added {added_count} camera(s), {skipped_count} already existed',
                'added': added_count,
                'skipped': skipped_count
            })

        except Exception as e:
            logger.error(f"Error adding group members: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/groups/<int:group_id>/members', methods=['DELETE'])
    def api_remove_group_members(group_id):
        """Remove cameras from a group"""
        try:
            data = request.get_json()
            camera_names = data.get('cameras', [])

            if not camera_names:
                return jsonify({'success': False, 'error': 'No cameras specified'}), 400

            cursor = db_manager.conn.cursor()

            # Check if group exists
            cursor.execute("SELECT id FROM camera_groups WHERE id = ?", group_id)
            if not cursor.fetchone():
                cursor.close()
                return jsonify({'success': False, 'error': 'Group not found'}), 404

            # Remove members
            placeholders = ','.join('?' * len(camera_names))
            query = f"""
                DELETE FROM camera_group_members
                WHERE group_id = ? AND camera_name IN ({placeholders})
            """
            cursor.execute(query, group_id, *camera_names)
            removed_count = cursor.rowcount

            db_manager.conn.commit()
            cursor.close()

            logger.info(f"Removed {removed_count} cameras from group ID: {group_id}")

            return jsonify({
                'success': True,
                'message': f'Removed {removed_count} camera(s)',
                'removed': removed_count
            })

        except Exception as e:
            logger.error(f"Error removing group members: {e}")
            db_manager.conn.rollback()
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

    @app.route('/api/sla/targets', methods=['GET'])
    def api_get_sla_targets():
        """Get all SLA targets"""
        try:
            cursor = db_manager.conn.cursor()

            cursor.execute("""
                SELECT id, target_name, uptime_percentage, max_downtime_minutes_monthly,
                       description, active
                FROM sla_targets
                WHERE active = 1
                ORDER BY uptime_percentage DESC
            """)

            targets = []
            for row in cursor.fetchall():
                targets.append({
                    'id': row[0],
                    'target_name': row[1],
                    'uptime_percentage': float(row[2]),
                    'max_downtime_minutes_monthly': row[3],
                    'description': row[4],
                    'active': bool(row[5])
                })

            cursor.close()

            return jsonify({
                'success': True,
                'targets': targets
            })

        except Exception as e:
            logger.error(f"Error getting SLA targets: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/sla/violations', methods=['GET'])
    def api_get_sla_violations():
        """Get cameras violating SLA or at risk"""
        try:
            days = int(request.args.get('days', 30))
            target = float(request.args.get('target', 95.0))
            threshold = float(request.args.get('threshold', 2.0))  # Within 2% of target

            compliance = _calculate_sla_from_health_log(db_manager, days, target)

            # Cameras failing SLA
            failing = [c for c in compliance if not c.get('meets_sla', False)]

            # Cameras at risk (within threshold of target)
            at_risk = [c for c in compliance
                      if c.get('meets_sla', False) and
                      c.get('uptime_percentage', 100) < (target + threshold)]

            return jsonify({
                'success': True,
                'days_analyzed': days,
                'target_uptime': target,
                'total_failing': len(failing),
                'total_at_risk': len(at_risk),
                'failing_cameras': sorted(failing, key=lambda x: x.get('uptime_percentage', 0))[:20],
                'at_risk_cameras': sorted(at_risk, key=lambda x: x.get('uptime_percentage', 100))[:20]
            })

        except Exception as e:
            logger.error(f"Error getting SLA violations: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/sla/monthly-report', methods=['GET'])
    def api_get_monthly_sla_report():
        """Get monthly SLA compliance report"""
        try:
            cursor = db_manager.conn.cursor()

            # Get monthly compliance data from view
            cursor.execute("""
                SELECT TOP 50
                    camera_name,
                    year,
                    month,
                    downtime_incidents,
                    total_downtime_minutes,
                    avg_downtime_minutes,
                    max_downtime_minutes,
                    uptime_percentage
                FROM vw_monthly_sla_compliance
                ORDER BY year DESC, month DESC, uptime_percentage ASC
            """)

            monthly_data = []
            for row in cursor.fetchall():
                monthly_data.append({
                    'camera_name': row[0],
                    'year': row[1],
                    'month': row[2],
                    'downtime_incidents': row[3],
                    'total_downtime_minutes': row[4],
                    'avg_downtime_minutes': float(row[5]) if row[5] else 0,
                    'max_downtime_minutes': row[6],
                    'uptime_percentage': float(row[7]) if row[7] else 100.0
                })

            cursor.close()

            # Group by month
            by_month = {}
            for data in monthly_data:
                key = f"{data['year']}-{data['month']:02d}"
                if key not in by_month:
                    by_month[key] = []
                by_month[key].append(data)

            return jsonify({
                'success': True,
                'monthly_data': monthly_data,
                'by_month': by_month
            })

        except Exception as e:
            logger.error(f"Error getting monthly SLA report: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/sla/summary', methods=['GET'])
    def api_get_sla_summary():
        """Get comprehensive SLA summary with multiple targets"""
        try:
            days = int(request.args.get('days', 30))

            cursor = db_manager.conn.cursor()

            # Get SLA targets
            cursor.execute("""
                SELECT target_name, uptime_percentage
                FROM sla_targets
                WHERE active = 1
                ORDER BY uptime_percentage DESC
            """)

            targets = []
            for row in cursor.fetchall():
                targets.append({
                    'name': row[0],
                    'target': float(row[1])
                })

            cursor.close()

            # Calculate compliance for each target
            summaries = []
            for target_info in targets:
                compliance = _calculate_sla_from_health_log(db_manager, days, target_info['target'])
                meeting = sum(1 for c in compliance if c.get('meets_sla', False))
                failing = len(compliance) - meeting

                summaries.append({
                    'target_name': target_info['name'],
                    'target_percentage': target_info['target'],
                    'total_cameras': len(compliance),
                    'meeting_sla': meeting,
                    'failing_sla': failing,
                    'compliance_rate': round((meeting / len(compliance) * 100), 2) if compliance else 100.0
                })

            return jsonify({
                'success': True,
                'days_analyzed': days,
                'summaries': summaries
            })

        except Exception as e:
            logger.error(f"Error getting SLA summary: {e}")
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

    @app.route('/api/maintenance/create', methods=['POST'])
    def api_create_maintenance_window():
        """Create a new maintenance window"""
        try:
            data = request.get_json()
            camera_name = data.get('camera_name', '').strip()
            maintenance_type = data.get('maintenance_type', 'planned')
            scheduled_start = data.get('scheduled_start')
            scheduled_end = data.get('scheduled_end')
            description = data.get('description', '')
            suppress_alerts = data.get('suppress_alerts', True)
            technician = data.get('technician', '')
            vendor = data.get('vendor', '')
            created_by = data.get('created_by', 'system')

            # Validation
            if not camera_name:
                return jsonify({'success': False, 'error': 'Camera name is required'}), 400

            if not scheduled_start or not scheduled_end:
                return jsonify({'success': False, 'error': 'Start and end times are required'}), 400

            # Parse dates
            try:
                start_dt = datetime.fromisoformat(scheduled_start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(scheduled_end.replace('Z', '+00:00'))
            except:
                return jsonify({'success': False, 'error': 'Invalid date format. Use ISO format.'}), 400

            if end_dt <= start_dt:
                return jsonify({'success': False, 'error': 'End time must be after start time'}), 400

            cursor = db_manager.conn.cursor()

            # Get camera IP
            camera_ip = None
            for cam_id, cam_info in cameras.items():
                if cam_info.get('name') == camera_name or cam_id == camera_name:
                    camera_ip = cam_info.get('ip')
                    break

            # Create maintenance window
            cursor.execute("""
                INSERT INTO maintenance_schedule
                    (camera_name, camera_ip, maintenance_type, scheduled_start, scheduled_end,
                     status, suppress_alerts, description, technician, vendor, created_by)
                VALUES (?, ?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?)
            """, camera_name, camera_ip, maintenance_type, start_dt, end_dt,
                suppress_alerts, description, technician, vendor, created_by)

            db_manager.conn.commit()

            cursor.execute("SELECT @@IDENTITY as id")
            maint_id = cursor.fetchone()[0]
            cursor.close()

            logger.info(f"Created maintenance window ID {maint_id} for {camera_name}")

            return jsonify({
                'success': True,
                'message': 'Maintenance window created successfully',
                'maintenance_id': maint_id
            })

        except Exception as e:
            logger.error(f"Error creating maintenance window: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/maintenance/list', methods=['GET'])
    def api_list_maintenance_windows():
        """List all maintenance windows with optional filters"""
        try:
            status = request.args.get('status')  # scheduled, in-progress, completed, cancelled
            camera_name = request.args.get('camera_name')
            days_ahead = int(request.args.get('days_ahead', 30))
            days_back = int(request.args.get('days_back', 7))

            cursor = db_manager.conn.cursor()

            query = """
                SELECT
                    id, camera_name, camera_ip, maintenance_type,
                    scheduled_start, scheduled_end, actual_start, actual_end,
                    status, suppress_alerts, description, technician, vendor,
                    mims_ticket_id, created_by, created_at
                FROM maintenance_schedule
                WHERE scheduled_start >= DATEADD(DAY, ?, GETDATE())
                    AND scheduled_start <= DATEADD(DAY, ?, GETDATE())
            """
            params = [-days_back, days_ahead]

            if status:
                query += " AND status = ?"
                params.append(status)

            if camera_name:
                query += " AND camera_name = ?"
                params.append(camera_name)

            query += " ORDER BY scheduled_start DESC"

            cursor.execute(query, *params)

            windows = []
            for row in cursor.fetchall():
                windows.append({
                    'id': row[0],
                    'camera_name': row[1],
                    'camera_ip': row[2],
                    'maintenance_type': row[3],
                    'scheduled_start': row[4].isoformat() if row[4] else None,
                    'scheduled_end': row[5].isoformat() if row[5] else None,
                    'actual_start': row[6].isoformat() if row[6] else None,
                    'actual_end': row[7].isoformat() if row[7] else None,
                    'status': row[8],
                    'suppress_alerts': bool(row[9]),
                    'description': row[10],
                    'technician': row[11],
                    'vendor': row[12],
                    'mims_ticket_id': row[13],
                    'created_by': row[14],
                    'created_at': row[15].isoformat() if row[15] else None
                })

            cursor.close()

            return jsonify({
                'success': True,
                'count': len(windows),
                'windows': windows
            })

        except Exception as e:
            logger.error(f"Error listing maintenance windows: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/maintenance/<int:window_id>', methods=['GET'])
    def api_get_maintenance_window(window_id):
        """Get specific maintenance window details"""
        try:
            cursor = db_manager.conn.cursor()

            cursor.execute("""
                SELECT
                    id, camera_name, camera_ip, maintenance_type,
                    scheduled_start, scheduled_end, actual_start, actual_end,
                    status, suppress_alerts, description, technician, vendor,
                    mims_ticket_id, notes, created_by, created_at, updated_at
                FROM maintenance_schedule
                WHERE id = ?
            """, window_id)

            row = cursor.fetchone()
            if not row:
                cursor.close()
                return jsonify({'success': False, 'error': 'Maintenance window not found'}), 404

            window = {
                'id': row[0],
                'camera_name': row[1],
                'camera_ip': row[2],
                'maintenance_type': row[3],
                'scheduled_start': row[4].isoformat() if row[4] else None,
                'scheduled_end': row[5].isoformat() if row[5] else None,
                'actual_start': row[6].isoformat() if row[6] else None,
                'actual_end': row[7].isoformat() if row[7] else None,
                'status': row[8],
                'suppress_alerts': bool(row[9]),
                'description': row[10],
                'technician': row[11],
                'vendor': row[12],
                'mims_ticket_id': row[13],
                'notes': row[14],
                'created_by': row[15],
                'created_at': row[16].isoformat() if row[16] else None,
                'updated_at': row[17].isoformat() if row[17] else None
            }

            cursor.close()

            return jsonify({
                'success': True,
                'window': window
            })

        except Exception as e:
            logger.error(f"Error getting maintenance window: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/maintenance/<int:window_id>', methods=['PUT'])
    def api_update_maintenance_window(window_id):
        """Update maintenance window"""
        try:
            data = request.get_json()

            # Build dynamic UPDATE query
            update_fields = []
            params = []

            field_map = {
                'maintenance_type': 'maintenance_type',
                'scheduled_start': 'scheduled_start',
                'scheduled_end': 'scheduled_end',
                'actual_start': 'actual_start',
                'actual_end': 'actual_end',
                'status': 'status',
                'suppress_alerts': 'suppress_alerts',
                'description': 'description',
                'technician': 'technician',
                'vendor': 'vendor',
                'mims_ticket_id': 'mims_ticket_id',
                'notes': 'notes'
            }

            for api_field, db_field in field_map.items():
                if api_field in data:
                    value = data[api_field]
                    # Parse datetime fields
                    if api_field in ['scheduled_start', 'scheduled_end', 'actual_start', 'actual_end'] and value:
                        try:
                            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        except:
                            return jsonify({'success': False, 'error': f'Invalid date format for {api_field}'}), 400
                    update_fields.append(f"{db_field} = ?")
                    params.append(value)

            if not update_fields:
                return jsonify({'success': False, 'error': 'No fields to update'}), 400

            # Add updated_at
            update_fields.append("updated_at = GETDATE()")
            params.append(window_id)

            cursor = db_manager.conn.cursor()

            # Check if window exists
            cursor.execute("SELECT id FROM maintenance_schedule WHERE id = ?", window_id)
            if not cursor.fetchone():
                cursor.close()
                return jsonify({'success': False, 'error': 'Maintenance window not found'}), 404

            # Update
            query = f"UPDATE maintenance_schedule SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, *params)
            db_manager.conn.commit()
            cursor.close()

            logger.info(f"Updated maintenance window ID: {window_id}")

            return jsonify({
                'success': True,
                'message': 'Maintenance window updated successfully'
            })

        except Exception as e:
            logger.error(f"Error updating maintenance window: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/maintenance/<int:window_id>', methods=['DELETE'])
    def api_delete_maintenance_window(window_id):
        """Delete maintenance window"""
        try:
            cursor = db_manager.conn.cursor()

            # Check if exists
            cursor.execute("SELECT camera_name FROM maintenance_schedule WHERE id = ?", window_id)
            row = cursor.fetchone()
            if not row:
                cursor.close()
                return jsonify({'success': False, 'error': 'Maintenance window not found'}), 404

            camera_name = row[0]

            # Delete
            cursor.execute("DELETE FROM maintenance_schedule WHERE id = ?", window_id)
            db_manager.conn.commit()
            cursor.close()

            logger.info(f"Deleted maintenance window ID {window_id} for {camera_name}")

            return jsonify({
                'success': True,
                'message': 'Maintenance window deleted successfully'
            })

        except Exception as e:
            logger.error(f"Error deleting maintenance window: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    # ==========================================================================
    # DOWNTIME TRACKING APIs (Extended)
    # ==========================================================================

    @app.route('/api/downtime/current', methods=['GET'])
    def api_get_current_downtime():
        """Get all cameras currently experiencing downtime"""
        try:
            cursor = db_manager.conn.cursor()

            cursor.execute("""
                SELECT
                    camera_name, camera_ip, downtime_start,
                    DATEDIFF(MINUTE, downtime_start, GETDATE()) as duration_minutes,
                    status_before, status_during
                FROM camera_downtime_log
                WHERE downtime_end IS NULL
                ORDER BY downtime_start ASC
            """)

            downtimes = []
            for row in cursor.fetchall():
                downtimes.append({
                    'camera_name': row[0],
                    'camera_ip': row[1],
                    'downtime_start': row[2].isoformat() if row[2] else None,
                    'duration_minutes': row[3],
                    'status_before': row[4],
                    'status_during': row[5]
                })

            cursor.close()

            return jsonify({
                'success': True,
                'count': len(downtimes),
                'downtimes': downtimes
            })

        except Exception as e:
            logger.error(f"Error getting current downtime: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/downtime/history', methods=['GET'])
    def api_get_downtime_history():
        """Get downtime history for cameras"""
        try:
            days = int(request.args.get('days', 30))
            camera_name = request.args.get('camera_name')

            cursor = db_manager.conn.cursor()

            query = """
                SELECT
                    camera_name, camera_ip, downtime_start, downtime_end,
                    duration_minutes, status_before, status_during,
                    recovery_method, mims_ticket_id
                FROM camera_downtime_log
                WHERE downtime_start >= DATEADD(DAY, ?, GETDATE())
                    AND downtime_end IS NOT NULL
            """
            params = [-days]

            if camera_name:
                query += " AND camera_name = ?"
                params.append(camera_name)

            query += " ORDER BY downtime_start DESC"

            cursor.execute(query, *params)

            history = []
            for row in cursor.fetchall():
                history.append({
                    'camera_name': row[0],
                    'camera_ip': row[1],
                    'downtime_start': row[2].isoformat() if row[2] else None,
                    'downtime_end': row[3].isoformat() if row[3] else None,
                    'duration_minutes': row[4],
                    'status_before': row[5],
                    'status_during': row[6],
                    'recovery_method': row[7],
                    'mims_ticket_id': row[8]
                })

            cursor.close()

            return jsonify({
                'success': True,
                'days_analyzed': days,
                'count': len(history),
                'history': history
            })

        except Exception as e:
            logger.error(f"Error getting downtime history: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/downtime/summary', methods=['GET'])
    def api_get_downtime_summary():
        """Get downtime summary statistics"""
        try:
            days = int(request.args.get('days', 30))

            cursor = db_manager.conn.cursor()

            # Total incidents and duration
            cursor.execute("""
                SELECT
                    COUNT(*) as total_incidents,
                    SUM(duration_minutes) as total_downtime_minutes,
                    AVG(CAST(duration_minutes AS FLOAT)) as avg_downtime_minutes,
                    MAX(duration_minutes) as max_downtime_minutes
                FROM camera_downtime_log
                WHERE downtime_start >= DATEADD(DAY, ?, GETDATE())
                    AND downtime_end IS NOT NULL
            """, -days)

            row = cursor.fetchone()
            total_incidents = row[0] or 0
            total_downtime = row[1] or 0
            avg_downtime = round(row[2], 2) if row[2] else 0
            max_downtime = row[3] or 0

            # Top cameras by downtime
            cursor.execute("""
                SELECT TOP 10
                    camera_name,
                    COUNT(*) as incident_count,
                    SUM(duration_minutes) as total_minutes
                FROM camera_downtime_log
                WHERE downtime_start >= DATEADD(DAY, ?, GETDATE())
                    AND downtime_end IS NOT NULL
                GROUP BY camera_name
                ORDER BY total_minutes DESC
            """, -days)

            top_cameras = []
            for row in cursor.fetchall():
                top_cameras.append({
                    'camera_name': row[0],
                    'incident_count': row[1],
                    'total_downtime_minutes': row[2]
                })

            # Currently down
            cursor.execute("""
                SELECT COUNT(*)
                FROM camera_downtime_log
                WHERE downtime_end IS NULL
            """)
            currently_down = cursor.fetchone()[0]

            cursor.close()

            return jsonify({
                'success': True,
                'days_analyzed': days,
                'summary': {
                    'total_incidents': total_incidents,
                    'total_downtime_minutes': total_downtime,
                    'total_downtime_hours': round(total_downtime / 60.0, 2),
                    'avg_downtime_minutes': avg_downtime,
                    'max_downtime_minutes': max_downtime,
                    'currently_down': currently_down
                },
                'top_cameras': top_cameras
            })

        except Exception as e:
            logger.error(f"Error getting downtime summary: {e}")
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

    # ==========================================================================
    # PHASE 5: ALERTING & NOTIFICATIONS APIs
    # ==========================================================================

    @app.route('/api/alerts/rules', methods=['GET'])
    def api_get_alert_rules():
        """Get all alert rules"""
        try:
            cursor = db_manager.conn.cursor()

            # Get filter parameters
            enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'
            rule_type = request.args.get('type')

            query = """
                SELECT id, rule_name, rule_type, description,
                       threshold_value, threshold_operator, evaluation_window_minutes,
                       applies_to, camera_name, group_id,
                       severity, enabled, suppress_during_maintenance,
                       rate_limit_minutes, notification_channels,
                       email_recipients, webhook_url,
                       escalation_enabled, escalation_after_minutes, escalation_recipients,
                       created_by, created_at, updated_at
                FROM alert_rules
                WHERE 1=1
            """

            params = []
            if enabled_only:
                query += " AND enabled = 1"
            if rule_type:
                query += " AND rule_type = ?"
                params.append(rule_type)

            query += " ORDER BY severity DESC, created_at DESC"

            cursor.execute(query, params)

            rules = []
            for row in cursor.fetchall():
                rules.append({
                    'id': row[0],
                    'rule_name': row[1],
                    'rule_type': row[2],
                    'description': row[3],
                    'threshold_value': float(row[4]) if row[4] else None,
                    'threshold_operator': row[5],
                    'evaluation_window_minutes': row[6],
                    'applies_to': row[7],
                    'camera_name': row[8],
                    'group_id': row[9],
                    'severity': row[10],
                    'enabled': bool(row[11]),
                    'suppress_during_maintenance': bool(row[12]),
                    'rate_limit_minutes': row[13],
                    'notification_channels': row[14],
                    'email_recipients': row[15],
                    'webhook_url': row[16],
                    'escalation_enabled': bool(row[17]),
                    'escalation_after_minutes': row[18],
                    'escalation_recipients': row[19],
                    'created_by': row[20],
                    'created_at': row[21].isoformat() if row[21] else None,
                    'updated_at': row[22].isoformat() if row[22] else None
                })

            cursor.close()
            return jsonify({'success': True, 'rules': rules})

        except Exception as e:
            logger.error(f"Error fetching alert rules: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/alerts/rules', methods=['POST'])
    def api_create_alert_rule():
        """Create a new alert rule"""
        try:
            data = request.get_json()

            # Validate required fields
            required = ['rule_name', 'rule_type', 'severity']
            for field in required:
                if field not in data:
                    return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

            cursor = db_manager.conn.cursor()

            cursor.execute("""
                INSERT INTO alert_rules (
                    rule_name, rule_type, description,
                    threshold_value, threshold_operator, evaluation_window_minutes,
                    applies_to, camera_name, group_id,
                    severity, enabled, suppress_during_maintenance,
                    rate_limit_minutes, notification_channels,
                    email_recipients, webhook_url,
                    escalation_enabled, escalation_after_minutes, escalation_recipients,
                    created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get('rule_name'),
                data.get('rule_type'),
                data.get('description'),
                data.get('threshold_value'),
                data.get('threshold_operator', '<'),
                data.get('evaluation_window_minutes', 30),
                data.get('applies_to', 'all'),
                data.get('camera_name'),
                data.get('group_id'),
                data.get('severity'),
                data.get('enabled', True),
                data.get('suppress_during_maintenance', True),
                data.get('rate_limit_minutes', 60),
                data.get('notification_channels', 'email'),
                data.get('email_recipients'),
                data.get('webhook_url'),
                data.get('escalation_enabled', False),
                data.get('escalation_after_minutes', 120),
                data.get('escalation_recipients'),
                data.get('created_by', 'system')
            ))

            db_manager.conn.commit()

            # Get the newly created rule ID
            cursor.execute("SELECT @@IDENTITY")
            rule_id = cursor.fetchone()[0]

            cursor.close()
            return jsonify({'success': True, 'rule_id': rule_id, 'message': 'Alert rule created successfully'})

        except Exception as e:
            logger.error(f"Error creating alert rule: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/alerts/rules/<int:rule_id>', methods=['PUT'])
    def api_update_alert_rule(rule_id):
        """Update an existing alert rule"""
        try:
            data = request.get_json()
            cursor = db_manager.conn.cursor()

            # Build update query dynamically based on provided fields
            update_fields = []
            params = []

            updatable_fields = {
                'rule_name': 'rule_name',
                'description': 'description',
                'threshold_value': 'threshold_value',
                'threshold_operator': 'threshold_operator',
                'evaluation_window_minutes': 'evaluation_window_minutes',
                'severity': 'severity',
                'enabled': 'enabled',
                'suppress_during_maintenance': 'suppress_during_maintenance',
                'rate_limit_minutes': 'rate_limit_minutes',
                'notification_channels': 'notification_channels',
                'email_recipients': 'email_recipients',
                'webhook_url': 'webhook_url',
                'escalation_enabled': 'escalation_enabled',
                'escalation_after_minutes': 'escalation_after_minutes',
                'escalation_recipients': 'escalation_recipients'
            }

            for key, col in updatable_fields.items():
                if key in data:
                    update_fields.append(f"{col} = ?")
                    params.append(data[key])

            if not update_fields:
                return jsonify({'success': False, 'error': 'No fields to update'}), 400

            # Always update updated_at
            update_fields.append("updated_at = GETDATE()")
            params.append(rule_id)

            query = f"UPDATE alert_rules SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, params)
            db_manager.conn.commit()

            cursor.close()
            return jsonify({'success': True, 'message': 'Alert rule updated successfully'})

        except Exception as e:
            logger.error(f"Error updating alert rule: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/alerts/rules/<int:rule_id>', methods=['DELETE'])
    def api_delete_alert_rule(rule_id):
        """Delete an alert rule"""
        try:
            cursor = db_manager.conn.cursor()

            # Check if rule exists
            cursor.execute("SELECT rule_name FROM alert_rules WHERE id = ?", rule_id)
            row = cursor.fetchone()

            if not row:
                cursor.close()
                return jsonify({'success': False, 'error': 'Alert rule not found'}), 404

            rule_name = row[0]

            # Delete the rule (cascade will delete related alerts in history)
            cursor.execute("DELETE FROM alert_rules WHERE id = ?", rule_id)
            db_manager.conn.commit()

            cursor.close()
            return jsonify({'success': True, 'message': f'Alert rule "{rule_name}" deleted successfully'})

        except Exception as e:
            logger.error(f"Error deleting alert rule: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/alerts/history', methods=['GET'])
    def api_get_alert_history():
        """Get alert history"""
        try:
            cursor = db_manager.conn.cursor()

            # Get filter parameters
            days = int(request.args.get('days', 7))
            status = request.args.get('status')
            severity = request.args.get('severity')
            camera_name = request.args.get('camera_name')
            limit = int(request.args.get('limit', 100))

            query = """
                SELECT ah.id, ah.alert_rule_id, ar.rule_name,
                       ah.camera_name, ah.alert_type, ah.severity,
                       ah.message, ah.trigger_value, ah.threshold_value,
                       ah.status, ah.triggered_at, ah.acknowledged_at,
                       ah.acknowledged_by, ah.resolved_at, ah.resolved_by,
                       ah.notification_sent, ah.notification_sent_at,
                       ah.escalated, ah.escalated_at,
                       ah.metadata
                FROM alert_history ah
                LEFT JOIN alert_rules ar ON ah.alert_rule_id = ar.id
                WHERE ah.triggered_at >= DATEADD(DAY, ?, GETDATE())
            """

            params = [-days]

            if status:
                query += " AND ah.status = ?"
                params.append(status)

            if severity:
                query += " AND ah.severity = ?"
                params.append(severity)

            if camera_name:
                query += " AND ah.camera_name = ?"
                params.append(camera_name)

            query += " ORDER BY ah.triggered_at DESC"

            cursor.execute(query, params)

            alerts = []
            for row in cursor.fetchall()[:limit]:
                alerts.append({
                    'id': row[0],
                    'alert_rule_id': row[1],
                    'rule_name': row[2],
                    'camera_name': row[3],
                    'alert_type': row[4],
                    'severity': row[5],
                    'message': row[6],
                    'trigger_value': float(row[7]) if row[7] else None,
                    'threshold_value': float(row[8]) if row[8] else None,
                    'status': row[9],
                    'triggered_at': row[10].isoformat() if row[10] else None,
                    'acknowledged_at': row[11].isoformat() if row[11] else None,
                    'acknowledged_by': row[12],
                    'resolved_at': row[13].isoformat() if row[13] else None,
                    'resolved_by': row[14],
                    'notification_sent': bool(row[15]),
                    'notification_sent_at': row[16].isoformat() if row[16] else None,
                    'escalated': bool(row[17]),
                    'escalated_at': row[18].isoformat() if row[18] else None,
                    'metadata': row[19]
                })

            cursor.close()
            return jsonify({'success': True, 'alerts': alerts, 'count': len(alerts)})

        except Exception as e:
            logger.error(f"Error fetching alert history: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/alerts/history/<int:alert_id>/acknowledge', methods=['POST'])
    def api_acknowledge_alert(alert_id):
        """Acknowledge an alert"""
        try:
            data = request.get_json()
            acknowledged_by = data.get('acknowledged_by', 'system')

            cursor = db_manager.conn.cursor()

            cursor.execute("""
                UPDATE alert_history
                SET status = 'acknowledged',
                    acknowledged_at = GETDATE(),
                    acknowledged_by = ?
                WHERE id = ? AND status = 'triggered'
            """, acknowledged_by, alert_id)

            db_manager.conn.commit()

            if cursor.rowcount == 0:
                cursor.close()
                return jsonify({'success': False, 'error': 'Alert not found or already acknowledged'}), 404

            cursor.close()
            return jsonify({'success': True, 'message': 'Alert acknowledged successfully'})

        except Exception as e:
            logger.error(f"Error acknowledging alert: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/alerts/history/<int:alert_id>/resolve', methods=['POST'])
    def api_resolve_alert(alert_id):
        """Resolve an alert"""
        try:
            data = request.get_json()
            resolved_by = data.get('resolved_by', 'system')
            resolution_notes = data.get('resolution_notes', '')

            cursor = db_manager.conn.cursor()

            cursor.execute("""
                UPDATE alert_history
                SET status = 'resolved',
                    resolved_at = GETDATE(),
                    resolved_by = ?,
                    resolution_notes = ?
                WHERE id = ? AND status != 'resolved'
            """, resolved_by, resolution_notes, alert_id)

            db_manager.conn.commit()

            if cursor.rowcount == 0:
                cursor.close()
                return jsonify({'success': False, 'error': 'Alert not found or already resolved'}), 404

            cursor.close()
            return jsonify({'success': True, 'message': 'Alert resolved successfully'})

        except Exception as e:
            logger.error(f"Error resolving alert: {e}")
            db_manager.conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/alerts/statistics', methods=['GET'])
    def api_get_alert_statistics():
        """Get alert statistics"""
        try:
            cursor = db_manager.conn.cursor()
            days = int(request.args.get('days', 30))

            # Get alert counts by severity
            cursor.execute("""
                SELECT severity, COUNT(*) as count
                FROM alert_history
                WHERE triggered_at >= DATEADD(DAY, ?, GETDATE())
                GROUP BY severity
            """, -days)

            by_severity = {}
            for row in cursor.fetchall():
                by_severity[row[0]] = row[1]

            # Get alert counts by status
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM alert_history
                WHERE triggered_at >= DATEADD(DAY, ?, GETDATE())
                GROUP BY status
            """, -days)

            by_status = {}
            for row in cursor.fetchall():
                by_status[row[0]] = row[1]

            # Get alert counts by type
            cursor.execute("""
                SELECT alert_type, COUNT(*) as count
                FROM alert_history
                WHERE triggered_at >= DATEADD(DAY, ?, GETDATE())
                GROUP BY alert_type
            """, -days)

            by_type = {}
            for row in cursor.fetchall():
                by_type[row[0]] = row[1]

            # Get top cameras by alert count
            cursor.execute("""
                SELECT TOP 10 camera_name, COUNT(*) as alert_count
                FROM alert_history
                WHERE triggered_at >= DATEADD(DAY, ?, GETDATE())
                GROUP BY camera_name
                ORDER BY COUNT(*) DESC
            """, -days)

            top_cameras = []
            for row in cursor.fetchall():
                top_cameras.append({'camera_name': row[0], 'alert_count': row[1]})

            # Get total counts
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'triggered' THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN notification_sent = 1 THEN 1 ELSE 0 END) as notifications_sent,
                    SUM(CASE WHEN escalated = 1 THEN 1 ELSE 0 END) as escalated
                FROM alert_history
                WHERE triggered_at >= DATEADD(DAY, ?, GETDATE())
            """, -days)

            row = cursor.fetchone()
            totals = {
                'total_alerts': row[0],
                'active_alerts': row[1] or 0,
                'notifications_sent': row[2] or 0,
                'escalated_alerts': row[3] or 0
            }

            cursor.close()

            return jsonify({
                'success': True,
                'days_analyzed': days,
                'totals': totals,
                'by_severity': by_severity,
                'by_status': by_status,
                'by_type': by_type,
                'top_cameras': top_cameras
            })

        except Exception as e:
            logger.error(f"Error fetching alert statistics: {e}")
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
