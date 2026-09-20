# Consulta de identificação DigiLink — experimento de 20/09/2026

**Estado:** identificação real bem-sucedida, conforme saída enviada pelo
usuário em 192-id-user-run.txt (`192-id-user-run.txt`; evidência local não incluída). Slot 0 respondeu
família 1, módulos `14 13 15 13`, combinação `0x13151314`, enum DSI 16:
**192 I/O**. Cinco consultas e neutralizações retornaram sucesso. A
configuração PCI foi restaurada. Áudio ainda não foi transmitido.

Fonte: `DIO_64/DSI.dll` 26.4.1.179, SHA256
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`.
O arquivo da instalação Pro Tools e o extraído do pacote são idênticos.
Endereços abaixo são RVAs; somar `0x180000000` para obter os endereços do
disassembly preservado (`digilink-disassembly.txt`; evidência local não incluída). Nomes sem símbolos são
interpretações baseadas no código e no RTTI, não documentação pública Avid.

## Cadeia do caminho HD Native

1. Objeto criado em `0x193a90` tem vtable `0x7738d8`, RTTI **CGreenCard**.
   Portanto, neste binário, o nome Green não implica uma placa DSP antiga.
2. Método `0x1941b0` fornece `card+0xb0` a `0x0819a0`, que chama
   `0x196a90` para construir um nó. Tipo interno `0x805`, atribuído em
   `0x1941d0`, seleciona construtor `0x19b1d0`.
3. Esse construtor instala vtable **CGreenTDM2Node** `0x774580`, interface
   de consulta `0x774770` no subobjeto `+8`, e obtém **IBalance** via
   `0x0803e0`, armazenando-o em `node+0x80`.
4. Método de enumeração `0x193e80` chama `0x1968a0` sobre esse nó.
   Obtém sua interface pela virtual `+0xb0` (`0x199670`, retorna `node+8`).
5. Predicado virtual `+0x48` encaminha via `0x19b340` a IBalance `+0x48`,
   implementado em `0x19c830`: exige objeto inicializado e pelo menos um dos
   quatro bits baixos de **BAR0+0x70004**. Isto não identifica um modelo.
6. Enumeração `0x196950` lê **banco 1, registro 0x10**, por posição, através
   da interface virtual `+0x10`. Só usa o byte devolvido após sucesso.

## Comando, resposta e espera

Interface `0x198d80` encaminha a `0x199ad0`, que codifica:

```text
comando = ((banco << 8) | registro) << 8
identificação da família = 0x011000
```

Virtual do nó `+0x1e0` = `0x19b370`; transação em `0x19b760`:

- Envia comando pela virtual do nó `+0xc0` (`0x19b910`), que chama
  IBalance `+0x60` = **0x19f6c0**.
- Lê resposta pela virtual `+0xc8` (`0x19b4b0`), que chama
  IBalance `+0x58` = **0x19e7b0**.
- Compara os bits `23:8` da resposta com os do comando. O byte `7:0`
  contém o valor devolvido. Há espera limitada e retorno de erro.
- Após sucesso, `0x19b370` envia **comando zero** e aguarda sua resposta.

As duas implementações IBalance usam tabelas com posições **0 a 7**:

| Operação | Offset BAR0 | Máscara |
|---|---|---|
| Enviar | `0x7001c + 4*posição` | Preservar bits `31:24`, substituir `23:0` |
| Receber | `0x70040 + 4*posição` | Usar bits `23:0` |

A posição lógica ainda não foi correlacionada experimentalmente às duas
portas físicas e aos encadeamentos. O programa imprime `slot`, não uma
porta física suposta.

O programa Linux escolhe timeout de **100 ms** por espera e pausa de
**50 µs**, também com limite de iterações. O código Windows usa constantes
100000 e 50 em seus serviços de tempo; a unidade desses serviços ainda não
foi provada. Assim, os tempos Linux são parâmetros deste experimento.

## Como distinguir a 192 de uma 96

Família bruta **1** seleciona `0x1ada80` na fábrica `0x1a4160`.
RTTI das vtables `0x778358` e `0x778390`: **CDjangoPeripheral**.
Esse nome sozinho não identifica a 192.

Inicialização da família em `0x1ae270` lê registros **0x14..0x17**, banco 1,
através de `0x1a4e80`. Combina os quatro bytes em ordem little endian e
escolhe enum interno 15, 16 ou 17. `0x1205b0` retorna esse enum; `0x0873d0`
o copia para o descritor usado por `0x087b10`.

Na tabela desta última rotina, **16 e 17** apontam ao trecho `0x087bbe`,
que usa a string **192 I/O**. O enum 15 segue outro trecho, `0x087b98`.
O teste só declara a 192 após família 1, quatro leituras com resposta
correlacionada, retorno neutro confirmado e enum 16/17. Os valores exatos
das combinações aceitas estão em `tools/digilink_query.h`.

A rotina Windows depois configura taxa/estado e consulta outros registros.
Essas etapas foram excluídas deste teste de identificação.

## Limites e execução

Executável: `linux-research/identify-192`; fontes `tools/identify_192.c` e
`tools/digilink_query.h`. Compilação:

```sh
gcc -std=c11 -O2 -Wall -Wextra -Werror -o linux-research/identify-192 linux-research/tools/identify_192.c
sudo ./linux-research/identify-192 --identify-192
```

- Recusa PCI/subsystem diferente de `11af:ef80`, BAR diferente de 4 MiB,
  driver associado, bus mastering ativo, identidade diferente de `0xd400`
  ou versão diferente da observada `0x01050040`.
- Habilita temporariamente PCI COMMAND.MEMORY e restaura/verifica COMMAND.
  Usa lock consultivo no arquivo de configuração; isso não impede outro
  software que ignore esse lock de acessar o dispositivo.
- Lê estado e os oito pares comando/resposta. Se o predicado de presença
  for falso, termina sem escrever no BAR.
- Só emite leituras do banco 1 para `0x10` e `0x14..0x17`, e comando neutro.
  Recusa transação se já houver comando ou cabeçalho de resposta pendente.
- Em timeout também tenta comando neutro; interrompe a varredura se não
  consegue confirmar a neutralização. Preserva o byte superior do registro.
- Não reproduz a inicialização CBalance, não configura clock, não aciona
  reset, não habilita DMA/IRQs/áudio e não grava firmware.
- SIGINT/TERM/HUP solicitam saída com neutralização. SIGBUS/SEGV restauram
  somente PCI: não é seguro repetir MMIO após uma falha de acesso.
  SIGKILL, falha do sistema e perda de energia não permitem garantir limpeza.

O estado atual pode não estar inicializado para comunicação. Ausência de
resposta não prova cabo defeituoso, interface ausente ou incompatibilidade.
Identificação bem-sucedida também não prova transporte de áudio funcional.

Saída `result`/`cleanup`: 0 sucesso, 1 timeout, 2 ocupado, 3 pedido recusado,
4 cancelado, 5 falha de neutralização. Código do processo: 0 = identificou;
1 = erro de acesso/pré-condição; 2 = uso inválido; 3 = não identificou;
4 = restauração PCI falhou; 5 = neutralização não confirmada;
128+sinal = interrompido.

## Verificação realizada

`python3 linux-research/tools/test_digilink.py`: **11 testes passaram**.
Incluem simulador de respostas para oito posições, correlação de cabeçalho,
timeout de leitura e neutralização, cancelamento, resposta antiga, lista
fechada de comandos e distinção de modelos. Integração usa arquivos PCI/BAR
simulados: restauração byte a byte, recusas, falhas injetadas e sinal fatal.
Nenhum desses testes acessa hardware real.
