# Reprodução ALSA prolongada confirmada — 20/09/2026

O usuário confirmou **“Maravilhoso! Funcionou!”** após o ensaio
`run-alsa-test.sh --stability`. Os logs e JSON locais foram inspecionados.

| Medida | Sessão longa | Reabertura curta |
|---|---:|---:|
| Duração nominal do arquivo | 320 s | 8 s |
| Tempo medido pelo supervisor | 320,305 s | 8,279 s |
| Quadros no arquivo | 15360000 | 384000 |
| Quadros enviados e consumidos | 15361024 | 385024 |
| Voltas completas do anel | 1875 | 47 |
| Retorno do player | 0 | 0 |
| Resultado do supervisor | sucesso | sucesso |

Totais: **15746048 quadros, 1922 voltas do buffer, duas partidas/paradas,
zero XRUNs e zero erros registrados pelo driver**. Maior intervalo de polling
observado: **1695 µs (1,695 ms)**. Este valor não é a latência total de áudio.

O avanço continuou nos registros de progresso durante a sessão longa. A
sequência de 8 segundos se repetiu 40 vezes dentro da mesma sessão ALSA,
incluindo seus trechos silenciosos, sem fechar/reabrir o PCM a cada sequência.
Ambos os arquivos tiveram exatamente 1024 quadros extras enfileirados e
consumidos, dentro da tolerância baseada no primeiro teste com `aplay`.
A origem desse preenchimento ainda não foi rastreada no player.

O ensaio é estéreo S24_3LE/48 kHz, pico −40 dBFS, saídas analógicas 1–2.
O usuário confirmou funcionamento auditivo; não houve medição de distorção,
precisão de clock ou verificação independente de amostras analógicas.

## Encerramento e integridade

Mute `0=2` e rota `4d=0` restaurados em ambas as sessões. O log informa módulo
removido e PCI sem driver. Os arquivos locais `pci-before.bin`/`pci-after.bin`
foram comparados: os 64 bytes são idênticos, COMMAND `0x0100`.
Todos os hashes do build foram conferidos antes desta atualização documental.

Módulo validado SHA256:
`196417b11f10dd43424ec4a6d76d5ff78487ac054e905fe1708dd5f2ec7e1b44`.
Kernel `6.12.107+deb13-amd64`; placa `0000:81:00.0`, dispositivo ALSA
`hw:3,0`, id `AvidNative`. O número 3 é desta execução, não uma garantia de
numeração futura.

## Evidências e limites

- Log completo (`alsa-test-xanHGa/console.log`; evidência local não incluída).
- Relatório da sessão longa (`alsa-test-xanHGa/session-1.json`; evidência local não incluída).
- Relatório da reabertura (`alsa-test-xanHGa/session-2.json`; evidência local não incluída).
- Log do módulo (`alsa-test-xanHGa/module.log`; evidência local não incluída).
- [Procedimento e alterações do ensaio](alsa-stability-test.md).

A reprodução prolongada foi validada durante esse intervalo neste conjunto;
isso não demonstra estabilidade por horas, sob carga concorrente ou em outros
estados de inicialização. Continuam pendentes partida a frio, captura ALSA,
outras taxas/canais, medições de qualidade/latência e uso por aplicativos
comuns. O RX foi descartado; avanço de índice não comprova captura válida.

O driver permanece experimental, manual, restrito a root, estéreo a 48 kHz
com buffer fixo. O limite padrão continua 30 segundos; o modo de estabilidade
seleciona 360. Não houve instalação permanente.
