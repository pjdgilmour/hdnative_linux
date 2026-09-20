# Roteamento da 192: próximo diagnóstico

O controle de mute já foi alterado de 2 para 0 e restaurado para 2, com
verificação no hardware, mas sem som. É necessário verificar o encaminhamento
dos canais até os módulos de saída. Não se concluiu que ele esteja incorreto.

## Evidência estática

DSI.dll, RVAs relativos a `0x180000000`; trechos preservados em
192-routing-disassembly.txt (`192-routing-disassembly.txt`; evidência local não incluída).

- `0x1af1d0` envia entradas de uma tabela de palavras em `outer+0x58` para
  banco 1, registros `0x40 + índice`. `0x1afef0` chama essa rotina com índice
  inicial 0 e quantidade `0x1e` (30) para a atualização completa.
- `0x1af130` altera uma entrada por `0x1b1ba0`, depois envia a entrada por
  `0x1af1d0`. Os índices aceitos no setter são menores que 30.
- `0x1b1ba0` faz `tabela[destino+i] = origem+i`, em palavras de 16 bits;
  a escrita DigiLink usa o byte baixo do valor. A descrição origem/destino
  é uma interpretação do uso da tabela, não um símbolo exportado.
- `0x1b1e40` constrói metadados da tabela a partir dos quatro módulos;
  `0x1b1bf0` constrói a seleção padrão. Não portar essa seleção como se
  fosse necessariamente o roteamento atual escolhido pelo usuário no Windows.
- `0x1aa0d0` associa índices 9..24 a módulo `(índice-9)/4` e subíndice
  `(índice-9)%4`. A placa DA no módulo 1 ocupa, portanto, índices 13..16,
  associados aos registros `0x4d..0x50`. A associação exata de subíndice
  com pares de canais físicos ainda exige validação.

## Consulta de leitura executada

```sh
sudo ./linux-research/identify-192 --inspect-routing
```

Mantém as verificações do diagnóstico anterior: PCI/subsystem/firmware,
transporte quieto, 192 conhecida no slot 0 com módulos `0x13151314`.
Lê controles/status, depois os 30 registros `0x40..0x5d` duas vezes.
Mostra um vetor de bytes em ordem crescente de registro para cada passagem
e informa se os valores permaneceram iguais. Interrompe em erro de consulta
ou limpeza. O modo anterior `--inspect-192` continua com sua lista restrita.

É uma tentativa de readback da tabela: ACK e estabilidade, isoladamente,
não provam semântica válida dos registros. Não envia comandos WRITE para
a 192, não altera roteamento/mute, não gera áudio nem carrega módulo de kernel.
Escreve comandos de consulta/neutros no transporte PCI e restaura COMMAND.

Compilação `-Wall -Wextra -Werror`; 16 testes DigiLink simulados passaram,
incluindo a lista exata de registros, ausência do bit WRITE e recusa antes
de identificar a 192 ou quando há DMA ativo.

O usuário executou a consulta: os 30 valores retornaram zero em ambas as
passagens, com `ROUTING_READS_STABLE=yes`. Isso é compatível com ausência de
rotas configuradas, mas também com readback não implementado nessa faixa.
Extrato informado (`192-routing-user-run.txt`; evidência local não incluída). A consulta posterior de PCI
confirmou o cabeçalho inicial e ausência de driver associado.

## Primeira entrada do módulo DA

O método de metadados do módulo AD (`vtable 0x778728 + 0x28` → `0x1a88b0`)
preenche a segunda tabela de metadados com zeros; o módulo DA
(`vtable 0x7786c0 + 0x28` → `0x1b0a20`) preenche-a com 2 em cada uma das
quatro entradas. `0x1b1e40` posiciona esses dados a partir do índice
`9 + 4 * número_do_módulo`.

Em `0x1b1bf0`, a seleção padrão começa com o contador de origem em 1. A
condição para saída do módulo 0 (`tabela+0x8a`) é falsa para o AD. A condição
do módulo 1 (`tabela+0x92`) é verdadeira para o DA e atribui `1,2,3,4` às
entradas 13..16. Assim a primeira atribuição corresponde à escrita
**registro 0x4d = 1**. Isso fundamenta o candidato ao primeiro par analógico;
a confirmação final do par físico depende do hardware.

## Teste preparado: uma única entrada, com restauração

```sh
sudo ./linux-research/run-dma-tone.sh --route-192
```

Inclui o desmute já testado e o tom de cinco sinais de 128 ms em 48 kHz,
a −40 dBFS, nos canais lógicos 1–2. Não configura clock nem firmware.

1. Revalida identidade, módulos e controles. Exige duas leituras da tabela
   inteira zerada, como a observada. Recusa uma tabela já configurada.
2. Ainda com mute ativo, escreve **somente** banco 1, registro `0x4d`, valor 1.
   Exige duas leituras com `0x4d=1` e todas as outras entradas ainda zeradas.
   Se a escrita for ignorada ou a leitura continuar em zero, não desmuta
   e não inicia áudio; tenta restaurar o valor zero mesmo assim.
3. Desmuta e verifica os controles antes de cada transferência. Só inicia
   áudio após verificar tanto mute quanto roteamento.
4. Para o transporte; tenta restaurar o mute, depois a rota para zero.
   Cada restauração tem no máximo três tentativas e verificação por leitura.
   Perda de ACK não dispensa a tentativa de restauração.

Saída esperada: `route_before=0`, `route_during=1`, `route_after=0`,
`route_restored=Y`, além de mute `2 → 0 → 2` e `mute_restored=Y`.
O flag de rota confirma a leitura da tabela zerada ao término; não comprova
todos os estados internos. O suporte de readback só ficará mais bem sustentado
se a transição `0 → 1 → 0` for observada. Travamento ou falha de comunicação
pode impedir restauração; continua sendo um experimento de kernel.

Validação: compilação `W=1` sem avisos e sintaxe do script; simulações do
helper real para sequência combinada de rota/mute, tabela já configurada,
ACK de rota perdido com escrita aplicada, escrita ignorada, leitura sempre
zero, restauração que falha e lista restrita de comandos. Resultado de
hardware: **o usuário ouviu os sinais**, com `result=0`, rota `0 → 1 → 0`,
mute `2 → 0 → 2`, ambas as restaurações confirmadas e módulo removido.
Isso sustenta o mapeamento testado e o readback de `0x4d`, sem validar
isoladamente todas as outras entradas. Veja
[primeiro áudio confirmado](first-audible-playback.md).
Hashes: `dma-route-build.json`.
