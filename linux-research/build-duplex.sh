#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
make -C "/lib/modules/$(uname -r)/build" M="$PWD/kernel" W=1 avid_native_duplex.ko
spa-json-dump desktop/91-avid-native-duplex.conf >/dev/null
python3 tools/test_duplex_ring.py
python3 tools/test_duplex_streams.py
python3 tools/test_duplex_lifecycle.py
python3 tools/test_duplex_manager.py
python3 - <<'PY'
from pathlib import Path
import hashlib,json,os,subprocess
load=['kernel/avid_native_duplex.ko','desktop/91-avid-native-duplex.conf','duplex-driver.sh','tools/manage_duplex.py']
sources=['kernel/avid_native_duplex.c','kernel/native_duplex_ring.h','kernel/native_capture_ring.h','kernel/native_192_capture_control.h','kernel/Makefile','build-duplex.sh','tools/test_duplex_ring.py','tools/test_duplex_streams.py','tools/test_duplex_lifecycle.py','tools/test_duplex_manager.py']
vermagic=subprocess.check_output(['/usr/sbin/modinfo','-F','vermagic',load[0]],text=True).strip()
assert vermagic.split()[0]==os.uname().release
hashes=lambda files:{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}
Path('reports').mkdir(exist_ok=True)
Path('reports/duplex-build.json').write_text(json.dumps({'kernel':os.uname().release,'vermagic':vermagic,'load_files_sha256':hashes(load),'source_files_sha256':hashes(sources),'status':'compiled and simulated; independent duplex hardware validation pending'},indent=2)+'\n')
print('DUPLEX_BUILD_READY=yes; hardware validation pending')
PY
