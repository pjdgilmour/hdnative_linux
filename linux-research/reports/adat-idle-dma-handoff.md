# ADAT: endereços DMA residuais com motores desligados

## Snapshot fornecido

Após a recusa `adat-test-phjU44`, duas leituras mostraram:

| Registro | Valor, nas duas passagens |
| --- | --- |
| RX DMA low, 0x40918 | 0x79062000 |
| TX DMA low, 0x41118 | 0x78e60000 |
| Status DMA low, 0x4093c | 0x79464000 |
| respectivos high, 0x40958/0x41158/0x4097c | 0 |
| controle DMA, DigiLink, reset e máscaras IRQ | 0 |
| controle do núcleo | 0x00000a00 |
| comandos DigiLink slot 0 | ociosos |

Os endereços não nulos bastam para acionar o EBUSY da guarda anterior,
mesmo com motores desligados. São compatíveis com registros residuais
após a sessão Windows. Não demonstram memória ainda válida ou DMA ativo.
O utilitário recusaria bus mastering ativo antes dessa leitura; o
cabeçalho PCI do teste anterior tinha COMMAND=0x0100.

`TRANSPORT_READS_STABLE=no` decorre da variação do status DigiLink
`0x9e180101` → `0x9e1a0101` (XOR 0x00020000). Ela não altera a máscara
0x101 exigida para presença de link. Isso não comprova lock ADAT.
Os seis campos de endereço DMA permaneceram iguais.

## Opção restrita no ensaio óptico

`run-adat-test.sh ... --allow-idle-dma` passa `allow_idle_dma=1` ao módulo
experimental `avid_native_adat`. Sem essa opção, endereços não nulos
continuam recusados. Não há alteração no módulo duplex dos aplicativos.

O probe e o prepare agora verificam:

1. PCI bus mastering desligado e conclusão das transações pendentes.
2. Núcleo, reset, controles DMA/DigiLink e IRQs no estado quieto exigido,
   em duas passagens separadas por 1–1,5 ms.
3. Se os endereços não forem zero: opção explícita, estabilidade dos seis
   campos, três bases de 32 bits não nulas e alinhadas a 256 bytes, high=0.
4. Nova conferência de PCI COMMAND antes de aceitar o estado.

Os endereços antigos são somente valores salvos para restauração. Não
são mapeados, desreferenciados ou usados para DMA. O driver aloca buffers
com `dma_alloc_coherent` e programa as seis partes de seus endereços.
Confere o readback contra os endereços alocados após setup e novamente
imediatamente antes de habilitar bus mastering no START. Também verifica
que transmissão/DMA ainda não estão habilitados. Falha impede o START.

A limpeza existente desliga transmissão/DMA, desabilita bus mastering,
aguarda transações pendentes e só então restaura os registros salvos e
libera buffers. Se a drenagem falha, preserva memória e módulo em quarentena.
Os valores residuais originais são restaurados como registros inativos;
isso não autoriza seu uso por outro driver. Eles não são zerados por um
utilitário separado para contornar a guarda.

Essa mudança viabiliza testar após Windows sem desligar a interface.
Não corrige por si só a corrupção de amostras ADAT e não modifica o
formato dos samples, mute, roteamento, seleção digital, SRC ou clock.
Os critérios de aprovação do áudio continuam os mesmos.

## Validação offline

Build W=1 para 6.12.107+deb13-amd64. Passaram os testes de 32 perfis,
2,74 milhões de frames de ring, limites dos tons, lifecycle/cleanup e cinco
casos de análise/aceitação. O novo teste compila as funções reais de
quiet_state, setup_dma e verify_dma_buffers com MMIO/PCI simulados:

- recusa sem opção, motores ativos, PCI master ativo, transação pendente,
  erro de config, endereço instável, high não zero ou desalinhamento;
- programa os buffers novos e detecta escrita ignorada em cada um dos
  seis campos antes de permitir o caminho de START;
- reutiliza o teste real de cleanup com os seis endereços observados,
  verificando restauração em ordem reversa depois da drenagem e as
  proteções de ACK perdido/quarentena;
- ASan/UBSan; opções do script verificadas sem executar comandos de hardware.

Nenhum módulo foi carregado durante o desenvolvimento. O manifesto foi
atualizado com os hashes do novo módulo e dependências.

## Próximo teste físico

Com a 192 ainda ligada após o Windows, cabo OUT → IN nos conectores
ópticos fixos do gabinete, 48 kHz, aplicativos fechados, monitores mutados
e trabalho salvo (módulo de kernel experimental):

```sh
sudo ./linux-research/run-adat-test.sh enclosure 1 1 --allow-idle-dma
```

A coleta continua limitada a 10 s, com watchdog do módulo em 15 s.
Enviar a saída completa, inclusive se houver nova recusa. Não forçar
reset nem reproduzir uma captura distorcida nos monitores.


## Resultado físico: guarda de transporte passou, probe recusado com EPROTO

Na sessão `adat-test-NF8slx`, `allow_idle_dma=1` passou pela verificação de
estado quieto: o log registrou as três bases residuais, motores e master
desligados e transações pendentes drenadas. Em seguida o probe retornou
`-71` (`EPROTO`), antes de anunciar ALSA ready. Não há gravação nova.
PCI HEADER foi restaurado e a placa ficou desvinculada.

O próximo passo explícito do probe é `n192_preflight`. Nesse helper,
`n192_expect` retorna EPROTO quando uma leitura concluída difere do valor
esperado. O perfil exige IDs `14 13 15 13`, registros 0x11..0x13 com valores
49/01/01 e controles 0..3 com 02/00/00/00. O log não inclui a etapa exata
nem o registro divergente, portanto essa origem deve ser confirmada por
leitura. Não interpretar o texto genérico "Protocol error" como prova de
DigiLink quebrado, firmware inválido ou defeito no cabo.

O utilitário já existente pode consultar todos esses campos e as rotas
sem exigir endereços DMA zerados:

```sh
sudo ./linux-research/identify-192 --inspect-routing
```

Manter a 192 ligada e não iniciar outro driver. O utilitário envia apenas
consultas pelo DigiLink, sem WRITE de controle no periférico e sem iniciar
DMA/áudio ou reset. Preserva as guardas PCI/estado quieto e restaura PCI
COMMAND. Valores inesperados de controles são impressos, em vez de serem
normalizados. A próxima decisão depende dessa leitura; nenhum novo perfil
de controle foi aceito nem nenhuma escrita adicional preparada nesta revisão.
