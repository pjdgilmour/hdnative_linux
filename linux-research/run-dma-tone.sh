#!/bin/sh
# Same bounded transport as silence; adds five short tone bursts.
set -eu
cd -- "$(dirname -- "$0")"
module=avid_native_dma_probe
long=0
unmute=0
route=0
case "${1-}" in
    '') ;;
    --long) long=1 ;;
    --unmute-192) long=1; unmute=1 ;;
    --route-192) long=1; unmute=1; route=1 ;;
    *) echo 'Uso: run-dma-tone.sh [--long|--unmute-192|--route-192]' >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    echo 'Uso: run-dma-tone.sh [--long|--unmute-192|--route-192]' >&2
    exit 2
fi
if [ "$(id -u)" != 0 ]; then
    echo 'Execute este script com sudo no terminal local.' >&2
    exit 1
fi
if [ -d "/sys/module/$module" ]; then
    echo 'O módulo do experimento já está carregado; não vou repetir o teste.' >&2
    exit 1
fi
cleanup() {
    if [ -d "/sys/module/$module" ]; then
        if /usr/sbin/rmmod "$module"; then
            echo 'EXPERIMENT_MODULE_REMOVED=yes'
        else
            echo 'EXPERIMENT_MODULE_REMOVED=no; preserve esta saída para análise.' >&2
        fi
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
echo 'Cinco sinais curtos a -40 dBFS, nos canais lógicos 1–2. Volume de monitoração baixo.'
echo 'Frequência nominal 1 kHz em 48 kHz; a taxa atual da 192 será preservada.'
if [ "$long" = 1 ]; then
    echo 'Modo longo: 128 ms de sinal por repetição em 48 kHz; amplitude mantida em -40 dBFS.'
fi
if [ "$unmute" = 1 ]; then
    echo '192: teste temporário do mute (controle 0: 0x02 -> 0x00 -> 0x02), com verificação.'
    echo 'Mantenha o volume baixo; a restauração será tentada também se houver erro.'
fi
if [ "$route" = 1 ]; then
    echo '192: roteamento temporário da primeira entrada DA (reg. 0x4d: 0 -> 1 -> 0).'
    echo 'O áudio só começa após verificar o roteamento e o desmute.'
fi
/usr/sbin/insmod "kernel/$module.ko" run_tone=1 tone_long="$long" unmute_192="$unmute" route_192="$route"
for key in result tx_consumed rx_produced status_sequence tx_mmio_first tx_mmio_last tx_mmio_changes pci_restored; do
    printf '%s=' "$key"
    cat "/sys/module/$module/parameters/$key"
done
if [ "$unmute" = 1 ]; then
    for key in mute_write_attempted control_before control_during control_after mute_restored; do
        printf '%s=' "$key"
        cat "/sys/module/$module/parameters/$key"
    done
    if [ "$(cat "/sys/module/$module/parameters/mute_write_attempted")" = Y ] &&
       [ "$(cat "/sys/module/$module/parameters/mute_restored")" != Y ]; then
        echo 'ATENÇÃO: restauração do mute não confirmada. Não repita o teste; preserve o log.' >&2
    fi
fi
if [ "$route" = 1 ]; then
    for key in route_write_attempted route_before route_during route_after route_restored; do
        printf '%s=' "$key"
        cat "/sys/module/$module/parameters/$key"
    done
    if [ "$(cat "/sys/module/$module/parameters/route_write_attempted")" = Y ] &&
       [ "$(cat "/sys/module/$module/parameters/route_restored")" != Y ]; then
        echo 'ATENÇÃO: restauração do roteamento não confirmada. Não repita o teste; preserve o log.' >&2
    fi
fi
echo '--- Registros do módulo ---'
dmesg --notime | grep "$module" | awk '
    /: initial id=/ { n=0 }
    { lines[++n]=$0 }
    END { for (i=1; i<=n; i++) print lines[i] }
' || true
echo 'Informe se ouviu os sinais nas saídas analógicas 1–2. O log sozinho não confirma áudio analógico.'
