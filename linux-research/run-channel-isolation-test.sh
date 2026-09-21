#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
(($# == 0)) || { echo 'Uso: sudo ./run-channel-isolation-test.sh'; exit 2; }
((EUID == 0)) || { echo 'Execute com sudo.'; exit 1; }
echo 'Mantenha o DB25 analógico: saídas 1–8 -> entradas 1–8. Monitores mutados; 48 kHz.'
echo 'Quatro etapas de 10 s: dois retornos positivos e duas verificações de isolamento.'
echo 'Não mude o cabo durante a sequência. Os canais lógicos de transporte continuam 1–2.'
echo '1/4: saída 1–2 / entrada 1–2; deve captar os tons.'
./run-channelmap-test.sh 1 1
echo '2/4: saída 3–4 / entrada 1–2; não deve captar os tons.'
./run-channelmap-test.sh 2 1 --expect-isolation
echo '3/4: saída 1–2 / entrada 3–4; não deve captar os tons.'
./run-channelmap-test.sh 1 2 --expect-isolation
echo '4/4: saída 3–4 / entrada 3–4; deve captar os tons.'
./run-channelmap-test.sh 2 2
echo 'CHANNEL_PAIR_ISOLATION_SEQUENCE_PASSED=yes'
echo 'Pares selecionados 1–2 e 3–4 diferenciados no loopback; os LEDs não foram usados como critério.'
