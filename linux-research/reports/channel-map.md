# Inventário e teste dos canais da 192 I/O

## Configuração deste exemplar

Os IDs retornados no ensaio de identificação foram `0x13151314`, em ordem
little endian. A interpretação abaixo combina o relato do proprietário,
a identificação do DSI e o manual da **192 I/O** (não o da HD I/O).

| Baia física | Índice interno | ID | Módulo | Canais físicos |
|---|---:|---:|---|---|
| 1 | 0 | 0x14 | entrada analógica AD | entradas 1–8 |
| 2 | 1 | 0x13 | saída analógica DA | saídas 1–8 |
| 3 | 2 | 0x15 | digital | 8 canais; ADAT escolhido para o próximo ensaio |
| 4, expansão | 3 | 0x13 | saída analógica DA | saídas 9–16 |

O aparelho oferece 16 canais de transporte por direção. Seus conectores
físicos não são todos canais lógicos adicionais: o roteamento escolhe as
conexões usadas. Os DB25 de entrada +4 dBu e −10 dBV são alternativas para
os mesmos oito conversores. As portas ópticas do chassi e do módulo DIGITAL
I/O são caminhos distintos. Fonte: [192 I/O Guide, capítulos 1–3](https://m.barryrudolph.com/recall/manuals/avid_192_manual.pdf).

Os dois bancos analógicos retornaram os tons nos oito pares de saída
selecionados, usando as oito entradas em loopback DB25. Veja o
[registro dos bancos completos](analog-banks-confirmed.md). A [contraprova entre 1–2 e 3–4](analog-pair-isolation-confirmed.md)
diferenciou os dois caminhos com seleções cruzadas. A numeração física
continua vinculada ao cabeamento informado. O digital aguarda ensaio;
os aplicativos continuam com o módulo duplex estéreo validado.

## Observação dos LEDs no primeiro banco

Em 20/09/2026, os quatro testes do primeiro banco retornaram correspondência
dos tons, zero XRUNs e restauração completa:

| Par solicitado (saída/entrada) | Sessão | Picos capturados, dBFS |
|---|---|---|
| 1–2 | U9pDts | −38,92 / −39,95 |
| 3–4 | R5p8FP | −40,24 / −39,88 |
| 5–6 | HIR9Qi | −39,87 / −40,07 |
| 7–8 | RMdHhM | −39,93 / −39,94 |

O usuário relatou que **somente os LEDs físicos 1–2 acenderam** em todos
os testes, com DB25 em loopback. Isso não deve ser descartado. O transporte
permanece nos canais lógicos 1–2 e remapeia os pares físicos; a hipótese é
que os medidores acompanhem esses canais lógicos. O manual descreve os
16 medidores, mas não especifica o ponto de medição nesse roteamento.
Portanto, essa explicação ainda é uma hipótese, e a correspondência dos tons
não resolve, sozinha, a numeração dos conectores.

Os antigos rótulos `INPUT_1`/`INPUT_2` identificavam as duas posições do
arquivo estéreo. O novo analisador mostra `PCM_CHANNEL_n` e a entrada
analógica **solicitada**, evitando confundi-los com identificação física.

Para distinguir os pares 1–2 e 3–4 sem mudar o cabo:

```sh
sudo ./linux-research/run-channel-isolation-test.sh
```

Mantenha o DB25 **saídas analógicas 1–8 → entradas analógicas 1–8**, o estado
de 48 kHz e os monitores mutados. Feche os aplicativos e pare o módulo duplex
antes. A sequência dura cerca de 40 segundos:

1. Saída 1–2 / entrada 1–2: exige os tons conhecidos.
2. Saída 3–4 / entrada 1–2: exige ausência dos tons.
3. Saída 1–2 / entrada 3–4: exige ausência dos tons.
4. Saída 3–4 / entrada 3–4: exige novamente os tons conhecidos.

Os testes negativos exigem amplitudes coerentes abaixo de −80 dBFS nas
janelas analisadas e RMS do intervalo completo de **1 a 9 s** abaixo de −65 dBFS, sem clipping
em qualquer parte da gravação. O primeiro e o último segundo são reportados
separadamente; o início não entra na decisão de isolamento dos tons.
Falhar na detecção do padrão, isoladamente, não basta para passar.
A sequência interrompe no primeiro erro. Os negativos não ampliam a lista
de canais aprovados. Sucesso diferencia os dois caminhos selecionados no
loopback; não é uma medição completa de crosstalk nem comprovação do ponto
de medição dos LEDs. Não mude os cabos durante a sequência.

## Revisão do primeiro teste de isolamento

A sequência parou na segunda etapa, sessão `channelmap-test-fbJprf`;
naquela execução, as etapas 3 e 4 ficaram pendentes. Elas passaram depois
em execuções individuais, conforme o marco abaixo. Houve zero XRUNs/erros do módulo
e restauração completa. O proprietário novamente observou apenas os LEDs
1–2 de entrada e saída.

O critério inicial aplicado ao RMS dos 10 s foi inadequado para distinguir
isolamento estável de transiente de abertura. No segundo canal, um transiente
com pico −43,62 dBFS em aproximadamente 0,140 s elevou o RMS total para
−64,77 dBFS, acima do limite −65 dBFS. Os tons nas janelas de análise ficaram
abaixo de −149 dBFS de amplitude coerente (não confundir com piso de ruído
ou medição completa de crosstalk).

O analisador versão 2 mantém os limites e mede RMS em todo o intervalo dos
tons, 1–9 s. Início e fim continuam no relatório e a proteção contra clipping
cobre os 10 s. Testes sintéticos verificam que um transiente inicial é
reportado, tons trocados e sinal dentro de 1–9 s continuam sendo rejeitados.

A [reanálise offline](isolation-startup-review.json) das duas gravações passa
nesses critérios. Essa reanálise, isoladamente, não concluía as quatro etapas. Os
relatórios originais não foram reescritos nem marcados retroativamente como
aprovados. A mudança de rota suprimiu o retorno dos tons na entrada
selecionada, mas a interpretação dos LEDs permanece hipótese.

## Contraprova concluída entre os pares 1–2 e 3–4

As etapas restantes foram executadas individualmente e passaram:

| Seleção de saída → entrada | Sessão | Resultado |
|---|---|---|
| 1–2 → 1–2 | eYBk4q | tons reconhecidos |
| 3–4 → 1–2 | fbJprf | ausência dos tons; critério estável aprovado em reanálise v2 |
| 1–2 → 3–4 | 7j2dI0 | isolamento aprovado em execução v2 |
| 3–4 → 3–4 | wDLeNh | tons reconhecidos em execução v2 |

Todas as execuções tiveram zero XRUNs/erros e restauração confirmada. A
comparação demonstra caminhos distintos sob as seleções do driver. Não
comprova por si só o ponto de medição dos LEDs nem a pinagem do cabo.
As saídas 9–16 passaram depois no ensaio do banco 2, registrado abaixo.
Veja [evidências e limites da contraprova](analog-pair-isolation-confirmed.md).

## Segundo banco analógico concluído

Com o DB25 no segundo módulo DA e nas mesmas entradas AD, passaram:

| Saídas → entradas | Sessão | Picos, dBFS |
|---|---|---|
| 9–10 → 1–2 | pGhHm1 | −38,99 / −39,99 |
| 11–12 → 3–4 | xUuQ7j | −39,97 / −39,86 |
| 13–14 → 5–6 | igzqIX | −39,88 / −40,06 |
| 15–16 → 7–8 | gQk6lP | −39,97 / −39,95 |

Cada par reconheceu os tons, sem XRUN/erro e com restauração completa.
O proprietário novamente observou somente os LEDs de entrada e saída 1–2.
O transporte lógico permaneceu 1–2; os registros de destino usados foram
`0x55..0x58`. A hipótese sobre os medidores continua compatível com o ensaio,
sem comprovação do ponto exato de medição. A cobertura agora inclui todos
os canais analógicos por pares. Digital e funcionamento simultâneo de todos
os canais ainda não foram testados.

## Preparação

Na raiz `/home/paulo/hdnative_linux`:

```sh
./linux-research/build-channelmap.sh
sudo ./linux-research/duplex-driver.sh stop
```

Feche aplicativos usando a interface antes de parar o módulo. Se estiver
usando o módulo antigo de reprodução, pare-o com `desktop-driver.sh stop`.
O teste recusa uma placa vinculada a qualquer driver, sem removê-lo.

Salve o trabalho, mantenha os monitores mutados e preserve o estado de
48 kHz dos testes anteriores. Use as entradas analógicas +4 dBu utilizadas
no loopback já validado. Não conecte simultaneamente fontes diferentes aos
dois bancos de nível da mesma entrada. Cada execução grava 10 segundos,
emite tons de −40 dBFS e tenta restaurar mute, rotas e estado PCI ao sair.
O módulo tem limite de 15 s e o gravador, timeout de 18 s. Não há monitoração
do sinal capturado nem alteração de clock, nível de entrada ou firmware.

## Teste com oito conexões analógicas

1. Ligue saídas **1–8** às entradas **1–8**, na mesma ordem. Execute:

   ```sh
   sudo ./linux-research/run-analog-bank-test.sh 1
   ```

2. Aguarde a conclusão e a remoção do módulo. Passe os cabos para saídas
   **9–16** → entradas **1–8**, na mesma ordem. Execute:

   ```sh
   sudo ./linux-research/run-analog-bank-test.sh 2
   ```

Cada grupo executa quatro testes de pares e interrompe no primeiro erro.
Não mova cabos durante uma execução. O retorno deve conter
`ANALOG_PAIR_TEST_PASSED=yes` para cada par. Falha não prova defeito físico:
pode indicar cabeamento, seleção ou interpretação incorreta do roteamento.

## Teste com somente duas conexões

Escolha o par físico de saída (1–8) e o par de entrada (1–4). Cada par `n`
corresponde aos canais `2n−1` e `2n`. Exemplo, saídas **9–10** ligadas às
entradas **1–2**:

```sh
sudo ./linux-research/run-channelmap-test.sh 5 1
```

Para testar também todas as entradas, mude o segundo argumento e mova os
cabos para o par correspondente. Para confirmar cada canal, a ligação física
precisa corresponder aos argumentos: software sozinho não identifica um
conector sem esse vínculo conhecido.

## Evidências e resultados

Cada pasta `reports/channelmap-test-*/` contém gravação WAV/raw, análise,
perfil físico informado, SHA256 do módulo e da gravação, estatísticas,
log e cabeçalho PCI antes/depois. `session.json` somente marca sucesso quando
os tons correspondem, não há XRUN/erro, os controles foram restaurados e
o cabeçalho PCI está igual ao inicial com a placa desvinculada.

```sh
python3 linux-research/tools/channelmap_coverage.py
```

O resumo considera somente sessões bem-sucedidas desse novo teste e mostra
canais analógicos aprovados/pendentes. As validações históricas estéreo não
são importadas automaticamente. O teste detecta o padrão de frequências e
a separação temporal entre canais, mas não mede THD, resposta em frequência,
crosstalk ou precisão de clock.

## ADAT: leitura antes da ativação

O caminho escolhido é o óptico do **módulo DIGITAL I/O**, a 48 kHz. O plano
é um cabo óptico OUT → IN desse mesmo módulo. Isso permite testar os oito
canais sem uma segunda interface ou clock externo, depois de confirmar a
seleção ADAT e seu estado. O teste de áudio digital ainda não está habilitado.

Com todos os drivers Avid parados, obtenha o estado inicial:

```sh
sudo ./linux-research/identify-192 --inspect-digital
```

O diagnóstico revisado foi executado: os três candidatos `0x30..0x32`
retornaram timeout nas duas passagens. Todos os retornos ao comando neutro
foram confirmados, a 192 continuou identificada e PCI COMMAND foi restaurado.
Não houve leitura válida desses controles nem WRITE no periférico.

A investigação rastreou o bloco usado pelo decodificador Windows até o
arquivo de preferências **DSIPrefs**. O próximo passo é analisar uma cópia
desse arquivo, distinguindo estado salvo de estado atual do hardware.
Não é necessário repetir as consultas já feitas. Veja
[as evidências e o leitor offline](digital-preferences-findings.md).

## Evidência técnica para o roteamento

DSI.dll do pacote Pro Tools 2026.4.1, SHA256
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`. Endereços RVA (base PE `0x180000000`):

- `0x1aa0d0`: endpoints 9–24 → módulo `(índice−9)/4` e par `(índice−9)%4`.
- `0x1af1d0`: índice da tabela de rotas → registro `0x40+índice`, banco 1.
- `0x1b1bf0`: construção das rotas padrão; módulo AD usa fontes 9–12;
  os dois DA usam destinos 13–16 e 21–24.
- O ensaio mantém o transporte estéreo validado: RX lógico 1–2 em registro
  `0x41`, fonte `8+input_pair`; TX lógico 1–2 (fonte 1) para registro
  `0x4c+output_pair` nos pares 1–4, ou `0x50+output_pair` nos pares 5–8.
- O helper exige a configuração exata de módulos e a tabela de rotas zerada,
  aceita escrita apenas no mute e nas duas rotas selecionadas e restaura
  ambas mesmo após ACK perdido. As outras rotas são verificadas duas vezes.
- Módulo digital: construtor `0x1b05f0`, vtable `0x7787d0`, decodificação
  de três bytes em `0x1b1010`, atualização em `0x1b1640`. O adaptador
  `0x1af740` calcula `0x20 + 8*módulo + subregistro`: módulo 2 → `0x30..0x32`.
  A seleção de fonte usa os dois bits baixos do segundo byte; conversores
  `0x1a9340`/`0x1a9380` mapeiam valores físicos 0/1/2 a enumerações 2/3/4.
  A associação definitiva dessas enumerações aos formatos e a sequência
  necessária para ativar ADAT ainda precisam ser verificadas.

Os binários/disassemblies proprietários não integram o repositório.
As alterações ficam em `avid_native_channelmap` e no diagnóstico de leitura;
a implementação duplex validada permanece igual.
