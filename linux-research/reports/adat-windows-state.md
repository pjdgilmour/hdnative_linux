# ADAT do gabinete com a configuração deixada pelo Windows

## Leitura que explica a recusa EPROTO

Depois de `adat-test-NF8slx`, o diagnóstico retornou duas passagens iguais:

| Registro | Perfil antigo | Após a gravação Windows |
| --- | --- | --- |
| 0x12 | 0x01 | 0x03 |
| controle 0 | 0x02 | 0x00 |
| controle 1 | 0x00 | 0x80 |
| controles 2 e 3 | 0 | 0 |
| 30 rotas | todas zero | tabela Windows preservada |

A identidade e versão se mantiveram. A primeira divergência na ordem da
pré-verificação é 0x12, suficiente para EPROTO; as demais também seriam
recusadas. Não interpretar 0x12=3 como prova de lock ADAT sem decodificação
confirmada. O significado causal do controle 1=0x80 para o áudio ainda
não foi testado. Não escrevemos nesse registro.

Tabela 0x40..0x5d, em decimal:

```
0 9 10 11 12 25 26 27 28 0 0 0 0 1 2 3 4 0 0 0 0 0 0 0 0 5 6 7 8 1
```

`0x45=25` liga o primeiro par óptico ao quinto par de transporte; `0x59=5`
leva o quinto par de transporte ao primeiro par óptico. Portanto, o
ensaio pode usar **canais lógicos 9–10**, mantendo o ADAT físico **1–2**.
Isso corresponde às entradas/saídas lógicas 9–16 do print Windows.

## Novo modo, sem reprogramação da 192

```sh
sudo ./linux-research/run-adat-test.sh enclosure 1 1 --windows-state
```

- Restrito ao perfil observado do gabinete; aceita os quatro pares e
  seleções cruzadas para isolamento. Habilita a opção restrita de endereços DMA
  residuais já testada, sem reutilizar a memória apontada por eles.
- Exige exatamente os IDs, controles, status e 30 rotas observados acima;
  lê em duas passagens. Não aceita valores arbitrários de preferências.
- A camada DigiLink recusa **todos os comandos WRITE ao periférico**.
  Durante o teste, as rotas são apenas lidas; controle 0 permanece 0,
  controle 1 permanece 0x80, sem escrita de clock, formato ou SRC.
- Usa byte 36 do frame DMA para o par lógico 9–10: segundo grupo de
  32 bytes, com PCM a partir do byte 4 dentro do grupo. O padrão de 750/1500 Hz, −40 dBFS,
  mantém duração de 10 s. Todos os outros canais TX recebem zeros.
- O novo helper `native_adat_ring.h` é exclusivo do ensaio óptico. O
  helper compartilhado e o módulo duplex dos aplicativos não mudaram.
- Após desligar DMA, confere novamente controles e rotas. Neste modo,
  `mute_restored=Y` e `route_restored=Y` significam preservação conferida,
  não comandos de restauração enviados à 192. Mudança inesperada falha
  a aceitação e não é corrigida por escrita automática.
- O gerenciamento PCI/DMA continua programando a placa HD Native com
  buffers Linux, fazendo os resets de transporte já existentes e
  restaurando seus registradores ao terminar. "Sem WRITE à 192" não
  significa ausência de escritas PCI/MMIO à placa HD Native.

A pré-verificação no probe passou a informar registro, esperado e
observado em caso de recusa, evitando outro log de EPROTO sem contexto.
No primeiro par, o perfil registra RX/TX 9–10, entrada 0x45 e seletor TX=5;
o avaliador recusa metadados incompatíveis com esse modo.

## Validação offline da versão inicial

Build W=1 no kernel 6.12.107+deb13-amd64. Passaram os testes anteriores de
controle/DMA/lifecycle/aceitação e o novo `test_adat_windows_state.py`:

- bloqueio de todos os 65536 pares registro/valor de WRITE no modo Windows;
- recusa de cada controle/rota divergente e confirmação de preservação;
- comparação do payload TX real nos offsets 4/36 com o gerador original;
- zeros nos demais canais e 4,096 milhões de frames de captura simulada,
  incluindo voltas dos buffers, com ASan/UBSan;
- rejeição de metadados de transporte incorretos na aceitação;
- opções de CLI verificadas sem carregar módulo ou acessar hardware.

Os critérios de frequência, amplitude, clipping e restauração não foram
relaxados. Não houve execução física durante o desenvolvimento.

## Execução e próximo banco

Manter a 192 ligada após a sessão Windows, cabo OUT → IN nos ópticos
fixos do gabinete, 48 kHz, aplicativos fechados, monitores mutados e
trabalho salvo. É um módulo experimental de kernel, com risco de travamento.
O comando acima passou na sessão UYG7iv. O próximo ensaio é
`sudo ./linux-research/run-adat-bank-test.sh enclosure --windows-state`.
Veja [resultado e expansão](adat-enclosure-bank.md) para a tabela de offsets,
testes atualizados e limites de validação. Nenhum teste precisa
reproduzir o WAV capturado para avaliar o retorno.

Este ensaio separa o remapeamento temporário da 192 do transporte Linux:
a sessão UYG7iv confirmou o primeiro par no estado inicializado pelo Windows.
Os demais pares agora podem ser selecionados e aguardam validação física.
Não implementa inicialização a frio ou o ADAT do módulo.


## Correção após o primeiro ensaio completo

A versão inicial usava erroneamente o byte 28 e produziu a captura
`adat-test-E1eorI` com metadados lidos como PCM. O valor correto é 36;
TX e RX foram corrigidos e os testes passaram a cobrir fronteiras de grupo
com referência independente. Veja [evidência e regressão](adat-packet-layout-fix.md).
