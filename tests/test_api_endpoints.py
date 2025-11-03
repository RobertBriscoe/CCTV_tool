"""
Unit tests for CCTV Tool v2 API endpoints
"""

import unittest
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock environment before importing
os.environ['DB_PASSWORD'] = 'test'
os.environ['SMTP_PASSWORD'] = 'test'
os.environ['CAMERA_DEFAULT_PASSWORD'] = 'test'

class TestAPIEndpoints(unittest.TestCase):
    """Test API endpoint functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Import here to avoid import errors
        from CCTV_OperationsTool_Fixed import app, CAMERAS
        self.app = app
        self.client = app.test_client()
        self.cameras = CAMERAS

    def test_health_check(self):
        """Test health check endpoint"""
        response = self.client.get('/api/health')
        self.assertIn(response.status_code, [200, 503])  # Can be degraded
        data = json.loads(response.data)
        self.assertIn('status', data)
        self.assertIn('version', data)
        self.assertEqual(data['version'], '6.0')

    def test_camera_list(self):
        """Test camera list endpoint"""
        response = self.client.get('/api/cameras/list')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('total', data)
        self.assertIn('cameras', data)
        self.assertGreater(data['total'], 0)

    def test_camera_search(self):
        """Test camera search endpoint"""
        response = self.client.get('/api/cameras/search?q=I10&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('query', data)
        self.assertIn('results', data)
        self.assertEqual(data['query'], 'i10')

    def test_camera_search_invalid(self):
        """Test camera search with invalid query"""
        response = self.client.get('/api/cameras/search?q=a')
        self.assertEqual(response.status_code, 400)

    def test_camera_list_with_search(self):
        """Test camera list with search parameter"""
        response = self.client.get('/api/cameras/list?search=001&limit=10')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('cameras', data)
        self.assertLessEqual(len(data['cameras']), 10)

    def test_camera_list_with_sort(self):
        """Test camera list with sorting"""
        response = self.client.get('/api/cameras/list?sort=name&order=asc&limit=5')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        cameras = data['cameras']
        if len(cameras) >= 2:
            # Check if sorted
            self.assertLessEqual(cameras[0]['name'], cameras[1]['name'])

    def test_highway_filter(self):
        """Test cameras by highway filter"""
        response = self.client.get('/api/cameras/by-highway?highway=I10')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('highways', data)
        self.assertIn('total_cameras', data)
        self.assertIn('data', data)

    def test_bulk_camera_info(self):
        """Test bulk camera info endpoint"""
        # Get first camera IP
        if self.cameras:
            first_camera = list(self.cameras.values())[0]
            test_data = {
                'camera_ips': [first_camera['ip']]
            }
            response = self.client.post(
                '/api/cameras/bulk-info',
                data=json.dumps(test_data),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn('cameras', data)
            self.assertEqual(len(data['cameras']), 1)

    def test_metrics_endpoint(self):
        """Test metrics endpoint"""
        response = self.client.get('/api/metrics')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('cameras_total', data)
        self.assertIn('services_up', data)

    def test_config_endpoint(self):
        """Test configuration endpoint"""
        response = self.client.get('/api/config')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('email', data)
        self.assertIn('mims', data)
        self.assertIn('storage', data)

    def test_dashboard_loads(self):
        """Test that dashboard HTML loads"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'FDOT CCTV Operations Tool', response.data)

class TestCameraLocationExtraction(unittest.TestCase):
    """Test location extraction utility"""

    def setUp(self):
        """Import function"""
        from CCTV_OperationsTool_Fixed import extract_location
        self.extract_location = extract_location

    def test_extract_location_standard(self):
        """Test standard camera name format"""
        result = self.extract_location("CCTV-I10-001.5-EB")
        self.assertEqual(result, "I10 MM 001.5 EB")

    def test_extract_location_no_direction(self):
        """Test camera name without direction"""
        result = self.extract_location("CCTV-I110-002.3")
        self.assertIn("I110", result)
        self.assertIn("002.3", result)

    def test_extract_location_invalid(self):
        """Test invalid camera name"""
        result = self.extract_location("INVALID")
        self.assertEqual(result, "INVALID")

if __name__ == '__main__':
    unittest.main()
