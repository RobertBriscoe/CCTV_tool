"""
Email Notification System for FDOT CCTV Operations Tool
Sends email notifications when alerts are triggered
"""

import logging
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Optional
import threading

logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    Handles email notifications for alerts
    """

    def __init__(self):
        """Initialize email notifier with SMTP configuration"""
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.office365.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('SMTP_FROM_EMAIL', self.smtp_username)
        self.from_name = os.getenv('SMTP_FROM_NAME', 'FDOT CCTV Monitoring System')

        # Default recipients (comma-separated in env)
        self.default_recipients = os.getenv('ALERT_EMAIL_RECIPIENTS', '').split(',')
        self.default_recipients = [r.strip() for r in self.default_recipients if r.strip()]

        self.enabled = bool(self.smtp_username and self.smtp_password)

        if self.enabled:
            logger.info(f"Email Notifier initialized (SMTP: {self.smtp_server}:{self.smtp_port})")
        else:
            logger.warning("Email Notifier disabled - missing SMTP credentials")

    def send_alert_notification(self, alert: Dict, recipients: Optional[List[str]] = None) -> bool:
        """
        Send email notification for an alert

        Args:
            alert: Alert dictionary with details
            recipients: List of email addresses (uses defaults if None)

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Email notifications disabled - skipping")
            return False

        # Use default recipients if none provided
        if not recipients:
            recipients = self.default_recipients

        if not recipients:
            logger.warning("No email recipients configured")
            return False

        try:
            # Build email content
            subject = self._build_subject(alert)
            body_html = self._build_html_body(alert)
            body_text = self._build_text_body(alert)

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ', '.join(recipients)
            msg['X-Priority'] = self._get_priority(alert.get('severity', 'warning'))

            # Attach both text and HTML versions
            msg.attach(MIMEText(body_text, 'plain'))
            msg.attach(MIMEText(body_html, 'html'))

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Alert email sent to {len(recipients)} recipient(s): {alert.get('camera_name', 'N/A')}")
            return True

        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False

    def send_alert_notification_async(self, alert: Dict, recipients: Optional[List[str]] = None):
        """
        Send email notification asynchronously in a background thread

        Args:
            alert: Alert dictionary with details
            recipients: List of email addresses (uses defaults if None)
        """
        thread = threading.Thread(
            target=self.send_alert_notification,
            args=(alert, recipients),
            daemon=True
        )
        thread.start()

    def _build_subject(self, alert: Dict) -> str:
        """Build email subject line"""
        severity = alert.get('severity', 'warning').upper()
        camera_name = alert.get('camera_name', 'Unknown Camera')
        alert_type = alert.get('alert_type', 'alert')

        # Create concise subject
        severity_icon = {
            'INFO': 'ℹ️',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🚨'
        }.get(severity, '⚠️')

        return f"{severity_icon} [{severity}] CCTV Alert: {camera_name}"

    def _build_html_body(self, alert: Dict) -> str:
        """Build HTML email body"""
        severity = alert.get('severity', 'warning').upper()
        camera_name = alert.get('camera_name', 'Unknown Camera')
        alert_type = alert.get('alert_type', 'alert').replace('_', ' ').title()
        message = alert.get('message', 'No details available')
        triggered_at = alert.get('triggered_at', datetime.now())

        # Format timestamp
        if isinstance(triggered_at, str):
            time_str = triggered_at
        else:
            time_str = triggered_at.strftime('%Y-%m-%d %H:%M:%S')

        # Severity colors
        severity_color = {
            'INFO': '#3498db',
            'WARNING': '#f39c12',
            'ERROR': '#e74c3c',
            'CRITICAL': '#c0392b'
        }.get(severity, '#f39c12')

        # Build HTML
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background-color: {severity_color};
            color: white;
            padding: 20px;
            border-radius: 5px 5px 0 0;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .content {{
            background-color: #f9f9f9;
            padding: 20px;
            border: 1px solid #ddd;
            border-top: none;
        }}
        .detail-row {{
            margin: 10px 0;
            padding: 10px;
            background-color: white;
            border-left: 3px solid {severity_color};
        }}
        .label {{
            font-weight: bold;
            color: #555;
        }}
        .value {{
            color: #333;
        }}
        .footer {{
            margin-top: 20px;
            padding: 15px;
            background-color: #ecf0f1;
            border-radius: 0 0 5px 5px;
            font-size: 12px;
            color: #7f8c8d;
        }}
        .message-box {{
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{severity} Alert</h1>
        </div>
        <div class="content">
            <div class="detail-row">
                <span class="label">Camera:</span>
                <span class="value">{camera_name}</span>
            </div>
            <div class="detail-row">
                <span class="label">Alert Type:</span>
                <span class="value">{alert_type}</span>
            </div>
            <div class="detail-row">
                <span class="label">Severity:</span>
                <span class="value">{severity}</span>
            </div>
            <div class="detail-row">
                <span class="label">Triggered:</span>
                <span class="value">{time_str}</span>
            </div>
            <div class="message-box">
                <strong>Details:</strong><br>
                {message}
            </div>
"""

        # Add trigger/threshold values if available
        if alert.get('trigger_value') is not None:
            html += f"""
            <div class="detail-row">
                <span class="label">Current Value:</span>
                <span class="value">{alert['trigger_value']:.2f}</span>
            </div>
"""

        if alert.get('threshold_value') is not None:
            html += f"""
            <div class="detail-row">
                <span class="label">Threshold:</span>
                <span class="value">{alert['threshold_value']:.2f}</span>
            </div>
"""

        html += """
        </div>
        <div class="footer">
            <p>This is an automated alert from the FDOT CCTV Monitoring System.</p>
            <p>Please do not reply to this email. For support, contact your system administrator.</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def _build_text_body(self, alert: Dict) -> str:
        """Build plain text email body"""
        severity = alert.get('severity', 'warning').upper()
        camera_name = alert.get('camera_name', 'Unknown Camera')
        alert_type = alert.get('alert_type', 'alert').replace('_', ' ').title()
        message = alert.get('message', 'No details available')
        triggered_at = alert.get('triggered_at', datetime.now())

        # Format timestamp
        if isinstance(triggered_at, str):
            time_str = triggered_at
        else:
            time_str = triggered_at.strftime('%Y-%m-%d %H:%M:%S')

        # Build text
        text = f"""
FDOT CCTV MONITORING SYSTEM - {severity} ALERT
{'=' * 60}

Camera: {camera_name}
Alert Type: {alert_type}
Severity: {severity}
Triggered: {time_str}

DETAILS:
{message}
"""

        # Add trigger/threshold values if available
        if alert.get('trigger_value') is not None:
            text += f"\nCurrent Value: {alert['trigger_value']:.2f}"

        if alert.get('threshold_value') is not None:
            text += f"\nThreshold: {alert['threshold_value']:.2f}"

        text += """

{'=' * 60}
This is an automated alert from the FDOT CCTV Monitoring System.
Please do not reply to this email.
"""
        return text

    def _get_priority(self, severity: str) -> str:
        """Get email priority header based on severity"""
        severity = severity.upper()
        if severity in ['CRITICAL', 'ERROR']:
            return '1'  # High priority
        elif severity == 'WARNING':
            return '3'  # Normal priority
        else:
            return '5'  # Low priority

    def send_test_email(self, recipient: str) -> bool:
        """
        Send a test email to verify configuration

        Args:
            recipient: Email address to send test to

        Returns:
            True if successful, False otherwise
        """
        test_alert = {
            'camera_name': 'TEST-CAMERA',
            'alert_type': 'test',
            'severity': 'info',
            'message': 'This is a test email to verify the FDOT CCTV alert notification system is working correctly.',
            'triggered_at': datetime.now()
        }

        return self.send_alert_notification(test_alert, [recipient])


def create_email_notifier() -> Optional[EmailNotifier]:
    """
    Factory function to create email notifier

    Returns:
        EmailNotifier instance or None if creation fails
    """
    try:
        notifier = EmailNotifier()
        return notifier
    except Exception as e:
        logger.error(f"Failed to create email notifier: {e}")
        return None
