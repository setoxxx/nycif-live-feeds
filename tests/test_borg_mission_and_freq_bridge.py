from __future__ import annotations

import json
import unittest
from pathlib import Path


class BorgMissionAndFreqBridgeTests(unittest.TestCase):
    def setUp(self):
        self.mission = json.loads(Path('docs/contracts/BORG_MISSION_ACQUISITION_V1.json').read_text())
        self.bridge = json.loads(Path('docs/contracts/BORG_FREQ_DISCOVERY_BRIDGE_V1.json').read_text())

    def test_acquisition_is_broad_but_not_bypass_based(self):
        self.assertEqual(self.mission['contract'], 'nycif.borg-mission-acquisition.v1')
        blocked = set(self.mission['aggressive_acquisition_definition']['does_not_mean'])
        self.assertIn('bypassing authentication', blocked)
        self.assertIn('evading rate limits', blocked)
        self.assertFalse(self.mission['automated_retrieval_policy']['private_or_loopback_network_targets_allowed'])
        self.assertFalse(self.mission['automated_retrieval_policy']['credential_discovery_or_extraction_allowed'])
        self.assertTrue(self.mission['automated_retrieval_policy']['robots_disallow_blocks_automated_html_fetch'])
        self.assertFalse(self.mission['learning']['may_self_authorize_new_rights_or_publication'])

    def test_acquisition_creates_observations_not_truth(self):
        self.assertIn('Acquisition creates observations, not truth', self.mission['publication_rule'])
        self.assertEqual(self.mission['authority']['source_acquisition'], 'BORG')
        self.assertEqual(self.mission['authority']['freq_public_safety_truth'], 'FREQ')
        self.assertTrue(self.mission['authority']['no_second_authority'])

    def test_freq_bridge_excludes_sensitive_radio_material(self):
        forbidden = set(self.bridge['observation_input']['forbidden_fields'])
        for field in (
            'raw_audio',
            'raw_iq',
            'private_transcript',
            'receiver_exact_location',
            'private_responder_identity',
            'tactical_detail',
            'encryption_key_material',
            'unpublished_exact_incident_coordinates',
        ):
            self.assertIn(field, forbidden)

    def test_freq_bridge_cannot_infer_or_publish_location(self):
        rules = self.bridge['location_rules']
        self.assertFalse(rules['borg_may_infer_incident_location_from_receiver_location'])
        self.assertFalse(rules['borg_may_triangulate_transmitter_or_caller_location'])
        self.assertFalse(rules['coordinate_presence_alone_creates_exact_authority'])
        self.assertFalse(rules['ambiguous_or_unresolved_observation_may_create_exact_public_pin'])
        self.assertTrue(rules['ambiguous_or_unresolved_observation_may_trigger_area_level_search'])

    def test_freq_alert_authority_remains_freq(self):
        public = self.bridge['public_projection']
        self.assertTrue(public['freq_public_alert_truth_remains_in_freq'])
        self.assertTrue(public['national_map_consumes_only_reader_safe_public_projection'])
        self.assertTrue(public['borg_cannot_activate_or_deactivate_freq_alert'])
        self.assertTrue(public['borg_corroboration_may_enrich_context_but_cannot_manufacture_alert'])

    def test_freq_runtime_freeze_is_respected(self):
        state = self.bridge['current_dependency_state']
        self.assertEqual(state['freq_repo'], 'setoxxx/freqmap')
        self.assertTrue(state['freq_integration_freeze'])
        self.assertIn('Gate 48 HOLD', state['freq_gate'])


if __name__ == '__main__':
    unittest.main()
