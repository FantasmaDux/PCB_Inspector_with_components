"""Run on the target Windows machine after setup. No server launch required."""
import sys
import unittest
from pathlib import Path
from PIL import Image
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'backend'))
from inspection import PCBAInspector

class InspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=PCBAInspector(ROOT/'config/inspection.json')
        if not cls.engine.health()['ready']:raise RuntimeError(cls.engine.error)
    def predict(self,target,reference='demo_reference.png',roi=None):
        with Image.open(ROOT/'samples'/target) as a,Image.open(ROOT/'samples'/reference) as b:
            return self.engine.predict(a.convert('RGB'),b.convert('RGB'),.4,40,roi)
    def test_identical_images_have_no_changes(self):
        result=self.predict('demo_reference.png')
        self.assertFalse(result['analysis_blocked'])
        self.assertEqual(result['detections'],[])
        self.assertEqual(result['machine_verdict'],'PASS')
    def test_removed_component_localized(self):
        result=self.predict('demo_missing.png')
        self.assertTrue(result['analysis_available'])
        self.assertGreater(len(result['detections']),0)
        for d in result['detections']:
            self.assertIsNone(d['score'])
            self.assertEqual(d['class_name'],'visual_difference')
            self.assertTrue(0<=d['anomaly_score']<=1)
            x1,y1,x2,y2=d['box'];self.assertTrue(0<=x1<x2<=result['width']);self.assertTrue(0<=y1<y2<=result['height'])
    def test_featureless_images_cannot_pass(self):
        blank=Image.new('RGB',(500,500),'green')
        result=self.engine.predict(blank,blank,.4)
        self.assertTrue(result['analysis_blocked']);self.assertEqual(result['machine_verdict'],'REVIEW')
    def test_mismatched_reference_is_not_silent_pass(self):
        result=self.predict('demo_missing.png','demo_wrong_reference.png')
        self.assertTrue(result['analysis_blocked'] or len(result['detections'])>0)
        self.assertNotEqual(result['machine_verdict'],'PASS')
    def test_roi_excludes_removed_component(self):
        result=self.predict('demo_missing.png',roi=[0,.65,.3,1])
        self.assertEqual(result['roi'],[0,.65,.3,1])
        for d in result['detections']:
            self.assertLess(d['box'][0],result['width']*.31)

if __name__=='__main__':unittest.main()
