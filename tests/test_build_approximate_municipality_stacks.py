import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_approximate_municipality_stacks import build


class ApproximateStacksTests(unittest.TestCase):
    def write_layer(self, root: Path, name: str, events: list[dict]) -> Path:
        base = root / name
        (base / 'pages').mkdir(parents=True)
        (base / 'manifest.json').write_text(
            json.dumps({'pages': [{'page': 'page-0001.json', 'count': len(events)}]}),
            encoding='utf-8',
        )
        (base / 'pages/page-0001.json').write_text(
            json.dumps({'events': events}),
            encoding='utf-8',
        )
        return base / 'manifest.json'

    def test_source_separation_and_unresolved_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            approved = self.write_layer(root, 'approved', [{'id': 'approved-1'}])
            review = self.write_layer(
                root,
                'review',
                [
                    {
                        'id': 'area-1',
                        'title': 'Permit',
                        'borough': 'Queens',
                        'coordinate_status': 'list_only',
                        'nycif': {'coordinate_status': 'list_only'},
                        'source': {'dataset': 'tvpp-9vvx', 'source_event_id': '1'},
                    },
                    {
                        'id': 'unknown-1',
                        'title': 'Unknown',
                        'coordinate_status': 'list_only',
                        'nycif': {'coordinate_status': 'list_only'},
                        'source': {'dataset': 'x', 'source_event_id': '2'},
                    },
                ],
            )
            lookup = root / 'parks.json'
            lookup.write_text('{}', encoding='utf-8')
            payload = build(approved, review, lookup)
            self.assertTrue(payload['source_contracts']['approximate-clustered-events']['cluster'])
            self.assertFalse(payload['source_contracts']['approximate-facility-events']['cluster'])
            self.assertFalse(payload['safety']['unresolved_geometry_emitted'])
            self.assertEqual(len(payload['features']), 1)
            props = payload['features'][0]['properties']
            self.assertEqual(props['coordinate_status'], 'approximate')
            self.assertFalse(props['promotion_allowed'])
            self.assertEqual(props['approximation_class'], 'municipality_level')


if __name__ == '__main__':
    unittest.main()
