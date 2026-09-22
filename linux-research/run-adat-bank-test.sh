#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
[[ ( $# == 1 || $# == 2 ) && ( $1 == enclosure || $1 == module ) ]] || {
    echo 'Uso: sudo ./run-adat-bank-test.sh enclosure|module [--windows-state]'; exit 2;
}
options=()
if [[ $# == 2 ]]; then
    [[ $1 == enclosure && $2 == --windows-state ]] || { echo '--windows-state exige enclosure.'; exit 2; }
    options=(--windows-state)
fi
((EUID == 0)) || { echo 'Execute com sudo no terminal local.'; exit 1; }
path=$1
echo "ADAT: $path; cabo óptico OUT -> IN do mesmo conjunto de portas; 48 kHz."
echo 'Seis etapas de 10 s: quatro pares e duas verificações de isolamento.'
echo 'Mantenha o cabo no lugar durante toda a sequência. Monitores mutados.'
echo '1/6: saída 1–2 / entrada 1–2; deve captar os tons.'
./run-adat-test.sh "$path" 1 1 "${options[@]}"
echo '2/6: saída 3–4 / entrada 1–2; não deve captar os tons.'
./run-adat-test.sh "$path" 2 1 --expect-isolation "${options[@]}"
echo '3/6: saída 1–2 / entrada 3–4; não deve captar os tons.'
./run-adat-test.sh "$path" 1 2 --expect-isolation "${options[@]}"
echo '4/6: saída 3–4 / entrada 3–4; deve captar os tons.'
./run-adat-test.sh "$path" 2 2 "${options[@]}"
echo '5/6: saída 5–6 / entrada 5–6; deve captar os tons.'
./run-adat-test.sh "$path" 3 3 "${options[@]}"
echo '6/6: saída 7–8 / entrada 7–8; deve captar os tons.'
./run-adat-test.sh "$path" 4 4 "${options[@]}"
echo "ADAT_BANK_SEQUENCE_PASSED=yes optical_path=$path"
echo 'Oito canais testados em pares; não é teste de oito canais simultâneos nem bit-perfect.'
