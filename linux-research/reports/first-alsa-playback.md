# Primeiro áudio ALSA confirmado — 20/09/2026

O usuário confirmou **“Confirmado!!! Ouvi o som!!”** após executar
`run-alsa-test.sh`. O log local está em
alsa-test-TNhjQF/console.log (`alsa-test-TNhjQF/console.log`; evidência local não incluída).

Duas sessões independentes pelo dispositivo `hw:3,0` (`AvidNative`), estéreo
S24_3LE a 48 kHz, com arquivo de 8 segundos e pico −40 dBFS. A aplicação
abriu, reproduziu e fechou a placa duas vezes. Houve confirmação auditiva;
a resposta não especifica separação dos canais nem ausência de cortes.

| Medida | Resultado acumulado |
|---|---:|
| Partidas / paradas | 2 / 2 |
| Quadros consumidos | 770048 |
| Voltas completas do anel nativo | 94 |
| XRUNs registrados pelo driver | 0 |
| Último erro | 0 |
| Maior intervalo observado de polling | 1618 µs |
| Avanço do índice RX descartado | 770049 |

Em cada sessão, `queued=consumed=385024`; o arquivo contém 384000 quadros.
A diferença é exatamente um período ALSA (1024 quadros). O log mostra que
os quadros adicionais foram enfileirados e consumidos; não indica perda de
1024 quadros pelo driver. Preenchimento na aplicação é uma hipótese; sua
origem não foi investigada neste marco.

Mute e rota foram restaurados nas duas sessões (`mute=2`, `route=0`). O módulo
foi removido e a placa ficou sem driver. Os arquivos locais de cabeçalho PCI
antes/depois foram comparados: os 64 bytes são idênticos, COMMAND `0x0100`.
Todos os hashes do registro de build foram conferidos antes da atualização
desta documentação, incluindo fontes, módulo, helpers e script.

Módulo validado SHA256:
`058da0f1b6ca20a09cb15c7dc845dbf5858440569af0f38e5a8767f2d744ca63`.
Kernel: `6.12.107+deb13-amd64`. PCI `0000:81:00.0`, firmware `01050040`,
192 no estado de 48 kHz já usado nos testes anteriores.

## O que este resultado comprova

Reprodução audível por ALSA neste conjunto, realimentação do anel ao longo
de várias voltas, e duas aberturas/fechamentos bem-sucedidos com restauração.
O avanço RX confirma somente índices; não valida amostras de entrada.

Ainda faltam ensaios longos, medida de taxa/latência/qualidade, partida a frio,
confirmação detalhada dos canais e captura. Permanecem as restrições do
protótipo: root, reprodução apenas, estéreo S24_3LE/48 kHz, buffer fixo e
limite de 30 segundos por sessão. Não foi instalado como driver permanente.

Próxima etapa recomendada no desenvolvimento: ensaio de estabilidade mais
longo com contagem de quadros e detecção de falhas, antes de liberar uso geral
por aplicativos ou desenvolver captura. Nenhum novo teste foi executado
nesta etapa de registro do resultado.
