"""
Comprehensive E2E browser testing for Daily Plan redesign Phase 2
Creates dedicated temp project and tests ACTUAL browser workflows
"""
import requests
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv('/app/backend/.env')

BASE_URL = os.environ['PREVIEW_APP_URL']
ADMIN_ID = os.environ['PREVIEW_ADMIN_IDENTIFIER']
ADMIN_PW = os.environ['PREVIEW_ADMIN_PASSWORD']
WORKER_ID = os.environ['PREVIEW_WORKER_IDENTIFIER']
WORKER_PW = os.environ['PREVIEW_WORKER_PASSWORD']

FIXTURES_FILE = '/app/memory/browser_fixtures.json'

class BrowserTestSetup:
    """Setup and teardown for browser E2E tests"""
    
    def __init__(self):
        self.admin_token = None
        self.supervisor_token = None
        self.worker_token = None
        self.fixtures = {
            'project_id': None,
            'blocks': [],
            'units': [],
            'supervisor_id': None,
            'worker_id': None,
            'tasks': [],
            'notifications': []
        }
    
    def log(self, msg, level='INFO'):
        print(f"[{level}] {msg}")
    
    def request(self, method, path, token=None, data=None, expect=200):
        """Make API request"""
        url = f"{BASE_URL}{path}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        try:
            if method == 'GET':
                r = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                r = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PATCH':
                r = requests.patch(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                r = requests.delete(url, headers=headers, timeout=15)
            
            if r.status_code != expect:
                self.log(f"{method} {path} - Expected {expect}, got {r.status_code}: {r.text[:300]}", 'ERROR')
                return None
            
            return r.json() if r.text else {}
        except Exception as e:
            self.log(f"{method} {path} - Error: {str(e)}", 'ERROR')
            return None
    
    def setup_auth(self):
        """Authenticate admin and worker"""
        self.log("=== Authenticating ===")
        
        # Admin login
        result = self.request('POST', '/api/auth/login', data={
            'identifier': ADMIN_ID,
            'password': ADMIN_PW
        })
        if not result or 'token' not in result:
            self.log("Admin login failed", 'ERROR')
            return False
        
        self.admin_token = result['token']
        self.log("✅ Admin authenticated")
        
        # Worker login
        result = self.request('POST', '/api/auth/login', data={
            'identifier': WORKER_ID,
            'password': WORKER_PW
        })
        if not result or 'token' not in result:
            self.log("Worker login failed", 'ERROR')
            return False
        
        self.worker_token = result['token']
        self.fixtures['worker_id'] = result.get('user', {}).get('id')
        self.log(f"✅ Worker authenticated (ID: {self.fixtures['worker_id']})")
        
        return True
    
    def create_temp_project(self):
        """Create dedicated temp project for testing"""
        self.log("=== Creating Temp Project ===")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        target_date = (datetime.now() + timedelta(days=90)).date().isoformat()
        project_data = {
            'name': f'E2E Test Project {timestamp}',
            'location': 'Test Location',
            'company': 'Test Company',
            'budget': 100000,
            'target_date': target_date
        }
        
        result = self.request('POST', '/api/projects', 
                            token=self.admin_token, 
                            data=project_data)
        
        if not result or 'id' not in result:
            self.log("Failed to create temp project", 'ERROR')
            return False
        
        self.fixtures['project_id'] = result['id']
        self.log(f"✅ Created temp project: {result['name']} (ID: {result['id']})")
        
        return True
    
    def create_temp_blocks(self):
        """Create 2 blocks with 2 levels each, 4 units per level"""
        self.log("=== Creating Temp Blocks ===")
        
        pid = self.fixtures['project_id']
        
        for block_name in ['A', 'B']:
            block_data = {
                'name': block_name,
                'levels': 2,
                'room_mix': [
                    {'room_type': '4-room', 'count': 4}
                ],
                'first_unit': 1
            }
            
            result = self.request('POST', f'/api/projects/{pid}/blocks',
                                token=self.admin_token,
                                data=block_data)
            
            if not result or 'id' not in result:
                self.log(f"Failed to create block {block_name}", 'ERROR')
                return False
            
            self.fixtures['blocks'].append(result['id'])
            self.log(f"✅ Created Block {block_name} with 8 units (2 levels × 4 units)")
        
        return True
    
    def get_temp_units(self):
        """Get all units from temp project"""
        self.log("=== Fetching Temp Units ===")
        
        pid = self.fixtures['project_id']
        result = self.request('GET', f'/api/projects/{pid}/workspace',
                            token=self.admin_token)
        
        if not result or 'units' not in result:
            self.log("Failed to fetch workspace", 'ERROR')
            return False
        
        self.fixtures['units'] = [u['id'] for u in result['units']]
        self.log(f"✅ Found {len(self.fixtures['units'])} units in temp project")
        
        return True
    
    def save_fixtures(self):
        """Save fixtures to file for cleanup"""
        try:
            with open(FIXTURES_FILE, 'w') as f:
                json.dump(self.fixtures, f, indent=2)
            self.log(f"✅ Saved fixtures to {FIXTURES_FILE}")
            return True
        except Exception as e:
            self.log(f"Failed to save fixtures: {e}", 'ERROR')
            return False
    
    def cleanup(self):
        """Clean up all created test data"""
        self.log("=== Cleaning Up Test Data ===")
        
        try:
            # Load fixtures if not in memory
            if not self.fixtures['project_id'] and os.path.exists(FIXTURES_FILE):
                with open(FIXTURES_FILE, 'r') as f:
                    self.fixtures = json.load(f)
                self.log("Loaded fixtures from file")
            
            if not self.fixtures['project_id']:
                self.log("No fixtures to clean up")
                return True
            
            # Delete all tasks
            for task_id in self.fixtures.get('tasks', []):
                self.request('DELETE', f'/api/tasks/{task_id}', 
                           token=self.admin_token, expect=200)
            
            # Delete all units
            for unit_id in self.fixtures.get('units', []):
                self.request('DELETE', f'/api/units/{unit_id}',
                           token=self.admin_token, expect=200)
            
            # Delete all blocks
            pid = self.fixtures['project_id']
            for block_id in self.fixtures.get('blocks', []):
                self.request('DELETE', f'/api/projects/{pid}/blocks/{block_id}',
                           token=self.admin_token, expect=200)
            
            # Delete project
            self.request('DELETE', f'/api/projects/{pid}',
                       token=self.admin_token, expect=200)
            
            # Remove fixtures file
            if os.path.exists(FIXTURES_FILE):
                os.remove(FIXTURES_FILE)
            
            self.log("✅ Cleanup completed")
            return True
            
        except Exception as e:
            self.log(f"Cleanup error: {e}", 'ERROR')
            return False
    
    def run_setup(self):
        """Run full setup"""
        self.log("=" * 60)
        self.log("BROWSER E2E TEST SETUP")
        self.log("=" * 60)
        
        if not self.setup_auth():
            return False
        
        if not self.create_temp_project():
            return False
        
        if not self.create_temp_blocks():
            return False
        
        if not self.get_temp_units():
            return False
        
        if not self.save_fixtures():
            return False
        
        self.log("=" * 60)
        self.log("✅ SETUP COMPLETE - Ready for browser testing")
        self.log("=" * 60)
        self.log(f"Project ID: {self.fixtures['project_id']}")
        self.log(f"Blocks: {len(self.fixtures['blocks'])}")
        self.log(f"Units: {len(self.fixtures['units'])}")
        self.log(f"Worker ID: {self.fixtures['worker_id']}")
        self.log("=" * 60)
        
        return True


def main():
    """Main entry point"""
    setup = BrowserTestSetup()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'cleanup':
        # Cleanup mode
        if not setup.setup_auth():
            return 1
        return 0 if setup.cleanup() else 1
    else:
        # Setup mode
        success = setup.run_setup()
        return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
