"""
CCTV Health Reporting System
Generates scheduled reports with system health metrics and trends
"""

import pyodbc
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates health and trend reports from historical data"""

    def __init__(self, db_config: Dict, email_config: Dict):
        self.db_config = db_config
        self.email_config = email_config

    def _get_connection(self):
        """Get database connection"""
        conn_str = (
            f"DRIVER={{{self.db_config['driver']}}};"
            f"SERVER={self.db_config['server']};"
            f"DATABASE={self.db_config['database']};"
            f"UID={self.db_config['username']};"
            f"PWD={self.db_config['password']};"
            f"PORT=1433;"
            f"TDS_Version=7.4;"
            f"Connection Timeout={self.db_config.get('timeout', 30)};"
        )
        return pyodbc.connect(conn_str)

    def get_system_health_summary(self, days: int = 7) -> Dict:
        """Get overall system health metrics for the last N days"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Overall stats
        cursor.execute("""
            SELECT
                COUNT(DISTINCT camera_name) as total_cameras,
                COUNT(*) as total_checks,
                SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_checks,
                SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) as offline_checks,
                SUM(CASE WHEN status = 'degraded' THEN 1 ELSE 0 END) as degraded_checks,
                AVG(CAST(response_time_ms AS FLOAT)) as avg_response_time
            FROM camera_health_log
            WHERE check_timestamp >= DATEADD(day, ?, GETDATE())
        """, -days)

        row = cursor.fetchone()

        total_checks = row[1] if row[1] else 1  # Prevent division by zero

        summary = {
            'total_cameras': row[0],
            'total_checks': row[1],
            'online_checks': row[2],
            'offline_checks': row[3],
            'degraded_checks': row[4],
            'avg_response_time': round(row[5], 2) if row[5] else 0,
            'uptime_percentage': round((row[2] / total_checks) * 100, 2) if total_checks > 0 else 0,
            'period_days': days
        }

        conn.close()
        return summary

    def get_top_failing_cameras(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """Get cameras with most failures in the last N days"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                camera_name,
                COUNT(*) as total_checks,
                SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) as offline_count,
                SUM(CASE WHEN status = 'degraded' THEN 1 ELSE 0 END) as degraded_count,
                CAST(SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) AS FLOAT) * 100.0 / COUNT(*) as failure_rate,
                AVG(CAST(response_time_ms AS FLOAT)) as avg_response_time
            FROM camera_health_log
            WHERE check_timestamp >= DATEADD(day, ?, GETDATE())
            GROUP BY camera_name
            HAVING SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) > 0
            ORDER BY offline_count DESC, degraded_count DESC
            OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
        """, -days, limit)

        cameras = []
        for row in cursor.fetchall():
            cameras.append({
                'camera_name': row[0],
                'total_checks': row[1],
                'offline_count': row[2],
                'degraded_count': row[3],
                'failure_rate': round(row[4], 1),
                'avg_response_time': round(row[5], 2) if row[5] else 0
            })

        conn.close()
        return cameras

    def get_current_offline_cameras(self) -> List[Dict]:
        """Get cameras that are currently offline"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                camera_name,
                camera_ip,
                current_status,
                last_check,
                last_online,
                consecutive_failures,
                uptime_percentage
            FROM camera_health_summary
            WHERE current_status = 'offline'
            ORDER BY consecutive_failures DESC, last_check DESC
        """)

        cameras = []
        for row in cursor.fetchall():
            cameras.append({
                'camera_name': row[0],
                'camera_ip': row[1],
                'status': row[2],
                'last_check': row[3],
                'last_online': row[4],
                'consecutive_failures': row[5],
                'uptime_percentage': round(row[6], 1) if row[6] else 0
            })

        conn.close()
        return cameras

    def get_performance_trends(self, days: int = 7) -> List[Dict]:
        """Get daily performance trends"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                CAST(check_timestamp AS DATE) as check_date,
                COUNT(*) as total_checks,
                SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_count,
                SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) as offline_count,
                SUM(CASE WHEN status = 'degraded' THEN 1 ELSE 0 END) as degraded_count,
                AVG(CAST(response_time_ms AS FLOAT)) as avg_response_time,
                COUNT(DISTINCT camera_name) as cameras_checked
            FROM camera_health_log
            WHERE check_timestamp >= DATEADD(day, ?, GETDATE())
            GROUP BY CAST(check_timestamp AS DATE)
            ORDER BY check_date ASC
        """, -days)

        trends = []
        for row in cursor.fetchall():
            total = row[1] if row[1] else 1
            trends.append({
                'date': row[0].strftime('%Y-%m-%d'),
                'total_checks': row[1],
                'online_count': row[2],
                'offline_count': row[3],
                'degraded_count': row[4],
                'uptime_percentage': round((row[2] / total) * 100, 2),
                'avg_response_time': round(row[5], 2) if row[5] else 0,
                'cameras_checked': row[6]
            })

        conn.close()
        return trends

    def get_recent_ai_analysis(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """Get recent AI image quality analysis results"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT TOP (?)
                camera_name,
                quality_score,
                analysis_timestamp,
                issues_detected
            FROM cctv_image_analysis
            WHERE analysis_timestamp >= DATEADD(day, ?, GETDATE())
                AND quality_score < 80
            ORDER BY quality_score ASC, analysis_timestamp DESC
        """, limit, -days)

        analyses = []
        for row in cursor.fetchall():
            analyses.append({
                'camera_name': row[0],
                'quality_score': row[1],
                'analysis_timestamp': row[2],
                'issues': row[3] if row[3] else 'None'
            })

        conn.close()
        return analyses

    def generate_daily_report(self) -> str:
        """Generate daily health report"""
        summary = self.get_system_health_summary(days=1)
        offline_cameras = self.get_current_offline_cameras()
        failing_cameras = self.get_top_failing_cameras(days=1, limit=5)
        ai_issues = self.get_recent_ai_analysis(days=1, limit=5)

        report = f"""
CCTV System Daily Health Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Report Period: Last 24 hours

═══════════════════════════════════════════════════════════════

📊 SYSTEM OVERVIEW

Total Cameras Monitored:  {summary['total_cameras']}
Total Health Checks:      {summary['total_checks']:,}
System Uptime:            {summary['uptime_percentage']}%
Average Response Time:    {summary['avg_response_time']}ms

Status Distribution:
  ✓ Online:    {summary['online_checks']:>6,} checks ({round((summary['online_checks']/summary['total_checks'])*100, 1) if summary['total_checks'] > 0 else 0}%)
  ⚠ Degraded:  {summary['degraded_checks']:>6,} checks ({round((summary['degraded_checks']/summary['total_checks'])*100, 1) if summary['total_checks'] > 0 else 0}%)
  ✗ Offline:   {summary['offline_checks']:>6,} checks ({round((summary['offline_checks']/summary['total_checks'])*100, 1) if summary['total_checks'] > 0 else 0}%)

═══════════════════════════════════════════════════════════════

🚨 CURRENTLY OFFLINE CAMERAS ({len(offline_cameras)})
"""

        if offline_cameras:
            for cam in offline_cameras[:10]:
                last_online_str = cam['last_online'].strftime('%Y-%m-%d %H:%M') if cam['last_online'] else 'Never'
                report += f"""
  • {cam['camera_name']}
    Last Online: {last_online_str}
    Consecutive Failures: {cam['consecutive_failures']}
    Uptime (All Time): {cam['uptime_percentage']}%
"""
        else:
            report += "\n  ✓ All cameras are currently online!\n"

        report += """
═══════════════════════════════════════════════════════════════

📉 TOP FAILING CAMERAS (Last 24 Hours)
"""

        if failing_cameras:
            for i, cam in enumerate(failing_cameras, 1):
                report += f"""
  {i}. {cam['camera_name']}
     Failures: {cam['offline_count']} / {cam['total_checks']} checks ({cam['failure_rate']}%)
     Avg Response Time: {cam['avg_response_time']}ms
"""
        else:
            report += "\n  ✓ No significant failures in the last 24 hours!\n"

        if ai_issues:
            report += """
═══════════════════════════════════════════════════════════════

🔍 AI IMAGE QUALITY ALERTS (Last 24 Hours)
"""
            for i, analysis in enumerate(ai_issues, 1):
                report += f"""
  {i}. {analysis['camera_name']} - Quality Score: {analysis['quality_score']}/100
     Timestamp: {analysis['analysis_timestamp'].strftime('%Y-%m-%d %H:%M')}
     Issues: {analysis['issues']}
"""

        report += """
═══════════════════════════════════════════════════════════════

For detailed analysis and historical trends, visit the CCTV Dashboard:
http://localhost:8080/dashboard

This is an automated report from the CCTV Operations Tool v2.
"""

        return report

    def generate_weekly_report(self) -> str:
        """Generate weekly summary report with trends"""
        summary = self.get_system_health_summary(days=7)
        trends = self.get_performance_trends(days=7)
        failing_cameras = self.get_top_failing_cameras(days=7, limit=10)
        offline_cameras = self.get_current_offline_cameras()

        report = f"""
CCTV System Weekly Health Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Report Period: Last 7 days

═══════════════════════════════════════════════════════════════

📊 WEEKLY SUMMARY

Total Cameras Monitored:  {summary['total_cameras']}
Total Health Checks:      {summary['total_checks']:,}
Weekly Uptime:            {summary['uptime_percentage']}%
Average Response Time:    {summary['avg_response_time']}ms

Overall Status Distribution:
  ✓ Online:    {summary['online_checks']:>6,} checks ({round((summary['online_checks']/summary['total_checks'])*100, 1) if summary['total_checks'] > 0 else 0}%)
  ⚠ Degraded:  {summary['degraded_checks']:>6,} checks ({round((summary['degraded_checks']/summary['total_checks'])*100, 1) if summary['total_checks'] > 0 else 0}%)
  ✗ Offline:   {summary['offline_checks']:>6,} checks ({round((summary['offline_checks']/summary['total_checks'])*100, 1) if summary['total_checks'] > 0 else 0}%)

═══════════════════════════════════════════════════════════════

📈 DAILY TREND ANALYSIS

Date          Uptime    Avg Response    Cameras    Status
────────────────────────────────────────────────────────────
"""

        for trend in trends:
            status_icon = "✓" if trend['uptime_percentage'] >= 95 else "⚠" if trend['uptime_percentage'] >= 90 else "✗"
            report += f"{trend['date']}    {trend['uptime_percentage']:>5.1f}%      {trend['avg_response_time']:>5.1f}ms        {trend['cameras_checked']:>3}      {status_icon}\n"

        report += """
═══════════════════════════════════════════════════════════════

🚨 CURRENTLY OFFLINE CAMERAS
"""

        if offline_cameras:
            for cam in offline_cameras[:10]:
                last_online_str = cam['last_online'].strftime('%Y-%m-%d %H:%M') if cam['last_online'] else 'Never'
                report += f"""
  • {cam['camera_name']}
    Last Online: {last_online_str}
    Consecutive Failures: {cam['consecutive_failures']}
    Uptime: {cam['uptime_percentage']}%
"""
        else:
            report += "\n  ✓ All cameras are currently online!\n"

        report += """
═══════════════════════════════════════════════════════════════

📉 TOP 10 PROBLEMATIC CAMERAS (Last 7 Days)
"""

        if failing_cameras:
            for i, cam in enumerate(failing_cameras, 1):
                report += f"""
  {i:>2}. {cam['camera_name']}
      Total Failures: {cam['offline_count']} / {cam['total_checks']} checks ({cam['failure_rate']}%)
      Degraded Events: {cam['degraded_count']}
      Avg Response Time: {cam['avg_response_time']}ms
"""
        else:
            report += "\n  ✓ No significant failures this week!\n"

        report += """
═══════════════════════════════════════════════════════════════

💡 RECOMMENDATIONS

"""

        # Add smart recommendations based on data
        if summary['uptime_percentage'] < 95:
            report += f"  ⚠  System uptime ({summary['uptime_percentage']}%) is below target (95%)\n"
            report += f"     → Review top failing cameras for hardware or network issues\n\n"

        if failing_cameras and failing_cameras[0]['failure_rate'] > 20:
            report += f"  ⚠  {failing_cameras[0]['camera_name']} has {failing_cameras[0]['failure_rate']}% failure rate\n"
            report += f"     → Recommend immediate inspection and possible replacement\n\n"

        if summary['avg_response_time'] > 500:
            report += f"  ⚠  Average response time ({summary['avg_response_time']}ms) is elevated\n"
            report += f"     → Check network performance and camera firmware\n\n"

        if len(offline_cameras) > 5:
            report += f"  ⚠  {len(offline_cameras)} cameras currently offline\n"
            report += f"     → Escalate to maintenance team for site visits\n\n"

        if summary['uptime_percentage'] >= 98 and not offline_cameras:
            report += "  ✓  System health is excellent! All cameras performing well.\n\n"

        report += """
═══════════════════════════════════════════════════════════════

For detailed analysis, historical trends, and AI image quality reports,
visit the CCTV Dashboard: http://localhost:8080/dashboard

This is an automated report from the CCTV Operations Tool v2.
"""

        return report

    def send_report(self, report: str, subject: str, recipients: List[str]):
        """Send report via email"""
        if not self.email_config.get('enabled', False):
            logger.info("Email disabled, report not sent")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject

            msg.attach(MIMEText(report, 'plain'))

            server = smtplib.SMTP(
                self.email_config['smtp_server'],
                self.email_config['smtp_port']
            )

            if self.email_config.get('username'):
                server.login(
                    self.email_config['username'],
                    self.email_config['password']
                )

            server.send_message(msg)
            server.quit()

            logger.info(f"Report sent successfully to {len(recipients)} recipients")
            return True

        except Exception as e:
            logger.error(f"Failed to send report: {e}")
            return False

    def send_daily_report(self, recipients: List[str]):
        """Generate and send daily report"""
        report = self.generate_daily_report()
        subject = f"CCTV Daily Health Report - {datetime.now().strftime('%Y-%m-%d')}"
        return self.send_report(report, subject, recipients)

    def send_weekly_report(self, recipients: List[str]):
        """Generate and send weekly report"""
        report = self.generate_weekly_report()
        subject = f"CCTV Weekly Health Report - Week of {datetime.now().strftime('%Y-%m-%d')}"
        return self.send_report(report, subject, recipients)
