#!/usr/bin/env python3
"""
CCTV Operations Tool - Fixed & Enhanced Version
===============================================
Complete FDOT CCTV management tool with:
- Camera reboots with MIMS ticket creation (success/fail)
- Snapshot capture with duration and interval controls
- Scheduled snapshot jobs
- Email notifications to maintenance team
- Shared folder output

FIXES:
- Added duration and interval controls for snapshots
- Fixed FFmpeg detection and fallback
- Proper MIMS ticket creation for all reboot outcomes
- Email notifications for maintenance team
- Improved error handling

Requirements:
pip install opencv-python pillow onvif-zeep pyodbc requests flask

Author: Enhanced by Claude
Version: 6.0 - Complete Operations Tool
"""

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("⚠️  OpenCV not available, using FFmpeg only")

import os
import smtplib
import logging
import zipfile
import json
import threading
import time
import socket
import requests
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, Dict, Any, List, Tuple
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from api_extensions import register_advanced_apis
from db_manager import DatabaseManager
from alert_engine import create_alert_engine
from email_notifier import create_email_notifier

# Try to import ONVIF for camera reboots
try:
    from onvif import ONVIFCamera
    ONVIF_AVAILABLE = True
except ImportError:
    ONVIF_AVAILABLE = False
    print("WARNING: onvif-zeep not installed. Reboot functionality disabled.")

# Try to import MIMS client
try:
    from mims_client import MIMSClient, MIMSTokenManager
    from scheduler_init import create_reboot_ticket
    MIMS_AVAILABLE = True
except ImportError:
    MIMS_AVAILABLE = False
    print("WARNING: MIMS client not available. Ticket creation disabled.")

# Try to import Health Monitor
try:
    from health_monitor import HealthCheckManager
    HEALTH_MONITOR_AVAILABLE = True
except ImportError:
    HEALTH_MONITOR_AVAILABLE = False
    print("WARNING: Health monitor not available.")

# Try to import Image Analyzer
try:
    from image_analyzer import ImageAnalyzer
    IMAGE_ANALYZER_AVAILABLE = True
except ImportError:
    IMAGE_ANALYZER_AVAILABLE = False
    print("WARNING: Image analyzer not available.")

# Try to import Report Generator
try:
    from report_generator import ReportGenerator
    REPORT_GENERATOR_AVAILABLE = True
except ImportError:
    REPORT_GENERATOR_AVAILABLE = False
    print("WARNING: Report generator not available.")

# Try to import Report Scheduler
try:
    from report_scheduler import ReportScheduler
    REPORT_SCHEDULER_AVAILABLE = True
except ImportError:
    REPORT_SCHEDULER_AVAILABLE = False
    print("WARNING: Report scheduler not available.")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Logging setup
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Set up logging handlers with error handling
handlers = [logging.StreamHandler()]
try:
    log_file = LOG_DIR / f'cctv_ops_{datetime.now():%Y%m%d}.log'
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    handlers.append(file_handler)
    print(f"✓ Logging to file: {log_file}")
except Exception as e:
    print(f"✗ Failed to create file handler: {e}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=handlers,
    force=True
)
logger = logging.getLogger("cctv_ops")

