"""Synthetic regression: videocystoscopy entries merge into the dated history.

No patient data, no network, no SQL writes, no MP4 downloads.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica" / "app"
JS = APP / "static" / "clinical_video_library.js"
CSS = APP / "static" / "clinical_video_timeline.css"
PANEL = APP / "patient_document_panel.py"


class VideoHistoryTimeline1498(unittest.TestCase):
    def test_assets_and_patient_scope(self):
        self.assertTrue(CSS.is_file())
        source = JS.read_text(encoding="utf-8")
        panel = PANEL.read_text(encoding="utf-8")
        self.assertIn("data-clinical-video-patient", source)
        self.assertIn("/api/clinical-videos/patient/", source)
        self.assertIn("renderTimeline(videos)", source)
        self.assertIn("const consultationEntries=", source)
        self.assertIn("stampKey(item.recorded_at)", source)
        self.assertIn("root.replaceChildren(...merged)", source)
        self.assertIn("videoEntries=shown.map(makeTimelineEntry)", source)
        self.assertIn("!node.classList.contains('cp-video-timeline-entry')", source)
        self.assertIn("clinical_video_timeline.css?v=1.4.98", source)
        self.assertIn("clinical_video_library.js?v=1.4.98", panel)
        self.assertIn("const source= document.createElement('source');".replace("const source= ","const source="), source)
        self.assertNotIn("fetch(url+'/play/'", source)
        self.assertNotIn("localStorage", source)

    def test_date_sort_and_search_with_node(self):
        if not shutil.which("node"):
            self.skipTest("Node not available; static checks still run")
        source = r"""
const fs=require('node:fs');
const assert=require('node:assert/strict');
const script=fs.readFileSync(process.argv[1], 'utf8');
const begin=script.indexOf('  function stampKey(');
const end=script.indexOf('  function makeTimelineEntry(',begin);
assert(begin>=0 && end>begin,'helpers not found');
const helpers=script.slice(begin,end);
const make=new Function('window',helpers+'return {stampKey,videoDate,visibleInSearch,entryKey};');
const win={location:{search:''}};
const {stampKey,videoDate,visibleInSearch,entryKey}=make(win);
const consult={classList:{contains:()=>false},querySelector:(selector)=>
  selector.endsWith('strong')?{textContent:'06/11/2026'}:{textContent:'16:30'}};
const clip={classList:{contains:()=>true},dataset:{videoTimestamp:stampKey('2026-11-08T10:30:00')}};
assert.equal(stampKey('2026-11-10T12:45:00'), '202611101245');
assert.equal(stampKey('10/11/2026','12:45'), '202611101245');
assert.equal(stampKey('2026-02-30T11:00:00'), '');
assert.equal(videoDate({recorded_at:'2026-11-08T10:30:00'}),'08/11/2026');
assert(entryKey(clip)>entryKey(consult));
assert.deepEqual([consult,clip].sort((a,b)=>entryKey(b).localeCompare(entryKey(a))),[clip,consult]);
assert(visibleInSearch({recorded_at:'2026-11-08T10:30:00'}));
win.location.search='?histq=cistoscopia';
assert(visibleInSearch({recorded_at:'2026-11-08T10:30:00'}));
win.location.search='?histq=diabetes';
assert(!visibleInSearch({recorded_at:'2026-11-08T10:30:00'}));
"""
        subprocess.run(["node", "--check", str(JS)], check=True)
        subprocess.run(["node", "-e", source, str(JS)], check=True)


if __name__ == "__main__":
    unittest.main()
