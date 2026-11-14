"""Historia 1.4.99: synthetic UI regression for compact gallery and clickable history.

Never opens clinical files, patient's database, private LAN or MP4.
"""
from pathlib import Path
import subprocess
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica" / "app"
JS = APP / "static" / "clinical_video_library.js"
CSS = APP / "static" / "clinical_video_timeline.css"
PANEL = APP / "patient_document_panel.py"


class VideoPlayer1499(unittest.TestCase):
    def test_style_and_cache_refresh(self):
        js = JS.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        panel = PANEL.read_text(encoding="utf-8")
        self.assertIn("grid-template-columns:minmax(245px,28%) minmax(0,1fr)!important", css)
        self.assertIn("grid-template-columns:110px minmax(0,1fr)!important", css)
        self.assertIn("object-fit:contain", (APP / "static/style.css").read_text(encoding="utf-8"))
        self.assertIn("clinical_video_timeline.css?v=1.4.99", js)
        self.assertIn("clinical_video_library.js?v=1.4.99", panel)
        self.assertIn("row.setAttribute('role','button')", js)
        self.assertIn("row.addEventListener('keydown'", js)
        self.assertIn("open.click()", js)
        self.assertIn("selectVideo(item,card)", js)
        self.assertIn("player.play().catch", js)
        self.assertNotIn("cp-video-timeline-open", js)
        self.assertNotIn("Ver grabación", js)
        self.assertNotIn("fetch(url+'/play/'", js)
        self.assertNotIn("setInterval(", js)

    def test_click_and_keyboard_open_same_video(self):
        if not shutil.which("node"):
            self.skipTest("node unavailable")
        case = r"""
const fs=require('node:fs');
const assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8');
const begin=code.indexOf('  function makeTimelineEntry(item){');
const end=code.indexOf('  function renderTimeline(videos){',begin);
assert(begin>=0 && end>begin);
const fragment=code.slice(begin,end);
const document={createElement(tag){
  return {tag,dataset:{},attrs:{},events:{},style:{},childNodes:[],
    append(...nodes){this.childNodes.push(...nodes);},
    setAttribute(k,v){this.attrs[k]=v;},
    addEventListener(name,fn){this.events[name]=fn;}};
}};
const previewById=new Map();
const item={id:'synthetic_video_1',recorded_at:'2026-11-14T09:45',size_bytes:269000000};
const list={children:[{dataset:{videoId:item.id}}]};
const dialog={open:false};
let opens=0,plays=0;
const open={click(){opens++;dialog.open=true;}};
const selectVideo=(vid,card)=>{assert.equal(vid.id,item.id);assert.equal(card,list.children[0]);plays++;};
const factory=new Function('document','previewById','videoDate','stampKey',
  'open','dialog','list','selectVideo','initialLoaded',
  'let pendingId=null;let loaded=initialLoaded;'+fragment+
  'return {makeTimelineEntry,getPending:()=>pendingId};');
const f=factory(document,previewById,()=> '14/11/2026',()=> '202611140945',
  open,dialog,list,selectVideo,true);
const row=f.makeTimelineEntry(item);
assert.equal(row.tag,'section');
assert.equal(row.attrs.role,'button');
assert.equal(row.tabIndex,0);
assert.equal(row.childNodes.length,3);
assert.equal(row.childNodes[2].childNodes.length,2);
row.events.click();
assert.equal(opens,1);
assert.equal(plays,1);
assert.equal(f.getPending(),null);
let prevented=false;
row.events.keydown({key:' ',preventDefault(){prevented=true;}});
assert(prevented);
assert.equal(plays,2);
row.events.keydown({key:'Escape',preventDefault(){throw Error('wrong key');}});
assert.equal(plays,2);
const dialog2={open:false}, open2={click(){dialog2.open=true;}};
const wait=factory(document,previewById,()=> '14/11/2026',()=> '202611140945',
  open2,dialog2,list,()=>{throw Error('must defer until catalog loaded');},false);
wait.makeTimelineEntry(item).events.click();
assert.equal(wait.getPending(),item.id);
"""
        subprocess.run(["node", "--check", str(JS)], check=True)
        subprocess.run(["node", "-e", case, str(JS)], check=True)


if __name__ == "__main__":
    unittest.main()