# Email Configuration
EMAIL_CONFIG = {
    "smtp_server": os.getenv("SMTP_SERVER", "mail.smtp2go.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "2525")),
    "smtp_username": os.getenv("SMTP_USERNAME", "d3sunguide"),
    "from_email": os.getenv("SMTP_FROM_EMAIL", "d3sunguide@d3sunguide.com"),
    "from_password": os.getenv("SMTP_PASSWORD", ""),
    "maintenance_team": os.getenv("MAINTENANCE_EMAILS", "").split(",") if os.getenv("MAINTENANCE_EMAILS") else [],
    "stakeholders": os.getenv("STAKEHOLDER_EMAILS", "").split(",") if os.getenv("STAKEHOLDER_EMAILS") else [],
    "enabled": os.getenv("EMAIL_ENABLED", "true").lower() == "true"
}

# MIMS Configuration
MIMS_CONFIG = {
    "base_url": os.getenv("MIMS_BASE_URL", "http://172.60.1.42:8080"),
    "group_id": int(os.getenv("MIMS_GROUP_ID", "1024")),
    "issue_id": int(os.getenv("MIMS_ISSUE_ID", "11")),
    "weather_id": int(os.getenv("MIMS_WEATHER_ID", "2")),
    "enabled": MIMS_AVAILABLE
}

# Storage Configuration
STORAGE_CONFIG = {
    "base_path": Path(os.getenv("SNAPSHOT_OUTPUT_DIR", "/var/cctv-snapshots")),
    "shared_folder": Path(os.getenv("SHARED_FOLDER", "/mnt/shared/cctv-snapshots")),
    "max_storage_gb": int(os.getenv("MAX_STORAGE_GB", "50"))
}

# Camera defaults
CAMERA_DEFAULTS = {
    "onvif_port": int(os.getenv("CAMERA_ONVIF_PORT", "80")),
    "onvif_user": os.getenv("CAMERA_DEFAULT_USERNAME", "admin"),
    "onvif_pass": os.getenv("CAMERA_DEFAULT_PASSWORD", "admin123"),
    "rtsp_port": int(os.getenv("CAMERA_RTSP_PORT", "554")),
    "rtsp_path": os.getenv("CAMERA_RTSP_PATH", "/stream1")
}

# Database Configuration (Microsoft SQL Server)
DB_CONFIG = {
    "server": os.getenv("DB_SERVER", "SG-8-Test-SQL"),
    "database": os.getenv("DB_DATABASE", "FDOT_CCTV_System"),
    "username": os.getenv("DB_USERNAME", "RTMCSNAP"),
    "password": os.getenv("DB_PASSWORD", ""),
    "driver": os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
    "timeout": int(os.getenv("DB_TIMEOUT", "30"))
}

# Flask Configuration
FLASK_CONFIG = {
    "host": os.getenv("FLASK_HOST", "0.0.0.0"),
    "port": int(os.getenv("FLASK_PORT", "8080")),
    "debug": os.getenv("FLASK_DEBUG", "false").lower() == "true"
}

# Camera Configuration Loader
def load_camera_config():
    """Load camera configuration from JSON file"""
    config_file = Path("camera_config.json")
    if not config_file.exists():
        logger.warning(f"Camera config file not found: {config_file}")
        return {}

    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        cameras = config.get("cameras", {})
        logger.info(f"Loaded {len(cameras)} cameras from configuration")
        return cameras
    except Exception as e:
        logger.error(f"Failed to load camera config: {e}")
        return {}

# Load cameras on startup
CAMERAS = load_camera_config()

# =============================================================================
# ENHANCED RTSP CAPTURE WITH MULTIPLE METHODS
# =============================================================================

class EnhancedRTSPCapture:
    """Multi-method RTSP capture with OpenCV and FFmpeg fallback"""
    
    def __init__(self, rtsp_url: str, camera_name: str):
        self.rtsp_url = rtsp_url
        self.camera_name = camera_name
        self.logger = logging.getLogger(f"capture.{camera_name}")
        self.ffmpeg_available = self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5,
                check=False
            )
            available = result.returncode == 0
            if available:
                self.logger.info("FFmpeg detected and available")
            return available
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.logger.warning("FFmpeg not found - using OpenCV only")
            return False
    
    def capture_snapshot(self, save_path: str, timeout: int = 20) -> Tuple[bool, str]:
        """
        Capture single snapshot with multiple fallback methods
        
        Returns:
            (success, message)
        """
        methods = [
            ("OpenCV-TCP", self._capture_opencv_tcp),
            ("OpenCV-UDP", self._capture_opencv_udp)
        ]
        
        if self.ffmpeg_available:
            methods.append(("FFmpeg", self._capture_ffmpeg))
        
        for method_name, method_func in methods:
            self.logger.info(f"Trying {method_name} for {self.camera_name}")
            try:
                if method_func(save_path, timeout):
                    self.logger.info(f"✓ {method_name} capture successful")
                    return True, f"Captured via {method_name}"
            except Exception as e:
                self.logger.warning(f"{method_name} failed: {e}")
                continue
        
        return False, "All capture methods failed"
    
    def _capture_opencv_tcp(self, save_path: str, timeout: int) -> bool:
        """OpenCV capture with TCP transport"""
        cap = None
        try:
            tcp_url = self.rtsp_url + ('?tcp' if '?' not in self.rtsp_url else '&tcp')
            cap = cv2.VideoCapture(tcp_url, cv2.CAP_FFMPEG)
            
            if not cap.isOpened():
                return False
            
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FPS, 5)
            
            # Skip initial frames
            for _ in range(5):
                ret, frame = cap.read()
                if ret and frame is not None:
                    break
                time.sleep(0.5)
            
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                if frame.shape[0] > 100 and frame.shape[1] > 100:
                    return cv2.imwrite(save_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return False
        finally:
            if cap:
                cap.release()
    
    def _capture_opencv_udp(self, save_path: str, timeout: int) -> bool:
        """OpenCV capture with UDP transport"""
        cap = None
        try:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
            if not cap.isOpened():
                return False
            
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
            time.sleep(2)
            
            for _ in range(10):
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    if frame.shape[0] > 100 and frame.shape[1] > 100:
                        return cv2.imwrite(save_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                time.sleep(0.3)
            return False
        finally:
            if cap:
                cap.release()
    
    def _capture_ffmpeg(self, save_path: str, timeout: int) -> bool:
        """FFmpeg direct capture"""
        try:
            cmd = [
                'ffmpeg', '-y',
                '-rtsp_transport', 'tcp',
                '-i', self.rtsp_url,
                '-frames:v', '1',
                '-q:v', '2',
                '-f', 'image2',
                '-timeout', str(timeout * 1000000),
                save_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout + 5,
                check=False
            )
            
            if result.returncode == 0 and os.path.exists(save_path):
                file_size = os.path.getsize(save_path)
                return file_size > 10000  # At least 10KB
            return False
        except subprocess.TimeoutExpired:
            return False

# =============================================================================
# CAMERA REBOOT WITH MIMS INTEGRATION
# =============================================================================

class CameraRebootManager:
    """Handles camera reboots with ONVIF and MIMS ticket creation"""
    
    def __init__(self, mims_client: Optional[Any] = None):
        self.mims_client = mims_client
        self.logger = logging.getLogger("reboot_mgr")
    
    def reboot_camera(
        self,
        camera_ip: str,
        camera_name: str,
        operator: str,
        reason: str,
        onvif_port: int = 80,
        onvif_user: str = "admin",
        onvif_pass: str = "admin123"
    ) -> Dict[str, Any]:
        """
        Reboot camera and create MIMS ticket
        
        Returns:
            {
                'success': bool,
                'message': str,
                'ticket_id': str or None,
                'outcome': 'success' or 'failure'
            }
        """
        result = {
            'success': False,
            'message': '',
            'ticket_id': None,
            'outcome': 'failure',
            'timestamp': datetime.now().isoformat()
        }
        
        # Attempt reboot
        reboot_success, reboot_msg = self._attempt_reboot(
            camera_ip, onvif_port, onvif_user, onvif_pass
        )
        
        result['success'] = reboot_success
        result['message'] = reboot_msg
        result['outcome'] = 'success' if reboot_success else 'failure'
        
        # Create MIMS ticket regardless of outcome
        if self.mims_client and MIMS_AVAILABLE:
            ticket_ok, ticket_result = self._create_mims_ticket(
                camera_name=camera_name,
                camera_ip=camera_ip,
                operator=operator,
                outcome=result['outcome'],
                reason=reason
            )

            if ticket_ok:
                # Check if ticket was skipped due to existing open tickets
                if isinstance(ticket_result, dict) and ticket_result.get('skipped'):
                    existing = ticket_result.get('existing_tickets', [])
                    result['ticket_id'] = 'skipped'
                    result['message'] += f" | MIMS ticket skipped (existing: {', '.join(existing)})"
                    self.logger.info(f"⊘ MIMS ticket skipped: {', '.join(existing)} already open")
                else:
                    ticket_id = ticket_result.get('id') or ticket_result.get('troubleTicketId')
                    result['ticket_id'] = str(ticket_id) if ticket_id else 'created'
                    result['message'] += f" | MIMS ticket: {result['ticket_id']}"
                    self.logger.info(f"✓ MIMS ticket created: {result['ticket_id']}")
            else:
                result['message'] += f" | MIMS ticket failed: {ticket_result}"
                self.logger.error(f"✗ MIMS ticket creation failed: {ticket_result}")
        else:
            result['message'] += " | MIMS not available"
        
        # Send email notification
        self._send_reboot_email(camera_name, result, operator, reason)
        
        return result
    
    def _attempt_reboot(
        self,
        camera_ip: str,
        onvif_port: int,
        user: str,
        password: str
    ) -> Tuple[bool, str]:
        """Attempt ONVIF camera reboot"""
        if not ONVIF_AVAILABLE:
            return False, "ONVIF not available"
        
        try:
            self.logger.info(f"Connecting to camera {camera_ip}:{onvif_port}")
            cam = ONVIFCamera(camera_ip, onvif_port, user, password)
            
            device_mgmt = cam.create_devicemgmt_service()
            device_mgmt.SystemReboot()
            
            self.logger.info(f"✓ Reboot command sent to {camera_ip}")
            return True, "Reboot successful"
        
        except Exception as e:
            self.logger.error(f"✗ Reboot failed for {camera_ip}: {e}")
            return False, f"Reboot failed: {str(e)}"
    
    def _create_mims_ticket(
        self,
        camera_name: str,
        camera_ip: str,
        operator: str,
        outcome: str,
        reason: str
    ) -> Tuple[bool, Any]:
        """Create MIMS ticket for reboot action"""
        try:
            # Get db_manager if available
            db_mgr = globals().get('db_manager')

            return create_reboot_ticket(
                mims_client=self.mims_client,
                camera_name=camera_name,
                cam_ip=camera_ip,
                operator=operator,
                outcome=outcome,
                reason=reason,
                submitting_group_id=MIMS_CONFIG['group_id'],
                issue_id=MIMS_CONFIG['issue_id'],
                weather_id=MIMS_CONFIG['weather_id'],
                db_manager=db_mgr
            )
        except Exception as e:
            self.logger.error(f"MIMS ticket creation exception: {e}")
            return False, {'error': str(e)}
    
    def _send_reboot_email(
        self,
        camera_name: str,
        result: Dict[str, Any],
        operator: str,
        reason: str
    ):
        """Send email notification about reboot"""
        if not EMAIL_CONFIG['enabled'] or not EMAIL_CONFIG['maintenance_team']:
            return

        # Don't send email if ticket was skipped (duplicate prevention)
        if result.get('ticket_id') == 'skipped':
            self.logger.info("Email notification skipped (duplicate ticket exists)")
            return

        try:
            status = "✓ SUCCESS" if result['success'] else "✗ FAILED"
            subject = f"CCTV Reboot {status}: {camera_name}"

            # Sanitize message - remove any IP addresses
            message = result.get('message', '')
            # Remove IP addresses (pattern: xxx.xxx.xxx.xxx)
            import re
            message = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP REDACTED]', message)
            # Remove port numbers (pattern: :80, :8080, etc)
            message = re.sub(r':\d+', '', message)

            # Simple status message without technical details
            if result['success']:
                status_detail = "Camera reboot command sent successfully."
            else:
                status_detail = "Camera reboot command failed. Technical details logged."

            body = f"""
CCTV Camera Reboot Notification
================================

Camera: {camera_name}
Status: {status}
Operator: {operator}
Reason: {reason}
Timestamp: {result['timestamp']}

{status_detail}

MIMS Ticket: {result.get('ticket_id', 'N/A')}

---
This is an automated notification from the FDOT CCTV Operations Tool.
For technical details, contact the operations team.
"""

            email_sender = EmailNotificationManager(EMAIL_CONFIG)
            email_sender.send_notification(
                to_emails=EMAIL_CONFIG['maintenance_team'],
                subject=subject,
                body=body
            )

            self.logger.info(f"Reboot notification emailed to maintenance team")

        except Exception as e:
            self.logger.error(f"Failed to send reboot email: {e}")

# =============================================================================
# SNAPSHOT CAPTURE WITH DURATION/INTERVAL CONTROLS
# =============================================================================

class SnapshotCaptureManager:
    """Manages snapshot capture with duration and interval controls"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("snapshot_mgr")
    
    def capture_multiple_snapshots(
        self,
        cameras: List[Dict[str, str]],
        duration_minutes: int = 5,
        interval_seconds: int = 30,
        output_format: str = 'folder'  # 'folder', 'zip', or 'email'
    ) -> Dict[str, Any]:
        """
        Capture snapshots from multiple cameras over a duration
        
        Args:
            cameras: List of camera dicts with 'name', 'ip', 'rtsp_url'
            duration_minutes: How long to capture (in minutes)
            interval_seconds: Time between captures (in seconds)
            output_format: Where to save ('folder', 'zip', 'email')
        
        Returns:
            Result dictionary with paths and stats
        """
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = self.storage_path / session_id
        session_path.mkdir(exist_ok=True)
        
        results = {
            'session_id': session_id,
            'session_path': str(session_path),
            'start_time': datetime.now().isoformat(),
            'duration_minutes': duration_minutes,
            'interval_seconds': interval_seconds,
            'cameras': {},
            'total_captures': 0,
            'successful_captures': 0,
            'failed_captures': 0
        }
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        capture_count = 0
        
        self.logger.info(
            f"Starting snapshot session {session_id}: "
            f"{len(cameras)} cameras, {duration_minutes}min, {interval_seconds}s interval"
        )
        
        while datetime.now() < end_time:
            capture_count += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            for camera in cameras:
                camera_name = camera['name']
                camera_path = session_path / camera_name
                camera_path.mkdir(exist_ok=True)
                
                if camera_name not in results['cameras']:
                    results['cameras'][camera_name] = {
                        'successful': 0,
                        'failed': 0,
                        'snapshots': []
                    }
                
                # Capture snapshot
                snapshot_file = camera_path / f"{camera_name}_{timestamp}.jpg"

                # Build RTSP URL if not provided
                if 'rtsp_url' in camera:
                    rtsp_url = camera['rtsp_url']
                else:
                    # Build RTSP URL from IP
                    cam_ip = camera.get('ip')
                    rtsp_user = camera.get('username', CAMERA_DEFAULTS['onvif_user'])
                    rtsp_pass = camera.get('password', CAMERA_DEFAULTS['onvif_pass'])
                    rtsp_port = camera.get('rtsp_port', CAMERA_DEFAULTS['rtsp_port'])
                    rtsp_path = camera.get('rtsp_path', CAMERA_DEFAULTS['rtsp_path'])
                    rtsp_url = f"rtsp://{rtsp_user}:{rtsp_pass}@{cam_ip}:{rtsp_port}{rtsp_path}"

                capturer = EnhancedRTSPCapture(rtsp_url, camera_name)
                success, message = capturer.capture_snapshot(str(snapshot_file))
                
                results['total_captures'] += 1
                
                if success:
                    results['successful_captures'] += 1
                    results['cameras'][camera_name]['successful'] += 1
                    results['cameras'][camera_name]['snapshots'].append(str(snapshot_file))
                    self.logger.debug(f"✓ Captured {camera_name} #{capture_count}")
                else:
                    results['failed_captures'] += 1
                    results['cameras'][camera_name]['failed'] += 1
                    self.logger.warning(f"✗ Failed {camera_name}: {message}")
            
            # Wait for next interval
            if datetime.now() < end_time:
                time.sleep(interval_seconds)
        
        results['end_time'] = datetime.now().isoformat()
        results['actual_duration_seconds'] = (
            datetime.fromisoformat(results['end_time']) -
            datetime.fromisoformat(results['start_time'])
        ).total_seconds()
        
        # Handle output format
        if output_format == 'zip':
            zip_path = self._create_zip(session_path)
            results['zip_file'] = str(zip_path)
        
        elif output_format == 'shared_folder':
            shared_path = self._copy_to_shared_folder(session_path)
            results['shared_folder'] = str(shared_path) if shared_path else None
        
        self.logger.info(
            f"Session complete: {results['successful_captures']}/{results['total_captures']} successful"
        )
        
        return results
    
    def _create_zip(self, session_path: Path) -> Path:
        """Create zip file of snapshot session"""
        zip_path = session_path.parent / f"{session_path.name}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in session_path.rglob('*.jpg'):
                arcname = file_path.relative_to(session_path.parent)
                zipf.write(file_path, arcname)
        
        self.logger.info(f"Created zip: {zip_path}")
        return zip_path
    
    def _copy_to_shared_folder(self, session_path: Path) -> Optional[Path]:
        """Copy snapshots to shared folder"""
        try:
            shared_base = STORAGE_CONFIG['shared_folder']
            if not shared_base.exists():
                self.logger.warning(f"Shared folder not accessible: {shared_base}")
                return None
            
            dest_path = shared_base / session_path.name
            shutil.copytree(session_path, dest_path, dirs_exist_ok=True)
            
            self.logger.info(f"Copied to shared folder: {dest_path}")
            return dest_path
        
        except Exception as e:
            self.logger.error(f"Failed to copy to shared folder: {e}")
            return None

# =============================================================================
# EMAIL NOTIFICATION MANAGER
# =============================================================================

class EmailNotificationManager:
    """Handles email notifications for operations"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("email_mgr")
    
    def send_notification(
        self,
        to_emails: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None
    ) -> bool:
        """Send email notification"""
        if not self.config['enabled']:
            self.logger.info("Email disabled, skipping notification")
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['from_email']
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject
            msg['Date'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach files if provided
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename={os.path.basename(file_path)}'
                            )
                            msg.attach(part)
            
            # Send email
            with smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port']) as server:
                server.starttls()
                server.login(self.config['smtp_username'], self.config['from_password'])
                server.send_message(msg)
            
            self.logger.info(f"✓ Email sent to {', '.join(to_emails)}")
            return True
        
        except Exception as e:
            self.logger.error(f"✗ Email failed: {e}")
            return False
    
    def send_snapshot_report(
        self,
        results: Dict[str, Any],
        to_emails: List[str],
        include_zip: bool = False
    ) -> bool:
        """Send snapshot capture report"""
        subject = f"CCTV Snapshot Report - {results['session_id']}"
        
        body = f"""
CCTV Snapshot Capture Report
============================

Session ID: {results['session_id']}
Start Time: {results['start_time']}
End Time: {results['end_time']}
Duration: {results['duration_minutes']} minutes
Interval: {results['interval_seconds']} seconds

Statistics:
-----------
Total Captures: {results['total_captures']}
Successful: {results['successful_captures']}
Failed: {results['failed_captures']}
Success Rate: {(results['successful_captures']/results['total_captures']*100):.1f}%

Camera Details:
---------------
"""
        
        for cam_name, cam_data in results['cameras'].items():
            body += f"\n{cam_name}:\n"
            body += f"  Successful: {cam_data['successful']}\n"
            body += f"  Failed: {cam_data['failed']}\n"
        
        body += f"""

Storage Location: {results['session_path']}
"""
        
        if results.get('shared_folder'):
            body += f"Shared Folder: {results['shared_folder']}\n"
        
        body += "\nThis is an automated report from the FDOT CCTV Operations Tool."
        
        attachments = []
        if include_zip and results.get('zip_file'):
            attachments.append(results['zip_file'])
        
        return self.send_notification(to_emails, subject, body, attachments)

# =============================================================================
# FLASK API
# =============================================================================

app = Flask(__name__)
CORS(app)

# Global managers
reboot_manager = None
snapshot_manager = None
email_manager = None
mims_client = None
health_manager = None

def initialize_managers():
    """Initialize global managers"""
    global reboot_manager, snapshot_manager, email_manager, mims_client, health_manager, report_generator, report_scheduler

    # Initialize MIMS client if available
    if MIMS_AVAILABLE:
        try:
            username = os.getenv("MIMS_USERNAME")
            password = os.getenv("MIMS_PASSWORD")
            token = os.getenv("MIMS_TOKEN")

            if (username and password) or token:
                from scheduler_init import create_mims_client
                mims_client = create_mims_client(username, password)
                if mims_client:
                    logger.info("✓ MIMS client initialized")
                else:
                    logger.warning("MIMS client initialization failed")
            else:
                logger.warning("MIMS credentials not provided (need username/password or token)")
        except Exception as e:
            logger.error(f"Failed to initialize MIMS client: {e}")

    reboot_manager = CameraRebootManager(mims_client)
    snapshot_manager = SnapshotCaptureManager(STORAGE_CONFIG['base_path'])
    email_manager = EmailNotificationManager(EMAIL_CONFIG)

    # Initialize Health Monitor with auto-remediation
    if HEALTH_MONITOR_AVAILABLE:
        try:
            # Pass reboot callback for auto-remediation
            reboot_callback = reboot_manager.reboot_camera if reboot_manager else None
            health_manager = HealthCheckManager(
                CAMERAS, DB_CONFIG, EMAIL_CONFIG, reboot_callback
            )
            logger.info("✓ Health monitor initialized with alerts and auto-remediation enabled")
        except Exception as e:
            logger.error(f"Failed to initialize health monitor: {e}")

    # Initialize Image Analyzer for AI-powered snapshot analysis
    global image_analyzer
    image_analyzer = None
    if IMAGE_ANALYZER_AVAILABLE:
        try:
            image_analyzer = ImageAnalyzer(DB_CONFIG)
            logger.info("✓ Image analyzer initialized with Gemini AI")
        except Exception as e:
            logger.error(f"Failed to initialize image analyzer: {e}")

    # Initialize Report Generator for scheduled reporting
    global report_generator
    report_generator = None
    if REPORT_GENERATOR_AVAILABLE:
        try:
            report_generator = ReportGenerator(DB_CONFIG, EMAIL_CONFIG)
            logger.info("✓ Report generator initialized")
        except Exception as e:
            logger.error(f"Failed to initialize report generator: {e}")

    # Initialize Report Scheduler for automated delivery
    global report_scheduler
    report_scheduler = None
    if REPORT_SCHEDULER_AVAILABLE and report_generator:
        try:
            report_scheduler = ReportScheduler(report_generator)
            logger.info("✓ Report scheduler initialized")
        except Exception as e:
            logger.error(f"Failed to initialize report scheduler: {e}")

    logger.info("✓ All managers initialized")

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files (snapshots, etc.)"""
    static_dir = Path(__file__).parent / 'static'
    return send_from_directory(static_dir, filename)

@app.route('/', methods=['GET'])
def dashboard():
    """Operator-friendly web dashboard with reboot, snapshot, and scheduling"""
    # Serve the enhanced dashboard HTML file
    dashboard_file = Path(__file__).parent / 'dashboard_enhanced.html'
    if dashboard_file.exists():
        with open(dashboard_file, 'r') as f:
            return f.read()

    # Fallback to basic dashboard if file not found
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FDOT CCTV Operations Tool</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        header { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #003366; font-size: 28px; }
        .subtitle { color: #666; margin-top: 5px; }
        .search-bar { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .search-input { width: 100%; padding: 12px 20px; font-size: 16px; border: 2px solid #ddd; border-radius: 6px; }
        .search-input:focus { outline: none; border-color: #003366; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-value { font-size: 32px; font-weight: bold; color: #003366; }
        .stat-label { color: #666; margin-top: 5px; font-size: 14px; }
        .camera-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; }
        .camera-card { background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); cursor: pointer; transition: transform 0.2s; }
        .camera-card:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
        .camera-name { font-weight: 600; color: #003366; margin-bottom: 8px; }
        .camera-info { font-size: 14px; color: #666; margin: 4px 0; }
        .loading { text-align: center; padding: 40px; color: #666; }
        .no-results { text-align: center; padding: 40px; color: #999; }
        .btn { background: #003366; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .btn:hover { background: #004488; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
        .filters { display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
        .filter-btn { padding: 8px 16px; border: 2px solid #ddd; background: white; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .filter-btn.active { border-color: #003366; background: #003366; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎥 FDOT CCTV Operations Tool</h1>
            <div class="subtitle">District 3 Camera Management System</div>
        </header>

        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-value" id="totalCameras">-</div>
                <div class="stat-label">Total Cameras</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="displayedCameras">-</div>
                <div class="stat-label">Displayed</div>
            </div>
        </div>

        <div class="search-bar">
            <input type="text" class="search-input" id="searchInput" placeholder="🔍 Search cameras by name, IP, location, or highway (e.g., 'I10', '10.164', 'MM 5')..." />
            <div class="filters">
                <button class="filter-btn active" onclick="filterHighway('all')">All</button>
                <button class="filter-btn" onclick="filterHighway('I10')">I-10</button>
                <button class="filter-btn" onclick="filterHighway('I110')">I-110</button>
                <button class="filter-btn" onclick="filterHighway('US90')">US-90</button>
                <button class="filter-btn" onclick="filterHighway('US98')">US-98</button>
            </div>
        </div>

        <div id="cameraContainer">
            <div class="loading">Loading cameras...</div>
        </div>
    </div>

    <script>
        let allCameras = [];
        let currentFilter = 'all';

        // Load cameras on page load
        async function loadCameras() {
            try {
                const response = await fetch('/api/cameras/list');
                const data = await response.json();
                allCameras = data.cameras;
                document.getElementById('totalCameras').textContent = data.total;
                displayCameras(allCameras);
            } catch (error) {
                document.getElementById('cameraContainer').innerHTML = '<div class="no-results">Error loading cameras</div>';
            }
        }

        // Display cameras
        function displayCameras(cameras) {
            const container = document.getElementById('cameraContainer');
            document.getElementById('displayedCameras').textContent = cameras.length;

            if (cameras.length === 0) {
                container.innerHTML = '<div class="no-results">No cameras found</div>';
                return;
            }

            container.innerHTML = cameras.map(cam => `
                <div class="camera-card" onclick="selectCamera('${cam.id}')">
                    <div class="camera-name">${cam.name}</div>
                    <div class="camera-info">📍 ${cam.location}</div>
                    <div class="camera-info">🌐 ${cam.ip}</div>
                </div>
            `).join('');
        }

        // Search cameras
        document.getElementById('searchInput').addEventListener('input', function(e) {
            const query = e.target.value.toLowerCase();
            if (query.length < 2) {
                filterCameras(currentFilter);
                return;
            }

            const filtered = allCameras.filter(cam =>
                cam.name.toLowerCase().includes(query) ||
                cam.ip.includes(query) ||
                cam.location.toLowerCase().includes(query)
            );
            displayCameras(filtered);
        });

        // Filter by highway
        function filterHighway(highway) {
            currentFilter = highway;

            // Update button states
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            filterCameras(highway);
        }

        function filterCameras(highway) {
            if (highway === 'all') {
                displayCameras(allCameras);
            } else {
                const filtered = allCameras.filter(cam => cam.location.includes(highway));
                displayCameras(filtered);
            }
        }

        // Select camera
        function selectCamera(cameraId) {
            const cam = allCameras.find(c => c.id === cameraId);
            if (cam) {
                alert(`Camera: ${cam.name}\\nIP: ${cam.ip}\\nLocation: ${cam.location}\\n\\nRTSP: ${cam.rtsp_url}`);
            }
        }

        // Load cameras on startup
        loadCameras();
    </script>
</body>
</html>
    """
    return html

@app.route('/api/health', methods=['GET'])
def health_check():
    """Enhanced health check endpoint for LibreNMS monitoring"""
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '6.0',
        'uptime': time.time(),  # Can be enhanced with actual uptime tracking
    }

    issues = []

    # Service checks
    services = {
        'mims_available': MIMS_AVAILABLE,
        'mims_authenticated': MIMS_AVAILABLE and mims_client is not None,
        'onvif_available': ONVIF_AVAILABLE,
        'opencv_available': CV2_AVAILABLE,
        'email_enabled': EMAIL_CONFIG['enabled']
    }
    health_status['services'] = services

    # Camera configuration check
    camera_stats = {
        'total_cameras': len(CAMERAS),
        'config_loaded': len(CAMERAS) > 0
    }
    health_status['cameras'] = camera_stats

    if len(CAMERAS) == 0:
        issues.append('No cameras loaded from configuration')

    # Database connectivity check
    db_healthy = False
    try:
        import pyodbc
        conn_str = (
            f"DRIVER={{{DB_CONFIG['driver']}}};"
            f"SERVER={DB_CONFIG['server']};"
            f"DATABASE={DB_CONFIG['database']};"
            f"UID={DB_CONFIG['username']};"
            f"PWD={DB_CONFIG['password']};"
            f"PORT=1433;"
            f"TDS_Version=7.4;"
            f"Connection Timeout={DB_CONFIG['timeout']};"
        )
        conn = pyodbc.connect(conn_str, timeout=5)
        conn.close()
        db_healthy = True
    except Exception as e:
        issues.append(f'Database connection failed: {str(e)}')

    health_status['database'] = {
        'connected': db_healthy,
        'server': DB_CONFIG['server'],
        'database': DB_CONFIG['database']
    }

    # Storage check
    storage_healthy = True
    try:
        base_path = STORAGE_CONFIG['base_path']
        if base_path.exists():
            stat = os.statvfs(str(base_path))
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            total_gb = (stat.f_blocks * stat.f_frsize) / (1024**3)
            used_percent = ((total_gb - free_gb) / total_gb) * 100 if total_gb > 0 else 0

            health_status['storage'] = {
                'path': str(base_path),
                'free_gb': round(free_gb, 2),
                'total_gb': round(total_gb, 2),
                'used_percent': round(used_percent, 2)
            }

            if free_gb < 5:
                issues.append(f'Low disk space: {free_gb:.2f} GB free')
                storage_healthy = False
        else:
            issues.append(f'Storage path does not exist: {base_path}')
            storage_healthy = False
    except Exception as e:
        issues.append(f'Storage check failed: {str(e)}')
        storage_healthy = False

    # Overall health determination
    critical_checks = [
        services['onvif_available'],
        camera_stats['config_loaded'],
        db_healthy,
        storage_healthy
    ]

    if not all(critical_checks):
        health_status['status'] = 'degraded'

    if issues:
        health_status['issues'] = issues

    # Return appropriate HTTP status code
    status_code = 200 if health_status['status'] == 'healthy' else 503

    return jsonify(health_status), status_code

