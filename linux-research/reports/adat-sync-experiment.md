# Estado pós-DigiTest: sincronismo comum e controles do módulo digital

## Resultado dos dois testes reais

O usuário confirmou o cabo OUT → IN no módulo DIGITAL I/O. Foram executadas
capturas de 10 s, 48 kHz/S24_3LE, tom 750/1500 Hz a −40 dBFS, mesmo transporte
lógico 1–2 e mesmas rotas temporárias 0x41=17 e 0x51=1.

| Sessão | Controle 1 durante a captura | Retorno | XRUNs / erro | Restauração |
| --- | --- | --- | --- | --- |
| adat-test-517Q9N | 0x00, preservado | 480000 frames inteiramente zero | 0 / 0 | mute, rotas e PCI |
| adat-test-jPNMgc | 0x80, temporário | 480000 frames inteiramente zero | 0 / 0 | controle 1, mute, rotas e PCI |

O segundo teste confirmou por leitura 0 → 128 → 0 no controle 1. O maior
intervalo de polling foi 1612 µs na referência e 1610 µs na comparação.
Em ambos, o módulo foi removido e a placa ficou desvinculada. Os hashes e
métricas estão em [adat-sync-experiment.json](adat-sync-experiment.json).

A leitura independente posterior confirmou controles `02/00/00/00`,
as 30 rotas em zero e PCI COMMAND restaurado, em duas passagens estáveis:
[post-sync-routing.txt](post-sync-routing.txt).

Isso demonstra que selecionar o bit de mestre **isoladamente não recuperou
o loopback do módulo neste estado**. Não identifica a causa única da ausência
de áudio, não invalida a matriz ADAT validada anteriormente e não confirma
inicialização após ciclo de energia. A continuidade da alimentação nesta
passagem Windows/Linux continua sem confirmação. Não reproduzir a mesma
comparação esperando resultado diferente sem nova hipótese.

## Decodificação do controle 1

DSI.dll local, SHA256
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`.
RVAs relativos à base 0x180000000; evidência estática, não documentação oficial.

| Bits | Construção no DSI | Evidência |
| --- | --- | --- |
| 0–2 | taxa: 48k→0, 96k→1, 192k→2, 44.1k→4, 88.2k→5, 176.4k→6 | encoder 0x1a5050; escritor 0x1afc87 |
| 3–6 | seleção de sincronismo, por tabela; Internal enum 0→0 | tabela 0x9aebf0, lookup 0x1a4af0; nome Internal em 0x087e90 |
| 7 | `slaveModeSelect == 1`, estado de mestre no objeto | escritor 0x1afce6; getter público e vtable abaixo |

`DsiGetPeripheralMasterStatus`/`GetPeripheralMasterStatus` exporta RVA
0x088ec0 e chama virtual +0x28. A vtable secundária da 192, RVA 0x778390,
aponta nesse slot para 0x1a4b80, que testa word `this+0x1c == 1`.
O setter em +0x30 é 0x1a5a80: bool verdadeiro→1, falso→2, atualização máscara
0x80. O log em 0x1a5846 identifica o campo como `slaveModeSelect`.

A vtable secundária é instalada em objeto primário+8; portanto, o mesmo
campo aparece como primário+0x24 no escritor 0x1afbc0. Essa diferença de
ponteiro é essencial para não confundir campos. Dispatcher em +0xb0,
0x1afef0, traduz máscara 0x80 em atualização dos controles 1 e 2; nosso
experimento altera apenas o bit de mestre no controle 1, mantendo controle
2=0. Não reproduz toda a chamada Windows nem promete inicialização completa.

## Novo experimento opt-in

`run-adat-test.sh module 1 1 --sync-profile` existe para reprodução técnica
desta comparação, não é necessário repetir agora. Só aceita o estado
pós-DigiTest observado, sem combinação com Windows-state, module-route ou
idle-DMA. Não muda o duplex nem sua instalação nos aplicativos.

A sequência é: conferir identidade/controles e 30 rotas, configurar duas
rotas, conferir novamente o estado mutado, escrever controle1=0x80 e ler
duas vezes, desmutar, conferir controles/rotas, transmitir por 10 s. A
limpeza para DMA, restaura mute, rotas e controle1=0. O retorno do clock
só é tentado com mute=2 confirmado. Falhas de restauração permanecem
registradas e impedem sucesso; ACK perdido também marca restauração
pendente. Não há reset nem atualização de firmware.

Build W=1 e testes passaram: 32 perfis ópticos, modo Windows somente
leitura, 16 perfis do módulo, DMA/endereço residual, limites e formato PCM,
analisador, mailbox e limpeza. O teste novo injeta ACK perdido, escrita
ignorada, falha de restauração, estado inválido e falta de mute antes de
restaurar o clock. Exercita a lista de escritas permitidas e impede
classificar sucesso sem `sync_restored=Y`.

## Configuração própria do módulo: sequência candidata, ainda offline

RTTI `CDjangoDizzyDigitalCard` → COL 0x8bc610 → vtable 0x7787d0.
O dispatcher +0x10 (0x1b0e80) chama 0x1b1640. Esta rotina constrói registros
locais 0, 1 e 2, nessa ordem quando todos estão selecionados. O adaptador
0x1af740 calcula `0x20 + índice_do_módulo*8 + registro_local`: para módulo
2, 0x30, 0x31, 0x32. Não há prova de suporte de leitura desses registros.

Para os cinco campos salvos `0,0,3,15,1`:

- Local 0: campo +0x18 nos bits 0–2 e +0x1c nos bits 4–7 → `0x00`.
- Local 1: fonte +0x20=3 passa pelo encoder 0x1a9380 → 1 nos bits 0–1;
  máscara SRC=15 passa pela inversão XOR 15 (0x1a9370) → 0 nos bits 2–5;
  bit6=(máscara==0), bit7=(máscara==15) → `0x81`.
- Local 2: campo +0x28=1 passa por XOR 1 → `0x00`.

Isso liga preferências e comandos candidatos, não comprova os valores
presentes no hardware. A rotina também pode normalizar campos. O callback posterior +0x10
do adaptador (vtable 0x7782f0) aponta para 0x1af920, que chama 0x1b1e40
para recompor informações de roteamento no objeto; não é, por si só,
um comando de firmware. A sequência externa completa ainda precisa de revisão. **Nenhuma escrita 0x30..0x32 foi habilitada ou
executada.** A próxima etapa é estabelecer a verificação e o procedimento
de recuperação dessas configurações antes de um teste de inicialização.

Reprodução offline, sem acesso ao hardware:

```sh
python3 linux-research/tools/inspect_192_digital_config.py \
  '/home/paulo/Downloads/Pro Tools_2026.4.1/Program Files 64/Avid/Pro Tools/DIO_64/DSI.dll' \
  prefs_protools/DSIPrefs
```

O utilitário exige o hash do DSI e o perfil salvo exato que foi rastreado;
recusa outro binário/topologia/perfil. [Saída](dsi-digital-config-evidence.json).
Os bytes calculados não são uma receita para gravar manualmente na placa.
