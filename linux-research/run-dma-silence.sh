#!/bin/sh
# Manual, bounded experiment only; does not install/autoload a driver.
set -eu
cd -- "$(dirname -- "$0")"
module=avid_native_dma_probe
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
        if rmmod "$module"; then
            echo 'EXPERIMENT_MODULE_REMOVED=yes'
        else
            echo 'EXPERIMENT_MODULE_REMOVED=no; preserve esta saída para análise.' >&2
        fi
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
echo 'Teste DMA experimental: 20 ms de silêncio. Monitores devem estar mutados.'
insmod "kernel/$module.ko" run_silence=1
for key in result tx_consumed rx_produced status_sequence pci_restored; do
    printf '%s=' "$key"
    cat "/sys/module/$module/parameters/$key"
done
echo '--- Registros do módulo ---'
dmesg --notime | grep "$module" | tail -n 12 || true
echo 'Este teste não confirma som nas saídas analógicas nem fornece dispositivo ALSA.'