@app.route('/api/metrics', methods=['GET'])
def metrics():
    """Prometheus-style metrics endpoint for LibreNMS"""
    metrics_data = {
        'cameras_total': len(CAMERAS),
        'services_up': sum([
            1 if MIMS_AVAILABLE else 0,
            1 if ONVIF_AVAILABLE else 0,
            1 if CV2_AVAILABLE else 0
        ]),
        'timestamp': datetime.now().isoformat()
    }

    return jsonify(metrics_data)

@app.route('/api/cameras/list', methods=['GET'])
def list_cameras():
    """
    Get list of configured cameras with search, filter, and sort capabilities

    Query parameters:
    - search: Search term (searches name, IP, location)
    - sort: Sort field (name, ip, location) default: name
    - order: Sort order (asc, desc) default: asc
    - limit: Number of results (default: all)
    - offset: Offset for pagination (default: 0)
    """
    # Get query parameters
    search = request.args.get('search', '').lower()
    sort_field = request.args.get('sort', 'name').lower()
    sort_order = request.args.get('order', 'asc').lower()
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int, default=0)

    camera_list = []
    for camera_id, camera_data in CAMERAS.items():
        # Build RTSP URL using camera IP and defaults
        rtsp_url = f"rtsp://{camera_data['ip']}:{CAMERA_DEFAULTS['rtsp_port']}{CAMERA_DEFAULTS['rtsp_path']}"

        # Extract location from camera name (e.g., "CCTV-I10-001.5-EB" -> "I10 MM 001.5")
        name = camera_data.get('name', camera_id)
        location = extract_location(name)

        camera_list.append({
            'id': camera_id,
            'name': name,
            'ip': camera_data['ip'],
            'location': location,
            'rtsp_url': rtsp_url,
            'reboot_url': camera_data.get('reboot_url', '/api/reboot'),
            'snapshot_url': camera_data.get('snapshot_url', '/api/snapshot')
        })

    # Apply search filter
    if search:
        camera_list = [
            cam for cam in camera_list
            if search in cam['name'].lower()
            or search in cam['ip'].lower()
            or search in cam['location'].lower()
        ]

    # Sort cameras
    reverse = (sort_order == 'desc')
    if sort_field in ['name', 'ip', 'location']:
        camera_list.sort(key=lambda x: x.get(sort_field, ''), reverse=reverse)

    # Get total before pagination
    total = len(camera_list)

    # Apply pagination
    if limit:
        camera_list = camera_list[offset:offset + limit]
    else:
        camera_list = camera_list[offset:]

    return jsonify({
        'total': total,
        'count': len(camera_list),
        'offset': offset,
        'cameras': camera_list
    })

