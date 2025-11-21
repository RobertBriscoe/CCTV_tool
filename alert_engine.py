"""
Alert Processing Engine for FDOT CCTV Operations Tool
Automatically evaluates alert rules and triggers alerts based on real-time conditions
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import pyodbc
import os

logger = logging.getLogger(__name__)

# Import email notifier if available
try:
    from email_notifier import EmailNotifier
    EMAIL_NOTIFIER_AVAILABLE = True
except ImportError:
    EMAIL_NOTIFIER_AVAILABLE = False
    logger.warning("Email notifier module not available")


class AlertEngine:
    """
    Background alert processing engine that evaluates rules and triggers alerts
    """

    def __init__(self, db_manager, cameras: Dict, check_interval_seconds: int = 300, email_notifier=None):
        """
        Initialize the alert engine

        Args:
            db_manager: Database manager instance
            cameras: Dictionary of camera configurations
            check_interval_seconds: How often to check rules (default: 5 minutes)
            email_notifier: EmailNotifier instance for sending notifications (optional)
        """
        # Store connection string for creating thread-local connections
        self.conn_str = (
            f"DRIVER={{{os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')}}};"
            f"SERVER={os.getenv('DB_SERVER')},1433;"
            f"DATABASE={os.getenv('DB_DATABASE')};"
            f"UID={os.getenv('DB_USERNAME')};"
            f"PWD={os.getenv('DB_PASSWORD')};"
            f"TrustServerCertificate=yes;"
        )
        self.cameras = cameras
        self.check_interval = check_interval_seconds
        self.running = False
        self.thread = None
        self.conn = None  # Thread-local connection
        self.email_notifier = email_notifier

        if self.email_notifier:
            logger.info(f"Alert Engine initialized with email notifications (check interval: {check_interval_seconds}s)")
        else:
            logger.info(f"Alert Engine initialized (check interval: {check_interval_seconds}s)")

    def start(self):
        """Start the alert engine in a background thread"""
        if self.running:
            logger.warning("Alert Engine already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("✓ Alert Engine started")

    def stop(self):
        """Stop the alert engine"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
        logger.info("Alert Engine stopped")

    def _run_loop(self):
        """Main processing loop"""
        logger.info("Alert Engine processing loop started")

        # Create thread-local database connection with autocommit to avoid cursor state issues
        try:
            self.conn = pyodbc.connect(self.conn_str, autocommit=True)
            logger.info("Alert Engine: Database connection established")
        except Exception as e:
            logger.error(f"Alert Engine: Failed to connect to database: {e}")
            return

        # Wait a bit before first check to let system stabilize
        time.sleep(30)

        while self.running:
            try:
                logger.debug("Alert Engine: Starting evaluation cycle")
                self._evaluate_all_rules()
                logger.debug(f"Alert Engine: Sleeping for {self.check_interval}s")
                time.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Alert Engine loop error: {e}", exc_info=True)
                time.sleep(60)  # Wait longer after error

        # Cleanup connection
        if self.conn:
            try:
                self.conn.close()
                logger.info("Alert Engine: Database connection closed")
            except:
                pass

    def _evaluate_all_rules(self):
        """Fetch and evaluate all enabled alert rules"""
        try:
            cursor = self.conn.cursor()

            # Get all enabled rules
            cursor.execute("""
                SELECT id, rule_name, rule_type, threshold_value, threshold_operator,
                       evaluation_window_minutes, applies_to, camera_name, group_id,
                       severity, suppress_during_maintenance, rate_limit_minutes
                FROM alert_rules
                WHERE enabled = 1
                ORDER BY severity DESC
            """)

            rules = []
            for row in cursor.fetchall():
                rules.append({
                    'id': row[0],
                    'rule_name': row[1],
                    'rule_type': row[2],
                    'threshold_value': float(row[3]) if row[3] else None,
                    'threshold_operator': row[4],
                    'evaluation_window_minutes': row[5],
                    'applies_to': row[6],
                    'camera_name': row[7],
                    'group_id': row[8],
                    'severity': row[9],
                    'suppress_during_maintenance': bool(row[10]),
                    'rate_limit_minutes': row[11]
                })

            cursor.close()

            if not rules:
                logger.debug("No enabled alert rules found")
                return

            logger.info(f"Evaluating {len(rules)} alert rules")

            # Evaluate each rule
            for rule in rules:
                try:
                    self._evaluate_rule(rule)
                except Exception as e:
                    logger.error(f"Error evaluating rule {rule['rule_name']}: {e}")

        except Exception as e:
            logger.error(f"Error fetching alert rules: {e}")

    def _evaluate_rule(self, rule: Dict):
        """Evaluate a single alert rule"""
        rule_type = rule['rule_type']

        # Determine which cameras to check
        cameras_to_check = self._get_cameras_for_rule(rule)

        if not cameras_to_check:
            return

        # Evaluate based on rule type
        if rule_type == 'sla_violation':
            self._check_sla_violations(rule, cameras_to_check)
        elif rule_type == 'extended_downtime':
            self._check_extended_downtime(rule, cameras_to_check)
        elif rule_type == 'recovery':
            self._check_camera_recovery(rule, cameras_to_check)
        else:
            logger.warning(f"Unknown rule type: {rule_type}")

    def _get_cameras_for_rule(self, rule: Dict) -> List[str]:
        """Get list of camera names that this rule applies to"""
        applies_to = rule['applies_to']

        if applies_to == 'camera' and rule['camera_name']:
            # Specific camera
            return [rule['camera_name']]

        elif applies_to == 'group' and rule['group_id']:
            # Camera group
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT camera_name
                    FROM camera_group_members
                    WHERE group_id = ?
                """, rule['group_id'])

                cameras = [row[0] for row in cursor.fetchall()]
                cursor.close()
                return cameras
            except Exception as e:
                logger.error(f"Error fetching group members: {e}")
                return []

        else:  # applies_to == 'all'
            # All cameras
            return list(self.cameras.keys())

    def _check_sla_violations(self, rule: Dict, cameras: List[str]):
        """Check for SLA violations (uptime % below threshold)"""
        threshold = rule['threshold_value']
        window_minutes = rule['evaluation_window_minutes']

        if not threshold:
            return

        try:
            cursor = self.conn.cursor()

            # Calculate uptime for each camera
            for camera_name in cameras:
                # Check maintenance window
                if rule['suppress_during_maintenance'] and self._is_in_maintenance(camera_name):
                    continue

                # Check rate limiting
                if not self._can_trigger_alert(rule['id'], camera_name, rule['rate_limit_minutes']):
                    continue

                # Calculate uptime percentage
                cursor.execute("""
                    SELECT COUNT(*) as total_checks,
                           SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_checks
                    FROM camera_health_log
                    WHERE camera_name = ?
                      AND check_timestamp >= DATEADD(MINUTE, ?, GETDATE())
                """, camera_name, -window_minutes)

                row = cursor.fetchone()
                if not row or row[0] == 0:
                    continue

                total_checks = row[0]
                online_checks = row[1] or 0
                uptime_pct = (online_checks / total_checks) * 100

                # Check if violation
                if uptime_pct < threshold:
                    message = f"SLA violation: {camera_name} uptime is {uptime_pct:.2f}% (threshold: {threshold}%)"
                    self._trigger_alert(
                        rule_id=rule['id'],
                        camera_name=camera_name,
                        alert_type=rule['rule_type'],
                        severity=rule['severity'],
                        message=message,
                        trigger_value=uptime_pct,
                        threshold_value=threshold
                    )

            cursor.close()

        except Exception as e:
            logger.error(f"Error checking SLA violations: {e}")

    def _check_extended_downtime(self, rule: Dict, cameras: List[str]):
        """Check for cameras down for extended period"""
        threshold_minutes = rule['threshold_value']

        if not threshold_minutes:
            return

        try:
            cursor = self.conn.cursor()

            for camera_name in cameras:
                # Check maintenance window
                if rule['suppress_during_maintenance'] and self._is_in_maintenance(camera_name):
                    continue

                # Check rate limiting
                if not self._can_trigger_alert(rule['id'], camera_name, rule['rate_limit_minutes']):
                    continue

                # Check for ongoing downtime
                cursor.execute("""
                    SELECT TOP 1 id, downtime_start
                    FROM camera_downtime_log
                    WHERE camera_name = ?
                      AND downtime_end IS NULL
                      AND downtime_start >= DATEADD(HOUR, -24, GETDATE())
                    ORDER BY downtime_start DESC
                """, camera_name)

                row = cursor.fetchone()
                if not row:
                    continue

                downtime_start = row[1]
                downtime_minutes = (datetime.now() - downtime_start).total_seconds() / 60

                # Check if exceeds threshold
                if downtime_minutes >= threshold_minutes:
                    message = f"Extended downtime: {camera_name} has been down for {int(downtime_minutes)} minutes"
                    self._trigger_alert(
                        rule_id=rule['id'],
                        camera_name=camera_name,
                        alert_type=rule['rule_type'],
                        severity=rule['severity'],
                        message=message,
                        trigger_value=downtime_minutes,
                        threshold_value=threshold_minutes
                    )

            cursor.close()

        except Exception as e:
            logger.error(f"Error checking extended downtime: {e}")

    def _check_camera_recovery(self, rule: Dict, cameras: List[str]):
        """Check for cameras that recently recovered from downtime"""
        threshold_minutes = rule['threshold_value']  # Min downtime before recovery alert
        window_minutes = rule['evaluation_window_minutes']  # How recent the recovery

        if not threshold_minutes or not window_minutes:
            return

        try:
            cursor = self.conn.cursor()

            for camera_name in cameras:
                # Check rate limiting
                if not self._can_trigger_alert(rule['id'], camera_name, rule['rate_limit_minutes']):
                    continue

                # Look for recent recoveries (downtime ended recently)
                cursor.execute("""
                    SELECT TOP 1 id, downtime_start, downtime_end, duration_minutes
                    FROM camera_downtime_log
                    WHERE camera_name = ?
                      AND downtime_end IS NOT NULL
                      AND downtime_end >= DATEADD(MINUTE, ?, GETDATE())
                      AND duration_minutes >= ?
                    ORDER BY downtime_end DESC
                """, camera_name, -window_minutes, threshold_minutes)

                row = cursor.fetchone()
                if not row:
                    continue

                duration_minutes = row[3] or 0
                message = f"Camera recovered: {camera_name} is back online after {int(duration_minutes)} minutes of downtime"

                self._trigger_alert(
                    rule_id=rule['id'],
                    camera_name=camera_name,
                    alert_type=rule['rule_type'],
                    severity=rule['severity'],
                    message=message,
                    trigger_value=duration_minutes,
                    threshold_value=threshold_minutes
                )

            cursor.close()

        except Exception as e:
            logger.error(f"Error checking camera recovery: {e}")

    def _is_in_maintenance(self, camera_name: str) -> bool:
        """Check if camera is currently in a maintenance window"""
        cursor = None
        try:
            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT COUNT(*)
                FROM maintenance_schedule
                WHERE camera_name = ?
                  AND status IN ('scheduled', 'in-progress')
                  AND suppress_alerts = 1
                  AND GETDATE() BETWEEN scheduled_start AND scheduled_end
            """, camera_name)

            count = cursor.fetchone()[0]
            return count > 0

        except Exception as e:
            logger.error(f"Error checking maintenance window for {camera_name}: {e}", exc_info=True)
            return False
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass

    def _can_trigger_alert(self, rule_id: int, camera_name: str, rate_limit_minutes: int) -> bool:
        """Check if alert can be triggered based on rate limiting"""
        if not rate_limit_minutes:
            return True

        cursor = None
        try:
            cursor = self.conn.cursor()

            # Check for recent alerts of same type for same camera
            cursor.execute("""
                SELECT TOP 1 triggered_at
                FROM alert_history
                WHERE alert_rule_id = ?
                  AND camera_name = ?
                  AND triggered_at >= DATEADD(MINUTE, ?, GETDATE())
                ORDER BY triggered_at DESC
            """, rule_id, camera_name, -rate_limit_minutes)

            row = cursor.fetchone()

            # If no recent alert found, can trigger
            return row is None

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Allow on error
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass

    def _trigger_alert(self, rule_id: int, camera_name: str, alert_type: str,
                      severity: str, message: str, trigger_value: float = None,
                      threshold_value: float = None):
        """Create an alert in the database and send notifications"""
        cursor = None
        alert_id = None

        try:
            cursor = self.conn.cursor()

            # Create metadata
            metadata = json.dumps({
                'triggered_by': 'alert_engine',
                'timestamp': datetime.now().isoformat(),
                'trigger_value': trigger_value,
                'threshold_value': threshold_value
            })

            # Insert alert into database
            cursor.execute("""
                INSERT INTO alert_history (
                    alert_rule_id, camera_name, alert_type, severity, message,
                    trigger_value, threshold_value, status, triggered_at,
                    notification_sent, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'triggered', GETDATE(), 0, ?)
            """, rule_id, camera_name, alert_type, severity, message,
                 trigger_value, threshold_value, metadata)

            # Get the alert ID we just created
            cursor.execute("SELECT @@IDENTITY")
            alert_id = cursor.fetchone()[0]

            logger.warning(f"🔔 ALERT TRIGGERED: [{severity.upper()}] {camera_name} - {message}")

            # Send email notification if notifier is available
            if self.email_notifier and alert_id:
                self._send_email_notification(rule_id, alert_id, camera_name, alert_type,
                                             severity, message, trigger_value, threshold_value)

        except Exception as e:
            logger.error(f"Error creating alert: {e}")
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass

    def _send_email_notification(self, rule_id: int, alert_id: int, camera_name: str,
                                alert_type: str, severity: str, message: str,
                                trigger_value: float = None, threshold_value: float = None):
        """Send email notification for an alert"""
        cursor = None
        try:
            # Get email recipients from alert rule
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT email_recipients, notification_channels
                FROM alert_rules
                WHERE id = ?
            """, rule_id)

            row = cursor.fetchone()
            if not row:
                logger.warning(f"Alert rule {rule_id} not found for email notification")
                return

            email_recipients_str = row[0]
            notification_channels = row[1] or 'email'

            # Check if email is enabled for this rule
            if 'email' not in notification_channels.lower():
                logger.debug(f"Email notifications disabled for rule {rule_id}")
                return

            # Parse email recipients
            recipients = []
            if email_recipients_str:
                recipients = [r.strip() for r in email_recipients_str.split(',') if r.strip()]

            # Build alert dict for email
            alert_dict = {
                'id': alert_id,
                'camera_name': camera_name,
                'alert_type': alert_type,
                'severity': severity,
                'message': message,
                'trigger_value': trigger_value,
                'threshold_value': threshold_value,
                'triggered_at': datetime.now()
            }

            # Send email (async to avoid blocking)
            success = False
            try:
                self.email_notifier.send_alert_notification_async(alert_dict, recipients if recipients else None)
                success = True
                logger.info(f"Email notification queued for alert {alert_id}")
            except Exception as e:
                logger.error(f"Failed to send email notification: {e}")

            # Update alert history with notification status
            update_cursor = self.conn.cursor()
            if success:
                update_cursor.execute("""
                    UPDATE alert_history
                    SET notification_sent = 1,
                        notification_sent_at = GETDATE(),
                        notification_channels = 'email'
                    WHERE id = ?
                """, alert_id)
            else:
                update_cursor.execute("""
                    UPDATE alert_history
                    SET notification_error = ?
                    WHERE id = ?
                """, str(e) if 'e' in locals() else 'Unknown error', alert_id)
            update_cursor.close()

        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass


def create_alert_engine(db_manager, cameras: Dict, check_interval: int = 300, email_notifier=None) -> Optional[AlertEngine]:
    """
    Factory function to create and start the alert engine

    Args:
        db_manager: Database manager instance
        cameras: Dictionary of camera configurations
        check_interval: Check interval in seconds (default: 300 = 5 minutes)
        email_notifier: EmailNotifier instance for sending notifications (optional)

    Returns:
        AlertEngine instance or None if creation fails
    """
    try:
        engine = AlertEngine(db_manager, cameras, check_interval, email_notifier)
        engine.start()
        return engine
    except Exception as e:
        logger.error(f"Failed to create alert engine: {e}")
        return None
