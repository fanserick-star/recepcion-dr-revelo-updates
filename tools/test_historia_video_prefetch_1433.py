"""Historia 1.4.33: bounded private LAN MP4 read-ahead regression.
Synthetic byte streams and WebView contracts only; no clinical files or LAN.
"""
import ast
import io
import queue
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/"historia-clinica/app/clinical_video_library.py"
source=p.read_text(encoding="utf-8")
tree=ast.parse(source)
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_buffered_video_body")
module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
scope={"queue":queue,"threading":threading,"logging":__import__("logging"),
       "_VIDEO_CHUNK_BYTES":512*1024,"_VIDEO_PREFETCH_CHUNKS":12}
exec(compile(module,str(p),"exec"),scope)
buffered=scope["_buffered_video_body"]

class TestSource(io.BytesIO):
    def __init__(self,source,wait=0):
        super().__init__(source)
        self.wait=wait
        self.read_calls=0
        self.closed_flag=False
    def read(self,n):
        if self.wait:time.sleep(self.wait)
        self.read_calls+=1
        return super().read(n)
    def close(self):
        self.closed_flag=True
        super().close()

# Never rewrite a single byte of an MP4 or insert anything between Range chunks.
payload=b"\x00\x00\x00\x18ftypisom"+bytes(range(256))*(1024*65)
original=TestSource(payload,0.002)
chunks=list(buffered(original))
assert b"".join(chunks)==payload
assert original.closed_flag
assert original.read_calls>=len(chunks)
assert all(0<len(chunk)<=512*1024 for chunk in chunks)
assert len(chunks)>10

# Exercise seeking: the upstream has already honored HTTP Range.
offset=143
selected=payload[offset:offset+700001]
ranged=TestSource(selected,0.001)
assert b"".join(buffered(ranged))==selected
assert ranged.closed_flag

# A slow downstream may never cause an unbounded RAM queue. A closing video
# must abort its prefetch worker and close the private connection.
large=TestSource(b"z"*(512*1024*45),0)
iterator=buffered(large)
first=next(iterator)
assert first==b"z"*(512*1024)
time.sleep(0.06)
assert large.read_calls<=scope["_VIDEO_PREFETCH_CHUNKS"]+4,large.read_calls
iterator.close()
assert large.closed_flag

# Background streaming of two videos preserves byte isolation.
one=TestSource(b"a"*400007,0.003)
two=TestSource(b"b"*600011,0.002)
assert b"".join(buffered(one))==b"a"*400007
assert b"".join(buffered(two))==b"b"*600011
assert one.closed_flag and two.closed_flag

assert "StreamingResponse(_buffered_video_body(upstream)" in source
assert 'headers={"Range": incoming_range}' in source
assert 'status_code=upstream.status' in source
assert '"Content-Range", "Content-Length"' in source
assert '"_VIDEO_PREFETCH_CHUNKS"' not in source
assert scope["_VIDEO_PREFETCH_CHUNKS"]*scope["_VIDEO_CHUNK_BYTES"]<=6*1024*1024

js=(ROOT/"historia-clinica/app/static/clinical_video_library.js").read_text(encoding="utf-8")
assert "player.preload='auto'" in js
assert "player.addEventListener('waiting',markWaiting)" in js
assert "player.addEventListener('stalled',markWaiting)" in js
assert "player.addEventListener('progress'," in js
assert "player.addEventListener('playing'," in js
assert "other!==player && !other.paused" in js
assert "player.buffered" in js
assert "Datos por delante:" in js
assert "Esta PC" in js
assert "preload='none'" in js
print("HISTORIA_1433_LAN_MP4_PREFETCH_BOUND_6MB_RANGE_BYTES_UI_DIAGNOSTICS_OK")
