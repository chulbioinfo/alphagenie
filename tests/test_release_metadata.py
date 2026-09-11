"""Release presentation must not overwrite sealed inference provenance."""
import unittest

from alphagenie import __version__
from app import manuscript_release as release


class ReleaseMetadataTests(unittest.TestCase):
    def test_verified_version_preserves_source_artifacts_and_epoch(self):
        record = release.public_release()
        self.assertEqual(__version__, '0.24.0')
        self.assertEqual(record['data_version'], 'v0.24')
        self.assertEqual(record['source_data_version'], 'v0.20')
        self.assertEqual(record['served_artifact_source_version'], 'v0.20')
        self.assertEqual(record['source_release_id'], release.manifest()['release_id'])
        self.assertEqual(release.manifest()['data_version'], 'v0.20')
        self.assertEqual(record['verified_reanalysis_status'], 'passed')
        self.assertEqual(record['verified_reanalysis_epoch'],
                         'dc23d1efac044e49a9f162e6561673d7')
        self.assertIn('same raw scores', record['verification_design'])
        for key in ('rbfox1', 'ptchd1', 'ccg17'):
            payload = release.payload(key)
            self.assertNotEqual(payload.get('release', {}).get('inference_run_epoch'),
                                record['verified_reanalysis_epoch'])