def extract_location(camera_name: str) -> str:
    """Extract location from camera name (e.g., 'CCTV-I10-001.5-EB' -> 'I10 MM 1.5 EB')"""
    try:
        parts = camera_name.replace('CCTV-', '').split('-')
        if len(parts) >= 3:
            highway = parts[0]  # I10
            mileMarker = parts[1]  # 001.5
            direction = parts[2] if len(parts) > 2 else ''  # EB/WB/NB/SB
            return f"{highway} MM {mileMarker} {direction}".strip()
        return camera_name
    except:
        return camera_name

@app.route('/api/cameras/search', methods=['GET'])
def search_cameras():
    """
    Quick camera search endpoint

    Query parameters:
    - q: Search query (required)
    - limit: Max results (default: 20)
    """
    query = request.args.get('q', '').lower()
    limit = request.args.get('limit', type=int, default=20)

    if not query or len(query) < 2:
        return jsonify({'error': 'Search query must be at least 2 characters'}), 400

    results = []
    for camera_id, camera_data in CAMERAS.items():
        name = camera_data.get('name', camera_id)
        ip = camera_data['ip']
        location = extract_location(name)

        # Check if query matches
        if (query in name.lower() or
            query in ip or
            query in location.lower() or
            query in camera_id.lower()):
            results.append({
                'id': camera_id,
                'name': name,
                'ip': ip,
                'location': location,
                'rtsp_url': f"rtsp://{ip}:{CAMERA_DEFAULTS['rtsp_port']}{CAMERA_DEFAULTS['rtsp_path']}"
            })

            if len(results) >= limit:
                break

    return jsonify({
        'query': query,
        'count': len(results),
        'results': results
    })

