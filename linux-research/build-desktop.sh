#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
make -C kernel -j2 W=1
spa-json-dump desktop/90-avid-native-desktop.conf >/dev/null
python3 tools/test_desktop_manager.py
python3 - <<'PY'
from pathlib import Path
import datetime,hashlib,json,os,subprocess
r=Path('.')
load=['kernel/avid_native_desktop.ko','desktop/90-avid-native-desktop.conf',
      'desktop-driver.sh','tools/manage_desktop.py']
sources=['kernel/avid_native_desktop.c','kernel/native_pcm_ring.h',
         'kernel/native_192_control.h','kernel/Makefile','tools/test_desktop_manager.py','build-desktop.sh']
def hashes(paths):
    return {name:hashlib.sha256((r/name).read_bytes()).hexdigest() for name in paths}
vermagic=subprocess.check_output(['/usr/sbin/modinfo','-F','vermagic',load[0]],text=True).strip()
assert vermagic.split()[0]==os.uname().release
record={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'kernel':os.uname().release,'vermagic':vermagic,
        'status':'compiled; manager fault tests passed; desktop hardware integration pending',
        'load_files_sha256':hashes(load),'source_files_sha256':hashes(sources),
        'checks':['make W=1 succeeded','SPA JSON parser succeeded','9 manager tests passed']}
(r/'reports/desktop-build.json').write_text(json.dumps(record,indent=2)+'\n')
print('DESKTOP_BUILD_READY=yes kernel='+record['kernel'])
PY
