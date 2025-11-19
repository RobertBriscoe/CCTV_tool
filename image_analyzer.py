"""
AI-Powered Image Analysis for CCTV Snapshots
Uses Google Gemini API to analyze camera image quality and detect issues
"""

import os
import json
import base64
import logging
import pyodbc
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests

logger = logging.getLogger(__name__)


class ImageAnalyzer:
    """
    Analyzes CCTV snapshots using Google Gemini AI to detect quality issues
    """

    def __init__(self, db_config: Dict):
        """
        Initialize the ImageAnalyzer

        Args:
            db_config: Database configuration dictionary
        """
        self.api_key = os.getenv('GEMINI_API_KEY')
        self.db_config = db_config
        self.enabled = bool(self.api_key)

        if not self.enabled:
            logger.warning("GEMINI_API_KEY not configured - AI analysis disabled")
        else:
            logger.info("AI Image Analysis enabled with Gemini API")
            self._ensure_tables()

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

    def _ensure_tables(self):
        """Create database tables if they don't exist"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Image analysis results table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='cctv_image_analysis' AND xtype='U')
                CREATE TABLE cctv_image_analysis (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    camera_name NVARCHAR(100) NOT NULL,
                    analysis_timestamp DATETIME NOT NULL,
                    quality_score INT NOT NULL,
                    issues_detected NVARCHAR(MAX),
                    recommendations NVARCHAR(MAX),
                    raw_analysis NVARCHAR(MAX),
                    created_at DATETIME DEFAULT GETDATE()
                )
            """)

            # Index for faster queries
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_image_analysis_camera_time')
                CREATE INDEX idx_image_analysis_camera_time
                ON cctv_image_analysis(camera_name, analysis_timestamp DESC)
            """)

            # Camera image quality status table (current state)
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='cctv_image_quality_status' AND xtype='U')
                CREATE TABLE cctv_image_quality_status (
                    camera_name NVARCHAR(100) PRIMARY KEY,
                    last_analysis DATETIME,
                    quality_score INT,
                    issues_detected NVARCHAR(MAX),
                    recommendations NVARCHAR(MAX),
                    consecutive_low_scores INT DEFAULT 0,
                    updated_at DATETIME DEFAULT GETDATE()
                )
            """)

            conn.commit()
            cursor.close()
            conn.close()
            logger.info("Image analysis database tables ready")

        except Exception as e:
            logger.error(f"Failed to create image analysis tables: {e}")

    def analyze_image(self, image_data: bytes, camera_name: str) -> Dict:
        """
        Analyze a camera snapshot using Gemini AI

        Args:
            image_data: Raw image bytes (JPEG)
            camera_name: Name of the camera

        Returns:
            Dictionary with analysis results
        """
        if not self.enabled:
            return {
                'success': False,
                'error': 'AI analysis not enabled - GEMINI_API_KEY not configured'
            }

        try:
            # Encode image to base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')

            # Prepare the prompt for Gemini
            analysis_prompt = """Analyze this CCTV camera snapshot and provide a quality assessment.

Evaluate the following aspects and provide a JSON response:

1. **Overall Quality Score** (0-100): Based on clarity, visibility, and usefulness for traffic monitoring
2. **Issues Detected**: List any problems found from these categories:
   - Image blur or focus issues
   - Lighting problems (too dark, overexposed, glare)
   - Obstructions (dirty lens, spider webs, vegetation, debris)
   - Camera positioning issues (tilted, wrong angle, pointing at sky)
   - Weather impact (fog, rain, snow reducing visibility)
   - Technical issues (color distortion, artifacts, noise)
   - No visible road/traffic (camera not showing intended area)

3. **Recommendations**: Specific maintenance actions needed

Respond ONLY with valid JSON in this exact format:
{
    "quality_score": <0-100>,
    "issues": ["issue1", "issue2"],
    "recommendations": ["recommendation1", "recommendation2"],
    "summary": "Brief one-sentence summary of image quality"
}

If the image shows a clear view of road/traffic with no issues, return a high score (80-100) with empty issues array."""

            # Call Gemini API
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"

            payload = {
                "contents": [{
                    "parts": [
                        {"text": analysis_prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_base64
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 1024
                }
            }

            response = requests.post(url, json=payload, timeout=30)

            if response.status_code != 200:
                logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f'API error: {response.status_code}'
                }

            # Parse response
            result = response.json()

            # Extract the text content
            try:
                text_content = result['candidates'][0]['content']['parts'][0]['text']

                # Clean up the response (remove markdown code blocks if present)
                text_content = text_content.strip()
                if text_content.startswith('```json'):
                    text_content = text_content[7:]
                if text_content.startswith('```'):
                    text_content = text_content[3:]
                if text_content.endswith('```'):
                    text_content = text_content[:-3]
                text_content = text_content.strip()

                # Parse JSON
                analysis = json.loads(text_content)

                # Store results in database
                self._store_analysis(camera_name, analysis)

                return {
                    'success': True,
                    'camera_name': camera_name,
                    'quality_score': analysis.get('quality_score', 0),
                    'issues': analysis.get('issues', []),
                    'recommendations': analysis.get('recommendations', []),
                    'summary': analysis.get('summary', ''),
                    'timestamp': datetime.now().isoformat()
                }

            except (KeyError, json.JSONDecodeError) as e:
                logger.error(f"Failed to parse Gemini response: {e}")
                logger.debug(f"Raw response: {result}")
                return {
                    'success': False,
                    'error': f'Failed to parse response: {e}'
                }

        except requests.exceptions.Timeout:
            logger.error(f"Gemini API timeout for {camera_name}")
            return {
                'success': False,
                'error': 'API timeout'
            }
        except Exception as e:
            logger.error(f"Image analysis failed for {camera_name}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _store_analysis(self, camera_name: str, analysis: Dict):
        """Store analysis results in database"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            timestamp = datetime.now()
            quality_score = analysis.get('quality_score', 0)
            issues = json.dumps(analysis.get('issues', []))
            recommendations = json.dumps(analysis.get('recommendations', []))
            raw_analysis = json.dumps(analysis)

            # Insert into history table
            cursor.execute("""
                INSERT INTO cctv_image_analysis
                (camera_name, analysis_timestamp, quality_score, issues_detected,
                 recommendations, raw_analysis)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (camera_name, timestamp, quality_score, issues, recommendations, raw_analysis))

            # Update current status table
            cursor.execute("""
                MERGE cctv_image_quality_status AS target
                USING (SELECT ? AS camera_name) AS source
                ON target.camera_name = source.camera_name
                WHEN MATCHED THEN
                    UPDATE SET
                        last_analysis = ?,
                        quality_score = ?,
                        issues_detected = ?,
                        recommendations = ?,
                        consecutive_low_scores = CASE
                            WHEN ? < 50 THEN consecutive_low_scores + 1
                            ELSE 0
                        END,
                        updated_at = GETDATE()
                WHEN NOT MATCHED THEN
                    INSERT (camera_name, last_analysis, quality_score, issues_detected,
                            recommendations, consecutive_low_scores)
                    VALUES (?, ?, ?, ?, ?, CASE WHEN ? < 50 THEN 1 ELSE 0 END);
            """, (
                camera_name,
                timestamp, quality_score, issues, recommendations, quality_score,
                camera_name, timestamp, quality_score, issues, recommendations, quality_score
            ))

            conn.commit()
            cursor.close()
            conn.close()

            logger.debug(f"Stored analysis for {camera_name}: score={quality_score}")

        except Exception as e:
            logger.error(f"Failed to store analysis for {camera_name}: {e}")

    def get_camera_quality_status(self, camera_name: str = None) -> List[Dict]:
        """
        Get current image quality status for cameras

        Args:
            camera_name: Optional specific camera name, or None for all

        Returns:
            List of camera quality status dictionaries
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            if camera_name:
                cursor.execute("""
                    SELECT camera_name, last_analysis, quality_score,
                           issues_detected, recommendations, consecutive_low_scores
                    FROM cctv_image_quality_status
                    WHERE camera_name = ?
                """, (camera_name,))
            else:
                cursor.execute("""
                    SELECT camera_name, last_analysis, quality_score,
                           issues_detected, recommendations, consecutive_low_scores
                    FROM cctv_image_quality_status
                    ORDER BY quality_score ASC
                """)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'camera_name': row[0],
                    'last_analysis': row[1].isoformat() if row[1] else None,
                    'quality_score': row[2],
                    'issues': json.loads(row[3]) if row[3] else [],
                    'recommendations': json.loads(row[4]) if row[4] else [],
                    'consecutive_low_scores': row[5]
                })

            cursor.close()
            conn.close()
            return results

        except Exception as e:
            logger.error(f"Failed to get quality status: {e}")
            return []

    def get_cameras_needing_attention(self, threshold: int = 50) -> List[Dict]:
        """
        Get cameras with quality scores below threshold

        Args:
            threshold: Quality score threshold (default 50)

        Returns:
            List of cameras needing attention
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT camera_name, last_analysis, quality_score,
                       issues_detected, recommendations, consecutive_low_scores
                FROM cctv_image_quality_status
                WHERE quality_score < ? OR consecutive_low_scores >= 3
                ORDER BY quality_score ASC
            """, (threshold,))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'camera_name': row[0],
                    'last_analysis': row[1].isoformat() if row[1] else None,
                    'quality_score': row[2],
                    'issues': json.loads(row[3]) if row[3] else [],
                    'recommendations': json.loads(row[4]) if row[4] else [],
                    'consecutive_low_scores': row[5]
                })

            cursor.close()
            conn.close()
            return results

        except Exception as e:
            logger.error(f"Failed to get cameras needing attention: {e}")
            return []

    def get_analysis_history(self, camera_name: str, limit: int = 10) -> List[Dict]:
        """
        Get analysis history for a specific camera

        Args:
            camera_name: Camera name
            limit: Maximum number of records

        Returns:
            List of historical analysis records
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT TOP (?) analysis_timestamp, quality_score,
                       issues_detected, recommendations
                FROM cctv_image_analysis
                WHERE camera_name = ?
                ORDER BY analysis_timestamp DESC
            """, (limit, camera_name))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'timestamp': row[0].isoformat() if row[0] else None,
                    'quality_score': row[1],
                    'issues': json.loads(row[2]) if row[2] else [],
                    'recommendations': json.loads(row[3]) if row[3] else []
                })

            cursor.close()
            conn.close()
            return results

        except Exception as e:
            logger.error(f"Failed to get analysis history for {camera_name}: {e}")
            return []

    def get_quality_summary(self) -> Dict:
        """
        Get overall image quality summary statistics

        Returns:
            Dictionary with summary statistics
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total_analyzed,
                    AVG(quality_score) as avg_score,
                    SUM(CASE WHEN quality_score >= 80 THEN 1 ELSE 0 END) as excellent,
                    SUM(CASE WHEN quality_score >= 50 AND quality_score < 80 THEN 1 ELSE 0 END) as acceptable,
                    SUM(CASE WHEN quality_score < 50 THEN 1 ELSE 0 END) as poor
                FROM cctv_image_quality_status
            """)

            row = cursor.fetchone()

            result = {
                'total_analyzed': row[0] or 0,
                'average_score': round(row[1] or 0, 1),
                'excellent_count': row[2] or 0,
                'acceptable_count': row[3] or 0,
                'poor_count': row[4] or 0
            }

            cursor.close()
            conn.close()
            return result

        except Exception as e:
            logger.error(f"Failed to get quality summary: {e}")
            return {
                'total_analyzed': 0,
                'average_score': 0,
                'excellent_count': 0,
                'acceptable_count': 0,
                'poor_count': 0
            }
