"""
Integration tests that exercise real Flask routes end-to-end, through
the actual test client - not just individual functions in isolation.

WHY THIS FILE EXISTS:
Every "does the full flow actually work" check up to this point was
run manually, in throwaway scripts, during development. That
verification was real, but none of it was committed, so none of it
runs automatically - a future change could silently break the
register -> login -> upload -> review -> success flow and nothing
would catch it. This file locks in the coverage that already existed
informally.
"""

import io
import os
import re
import unittest

import app as appmod
from modules.auth.db import init_db, db_connection
from modules.history.db import init_history_table


def get_csrf_token(client, path):
    response = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.data.decode())
    assert match, f"No CSRF token found on {path}"
    return match.group(1)


class TaxNovaIntegrationTest(unittest.TestCase):

    def setUp(self):
        appmod.app.config['TESTING'] = True
        # Rate limiting is disabled ONLY here, never in config.py - the
        # real limits (5/min login, 10/hour register) exist to stop
        # brute-forcing, but this suite legitimately registers/logs in
        # many more times than that within the same test run.
        #
        # Flask-Limiter reads its enabled flag once at init time
        # (app.py module import), so setting the config key here has
        # no effect - the limiter instance's attribute has to be
        # toggled directly instead.
        appmod.limiter.enabled = False
        self.client = appmod.app.test_client()
        # Isolated per-test DB path avoids interference between test
        # runs and with any real database.db a developer has locally.
        appmod.Config.DATABASE_PATH = os.path.join(
            os.path.dirname(__file__), 'test_integration.db'
        )
        init_db()
        init_history_table()

    def tearDown(self):
        try:
            os.remove(appmod.Config.DATABASE_PATH)
        except OSError:
            pass

    def register_and_login(self, email, password='secret123'):
        token = get_csrf_token(self.client, '/register')
        self.client.post('/register', data={
            'name': 'Test User', 'email': email, 'password': password,
            'csrf_token': token,
        })
        token = get_csrf_token(self.client, '/login')
        return self.client.post('/login', data={
            'email': email, 'password': password, 'csrf_token': token,
        }, follow_redirects=True)

    # ---------------- Auth flow ---------------- #

    def test_register_login_dashboard_flow(self):
        r = self.register_and_login('integration1@example.com')
        self.assertIn(b'Welcome back', r.data)

    def test_wrong_password_rejected(self):
        token = get_csrf_token(self.client, '/register')
        self.client.post('/register', data={
            'name': 'Test', 'email': 'integration2@example.com',
            'password': 'secret123', 'csrf_token': token,
        })
        token = get_csrf_token(self.client, '/login')
        r = self.client.post('/login', data={
            'email': 'integration2@example.com', 'password': 'wrongpass',
            'csrf_token': token,
        })
        self.assertIn(b'Invalid email or password', r.data)

    def test_dashboard_requires_login(self):
        r = self.client.get('/dashboard', follow_redirects=True)
        self.assertIn(b'Login', r.data)

    def test_csrf_blocks_tokenless_post(self):
        r = self.client.post('/register', data={
            'name': 'Attacker', 'email': 'csrf_test@example.com', 'password': 'secret123',
        })
        self.assertEqual(r.status_code, 400)

    # ---------------- Core tax flow ---------------- #

    def test_manual_entry_to_success_computes_tax(self):
        self.register_and_login('integration3@example.com')
        token = get_csrf_token(self.client, '/manual-entry')
        r = self.client.post('/success', data={
            'salary': '900000', 'tds': '30000', 'employer': 'Acme Corp',
            'invested_amount': '150000', 'csrf_token': token,
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Acme Corp', r.data)

    def test_editing_salary_changes_final_tax(self):
        # Regression coverage for a real bug: tax figures used to be
        # passed through as trust-the-client hidden fields, so editing
        # salary on the review page didn't change the final result.
        self.register_and_login('integration4@example.com')
        token = get_csrf_token(self.client, '/manual-entry')
        r_low = self.client.post('/success', data={
            'salary': '500000', 'tds': '0', 'employer': 'X',
            'invested_amount': '0', 'csrf_token': token,
        })
        r_high = self.client.post('/success', data={
            'salary': '3000000', 'tds': '0', 'employer': 'X',
            'invested_amount': '0', 'csrf_token': token,
        })
        self.assertNotEqual(r_low.data, r_high.data)

    def test_tie_does_not_show_false_winner_badge(self):
        self.register_and_login('integration5@example.com')
        token = get_csrf_token(self.client, '/manual-entry')
        r = self.client.post('/success', data={
            'salary': '350000', 'tds': '104', 'employer': 'Stark Industries',
            'invested_amount': '135000', 'csrf_token': token,
        })
        self.assertNotIn(b'BETTER CHOICE', r.data)
        self.assertIn(b'Both regimes result in the same tax', r.data)

    def test_invalid_salary_rejected_with_flash_message(self):
        self.register_and_login('integration6@example.com')
        token = get_csrf_token(self.client, '/manual-entry')
        r = self.client.post('/success', data={
            'salary': 'not-a-number', 'tds': '0', 'employer': 'X',
            'invested_amount': '0', 'csrf_token': token,
        })
        self.assertIn(b'valid salary amount', r.data)

    def test_calculation_appears_in_history(self):
        self.register_and_login('integration7@example.com')
        token = get_csrf_token(self.client, '/manual-entry')
        self.client.post('/success', data={
            'salary': '1200000', 'tds': '60000', 'employer': 'Infosys',
            'invested_amount': '100000', 'csrf_token': token,
        })
        r = self.client.get('/history')
        self.assertIn(b'Infosys', r.data)

    # ---------------- Upload security ---------------- #

    def test_non_pdf_upload_rejected(self):
        self.register_and_login('integration8@example.com')
        token = get_csrf_token(self.client, '/upload')
        data = {
            'pdf_file': (io.BytesIO(b'not a pdf'), 'virus.exe'),
            'csrf_token': token,
        }
        r = self.client.post('/upload', data=data, content_type='multipart/form-data')
        self.assertIn(b'Only PDF files are accepted', r.data)

    def test_uploaded_file_deleted_after_processing(self):
        self.register_and_login('integration9@example.com')
        upload_dir = appmod.app.config['UPLOAD_FOLDER']
        before = set(os.listdir(upload_dir))

        token = get_csrf_token(self.client, '/upload')
        with open(os.path.join(upload_dir, 'Hello 123.pdf'), 'rb') as f:
            data = {'pdf_file': (io.BytesIO(f.read()), 'test.pdf'), 'csrf_token': token}
            self.client.post('/upload', data=data, content_type='multipart/form-data')

        after = set(os.listdir(upload_dir))
        self.assertEqual(before, after, "Uploaded PII-bearing file was not cleaned up")


if __name__ == '__main__':
    unittest.main()