@app.route('/api/cameras/bulk-info', methods=['POST'])
def bulk_camera_info():
    """
    Get detailed info for multiple cameras at once

    Request body:
    {
        "camera_ips": ["10.164.244.149", "10.164.244.20", ...]
    }
    """
    data = request.json
    camera_ips = data.get('camera_ips', [])

    if not camera_ips:
        return jsonify({'error': 'camera_ips field required'}), 400

    results = []
    for camera_id, camera_data in CAMERAS.items():
        if camera_data['ip'] in camera_ips:
            name = camera_data.get('name', camera_id)
            results.append({
                'id': camera_id,
                'name': name,
                'ip': camera_data['ip'],
                'location': extract_location(name),
                'rtsp_url': f"rtsp://{camera_data['ip']}:{CAMERA_DEFAULTS['rtsp_port']}{CAMERA_DEFAULTS['rtsp_path']}"
            })

    return jsonify({
        'requested': len(camera_ips),
        'found': len(results),
        'cameras': results
    })

@app.route('/api/cameras/by-highway', methods=['GET'])
def cameras_by_highway():
    """
    Get cameras grouped by highway

    Query parameters:
    - highway: Filter by specific highway (e.g., I10, I110, US90)
    """
    highway_filter = request.args.get('highway', '').upper()

    # Group cameras by highway
    grouped = {}
    for camera_id, camera_data in CAMERAS.items():
        name = camera_data.get('name', camera_id)
        location = extract_location(name)

        # Extract highway from location (e.g., "I10 MM 1.5 EB" -> "I10")
        highway = location.split()[0] if location else 'UNKNOWN'

        # Apply filter if specified
        if highway_filter and highway != highway_filter:
            continue

        if highway not in grouped:
            grouped[highway] = []

        grouped[highway].append({
            'id': camera_id,
            'name': name,
            'ip': camera_data['ip'],
            'location': location,
            'rtsp_url': f"rtsp://{camera_data['ip']}:{CAMERA_DEFAULTS['rtsp_port']}{CAMERA_DEFAULTS['rtsp_path']}"
        })

    # Sort cameras within each highway by mile marker
    for highway in grouped:
        grouped[highway].sort(key=lambda x: x['location'])

    return jsonify({
        'highways': list(grouped.keys()),
        'total_cameras': sum(len(cams) for cams in grouped.values()),
        'data': grouped
    })

