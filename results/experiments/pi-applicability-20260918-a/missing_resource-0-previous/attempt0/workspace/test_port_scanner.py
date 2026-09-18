import json
import unittest
import port_scanner as m

class RegressionTests(unittest.TestCase):
    def test_parser(self):
        args=m.build_parser().parse_args([])
        self.assertEqual((args.retries,args.label),(2,'job'))
        self.assertEqual(m.build_parser().parse_args(['--retries','7']).retries,7)
    def test_record(self):
        value={'label':'job','values':[1,2]}
        self.assertEqual(json.loads(m.encode_record(value)),value)
    def test_resource(self):
        self.assertEqual(m.read_resource(lambda key:key.upper(),'job'),'JOB')
    def test_jobs(self):
        self.assertEqual(m.schedule_jobs([1,2],2),([1,2],2))
    def test_score_zero(self):
        self.assertEqual(m.normalize_score(0),0)
