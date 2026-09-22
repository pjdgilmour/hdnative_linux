# Espera do mailbox DigiLink após RlWCWh

**Atualização:** a sequência completa passou no hardware; veja
o [registro dos oito canais e duas contraprovas](adat-enclosure-confirmed.md).
O texto abaixo conserva o histórico de preparação deste teste.

## Evidência do ensaio

A primeira etapa de `run-adat-bank-test.sh enclosure --windows-state`
falhou durante a preparação ALSA, antes de START, na sessão
`adat-test-RlWCWh`. O perfil foi aceito no probe e o driver chegou à
verificação das rotas em prepare. A consulta ao registro 0x41 foi recusada:

- `stage=peripheral-route-check`, `error=-16` (EBUSY).
- `reg=41 expected=9 observed=ffffffff`: indisponível; não significa valor 0xff.
- No snapshot de erro: TX=0 e RX=0x00800000.
- starts=stops=0, zero frames; não houve teste de áudio dos novos pares.
- O módulo foi removido, o cabeçalho PCI restaurado e a placa desvinculada.

O código recusava imediatamente qualquer cabeçalho RX não nulo antes de
uma consulta. O snapshot posterior é compatível com essa guarda; não
estabelece por quanto tempo o RX ficou ocupado nem a semântica de 0x800000.
Não há evidência suficiente para atribuir a causa a clock, cabo ou formato.
O loopback positivo `adat-test-UYG7iv` continua válido para o par 1–2.

Neste modo, nenhum comando WRITE à 192 é permitido. Os indicadores
mute_restored=N / route_restored=N nesta falha significam que não houve
verificação final completa do perfil; não provam alteração de mute/rotas.

## Alteração restrita ao ensaio ADAT

O helper agora observa TX/RX antes de cada consulta e após limpar o seu
próprio comando. Exige dois snapshots livres, separados pela pausa de
50–100 us já usada no módulo. Se RX está ocupado, espera no máximo 100 ms,
com limite adicional de 2001 iterações. Isso evita tanto a recusa imediata
quanto aceitar uma única leitura zero no meio da transição.

TX não nulo continua sendo recusado imediatamente; não é sobrescrito.
Não se escreve no RX, não se ignora o bit 0x800000, não se força reset e não
se repete automaticamente uma transação que falhou. Um RX que permaneça
ocupado resulta em EBUSY; falha de liberação após o comando resulta em EIO.
A resposta ainda precisa ter o cabeçalho exato do registro consultado.

O log de prepare informa quantas esperas encontraram RX ocupado e os
últimos TX/RX observados em caso de falha. Os controles esperados, as 30
rotas, offsets PCM, amplitudes, critérios de análise e guardas DMA não
foram modificados. O módulo duplex dos aplicativos permanece inalterado.

## Verificação

`test_adat_mailbox.py` compila o helper real com UBSan e simula:
RX atrasado, zero transitório seguido de ocupação, RX permanentemente
ocupado, relógio simulado parado (limite de iterações), TX ativo desde o
início ou durante a espera, limpeza atrasada/presa e ACK de outro registro.
Confere que não se envia comando durante ocupação, que o byte alto TX é
preservado, que não há WRITE periférico nem retentativa de comando.

Build W=1 e testes de controle, lifecycle, handoff DMA, seleção independente
dos quatro pares TX/RX e análise/aceitação passaram. Nenhum módulo foi
carregado durante o desenvolvimento. A eficácia contra a falha física
observada ainda depende da próxima execução; o bit RX pode continuar preso.

## Repetição física

Manter a 192 ligada e configurada a 48 kHz, mesmo cabo OUT → IN do gabinete,
monitores mutados, aplicativos fechados e trabalho salvo:

```sh
sudo ./linux-research/run-adat-bank-test.sh enclosure --windows-state
```

A sequência continua parando na primeira falha e preservando o estado
Windows. Se recusar novamente, guardar a saída completa com os novos
campos de espera e diagnóstico. Não é necessário reproduzir o WAV.
