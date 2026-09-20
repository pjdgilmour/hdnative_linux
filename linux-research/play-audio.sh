#!/bin/bash
# Play the prepared and amplitude-verified user track through the proven module.
set -euo pipefail
cd -- "$(dirname -- "$0")"
module=avid_native_alsa
bdf=0000:81:00.0
if (($#)); then
    echo 'Uso: sudo ./play-audio.sh' >&2
    exit 2
fi
if ((EUID != 0)); then
    echo 'Execute com sudo no terminal local; este script carrega o módulo experimental.' >&2
    exit 1
fi
for tool in /usr/sbin/insmod /usr/sbin/rmmod /usr/sbin/modprobe /usr/sbin/modinfo /usr/bin/aplay python3; do
    command -v "$tool" >/dev/null || { echo "Ferramenta ausente: $tool" >&2; exit 1; }
done
if [[ -d /sys/module/$module || -d /sys/module/avid_native_dma_probe || -L /sys/bus/pci/devices/$bdf/driver ]]; then
    echo 'A placa ou um módulo de teste já está em uso. Não vou carregar outro.' >&2
    exit 1
fi
if [[ $(/usr/sbin/modinfo -F vermagic "kernel/$module.ko") != "$(uname -r) "* ]]; then
    echo 'O módulo precisa ser recompilado para o kernel atual.' >&2
    exit 1
fi
run_dir=$(mktemp -d "$PWD/reports/alsa-music-XXXXXX")
chmod 755 "$run_dir"
exec > >(tee "$run_dir/console.log") 2>&1
loaded=0
stats() {
    local key
    if [[ -d /sys/module/$module ]]; then
        for key in bound starts stops xruns last_error total_frames last_frames ring_wraps rx_discarded max_poll_us mute_restored route_restored; do
            printf '%s=' "$key"
            cat "/sys/module/$module/parameters/$key"
        done
    fi
}
cleanup() {
    local code=$?
    trap - EXIT INT TERM HUP
    set +e
    stats
    if ((loaded)) && [[ -d /sys/module/$module ]]; then
        if /usr/sbin/rmmod "$module"; then
            echo 'EXPERIMENT_MODULE_REMOVED=yes'
        else
            echo 'EXPERIMENT_MODULE_REMOVED=no; não repita; preserve este log.'
            code=1
        fi
    fi
    python3 - "$run_dir" "$bdf" <<'PY'
from pathlib import Path
import sys
root, bdf = Path(sys.argv[1]), sys.argv[2]
p = Path('/sys/bus/pci/devices')/bdf
try:
    with (p/'config').open('rb') as f:
        after = f.read(64)
    (root/'pci-after.bin').write_bytes(after)
    before = (root/'pci-before.bin').read_bytes()
    same = len(after) == 64 and after == before
    unbound = not (p/'driver').exists()
    print(f'PCI_HEADER_RESTORED={"yes" if same else "no"}')
    print(f'PCI_UNBOUND={"yes" if unbound else "no"}')
    if not same or not unbound:
        sys.exit(1)
except OSError as e:
    print(f'PCI_RESTORE_CHECK_FAILED={e}')
    sys.exit(1)
PY
    if (($?)); then code=1; fi
    echo '--- Registros desta execução ---'
    dmesg --notime | grep "$module" | awk '
        /: begin manual ALSA experiment/ { n=0 }
        { lines[++n]=$0 }
        END { for (i=1; i<=n; i++) print lines[i] }
    ' > "$run_dir/module.log"
    cat "$run_dir/module.log"
    echo "Logs: $run_dir"
    echo 'Informe se ouviu a música e se houve cortes, estalos ou distorção.'
    exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
python3 - "$run_dir" "$bdf" <<'PY'
from pathlib import Path
import sys
root, bdf = Path(sys.argv[1]), sys.argv[2]
with (Path('/sys/bus/pci/devices')/bdf/'config').open('rb') as f:
    data = f.read(64)
if len(data) != 64:
    raise SystemExit('Cabeçalho PCI incompleto; teste cancelado.')
(root/'pci-before.bin').write_bytes(data)
PY
python3 - <<'CHECK'
from pathlib import Path
import hashlib,json
m=json.loads(Path('prepared-audio/music.json').read_text())
p=Path('prepared-audio/music-48k-s24le.raw')
with p.open('rb') as f:
    digest=hashlib.file_digest(f,'sha256').hexdigest()
assert digest==m['output_sha256'],'PCM mudou depois da verificação'
assert p.stat().st_size==m['frames']*6
assert m['rate']==48000 and m['channels']==2 and m['format']=='S24_3LE'
assert 0<m['frames']<=48000*320 and max(m['peaks_s24'])<=83886
assert 1<=m['timeout_seconds']<=350
build=json.loads(Path('reports/alsa-stability-build.json').read_text())
assert hashlib.sha256(Path('kernel/avid_native_alsa.ko').read_bytes()).hexdigest()==build['sha256']['kernel/avid_native_alsa.ko'],'O módulo mudou desde o teste de estabilidade'
print(f"MUSIC_VERIFIED=yes source={m['source']} duration={m['duration_seconds']:.3f}s peak={m['peak_dbfs']:.2f}dBFS")
CHECK
cp prepared-audio/music.json "$run_dir/music.json"
time_limit=$(python3 -c 'import json; print(json.load(open("prepared-audio/music.json"))["timeout_seconds"])')
echo 'Música nas saídas analógicas 1–2 da 192; pico limitado a -40 dBFS.'
echo 'Mantenha o volume baixo e o trabalho salvo. Ctrl+C interrompe o teste.'
/usr/sbin/modprobe snd_pcm
loaded=1
/usr/sbin/insmod "kernel/$module.ko" enable_experimental=1 bdf="$bdf" max_stream_seconds=360
shopt -s nullglob
cards=(/sys/bus/pci/devices/"$bdf"/sound/card[0-9]*)
if ((${#cards[@]} != 1)); then
    echo 'Não encontrei exatamente uma placa ALSA associada ao PCI esperado.'
    exit 1
fi
card=${cards[0]##*/card}
echo "ALSA_DEVICE=hw:$card,0"
python3 tools/supervise_alsa.py --device "hw:$card,0" \
    --audio "$PWD/prepared-audio/music-48k-s24le.raw" --timeout "$time_limit" \
    --report "$run_dir/session-1.json"
echo 'MUSIC_SOFTWARE_TEST=completed; confirmação auditiva depende de você.'
