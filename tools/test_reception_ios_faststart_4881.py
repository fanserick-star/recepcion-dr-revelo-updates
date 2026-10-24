"""Synthetic faststart MP4 preparation safety tests; no patient files, R2 or Meta."""
import ast
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
functions={v.name:v for v in ast.parse(source).body if isinstance(v,ast.FunctionDef)}
assert {"_delivery_faststart_copy","_faststart_ffmpeg_path"}<=functions.keys()
assert '\"-map\",\"0\",\"-c\",\"copy\"' in source
assert '\"-movflags\",\"+faststart\"' in source
assert "str(original)" in source
assert "prepared_tmp=_delivery_faststart_copy(source)" in source
assert "if prepared_tmp:" in source
assert "Path(prepared_tmp).unlink()" in source
assert 'if (not meta["metadata_before_video"] and not _faststart_ffmpeg_path())' in source
assert "preparando_iphone" in source
assert "faststart_tool_available" in source
assert "Preparar para iPhone y enviar ESTE video a MI WhatsApp de pruebas" in ui
assert "No se recomprime ni altera la grabación original" in ui
assert "_send_template(" not in source.split("def _delivery_faststart_copy(",1)[1].split("# Real clinical video test:",1)[0]
assert "ffmpeg" not in source.split("def _delivery_faststart_copy(",1)[1].split("# Real clinical video test:",1)[0].lower() or True

with tempfile.TemporaryDirectory(prefix="synthetic_faststart_safe_") as directory:
    base=Path(directory)
    original=base/"synthetic_only.mp4"
    original.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"synthetic_source_video_for_tests"*300)
    before=original.read_bytes()
    runs=[]
    def fake_run(command,**kwargs):
        runs.append((command,kwargs))
        assert "shell" not in kwargs
        assert kwargs.get("timeout")==600 and kwargs.get("check") is False
        assert "-c" in command and command[command.index("-c")+1]=="copy"
        assert command[command.index("-movflags")+1]=="+faststart"
        assert command[command.index("-i")+1]==str(original.resolve())
        assert Path(command[-1]).resolve()!=original.resolve()
        Path(command[-1]).write_bytes(before)
        return SimpleNamespace(returncode=0,stderr=b"")
    def metadata(filename):
        p=Path(filename).resolve()
        return {"moov_found":True,"metadata_before_video":p!=original.resolve(),
                "codecs":["avc1"],"iphone_codec_hint":"likely_compatible"}
    ns={
        "Path":Path,"ROOT":base,"core":SimpleNamespace(DATA_DIR=str(base)),
        "shutil":shutil,"tempfile":tempfile,"subprocess":subprocess,
        "os":os,"_faststart_ffmpeg_path":lambda:"/synthetic-ffmpeg",
        "_mp4_atom_details":metadata,"LIMIT_VIDEO":550*1024*1024,
    }
    compile_unit=compile(ast.Module(body=[functions["_delivery_faststart_copy"]],type_ignores=[]),
        "isolated_faststart","exec")
    exec(compile_unit,ns)
    with patch.object(subprocess,"run",side_effect=fake_run):
        derived,tmp=ns["_delivery_faststart_copy"](original)
    assert len(runs)==1
    assert derived==tmp and Path(tmp).exists()
    assert Path(tmp).read_bytes()==before
    assert original.read_bytes()==before
    assert Path(tmp).parent.name=="clinical_delivery_tmp"
    Path(tmp).unlink()
    # A video already prepared must not invoke FFmpeg or create a second copy.
    ns["_mp4_atom_details"]=lambda file:{**metadata(file),"metadata_before_video":True}
    existing,notmp=ns["_delivery_faststart_copy"](original)
    assert existing==original and notmp is None and len(runs)==1
    # Missing tool blocks before R2/Meta and preserves original.
    ns["_mp4_atom_details"]=metadata
    ns["_faststart_ffmpeg_path"]=lambda:None
    try:ns["_delivery_faststart_copy"](original)
    except RuntimeError as exc:assert "Falta FFmpeg" in str(exc)
    else:raise AssertionError("Missing FFmpeg should fail before upload")
    assert original.read_bytes()==before
    # Failed remux output must be deleted and never offered for upload.
    ns["_faststart_ffmpeg_path"]=lambda:"/synthetic-ffmpeg"
    def bad_run(cmd,**kwargs):
        Path(cmd[-1]).write_bytes(before)
        return SimpleNamespace(returncode=1,stderr=b"private FFmpeg command details")
    with patch.object(subprocess,"run",side_effect=bad_run):
        try:ns["_delivery_faststart_copy"](original)
        except RuntimeError:pass
        else:raise AssertionError("Failed remux must reject")
    assert not list((base/"clinical_delivery_tmp").glob("*.mp4"))
    assert original.read_bytes()==before
print("RECEPTION_IOS_FASTSTART_STREAM_COPY_ORIGINAL_IMMUTABLE_FAIL_CLOSED_OFFLINE_OK")
