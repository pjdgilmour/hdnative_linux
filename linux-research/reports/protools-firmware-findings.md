# Arquivos adicionais do Pro Tools 2026.4.1

Inspeção local em 20/09/2026, sem executar programas Windows ou acessar hardware.

Origem:
`/home/paulo/Downloads/Pro Tools_2026.4.1/Program Files 64/Avid/Pro Tools/`

## Resultado

Foram encontrados os firmwares D400 referenciados pelo driver. A relação
foi verificada pelo identificador interno, checksum do conteúdo e registros
da tabela de firmware na DSI.dll; não depende somente dos nomes dos arquivos.

| Arquivo | Bytes | Alvo no cabeçalho | MD5 do payload | Registro correspondente na DSI (RVA) |
|---|---:|---|---|---|
| ProToolsNative_FW_d400.bin | 2.119.010 | `0xd400` | `0611f1d6ca70f81025ccd1c08ca0f05b` | `0x9af490` |
| ProToolsNative_FW_MSI_d400.bin | 2.119.010 | `0xd400` | `44cdde475c2f8478440178366be46649` | `0x9af4b8` |

O identificador D400 coincide com `BAR0+0x00 = 0x0000d400`, obtido no teste
real da HD Native PCIe. Os dois arquivos são diferentes apesar do mesmo
tamanho e dos mesmos bytes `01 05 00 00 00 00` no trecho de metadados do
cabeçalho. A tabela da DSI também os distingue por um campo adicional:
`0x00000000` para a imagem normal e `0x00020000` para a imagem denominada MSI.
A regra completa de seleção entre as variantes ainda não foi reconstruída.

Não se concluiu qual imagem está gravada atualmente na placa. O registrador
de versão `0x01050040` não é um hash do firmware e, isoladamente, não resolve
essa pergunta. Não há necessidade de atualização demonstrada pelos testes.

## Formato observado e validação

Nos 11 arquivos `.bin` da raiz dessa pasta, foi encontrado o mesmo envelope:

| Offset | Conteúdo observado |
|---|---|
| `0x00` | Valor de 32 bits little-endian `1`; semântica não confirmada |
| `0x04` | Bytes ASCII `taem`, inteiro little-endian `0x6d656174` |
| `0x08` | 16 bytes de MD5 |
| `0x18` | Identificador de alvo de 16 bits little-endian |
| `0x1a`–`0x1f` | Metadados preservados como bytes; não tratar como versão completa sem analisar o leitor |
| `0x20` em diante | Conteúdo cujo MD5 coincide com o campo do cabeçalho |

Todos os 11 checksums internos conferem. Isso é uma checagem de consistência,
não uma assinatura de autenticidade.

A rotina DSI RVA `0x1ca0e0` compara a marca em `buffer+4` com `0x6d656174`.
Quando a encontra, avança o buffer em 32 bytes e subtrai 32 do tamanho.
Ela calcula/verifica um digest quando o argumento correspondente é fornecido.
Há caminhos explícitos para PCI device IDs `ef70`, `ef80` e `ef88`.
O caminho `ef80`/`ef88` escreve em BAR+`0x54` e usa a região +`0x80000` ao
encaminhar o payload a `0x1c9f10`. Isso é evidência estática do caminho de
programação, não uma sequência de atualização validada para execução Linux.
O disassembly recortado está em `firmware-loader-disassembly.txt`.

## DIO_64

Os **52 arquivos** de DIO_64, incluindo as **48 DLLs**, coincidem byte a byte
com suas contrapartes extraídas do MSI do HD Driver. As comparações foram
feitas por SHA-256. Portanto, a análise anterior da DSI.dll e seus RVAs
continua aplicável. Agora há também uma cópia persistente em Downloads, sem
depender da extração temporária em `/tmp`.

DSI.dll SHA-256:
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`

Não foram encontrados arquivos de código-fonte `.h`/`.cpp` ou símbolos `.pdb`
na busca realizada na árvore do pacote Pro Tools.

## Outros arquivos

- `ProToolsNative_FW_d410.bin` e `d411.bin`: alvos internos D410 e D411,
  diferentes do D400 observado na placa. O script não encontrou registros
  correspondentes por digest+nome na tabela analisada da DSI.
- `BowmanFPGA*D700.bin`: alvo D700, associado ao caminho Thunderbolt já
  identificado na análise anterior.
- `Tophat*D200.bin` e `Ritz*D303.bin`: outros alvos; não confundir com D400.
- `TIShell.out`, `TIShellMiX.out` e `TIShellMiX_192.out`: executáveis ELF32
  para TI TMS320C6000, com símbolos e informações de depuração. Em particular,
  `TIShellMiX_192.out` tem 1.899 entradas na tabela de símbolos. A presença
  de `192` no nome não demonstra que seja firmware da interface 192 I/O.
  Seus nomes aparecem em `TIShellMgr.dll`; a relação com o caminho Native
  ainda não foi demonstrada.

## Impacto no projeto

Os arquivos esclarecem a correspondência entre driver e imagens de firmware
e permitem estudar o formato/caminho de programação. Não substituem a lógica
host que falta: inicialização DigiLink, enumeração da 192, clock, DMA e IRQs.
A placa já respondeu usando o firmware existente; a próxima etapa continua
sendo reconstruir sua comunicação com a 192, não programar uma imagem apenas
porque ela foi encontrada.

Inventário completo com hashes: protools-inventory.json (`protools-inventory.json`; evidência local não incluída).
Gerador: [inventory_protools.py](../tools/inventory_protools.py).
