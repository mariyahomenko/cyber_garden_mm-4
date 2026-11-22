import unittest
from cyberdoc.research import extract_candidates, validate, SOLAR, RAG
class FakeDoc:
    path='/tmp/article.pdf'
    pages_text=['PCE = 22.5% and Voc = 1050 mV. Jsc = 21.1 mA/cm². FF = 80%.', 'Recall@5: 0.84, MRR: 0.65']
class ResearchTests(unittest.TestCase):
    def test_solar_extraction(self):
        rows=extract_candidates(FakeDoc(),SOLAR)
        self.assertEqual(len(rows),4)
        self.assertEqual(next(r for r in rows if r['metric_name']=='Voc')['normalized_value'],1.05)
        self.assertTrue(all(r['source_page']==1 for r in rows))
    def test_rag_extraction(self):
        rows=extract_candidates(FakeDoc(),RAG)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['metric_k'],5)
    def test_invalid_value_retained(self):
        r={'domain':SOLAR,'result_id':'1','metric_name':'PCE','normalized_value':150,'normalized_unit':'%',
           'source_page':1,'source_fragment':'PCE=150%', 'extraction_status':'candidate'}
        self.assertIn('percent_range', [f['check_name'] for f in validate(r)])
        self.assertEqual(r['normalized_value'],150)
if __name__=='__main__':unittest.main()