@app.route('/api/camera/reboot', methods=['POST'])
def reboot_camera():
    """Reboot a camera with MIMS ticket creation"""
    data = request.json
    
    required_fields = ['camera_ip', 'camera_name', 'operator', 'reason']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    result = reboot_manager.reboot_camera(
        camera_ip=data['camera_ip'],
        camera_name=data['camera_name'],
        operator=data['operator'],
        reason=data['reason'],
        onvif_port=data.get('onvif_port', CAMERA_DEFAULTS['onvif_port']),
        onvif_user=data.get('onvif_user', CAMERA_DEFAULTS['onvif_user']),
        onvif_pass=data.get('onvif_pass', CAMERA_DEFAULTS['onvif_pass'])
    )
    
    return jsonify(result)

@app.route('/api/snapshot/capture', methods=['POST'])
def capture_snapshots():
    """Capture snapshots with duration and interval controls"""
    data = request.json

    if 'cameras' not in data:
        return jsonify({'error': 'cameras field required'}), 400

    duration_minutes = data.get('duration_minutes', 5)
    interval_seconds = data.get('interval_seconds', 30)
    output_format = data.get('output_format', 'shared_folder')  # Default to shared folder

    # Generate session ID
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Run capture in background thread
    def capture_task():
        results = snapshot_manager.capture_multiple_snapshots(
            cameras=data['cameras'],
            duration_minutes=duration_minutes,
            interval_seconds=interval_seconds,
            output_format=output_format
        )

        # Send email if requested
        if data.get('email_report'):
            email_manager.send_snapshot_report(
                results=results,
                to_emails=data.get('email_recipients', EMAIL_CONFIG['maintenance_team']),
                include_zip=data.get('include_zip', False)
            )

    thread = threading.Thread(target=capture_task, daemon=True)
    thread.start()

    return jsonify({
        'message': 'Snapshot capture started',
        'session_id': session_id,
        'duration_minutes': duration_minutes,
        'interval_seconds': interval_seconds,
        'cameras': len(data['cameras'])
    })

@app.route('/api/snapshot/sessions', methods=['GET'])
def list_sessions():
    """List available snapshot sessions"""
    sessions = []
    
    for session_dir in STORAGE_CONFIG['base_path'].glob('*'):
        if session_dir.is_dir():
            sessions.append({
                'session_id': session_dir.name,
                'path': str(session_dir),
                'created': datetime.fromtimestamp(session_dir.stat().st_ctime).isoformat(),
                'size_mb': sum(f.stat().st_size for f in session_dir.rglob('*') if f.is_file()) / 1024 / 1024
            })
    
    return jsonify(sorted(sessions, key=lambda x: x['created'], reverse=True))

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    return jsonify({
        'email': {
            'enabled': EMAIL_CONFIG['enabled'],
            'smtp_server': EMAIL_CONFIG['smtp_server'],
            'maintenance_team': EMAIL_CONFIG['maintenance_team']
        },
        'mims': {
            'enabled': MIMS_AVAILABLE and mims_client is not None,
            'base_url': MIMS_CONFIG['base_url']
        },
        'storage': {
            'base_path': str(STORAGE_CONFIG['base_path']),
            'shared_folder': str(STORAGE_CONFIG['shared_folder']),
            'max_storage_gb': STORAGE_CONFIG['max_storage_gb']
        },
        'defaults': CAMERA_DEFAULTS
    })

# =============================================================================
# HEALTH MONITORING API
# =============================================================================

