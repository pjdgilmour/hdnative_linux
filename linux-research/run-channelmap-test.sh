#!/bin/bash
# Bounded capture experiment; no persistent driver/configuration installation.
set -euo pipefail
cd -- "$(dirname -- "$0")"
module=avid_native_channelmap
bdf=0000:81:00.0
case "${1-}:${2-}" in
  [1-8]:[1-4]) output_pair=$1; input_pair=$2 ;;
  *) echo 'Uso: sudo ./run-channelmap-test.sh PAR_SAIDA(1..8) PAR_ENTRADA(1..4) [--expect-isolation]'; exit 2 ;;
esac
expectation=loopback
if (($# == 3)) && [[ $3 == --expect-isolation ]]; then
    expectation=isolation
    ((output_pair <= 4 && output_pair != input_pair)) || {
        echo 'Isolamento limitado a pares distintos do primeiro banco analógico.'; exit 2;
    }
elif (($# != 2)); then exit 2; fi
((EUID == 0)) || { echo 'Execute com sudo no terminal local.'; exit 1; }
for tool in /usr/sbin/insmod /usr/sbin/rmmod /usr/sbin/modprobe /usr/sbin/modinfo /usr/bin/arecord timeout python3; do
    command -v "$tool" >/dev/null || { echo "Ferramenta ausente: $tool"; exit 1; }
done
python3 - <<'PY'
from pathlib import Path
import hashlib,json,os
m=json.loads(Path('reports/channelmap-build.json').read_text())
assert m['kernel']==os.uname().release,'Recompile para o kernel atual'
for p,h in m['sha256'].items():
    assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Recompile: arquivo mudou: '+p
PY
if [[ -L /sys/bus/pci/devices/$bdf/driver || -d /sys/module/$module ]]; then
    echo 'A placa já está em uso. Feche os aplicativos e execute primeiro:'
    echo "sudo $PWD/duplex-driver.sh stop   # ou desktop-driver.sh stop, conforme o módulo ativo"
    echo 'Depois repita este teste. Nenhum driver foi removido por este comando.'
    exit 1
fi
run_dir=$(mktemp -d "$PWD/reports/channelmap-test-XXXXXX")
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
    python3 - "$run_dir" "$bdf" "$code" <<'PY'
from pathlib import Path
import sys,json,hashlib
r=Path(sys.argv[1]);p=Path('/sys/bus/pci/devices')/sys.argv[2]
with (p/'config').open('rb') as f: after=f.read(64)
(r/'pci-after.bin').write_bytes(after)
same=len(after)==64 and after==(r/'pci-before.bin').read_bytes()
unbound=not (p/'driver').exists()
print('PCI_HEADER_RESTORED='+('yes' if same else 'no'))
print('PCI_UNBOUND='+('yes' if unbound else 'no'))
stats=dict(line.split('=',1) for line in (r/'stats.txt').read_text().splitlines() if '=' in line)
analysis=json.loads((r/'capture.json').read_text()) if (r/'capture.json').exists() else {}
profile=json.loads((r/'profile.json').read_text()) if (r/'profile.json').exists() else {}
ok=(int(sys.argv[3])==0 and same and unbound and analysis.get('expectation_met') is True
    and analysis.get('expectation')==profile.get('expectation')
    and stats.get('starts')=='1' and stats.get('stops')=='1'
    and all(stats.get(k)=='0' for k in ['xruns','last_error'])
    and all(stats.get(k)=='Y' for k in ['mute_restored','route_restored']))
summary={**profile,'passed':ok,'pci_header_restored':same,'pci_unbound':unbound,'stats':stats,
         'analysis':analysis,'raw_sha256':hashlib.sha256((r/'capture.raw').read_bytes()).hexdigest() if (r/'capture.raw').exists() else None}
(r/'session.json').write_text(json.dumps(summary,indent=2)+'\n')
label='ISOLATION_TEST_PASSED' if profile.get('expectation')=='isolation' else 'ANALOG_PAIR_TEST_PASSED'
print(label+'='+('yes' if ok else 'no'))
raise SystemExit(0 if ok else 1)
PY
    if (($?)); then code=1; fi
    dmesg --notime | awk '/avid_native_channelmap: begin bounded capture test/{s=""} /avid_native_channelmap/{s=s $0 "\n"} END{printf "%s",s}' > "$run_dir/module.log"
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
echo "Resultado esperado: $expectation; transporte lógico 1–2, com rotas físicas selecionadas."
echo "Saídas analógicas $((2*output_pair-1))–$((2*output_pair)) -> entradas $((2*input_pair-1))–$((2*input_pair))."
echo 'Gravação de 10 s; 750 Hz no primeiro canal, 1500 Hz no segundo, depois ambos; pico -40 dBFS.'
echo 'Mantenha monitores mutados, trabalho salvo e 192 no mesmo estado de 48 kHz.'
python3 - "$run_dir" "$output_pair" "$input_pair" "$expectation" <<'PY'
from pathlib import Path
import sys,json,hashlib
r=Path(sys.argv[1]);o=int(sys.argv[2]);i=int(sys.argv[3])
r.joinpath('profile.json').write_text(json.dumps({'output_pair':o,'input_pair':i,'expectation':sys.argv[4],
    'output_channels':[2*o-1,2*o],'input_channels':[2*i-1,2*i],
    'expected_module_ids':'0x13151314','output_register':hex(0x4c+o if o<=4 else 0x50+o),
    'input_selector':8+i,'sample_rate':48000,'physical_wiring':'bank1 DB25 output1-8 to input1-8' if sys.argv[4]=='isolation' else 'user supplied, must match selected pairs',
    'module_sha256':hashlib.sha256(Path('kernel/avid_native_channelmap.ko').read_bytes()).hexdigest()},indent=2)+'\n')
PY
/usr/sbin/modprobe snd_pcm
loaded=1
/usr/sbin/insmod "kernel/$module.ko" enable_experimental=1 loopback=1 output_pair="$output_pair" input_pair="$input_pair"
[[ $(cat /sys/module/$module/parameters/bound) == Y ]]
echo 'ALSA_CAPTURE_DEVICE=hw:AvidChannelMap,0'
timeout --signal=TERM --kill-after=3s 18s /usr/bin/arecord --fatal-errors \
    -D hw:AvidChannelMap,0 -t raw -f S24_3LE -r 48000 -c 2 \
    --period-size=1024 --buffer-size=4096 -d 10 "$run_dir/capture.raw"
stats
for key in last_error xruns; do [[ $(cat /sys/module/$module/parameters/$key) == 0 ]]; done
for key in mute_restored route_restored; do [[ $(cat /sys/module/$module/parameters/$key) == Y ]]; done
python3 tools/analyze_channelmap.py "$run_dir/capture.raw" --input-pair "$input_pair" --expectation "$expectation"
echo 'Análise concluída; o resultado do par será emitido depois da restauração PCI.'
