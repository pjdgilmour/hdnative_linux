#!/bin/bash
# Temporary, root-only playback prototype. No driver installation/default changes.
set -euo pipefail
cd -- "$(dirname -- "$0")"
module=avid_native_alsa
bdf=0000:81:00.0
stability=0
stream_limit=30
case "${1-}" in
    '') ;;
    --stability) stability=1; stream_limit=360 ;;
    *) echo 'Uso: sudo ./run-alsa-test.sh [--stability]' >&2; exit 2 ;;
esac
if (($# > 1)); then
    echo 'Uso: sudo ./run-alsa-test.sh [--stability]' >&2
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
run_dir=$(mktemp -d "$PWD/reports/alsa-test-XXXXXX")
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
    echo 'Informe se ouviu os canais 1, 2 e ambos, e se houve cortes, estalos ou repetições fora da sequência de 8 segundos.'
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
python3 tools/make_alsa_tone.py --output "$run_dir/tone.raw"
if ((stability)); then
    python3 tools/make_alsa_tone.py --output "$run_dir/tone-long.raw" --repeat 40
    echo 'Estabilidade ALSA: 5 min 20 s contínuos, depois reabertura de 8 s; pico -40 dBFS.'
    echo 'A sequência de 8 s se repete dentro do mesmo stream. Progresso a cada 10 s.'
else
    echo 'Teste ALSA experimental: duas reproduções de 8 segundos, pico -40 dBFS.'
fi
echo 'Em cada reprodução: canal 1 (440 Hz), canal 2 (660 Hz), depois ambos, com pausas.'
echo 'Mantenha o volume baixo e o trabalho salvo: o módulo ainda pode travar o sistema.'
echo 'A 192 deve continuar no estado de 48 kHz dos testes anteriores; o clock será preservado.'
/usr/sbin/modprobe snd_pcm
loaded=1
/usr/sbin/insmod "kernel/$module.ko" enable_experimental=1 bdf="$bdf" max_stream_seconds="$stream_limit"
shopt -s nullglob
cards=(/sys/bus/pci/devices/"$bdf"/sound/card[0-9]*)
if ((${#cards[@]} != 1)); then
    echo 'Não encontrei exatamente uma placa ALSA associada ao PCI esperado.'
    exit 1
fi
card=${cards[0]##*/card}
echo "ALSA_DEVICE=hw:$card,0"
for session in 1 2; do
    echo "--- Reprodução $session/2 ---"
    audio="$run_dir/tone.raw"
    time_limit=15
    if ((stability && session == 1)); then
        audio="$run_dir/tone-long.raw"
        time_limit=340
    fi
    python3 tools/supervise_alsa.py --device "hw:$card,0" \
        --audio "$audio" --timeout "$time_limit" --report "$run_dir/session-$session.json"
    stats
    if [[ $(cat /sys/module/$module/parameters/last_error) != 0 ||
          $(cat /sys/module/$module/parameters/xruns) != 0 ||
          $(cat /sys/module/$module/parameters/mute_restored) != Y ||
          $(cat /sys/module/$module/parameters/route_restored) != Y ]]; then
        echo 'O driver informou uma falha; encerrando sem repetir.'
        exit 1
    fi
    if ((session == 1)); then sleep 1; fi
done
expected_total=768000
if ((stability)); then expected_total=15744000; fi
if [[ $(cat /sys/module/$module/parameters/starts) != 2 ||
      $(cat /sys/module/$module/parameters/stops) != 2 ]] ||
   (( $(cat /sys/module/$module/parameters/total_frames) < expected_total )); then
    echo 'Contagem de reprodução incompleta; preserve o log.'
    exit 1
fi
echo 'ALSA_SOFTWARE_TEST=completed; confirmação auditiva ainda depende de você.'