@app.route('/api/dashboard/health', methods=['GET'])
def get_dashboard_health():
    """Get camera health status for dashboard"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        # Get all camera statuses
        statuses = health_manager.get_all_camera_status()

        # Get statistics
        stats = health_manager.get_health_statistics()

        return jsonify({
            'cameras': statuses,
            'statistics': stats,
            'last_updated': datetime.now().isoformat()
        })
    except Exception as e:
        import traceback
        logger.error(f"Error getting health data: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e), 'details': traceback.format_exc()}), 500

@app.route('/api/camera/test', methods=['POST'])
def test_camera():
    """Manually test a specific camera's health"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        data = request.get_json()
        camera_name = data.get('camera_name')
        camera_ip = data.get('camera_ip')

        if not camera_name or not camera_ip:
            return jsonify({'error': 'camera_name and camera_ip required'}), 400

        # Perform health check
        result = health_manager.check_camera_health(camera_name, camera_ip, 'manual')

        # Log to database
        health_manager.log_health_check(result)

        return jsonify({
            'success': True,
            'result': {
                'camera_name': result['camera_name'],
                'camera_ip': result['camera_ip'],
                'status': result['status'],
                'ping_success': result['ping_success'],
                'snapshot_success': result['snapshot_success'],
                'response_time_ms': result['response_time_ms'],
                'timestamp': result['check_timestamp'].isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error testing camera: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cameras/test-all', methods=['POST'])
def test_all_cameras():
    """Trigger manual health check for all cameras"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        # Start health check in background thread
        import threading
        thread = threading.Thread(target=health_manager.check_all_cameras, args=('manual',), daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'message': f'Health check started for {len(CAMERAS)} cameras'
        })
    except Exception as e:
        logger.error(f"Error starting health check: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cameras/offline', methods=['GET'])
def get_offline_cameras():
    """Get list of offline cameras"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        statuses = health_manager.get_all_camera_status()
        offline = [s for s in statuses if s['status'] in ['offline', 'degraded']]

        return jsonify({
            'offline_cameras': offline,
            'count': len(offline)
        })
    except Exception as e:
        logger.error(f"Error getting offline cameras: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cameras/problem', methods=['GET'])
def get_problem_cameras():
    """Get cameras with repeated failures"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        statuses = health_manager.get_all_camera_status()
        problem = [s for s in statuses if s['consecutive_failures'] >= 3]

        return jsonify({
            'problem_cameras': problem,
            'count': len(problem)
        })
    except Exception as e:
        logger.error(f"Error getting problem cameras: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health/daily-summary', methods=['POST'])
def send_daily_summary():
    """Send daily health summary email"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    if not health_manager.alert_manager:
        return jsonify({'error': 'Alert manager not available'}), 503

    try:
        # Get health statistics
        stats = health_manager.get_health_statistics()

        # Get problem cameras
        statuses = health_manager.get_all_camera_status()
        problem_cameras = [s for s in statuses if s['consecutive_failures'] >= 3 or s['status'] in ['offline', 'degraded']]

        # Send daily summary
        health_manager.alert_manager.send_daily_summary(stats, problem_cameras)

        return jsonify({
            'success': True,
            'message': 'Daily summary email sent',
            'statistics': stats,
            'problem_cameras_count': len(problem_cameras)
        })
    except Exception as e:
        logger.error(f"Error sending daily summary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health/history/<camera_name>', methods=['GET'])
def get_camera_history(camera_name):
    """Get historical health data for a specific camera"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        # Get hours parameter (default 24)
        hours = request.args.get('hours', 24, type=int)
        hours = min(hours, 168)  # Max 7 days

        history = health_manager.get_camera_history(camera_name, hours)

        return jsonify({
            'camera_name': camera_name,
            'hours': hours,
            'data_points': len(history),
            'history': history
        })
    except Exception as e:
        logger.error(f"Error getting camera history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health/system-history', methods=['GET'])
def get_system_history():
    """Get aggregated system health history"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        # Get parameters
        hours = request.args.get('hours', 24, type=int)
        hours = min(hours, 168)  # Max 7 days
        interval = request.args.get('interval', 60, type=int)
        interval = max(15, min(interval, 240))  # 15 min to 4 hours

        history = health_manager.get_system_history(hours, interval)

        return jsonify({
            'hours': hours,
            'interval_minutes': interval,
            'data_points': len(history),
            'history': history
        })
    except Exception as e:
        logger.error(f"Error getting system history: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health/export-csv', methods=['GET'])
def export_health_csv():
    """Export health data as CSV file"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        # Get hours parameter (default 24)
        hours = request.args.get('hours', 24, type=int)
        hours = min(hours, 168)  # Max 7 days

        csv_data = health_manager.export_health_csv(hours)

        # Return as downloadable CSV file
        from flask import Response
        filename = f"health_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health/remediation', methods=['GET'])
def get_remediation_status():
    """Get cameras currently under auto-remediation"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        cameras = health_manager.remediation_manager.get_cameras_under_remediation()
        return jsonify({
            'cameras_under_remediation': cameras,
            'count': len(cameras),
            'auto_reboot_enabled': health_manager.remediation_manager.auto_reboot_enabled,
            'auto_reboot_threshold': health_manager.remediation_manager.auto_reboot_threshold
        })
    except Exception as e:
        logger.error(f"Error getting remediation status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health/remediation/<camera_name>', methods=['DELETE'])
def clear_remediation(camera_name):
    """Clear remediation state for a camera (allow auto-reboot again)"""
    if not health_manager:
        return jsonify({'error': 'Health monitor not available'}), 503

    try:
        # Get optional parameter to also clear ticket cooldown
        data = request.get_json() or {}
        clear_ticket_cooldown = data.get('clear_ticket_cooldown', False)

        cleared = health_manager.remediation_manager.clear_remediation(
            camera_name,
            clear_ticket_cooldown=clear_ticket_cooldown
        )

        if cleared:
            msg = f'Remediation state cleared for {camera_name}'
            if clear_ticket_cooldown:
                msg += ' (ticket cooldown also cleared)'
            return jsonify({
                'success': True,
                'message': msg
            })
        else:
            return jsonify({
                'success': False,
                'message': f'{camera_name} was not under remediation'
            }), 404
    except Exception as e:
        logger.error(f"Error clearing remediation: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# IMAGE ANALYSIS API ENDPOINTS
# =============================================================================

@app.route('/api/analysis/camera/<camera_name>', methods=['POST'])
def analyze_camera_image(camera_name):
    """Analyze a camera's current snapshot using AI"""
    if not image_analyzer:
        return jsonify({'error': 'Image analyzer not available'}), 503

    # Find camera in CAMERAS dict
    camera_data = None
    for cam_id, cam_info in CAMERAS.items():
        if cam_info.get('name') == camera_name or cam_id == camera_name:
            camera_data = cam_info
            break

    if not camera_data:
        return jsonify({'error': f'Camera {camera_name} not found'}), 404

    try:
        camera_ip = camera_data.get('ip')
        username = camera_data.get('username', CAMERA_DEFAULTS['onvif_user'])
        password = camera_data.get('password', CAMERA_DEFAULTS['onvif_pass'])

        # Try multiple HTTP snapshot endpoints (same as health monitor)
        camera_configs = [
            # Cohu cameras - Basic auth
            ("Cohu", "/jpegpull/snapshot", "basic", username, password),
            # Axis cameras - Digest auth with various credentials
            ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "root"),
            ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "T@mpa234"),
            ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "Service!1"),
            ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "FDOT", "FloridaD0t3!."),
            # Generic fallbacks
            ("Generic", "/snapshot.jpg", "basic", username, password),
        ]

        image_data = None
        for vendor, path, auth_type, user, passwd in camera_configs:
            try:
                url = f"http://{camera_ip}{path}"
                if auth_type == "basic":
                    auth = (user, passwd)
                    response = requests.get(url, auth=auth, timeout=10)
                else:  # digest
                    from requests.auth import HTTPDigestAuth
                    response = requests.get(url, auth=HTTPDigestAuth(user, passwd), timeout=10)

                if response.status_code == 200 and len(response.content) > 1000:
                    image_data = response.content
                    logger.debug(f"Captured snapshot from {camera_name} using {vendor} endpoint")
                    break
            except Exception as e:
                logger.debug(f"{vendor} snapshot failed for {camera_ip}: {e}")
                continue

        if not image_data:
            return jsonify({
                'error': f"Failed to capture snapshot from {camera_name} - all methods failed"
            }), 500

        # Analyze with AI
        analysis = image_analyzer.analyze_image(image_data, camera_name)

        return jsonify(analysis)

    except Exception as e:
        logger.error(f"Error analyzing camera {camera_name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/quality', methods=['GET'])
def get_quality_status():
    """Get image quality status for all cameras"""
    if not image_analyzer:
        return jsonify({'error': 'Image analyzer not available'}), 503

    try:
        cameras = image_analyzer.get_camera_quality_status()
        summary = image_analyzer.get_quality_summary()

        return jsonify({
            'cameras': cameras,
            'summary': summary
        })
    except Exception as e:
        logger.error(f"Error getting quality status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/quality/<camera_name>', methods=['GET'])
def get_camera_quality(camera_name):
    """Get image quality status for a specific camera"""
    if not image_analyzer:
        return jsonify({'error': 'Image analyzer not available'}), 503

    try:
        status = image_analyzer.get_camera_quality_status(camera_name)
        history = image_analyzer.get_analysis_history(camera_name)

        if not status:
            return jsonify({
                'camera_name': camera_name,
                'message': 'No analysis data available for this camera'
            }), 404

        return jsonify({
            'current': status[0] if status else None,
            'history': history
        })
    except Exception as e:
        logger.error(f"Error getting quality for {camera_name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/attention', methods=['GET'])
def get_cameras_needing_attention():
    """Get cameras with low quality scores needing maintenance"""
    if not image_analyzer:
        return jsonify({'error': 'Image analyzer not available'}), 503

    try:
        threshold = request.args.get('threshold', 50, type=int)
        cameras = image_analyzer.get_cameras_needing_attention(threshold)

        return jsonify({
            'cameras': cameras,
            'count': len(cameras),
            'threshold': threshold
        })
    except Exception as e:
        logger.error(f"Error getting cameras needing attention: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/batch', methods=['POST'])
def batch_analyze_cameras():
    """Analyze multiple cameras (or all) - runs in background"""
    if not image_analyzer:
        return jsonify({'error': 'Image analyzer not available'}), 503

    try:
        data = request.get_json() or {}
        camera_names = data.get('cameras', [])

        # If no cameras specified, analyze all
        if not camera_names:
            camera_names = [cam_info.get('name', cam_id) for cam_id, cam_info in CAMERAS.items()]

        # Limit to prevent overload
        max_cameras = 300
        if len(camera_names) > max_cameras:
            return jsonify({
                'error': f'Too many cameras. Maximum is {max_cameras} at a time.'
            }), 400

        # Start analysis in background (for now, do synchronously but limit)
        results = []
        for camera_name in camera_names:  # Process all requested cameras
            # Find camera in CAMERAS dict
            camera_data = None
            for cam_id, cam_info in CAMERAS.items():
                if cam_info.get('name') == camera_name or cam_id == camera_name:
                    camera_data = cam_info
                    break

            if not camera_data:
                results.append({
                    'camera_name': camera_name,
                    'success': False,
                    'error': 'Camera not found'
                })
                continue

            try:
                camera_ip = camera_data.get('ip')
                username = camera_data.get('username', CAMERA_DEFAULTS['onvif_user'])
                password = camera_data.get('password', CAMERA_DEFAULTS['onvif_pass'])

                # Try multiple HTTP snapshot endpoints
                camera_configs = [
                    ("Cohu", "/jpegpull/snapshot", "basic", username, password),
                    ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "root"),
                    ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "T@mpa234"),
                    ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "root", "Service!1"),
                    ("Axis", "/axis-cgi/jpg/image.cgi", "digest", "FDOT", "FloridaD0t3!."),
                    ("Generic", "/snapshot.jpg", "basic", username, password),
                ]

                image_data = None
                for vendor, path, auth_type, user, passwd in camera_configs:
                    try:
                        url = f"http://{camera_ip}{path}"
                        if auth_type == "basic":
                            response = requests.get(url, auth=(user, passwd), timeout=10)
                        else:
                            from requests.auth import HTTPDigestAuth
                            response = requests.get(url, auth=HTTPDigestAuth(user, passwd), timeout=10)

                        if response.status_code == 200 and len(response.content) > 1000:
                            image_data = response.content
                            break
                    except:
                        continue

                if image_data:
                    analysis = image_analyzer.analyze_image(image_data, camera_name)
                    results.append(analysis)
                else:
                    results.append({
                        'camera_name': camera_name,
                        'success': False,
                        'error': 'Snapshot capture failed'
                    })
            except Exception as e:
                results.append({
                    'camera_name': camera_name,
                    'success': False,
                    'error': str(e)
                })

        return jsonify({
            'results': results,
            'analyzed': len([r for r in results if r.get('success')]),
            'total_requested': len(camera_names)
        })

    except Exception as e:
        logger.error(f"Error in batch analysis: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# REPORTING & TREND ANALYSIS ENDPOINTS
# =============================================================================

@app.route('/api/reports/summary', methods=['GET'])
def get_system_summary():
    """Get system health summary for specified number of days"""
    if not report_generator:
        return jsonify({'error': 'Report generator not available'}), 503

    try:
        days = request.args.get('days', 7, type=int)
        summary = report_generator.get_system_health_summary(days)
        return jsonify(summary)
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/trends', methods=['GET'])
def get_performance_trends():
    """Get daily performance trends"""
    if not report_generator:
        return jsonify({'error': 'Report generator not available'}), 503

    try:
        days = request.args.get('days', 7, type=int)
        trends = report_generator.get_performance_trends(days)
        return jsonify({'trends': trends, 'period_days': days})
    except Exception as e:
        logger.error(f"Error getting trends: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/failing-cameras', methods=['GET'])
def get_failing_cameras():
    """Get cameras with most failures"""
    if not report_generator:
        return jsonify({'error': 'Report generator not available'}), 503

    try:
        days = request.args.get('days', 7, type=int)
        limit = request.args.get('limit', 10, type=int)
        cameras = report_generator.get_top_failing_cameras(days, limit)
        return jsonify({'cameras': cameras, 'period_days': days})
    except Exception as e:
        logger.error(f"Error getting failing cameras: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/daily', methods=['GET'])
def generate_daily_report():
    """Generate daily health report (text format)"""
    if not report_generator:
        return jsonify({'error': 'Report generator not available'}), 503

    try:
        report = report_generator.generate_daily_report()
        return jsonify({'report': report})
    except Exception as e:
        logger.error(f"Error generating daily report: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/weekly', methods=['GET'])
def generate_weekly_report():
    """Generate weekly summary report (text format)"""
    if not report_generator:
        return jsonify({'error': 'Report generator not available'}), 503

    try:
        report = report_generator.generate_weekly_report()
        return jsonify({'report': report})
    except Exception as e:
        logger.error(f"Error generating weekly report: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/send-daily', methods=['POST'])
def send_daily_report():
    """Send daily report via email"""
    if not report_generator:
        return jsonify({'error': 'Report generator not available'}), 503

    try:
        data = request.get_json() or {}
        recipients = data.get('recipients', [])

        if not recipients:
            # Default to stakeholder emails
            stakeholder_emails = os.getenv('STAKEHOLDER_EMAILS', '')
            recipients = [e.strip() for e in stakeholder_emails.split(',') if e.strip()]

        if not recipients:
            return jsonify({'error': 'No recipients specified'}), 400

        success = report_generator.send_daily_report(recipients)

        if success:
            return jsonify({'message': f'Daily report sent to {len(recipients)} recipients'})
        else:
            return jsonify({'error': 'Failed to send report'}), 500
    except Exception as e:
        logger.error(f"Error sending daily report: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/send-weekly', methods=['POST'])
def send_weekly_report():
    """Send weekly report via email"""
    if not report_generator:
        return jsonify({'error': 'Report generator not available'}), 503

    try:
        data = request.get_json() or {}
        recipients = data.get('recipients', [])

        if not recipients:
            # Default to stakeholder emails
            stakeholder_emails = os.getenv('STAKEHOLDER_EMAILS', '')
            recipients = [e.strip() for e in stakeholder_emails.split(',') if e.strip()]

        if not recipients:
            return jsonify({'error': 'No recipients specified'}), 400

        success = report_generator.send_weekly_report(recipients)

        if success:
            return jsonify({'message': f'Weekly report sent to {len(recipients)} recipients'})
        else:
            return jsonify({'error': 'Failed to send report'}), 500
    except Exception as e:
        logger.error(f"Error sending weekly report: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """Get report scheduler status and configuration"""
    if not report_scheduler:
        return jsonify({'error': 'Report scheduler not available'}), 503

    try:
        status = report_scheduler.get_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        return jsonify({'error': str(e)}), 500

# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point"""
    logger.info("="*70)
    logger.info("FDOT CCTV Operations Tool v6.0")
    logger.info("="*70)

    # Initialize managers
    initialize_managers()

    # Register advanced feature APIs (groups, search, SLA, maintenance)
    try:
        # Create database manager for API endpoints
        db_manager = DatabaseManager()
        register_advanced_apis(app, CAMERAS, db_manager)
        logger.info("✓ Advanced feature APIs registered")
    except Exception as e:
        logger.error(f"Failed to register advanced APIs: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # Create Email Notifier for alerts
    email_notifier = None
    try:
        email_notifier = create_email_notifier()
        if email_notifier and email_notifier.enabled:
            logger.info("✓ Email Notifier initialized for alerts")
        else:
            logger.info("Email notifications disabled (missing SMTP configuration)")
    except Exception as e:
        logger.warning(f"Failed to create email notifier: {e}")

    # Start Alert Processing Engine
    try:
        alert_engine = create_alert_engine(db_manager, CAMERAS, check_interval=300, email_notifier=email_notifier)
        if alert_engine:
            logger.info("✓ Alert Processing Engine started (check interval: 5 minutes)")
        else:
            logger.warning("Alert Processing Engine failed to start")
    except Exception as e:
        logger.error(f"Failed to start Alert Processing Engine: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # Start health monitoring background checks
    if health_manager:
        try:
            health_manager.start_background_checks()
            logger.info("✓ Health monitoring started")
        except Exception as e:
            logger.error(f"Failed to start health monitoring: {e}")

    # Start report scheduler
    if report_scheduler:
        try:
            report_scheduler.start()
            status = report_scheduler.get_status()
            logger.info(f"✓ Report scheduler started (Daily: {status['daily_report_time']}, Weekly: Day {status['weekly_report_day']} at {status['weekly_report_time']})")
        except Exception as e:
            logger.error(f"Failed to start report scheduler: {e}")

    # Print status
    print("\n" + "="*70)
    print("CCTV Operations Tool Started")
    print("="*70)
    print(f"✓ Storage: {STORAGE_CONFIG['base_path']}")
    print(f"{'✓' if ONVIF_AVAILABLE else '✗'} ONVIF Reboot: {'Available' if ONVIF_AVAILABLE else 'Not available'}")
    print(f"{'✓' if MIMS_AVAILABLE and mims_client else '✗'} MIMS Ticketing: {'Connected' if mims_client else 'Not connected'}")
    print(f"{'✓' if EMAIL_CONFIG['enabled'] else '✗'} Email Notifications: {'Enabled' if EMAIL_CONFIG['enabled'] else 'Disabled'}")
    print(f"{'✓' if health_manager else '✗'} Health Monitoring: {'Active' if health_manager else 'Disabled'}")
    print(f"\nAPI Server: http://localhost:5000")
    print("="*70)
    
    # Start Flask app
    app.run(
        host=FLASK_CONFIG['host'],
        port=FLASK_CONFIG['port'],
        debug=FLASK_CONFIG['debug'],
        threaded=True
    )

if __name__ == "__main__":
    main()
