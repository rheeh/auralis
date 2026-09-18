import unittest
from unittest.mock import patch
from app.core.local_access import allows_browser

class LocalBoundaryTest(unittest.TestCase):
    def test_untrusted_origin_and_fetch_metadata_rejected(self):
        self.assertFalse(allows_browser({'origin':'https://attacker.invalid'}))
        self.assertFalse(allows_browser({'sec-fetch-site':'cross-site'}))
        self.assertTrue(allows_browser({'origin':'http://127.0.0.1:5173'}))
    def test_desktop_requires_matching_instance_token_for_http_and_media(self):
        with patch.dict('os.environ',{'AURALIS_INSTANCE_TOKEN':'local-secret'}):
            self.assertFalse(allows_browser({'origin':'null'}))
            self.assertFalse(allows_browser({'origin':'null','x-auralis-token':'wrong'}))
            self.assertTrue(allows_browser({'origin':'null','x-auralis-token':'local-secret'}))
            self.assertTrue(allows_browser({'origin':'null'},{'instance_token':'local-secret'}))
