# ADAT do gabinete: oito canais confirmados em pares

A sequência completa `run-adat-bank-test.sh enclosure --windows-state`
passou nas seis etapas, com cabo óptico OUT → IN nos conectores fixos do
gabinete e a configuração Windows preservada. Não houve comandos WRITE
à 192. O módulo usado tem SHA-256:
`284e6b3cf247e887ea7d9ebfb683283afe52af0cb78e0123fa2486c29a37034f`.

| Etapa | Saída física | Entrada física | Sessão | Resultado |
| --- | --- | --- | --- | --- |
| 1 | 1–2 | 1–2 | 9g5EmT | tons corretos, −40 dBFS |
| 2 | 3–4 | 1–2 | fL6CJy | isolamento, arquivo inteiramente zero |
| 3 | 1–2 | 3–4 | eF0Ulq | isolamento, arquivo inteiramente zero |
| 4 | 3–4 | 3–4 | Hxc0Md | tons corretos, −40 dBFS |
| 5 | 5–6 | 5–6 | wuL2sj | tons corretos, −40 dBFS |
| 6 | 7–8 | 7–8 | P8yZ1z | tons corretos, −40 dBFS |

Cada sessão contém 480000 frames estéreo S24_3LE a 48 kHz, 10 segundos.
Todas terminaram com starts=stops=1, zero XRUNs, last_error=0, controles e
rotas preservados, módulo removido, cabeçalho PCI restaurado e placa livre.
O maior max_poll_us foi 1734; esse contador não é latência de áudio.
Não houve clipping nos retornos positivos.

## Conferência dos arquivos

Além da saída fornecida, foram conferidos localmente os seis `session.json`,
perfis, análises, hashes dos arquivos raw e igualdade dos snapshots PCI.
A função de aceitação atual aprovou os seis conjuntos. As duas capturas
de isolamento foram verificadas byte a byte como zero.

As quatro capturas positivas são idênticas entre si (mesmo SHA-256):
`188cc270af7138e2d2f3a3d6959140602c6cf8cc7f44dfebfae7cf6ffbda7933`.
As duas capturas de isolamento têm SHA-256:
`1b97524801d8c93d65973ee64c84ce13cf8ab979672b2666f225f8591f02a5b3`.
Isso mostra repetibilidade entre os pares; não é uma comparação bit-perfect
contra o fluxo TX completo. [Evidências estruturadas](adat-enclosure-confirmed.json).
Os arquivos originais dos ensaios foram preservados.

## Espera DigiLink observada no hardware

Antes da preparação bem-sucedida, o contador `idle_waits` registrou
306, 308, 306, 306, 304 e 307 nas respectivas etapas. Ele conta chamadas
à espera que encontraram RX ocupado, não tentativas de retransmissão,
falhas, milissegundos ou duração total. Todos os mailboxes observados
liberaram dentro das condições exigidas para prosseguir.

A alteração de espera resolveu a recusa nesta sequência. Não determina
por si só a semântica do bit 0x800000 nem garante todas as condições futuras.
Os offsets 36, 42, 48 e 54 agora têm resultados físicos positivos nesse
perfil de rotas, correspondendo aos pares lógicos 9–10, 11–12, 13–14 e 15–16.

## Escopo e próximo caminho

Confirmados os oito canais de entrada/saída do ADAT do gabinete, testados
em pares, e isolamento nas duas direções entre 1–2 e 3–4. Não foram testados
os oito canais simultaneamente, isolamento de todas as combinações,
inicialização a frio ou uso multicanal nos aplicativos.

O ADAT do módulo DIGITAL I/O é um caminho distinto e continua pendente.
Para manter o método de comparação, a próxima referência deve selecionar
esse módulo no Windows, conferir o retorno físico OUT → IN do módulo,
salvar a gravação e o print e manter a 192 ligada na volta ao Linux.
A primeira ação no Linux será ler controles/rotas com `identify-192
--inspect-routing`, antes de preparar um perfil de teste específico.
O perfil `--windows-state` atual é exclusivo do gabinete e não deve ser
usado como se fosse o perfil do módulo. Também permanece pendente
inicializar o formato digital diretamente no Linux.
