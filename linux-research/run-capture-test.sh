#!/bin/bash
# Bounded capture experiment; no persistent driver/configuration installation.
set -euo pipefail
cd -- "$(dirname -- "$0")"
module=avid_native_capture
bdf=0000:81:00.0
loopback=0
case "${1-}" in
  --external) ;;
  --loopback) loopback=1 ;;
  *) echo 'Uso: sudo ./run-capture-test.sh --external | --loopback'; exit 2 ;;
esac
(($# == 1)) || exit 2
((EUID == 0)) || { echo 'Execute com sudo no terminal local.'; exit 1; }
for tool in /usr/sbin/insmod /usr/sbin/rmmod /usr/sbin/modprobe /usr/sbin/modinfo /usr/bin/arecord timeout python3; do
    command -v "$tool" >/dev/null || { echo "Ferramenta ausente: $tool"; exit 1; }
done
python3 - <<'PY'
from pathlib import Path
import hashlib,json,os
m=json.loads(Path('reports/capture-build.json').read_text())
assert m['kernel']==os.uname().release,'Recompile para o kernel atual'
for p,h in m['sha256'].items():
    assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Recompile: arquivo mudou: '+p
PY
if [[ -L /sys/bus/pci/devices/$bdf/driver || -d /sys/module/$module ]]; then
    echo 'A placa já está em uso. Feche os aplicativos e execute primeiro:'
    echo "sudo $PWD/desktop-driver.sh stop"
    echo 'Depois repita este teste. Nenhum driver foi removido por este comando.'
    exit 1
fi
run_dir=$(mktemp -d "$PWD/reports/capture-test-XXXXXX")
loaded=0
stats() {
    [[ -d /sys/module/$module ]] || return 0
    local key
    for key in bound starts stops xruns last_error total_frames last_frames ring_wraps tx_frames max_poll_us mute_restored route_restored; do
        printf '%s=' "$key"; cat "/sys/module/$module/parameters/$key"
    done
}
cleanup() {
    local code=$?
    trap - EXIT INT TERM HUP
    set +e
    stats > "$run_dir/stats.txt"
    cat "$run_dir/stats.txt"
    if ((loaded)) && [[ -d /sys/module/$module ]]; then
        if /usr/sbin/rmmod "$module"; then echo 'EXPERIMENT_MODULE_REMOVED=yes';
        else echo 'EXPERIMENT_MODULE_REMOVED=no; preserve o log e não repita.'; code=1; fi
    fi
    python3 - "$run_dir" "$bdf" <<'PY'
from pathlib import Path
import sys
r=Path(sys.argv[1]);p=Path('/sys/bus/pci/devices')/sys.argv[2]
with (p/'config').open('rb') as f: after=f.read(64)
(r/'pci-after.bin').write_bytes(after)
same=len(after)==64 and after==(r/'pci-before.bin').read_bytes()
unbound=not (p/'driver').exists()
print('PCI_HEADER_RESTORED='+('yes' if same else 'no'))
print('PCI_UNBOUND='+('yes' if unbound else 'no'))
raise SystemExit(0 if same and unbound else 1)
PY
    if (($?)); then code=1; fi
    dmesg --notime | awk '/avid_native_capture: begin bounded capture test/{s=""} /avid_native_capture/{s=s $0 "\n"} END{printf "%s",s}' > "$run_dir/module.log"
    cat "$run_dir/module.log"
    if [[ -n ${SUDO_UID-} && -n ${SUDO_GID-} ]]; then chown -R "$SUDO_UID:$SUDO_GID" "$run_dir"; fi
    echo "Logs e gravação: $run_dir"
    exit "$code"
}
python3 - "$run_dir" "$bdf" <<'PY'
from pathlib import Path
import sys
with (Path('/sys/bus/pci/devices')/sys.argv[2]/'config').open('rb') as f: data=f.read(64)
assert len(data)==64
(Path(sys.argv[1])/'pci-before.bin').write_bytes(data)
PY
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
# Save console output; directory stays private to root until cleanup hands it to sudo user.
exec > >(tee "$run_dir/console.log") 2>&1
echo 'Captura experimental: 10 s, entradas candidatas 1–2, 48 kHz/S24_3LE.'
if ((loopback)); then
    echo 'Loopback físico: saída analógica 1 -> entrada 1; saída 2 -> entrada 2.'
    echo 'Tom -40 dBFS: esquerda 750 Hz, direita 1500 Hz, depois ambos; sem monitorar a entrada.'
else
    echo 'Fonte externa em nível de linha nas entradas 1–2; TX envia silêncio.'
fi
echo 'Mantenha monitores mutados, trabalho salvo e 192 no estado de 48 kHz dos testes anteriores.'
/usr/sbin/modprobe snd_pcm
loaded=1
/usr/sbin/insmod "kernel/$module.ko" enable_experimental=1 loopback="$loopback"
[[ $(cat /sys/module/$module/parameters/bound) == Y ]]
echo 'ALSA_CAPTURE_DEVICE=hw:AvidCapture,0'
timeout --signal=TERM --kill-after=3s 18s /usr/bin/arecord --fatal-errors \
    -D hw:AvidCapture,0 -t raw -f S24_3LE -r 48000 -c 2 \
    --period-size=1024 --buffer-size=4096 -d 10 "$run_dir/capture.raw"
stats
for key in last_error xruns; do [[ $(cat /sys/module/$module/parameters/$key) == 0 ]]; done
for key in mute_restored route_restored; do [[ $(cat /sys/module/$module/parameters/$key) == Y ]]; done
args=()
((loopback)) && args+=(--loopback)
python3 tools/analyze_capture.py "$run_dir/capture.raw" "${args[@]}"
echo 'CAPTURE_TRANSPORT_TEST=completed; examine a gravação para confirmar a origem e os canais.'
