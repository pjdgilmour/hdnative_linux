#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
case "${1-}" in 1|2) bank=$1 ;; *) echo 'Uso: sudo ./run-analog-bank-test.sh 1|2'; exit 2;; esac
(($# == 1)) || exit 2
((EUID==0)) || { echo 'Execute com sudo.'; exit 1; }
if ((bank==1)); then
    echo 'Ligação necessária: saídas analógicas 1–8 -> entradas 1–8, na mesma ordem.'
else
    echo 'Ligação necessária: saídas analógicas 9–16 -> entradas 1–8, na mesma ordem.'
fi
echo 'Quatro testes de 10 segundos. Não mova cabos durante a execução. Monitores mutados.'
for input in 1 2 3 4; do
    output=$((input+4*(bank-1)))
    ./run-channelmap-test.sh "$output" "$input"
done
python3 tools/channelmap_coverage.py
