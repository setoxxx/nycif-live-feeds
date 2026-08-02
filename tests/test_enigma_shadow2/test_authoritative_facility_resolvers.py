import json,tempfile,unittest
from pathlib import Path
from nycif.normalize.facility_resolvers.library_resolver import resolve_library
from nycif.normalize.facility_resolvers.pool_resolver import resolve_pool
from nycif.normalize.facility_resolvers.dcp_facilities_resolver import resolve_dcp_facility,cross_check_dcp_facility
from nycif.normalize.facility_resolvers.park_ambiguity_resolver import resolve_borough_qualified_park

def write_lookup(path,aliases,ambiguous=()):
    path.write_text(json.dumps({'metadata':{'promotion_allowed':False},'aliases':aliases,'ambiguous_aliases':list(ambiguous)}))
class ResolverTests(unittest.TestCase):
    def record(self,location,borough='Brooklyn'): return {'evidence_tier':'unresolved','location':location,'borough':borough}
    def test_library_exact_name_and_borough(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'gerritsen beach':{'authority_id':'b1','facility_name':'Gerritsen Beach','facility_type':'library','borough':'Brooklyn','lat':40.6,'lng':-73.9}})
            result=resolve_library(self.record('Brooklyn Public Library- Gerritsen Beach'),lookup_path=p)
            self.assertEqual(result['coordinate_precision'],'certified_facility'); self.assertFalse(result['promotion_allowed'])
    def test_borough_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'bayside':{'authority_id':'q1','facility_name':'Bayside','facility_type':'library','borough':'Queens','lat':40.76,'lng':-73.77}})
            self.assertIsNone(resolve_library(self.record('Queens Public Library - Bayside','Brooklyn'),lookup_path=p))
    def test_ambiguous_alias_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{},['columbus'])
            self.assertIsNone(resolve_library(self.record('Columbus Library'),lookup_path=p))
    def test_pool_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'faber pool':{'authority_id':'R008-POOL','facility_name':'Faber Pool','facility_type':'pool','borough':'Staten Island','lat':40.6412,'lng':-74.1353}})
            self.assertIsNotNone(resolve_pool(self.record('Faber Pool in Faber Pool and Park','Staten Island'),lookup_path=p))
    def test_dcp_never_primary(self): self.assertIsNone(resolve_dcp_facility(self.record('Any Facility')))
    def test_dcp_cross_check_mismatch_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; write_lookup(p,{'x':{'authority_id':'d1','facility_name':'X','facility_type':'dcp_cross_check','borough':'Queens','lat':40.7,'lng':-73.8}})
            proposed={'facility_name':'X','latitude':40.6,'longitude':-73.9}
            self.assertIsNone(cross_check_dcp_facility(self.record('X','Brooklyn'),proposed,lookup_path=p))
    def test_borough_qualified_ambiguous_park(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'; p.write_text(json.dumps({'aliases':{'columbus':[{'park_id':'B1','park_name':'Columbus Park','borough':'Brooklyn','lat':40.69,'lng':-73.99},{'park_id':'M1','park_name':'Columbus Park','borough':'Manhattan','lat':40.71,'lng':-74.0}]}}))
            result=resolve_borough_qualified_park(self.record('Columbus Park','Brooklyn'),lookup_path=p); self.assertEqual(result['park_id'],'B1')
if __name__=='__main__': unittest.main()
