#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
make -C "/lib/modules/$(uname -r)/build" M="$PWD/kernel" W=1 avid_native_adat.ko
python3 tools/test_adat_control.py
python3 tools/test_adat_mailbox.py
python3 tools/test_adat_lifecycle.py
python3 tools/test_adat_idle_dma.py
python3 tools/test_adat_windows_state.py
python3 tools/test_adat_analysis.py
bash -n run-adat-test.sh run-adat-bank-test.sh
python3 - <<'PY'
from pathlib import Path
import hashlib,json,os,subprocess
files=['kernel/avid_native_adat.ko','kernel/avid_native_adat.c',
       'kernel/native_capture_ring.h','kernel/native_adat_ring.h','kernel/native_192_adat_control.h',
       'run-adat-test.sh','run-adat-bank-test.sh','tools/analyze_adat.py',
       'tools/adat_result.py','tools/analyze_capture.py','tools/analyze_channelmap.py']
vermagic=subprocess.check_output(['/usr/sbin/modinfo','-F','vermagic',files[0]],text=True).strip()
assert vermagic.split()[0]==os.uname().release
Path('reports').mkdir(exist_ok=True)
Path('reports/adat-build.json').write_text(json.dumps({'kernel':os.uname().release,
    'vermagic':vermagic,'sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
print('ADAT_BUILD_READY=yes; physical optical paths await loopback verification; digital format retained')
PY
