# 192: medidores OUTPUT ativos, sem som observado

## Resultado do teste longo

Usuário confirmou medidores OUTPUT 1–2 respondendo, mas nenhum som e nenhum
movimento no medidor do DEQ2496. Caminho: saídas analógicas 1–2 da 192 →
entradas 1 e 2 da Yamaha AG06 → DEQ2496. Segundo o usuário, a mesma ligação
funciona no Windows. Não foi informado o estado dos indicadores da AG06.

Extrato do resultado fornecido:

```text
result=0
tx_consumed=9
rx_produced=0
status_sequence=2
tx_mmio_first=9
tx_mmio_last=7211
tx_mmio_changes=500
pci_restored=Y
EXPERIMENT_MODULE_REMOVED=yes
```

Últimas cinco amostras MMIO TX/RX do log informado:
`0x1c1b/0x1c11`, `0x1c29/0x1c1f`, `0x1c27/0x1c1d`,
`0x1c28/0x1c1e`, `0x1c2b/0x1c21`. O encerramento próximo de 7168
é coerente com o limite por polling; 7211 ainda é menor que 8191.
O cabeçalho PCI de 64 bytes após o teste é idêntico ao baseline, sem driver
associado: `pci-after-tone-long.json`. Isso não confirma todos os estados
internos da FPGA ou da 192.

## Caminho de mute recuperado

Análise estática de DSI.dll, base `0x180000000`; evidência preservada em
disassembly (`192-mute-disassembly.txt`; evidência local não incluída). Não foi executado código Windows.

1. Export `SetAllTDMPeripheralsMute`, RVA `0x89100`, chama bus virtual `+0x68`.
   No caminho recuperado, `0x1980b0` aplica mute aos periféricos por `0x88430`.
2. `0x88430` chama virtual `+0x18` do periférico com propriedade **6** e booleano.
3. Na 192, vtable `0x778390`, esse método é `0x1af340`; propriedade 6 segue
   para `0x1a5aa0`. O índice 5 da tabela de bytes em `0x1a5e4c` seleciona
   o destino `0x1a5bc4` na tabela de RVAs em `0x1a5e24`.
4. Esse destino chama `0x1a4ee0`, que mantém um contador de mute no objeto
   base `+0x0c` por `0x80b20`: true incrementa; false decrementa. Dependendo
   do modo DSI, também atualiza o campo `+0x10`.
5. O virtual de atualização `+0xb0` é `0x1afef0`; flag `0x2` inclui a escrita
   do controle em `0x1afbc0` → `0x1af960`.
6. `0x1af960` monta **banco 1, registro 0**. O contador positivo controla
   o bit 1 e, no modo padrão, o bit 7. O bit 6 vem de base `+0x10`, que pode
   acompanhar o mute dependendo do modo. Outros campos de configuração também
   são incluídos: não é uma escrita isolada de um bit.
7. `0x1a5e80` envia ao hose virtual `+0x18`; `0x198d90` → `0x19a190`
   codifica a escrita como `((bank | 0x80) << 16) | (reg << 8) | value`.

Isso sustenta um controle de mute separado do DMA; a análise estática sozinha
não demonstra o estado atual da 192, nem localiza fisicamente o medidor em
relação ao mute/DAC. Uma escrita arbitrária de zero no registro 0 não seria
adequada, porque ele reúne vários campos. O teste preparado abaixo exige
o valor exato 0x02 observado posteriormente e verifica o retorno ao original.

## Consulta executada

```sh
sudo ./linux-research/identify-192 --inspect-192
```

Usa o mesmo transporte de consulta do identificador, com habilitação temporária
de PCI MEMORY e restauração de COMMAND. Exige a identidade/firmware conhecidos,
transporte quieto, slot 0 e módulos `0x13151314`. Não carrega módulo do kernel.
Depois da identificação consulta duas vezes:

- `0x11..0x13`: registros lidos pelo caminho DSI da família Django;
- `0x00..0x03`: **tentativa** de leitura dos controles. O suporte de readback
  destes registros ainda não foi demonstrado nos binários.

Só envia comandos com banco 1 e bit de escrita do periférico desativado,
mais o comando neutro. Não configura clock, mute, roteamento, DMA ou firmware.
Resposta consistente/ACK ou valor zero, isoladamente, não comprova readback
válido dos controles. Em caso de erro, interrompe as consultas de diagnóstico.

