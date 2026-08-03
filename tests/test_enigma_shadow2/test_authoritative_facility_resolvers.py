import json,tempfile,unittest
from pathlib import Path
from nycif.normalize.facility_resolvers.dpr_structures_resolver import resolve_dpr_structure
from nycif.normalize.facility_resolvers.library_resolver import resolve_library
from nycif.normalize.facility_resolvers.school_resolver import resolve_school
from nycif.normalize.facility_resolvers.pool_resolver import resolve_pool
from nycif.normalize.facility_resolvers.recreation_center_resolver import resolve_recreation_center
from nycif.normalize.facility_resolvers.dcp_facilities_resolver import resolve_dcp_facility,cross_check_dcp_facility
from nycif.normalize.facility_resolvers.park_ambiguity_resolver import resolve_borough_qualified_park

def write_lookup(path,aliases,ambiguous=()):
    path.write_text(json.dumps({'metadata':{'promotion_allowed':False},'aliases':aliases,'ambiguous_aliases':list(ambiguous)}))
class ResolverTests(unittest.TestCase):
    def record(self,location,borough='Brooklyn'): return {'evidence_tier':'unresolved','location':location,'borough':borough}
    def entry(self,name,kind,borough='Brooklyn',authority='a1'): return {'authority_id':authority,'facility_name':name,'facility_type':kind,'borough':borough,'lat':40.6,'lng':-73.9}
    def test_library_exact_name_and_borough(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'gerritsen beach':self.entry('Gerritsen Beach','library')})
            result=resolve_library(self.record('Brooklyn Public Library- Gerritsen Beach'),lookup_path=p)
            self.assertEqual(result['coordinate_precision'],'certified_facility'); self.assertFalse(result['promotion_allowed']); self.assertEqual(result['facility_matched_alias'],'gerritsen beach')
    def test_dpr_structure_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'salt marsh nature center':self.entry('Salt Marsh Nature Center','nature_center')})
            self.assertIsNotNone(resolve_dpr_structure(self.record('Salt Marsh Nature Center'),lookup_path=p))
    def test_school_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'ps 100 school':self.entry('PS 100 School','school')})
            self.assertIsNotNone(resolve_school(self.record('PS 100 School'),lookup_path=p))
    def test_recreation_center_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'brownsville recreation center':self.entry('Brownsville Recreation Center','recreation_center')})
            self.assertIsNotNone(resolve_recreation_center(self.record('Brownsville Recreation Center'),lookup_path=p))
    def test_borough_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'bayside':self.entry('Bayside','library','Queens','q1')})
            self.assertIsNone(resolve_library(self.record('Queens Public Library - Bayside','Brooklyn'),lookup_path=p))
    def test_ambiguous_alias_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{},['columbus'])
            self.assertIsNone(resolve_library(self.record('Columbus Library'),lookup_path=p))
    def test_pool_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'faber pool':self.entry('Faber Pool','pool','Staten Island','R008-POOL')})
            self.assertIsNotNone(resolve_pool(self.record('Faber Pool in Faber Pool and Park','Staten Island'),lookup_path=p))
    def test_dcp_never_primary(self): self.assertIsNone(resolve_dcp_facility(self.record('Any Facility')))
    def test_dcp_cross_check_mismatch_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'x':self.entry('X','dcp_cross_check','Queens','d1')})
            proposed={'facility_name':'X','latitude':40.6,'longitude':-73.9}
            self.assertIsNone(cross_check_dcp_facility(self.record('X','Brooklyn'),proposed,lookup_path=p))
    def test_borough_qualified_ambiguous_park(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; p.write_text(json.dumps({'aliases':{'columbus':[{'park_id':'B1','park_name':'Columbus Park','borough':'Brooklyn','lat':40.69,'lng':-73.99},{'park_id':'M1','park_name':'Columbus Park','borough':'Manhattan','lat':40.71,'lng':-74.0}]}}))
            result=resolve_borough_qualified_park(self.record('Columbus Park','Brooklyn'),lookup_path=p); self.assertEqual(result['park_id'],'B1')
if __name__=='__main__': unittest.main()
