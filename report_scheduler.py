"""
Scheduled Report Delivery System
Automatically sends daily and weekly health reports at specified times
"""

import threading
import time
import os
import logging
from datetime import datetime, timedelta
from typing import List

logger = logging.getLogger(__name__)


class ReportScheduler:
    """Background scheduler for automated report delivery"""

    def __init__(self, report_generator):
        self.report_generator = report_generator
        self.running = False
        self.thread = None

        # Get configuration from environment
        self.daily_report_time = os.getenv('DAILY_REPORT_TIME', '08:00')  # 8 AM
        self.weekly_report_day = int(os.getenv('WEEKLY_REPORT_DAY', '1'))  # Monday (0=Monday, 6=Sunday)
        self.weekly_report_time = os.getenv('WEEKLY_REPORT_TIME', '09:00')  # 9 AM
        self.report_enabled = os.getenv('SCHEDULED_REPORTS_ENABLED', 'true').lower() == 'true'

        # Get recipients
        stakeholder_emails = os.getenv('STAKEHOLDER_EMAILS', '')
        self.recipients = [e.strip() for e in stakeholder_emails.split(',') if e.strip()]

        # Track last sent times to avoid duplicates
        self.last_daily_report = None
        self.last_weekly_report = None

        logger.info(f"Report Scheduler initialized:")
        logger.info(f"  Daily reports: {self.daily_report_time} to {len(self.recipients)} recipients")
        logger.info(f"  Weekly reports: Day {self.weekly_report_day} at {self.weekly_report_time}")
        logger.info(f"  Enabled: {self.report_enabled}")

    def _parse_time(self, time_str: str) -> tuple:
        """Parse time string (HH:MM) to hour and minute"""
        try:
            parts = time_str.split(':')
            return int(parts[0]), int(parts[1])
        except:
            logger.error(f"Invalid time format: {time_str}, using default 08:00")
            return 8, 0

    def _should_send_daily_report(self) -> bool:
        """Check if it's time to send daily report"""
        now = datetime.now()
        report_hour, report_minute = self._parse_time(self.daily_report_time)

        # Check if current time matches schedule
        if now.hour != report_hour or now.minute != report_minute:
            return False

        # Check if we already sent today
        if self.last_daily_report:
            if self.last_daily_report.date() == now.date():
                return False

        return True

    def _should_send_weekly_report(self) -> bool:
        """Check if it's time to send weekly report"""
        now = datetime.now()
        report_hour, report_minute = self._parse_time(self.weekly_report_time)

        # Check if it's the correct day of week
        if now.weekday() != self.weekly_report_day:
            return False

        # Check if current time matches schedule
        if now.hour != report_hour or now.minute != report_minute:
            return False

        # Check if we already sent this week
        if self.last_weekly_report:
            days_since = (now - self.last_weekly_report).days
            if days_since < 7:
                return False

        return True

    def _send_daily_report(self):
        """Send daily health report"""
        try:
            if not self.recipients:
                logger.warning("No recipients configured for daily report")
                return

            logger.info(f"Sending scheduled daily report to {len(self.recipients)} recipients")
            success = self.report_generator.send_daily_report(self.recipients)

            if success:
                self.last_daily_report = datetime.now()
                logger.info("✓ Daily report sent successfully")
            else:
                logger.error("✗ Failed to send daily report")

        except Exception as e:
            logger.error(f"Error sending daily report: {e}")

    def _send_weekly_report(self):
        """Send weekly summary report"""
        try:
            if not self.recipients:
                logger.warning("No recipients configured for weekly report")
                return

            logger.info(f"Sending scheduled weekly report to {len(self.recipients)} recipients")
            success = self.report_generator.send_weekly_report(self.recipients)

            if success:
                self.last_weekly_report = datetime.now()
                logger.info("✓ Weekly report sent successfully")
            else:
                logger.error("✗ Failed to send weekly report")

        except Exception as e:
            logger.error(f"Error sending weekly report: {e}")

    def _scheduler_loop(self):
        """Main scheduler loop - runs every minute"""
        logger.info("Report scheduler loop started")

        while self.running:
            try:
                # Check if daily report should be sent
                if self._should_send_daily_report():
                    self._send_daily_report()

                # Check if weekly report should be sent
                if self._should_send_weekly_report():
                    self._send_weekly_report()

                # Sleep for 60 seconds before next check
                time.sleep(60)

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(60)

        logger.info("Report scheduler loop stopped")

    def start(self):
        """Start the background scheduler"""
        if not self.report_enabled:
            logger.info("Scheduled reports disabled in configuration")
            return False

        if not self.recipients:
            logger.warning("No recipients configured, scheduler not started")
            return False

        if self.running:
            logger.warning("Scheduler already running")
            return False

        self.running = True
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()

        logger.info("✓ Report scheduler started")
        return True

    def stop(self):
        """Stop the background scheduler"""
        if not self.running:
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

        logger.info("Report scheduler stopped")

    def get_status(self) -> dict:
        """Get scheduler status and configuration"""
        return {
            'enabled': self.report_enabled,
            'running': self.running,
            'recipients_count': len(self.recipients),
            'daily_report_time': self.daily_report_time,
            'weekly_report_day': self.weekly_report_day,
            'weekly_report_time': self.weekly_report_time,
            'last_daily_report': self.last_daily_report.isoformat() if self.last_daily_report else None,
            'last_weekly_report': self.last_weekly_report.isoformat() if self.last_weekly_report else None
        }
