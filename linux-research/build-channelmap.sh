#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
make -C "/lib/modules/$(uname -r)/build" M="$PWD/kernel" W=1 avid_native_channelmap.ko
gcc -std=c11 -O2 -Wall -Wextra -Werror tools/identify_192.c -o identify-192
python3 tools/test_digilink.py
python3 tools/test_channelmap.py
python3 tools/test_channelmap_lifecycle.py
python3 tools/test_capture_analysis.py
python3 tools/test_channelmap_coverage.py
python3 tools/test_channelmap_isolation.py
bash -n run-channelmap-test.sh run-analog-bank-test.sh run-channel-isolation-test.sh
python3 - <<'PY'
from pathlib import Path
import hashlib,json,os,subprocess
files=['kernel/avid_native_channelmap.ko','kernel/avid_native_channelmap.c','kernel/native_capture_ring.h','kernel/native_192_channelmap_control.h','run-channelmap-test.sh','tools/analyze_capture.py','run-analog-bank-test.sh','tools/channelmap_coverage.py','tools/analyze_channelmap.py','run-channel-isolation-test.sh']
vermagic=subprocess.check_output(['/usr/sbin/modinfo','-F','vermagic',files[0]],text=True).strip()
assert vermagic.split()[0]==os.uname().release
Path('reports').mkdir(exist_ok=True)
Path('reports/channelmap-build.json').write_text(json.dumps({'kernel':os.uname().release,'vermagic':vermagic,'sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
print('CHANNELMAP_BUILD_READY=yes; physical pairs beyond 1-2 await loopback verification')
PY