Validação: compilação C11 `-Wall -Wextra -Werror`; 14 testes simulados passaram.
Cobrem permissões de registros, ausência do bit WRITE, correlação de respostas,
timeout, limpeza, cancelamento, pré-condições e restauração PCI. A simulação
não comprova suporte de readback do hardware. SHA256 do executável preparado:
`567828ee714687594b4891fd3d3f3298c6e3b702f27dccb5834702c0fe6aed44`.

## Resposta real e teste temporário de mute

O usuário executou a consulta: ambas as passagens retornaram `reg0=0x02`,
`reg1=reg2=reg3=0`, `reg11=0x49`, `reg12=reg13=1`, com resposta e limpeza
bem-sucedidas. Valores informados (`192-controls-user-run.txt`; evidência local não incluída).
O bit 1 ativo é compatível com mute. Naquele momento o suporte de readback
ainda era provisório; o teste seguinte confirmou a transição de ida e volta.

Teste posteriormente executado:

```sh
sudo ./linux-research/run-dma-tone.sh --unmute-192
```

O parâmetro inclui automaticamente o tom longo. O módulo:

- Confere duas vezes a identidade, os módulos e todos os valores acima;
  qualquer diferença impede a escrita de mute e o início do áudio.
- Escreve somente banco 1, registro 0, valor `0x00`, partindo de `0x02`;
  portanto só o bit 1 muda. Consulta o controle duas vezes e exige `0x00`,
  com registros 1–3 ainda zerados, antes de permitir o áudio.
- Confere novamente esses controles antes de cada repetição. Envia os cinco
  sinais já testados, de 128 ms em 48 kHz, a −40 dBFS, nos canais lógicos 1–2.
- Para o transporte, tenta restaurar `0x02` e confirma por duas leituras.
  Tenta a restauração mesmo quando o comando de desmute não recebe ACK,
  porque a interface pode tê-lo aplicado. Há no máximo três tentativas.
- Mantém o procedimento anterior de restauração PCI e drenagem DMA. Mesmo
  se a drenagem falhar, tenta restaurar o mute antes de preservar os buffers.

`control_before`, `control_during`, `control_after` usam valores decimais;
o percurso esperado é **2 → 0 → 2**. `mute_write_attempted=Y` significa que
uma escrita de controle foi enviada. `mute_restored=Y` confirma apenas o
readback do registro 0 original, não todos os estados internos da interface.
Se a escrita ocorreu e a restauração não foi confirmada, o script informa
explicitamente a falha; não repetir o experimento antes de analisar o log.

Esta é a primeira alteração de controle da 192, ainda experimental. Pode
haver transiente ao mudar mute e código de kernel pode travar a máquina;
manter monitoração baixa e trabalho salvo. Não muda taxa, roteamento nem
firmware. Restaurar mute no encerramento significa que a 192 volta ao estado
anterior: não é um dispositivo ALSA nem uma habilitação permanente de áudio.

Validação do helper C usado pelo módulo: precondições, ida/volta, ACK perdido
com escrita aplicada, escrita ignorada, falha de leitura/limpeza, resposta
pendente, tentativas limitadas de restauração e lista restrita de comandos.
Teste simulado passou; compilação do kernel `W=1` sem avisos.

## Resultado do teste de desmute

Saída informada (`dma-unmute-user-run.txt`; evidência local não incluída): `2 → 0 → 2` confirmado por leitura,
`mute_restored=Y`, `pci_restored=Y`, módulo removido. O usuário ouviu apenas
um estalo de comutação da interface; nenhum tom. O cabeçalho PCI de 64 bytes
coincide com o baseline (`pci-after-unmute.json`), sem driver associado.

O resultado `-110` era um falso negativo para **avanço TX**: a decisão no
código consultava apenas `tx_consumed`, que permaneceu em zero no snapshot
DMA, enquanto o MMIO avançou de 9 até 7197. Agora cada transferência exige
mudança de TX MMIO; uma transferência anterior não pode esconder uma posterior
travada. `test_tx_progress.py` executa a função C real com leituras simuladas:
movimento MMIO com snapshot zero passa; índice parado com snapshot positivo
ou progresso anterior retorna timeout. Compilação `W=1` sem avisos.

A correção não altera formato/amplitude nem resolve por si a ausência de som.
A consulta seguinte investiga o [roteamento da 192](192-routing-findings.md).
