#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
make -C "/lib/modules/$(uname -r)/build" M="$PWD/kernel" W=1 avid_native_capture.ko
python3 tools/test_capture.py
python3 tools/test_capture_lifecycle.py
python3 tools/test_capture_analysis.py
python3 - <<'PY'
from pathlib import Path
import hashlib,json,os,subprocess
files=['kernel/avid_native_capture.ko','kernel/avid_native_capture.c','kernel/native_capture_ring.h','kernel/native_192_capture_control.h','run-capture-test.sh','tools/analyze_capture.py']
vermagic=subprocess.check_output(['/usr/sbin/modinfo','-F','vermagic',files[0]],text=True).strip()
assert vermagic.split()[0]==os.uname().release
Path('reports').mkdir(exist_ok=True)
Path('reports/capture-build.json').write_text(json.dumps({'kernel':os.uname().release,'vermagic':vermagic,'sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
print('CAPTURE_BUILD_READY=yes; hardware capture is not yet validated')
PY
