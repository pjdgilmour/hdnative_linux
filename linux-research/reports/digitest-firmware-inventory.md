# DigiTest instalado: firmware embutido e evidência disponível

**Atualização pelos prints:** a unidade informa firmware instalado **4.9**,
e o DigiTest oferece **4.9**, com flash tipo B. O recurso DJII/4.9 passa
a ser o candidato principal, substituindo o foco preliminar em DJAN/3.0.
Veja [confirmação e estado após os diagnósticos](firmware-49-confirmed.md).

Origem, somente leitura:
`/media/paulo/Windows/Program Files/Avid/Pro Tools/Pro Tools Utilities/DigiTest/`.
Nenhum executável Windows foi executado, nenhum firmware foi transferido
para hardware e nenhum binário proprietário foi adicionado ao repositório.

O recurso VS_VERSION_INFO do DigiTest.exe informa **26.4.1.179**. SHA-256:
`f94a758decd6ab3776c4647e9e685e9e06c796edfc930616d0e9cde23e8d4f70`.
A DSI.dll local tem o mesmo hash da cópia já estudada:
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`.
O BerlinTests.dll tem SHA-256:
`f394874c4e6bb8a485c2240d6dd6c5e0546f384dc24ab2b4f9fff694a0d71f39`.

## Recursos relevantes

A árvore de recursos PE contém imagens binárias nomeadas, incluindo:

| Tipo / ID / idioma | RVA | Bytes | Rótulo associado na tabela |
| --- | --- | ---: | --- |
| DJAN / 102 / 1033 | 0x10e5d8 | 118430 | 3.0 |
| DJII / 104 / 1033 | 0x139bc8 | 131072 | 4.9 |
| MLGN / 103 / 1033 | 0x12b478 | 59215 | não interpretado aqui |

O recurso DJAN tem hash
`85e5f6147f944642defa5e37f78af8a84171aaea4bff22d7ad282b1d078df406`.
A entrada de tabela em RVA 0x7a130 contém ponteiro para a string UTF-16
DJAN em 0x7a318, ID 102, e ponteiro para string ASCII `3.0` em 0x7a324.
Para DJII, a entrada equivalente está em 0x7a1a8 e o rótulo `4.9` em 0x7a35c.
A base PE é 0x140000000. [Inventário de recursos e hashes](digitest-resources.json).

Strings do executável incluem CDjangoFlasher, CDjangoFlasher_FpgaBalance,
CDjangoFlasherFactory e DjangoFlasherThread, além da aba Audio I/O Firmware
e textos que identificam a família 96/192/192-Digital. Isso torna DJAN um
candidato relevante para a 192 (cujo objeto DSI é CDjangoPeripheral).
Ainda falta seguir a seleção exata por modelo/revisão na rotina do flasher;
não usar o nome do recurso sozinho para decidir gravar firmware.

O rótulo **3.0** é metadado do pacote; não é leitura da versão instalada,
nem verificação da versão mais recente distribuída pela Avid. A versão
0x01050040 lida na BAR é da HD Native e não identifica o firmware da 192.

## Arquivos separados de outros equipamentos

Foram encontrados SYNCHDFirmware221.sy5 e SYNCHDFirmware221.syh em SYNC HD
Firmware, e SyncXFirmware_1_2_1_5.sy6 / SyncXFirmware_1_2_2_4.sy6 em SYNC X
Firmware. Esses arquivos pertencem às famílias SYNC indicadas, não são
identificados como imagens da 192. Não confundir suas versões com a 192.

## Utilidade para o projeto

O executável oferece mais uma fonte primária local para estudar a seleção
de imagens, identificação/versão do periférico e transporte de comandos.
A DSI compartilhada evita duplicar investigação já feita. A imagem binária
pode conter lógica FPGA e não necessariamente código de CPU diretamente
desmontável; encontrar o firmware não fornece automaticamente o protocolo
de clock, SRC ou inicialização digital. O próximo trabalho deve localizar
as chamadas do flasher e relacioná-las ao modelo antes de atribuir semântica.


## Reprodução do inventário, sem executar o DigiTest

```sh
python3 linux-research/tools/inspect_digitest_resources.py \
  "/media/paulo/Windows/Program Files/Avid/Pro Tools/Pro Tools Utilities/DigiTest/DigiTest.exe"
```

O leitor valida limites da árvore PE, recusa ciclos e calcula hashes dos
recursos em memória. Reproduziu todos os registros do inventário acima.
Não extrai imagens nem grava qualquer arquivo ou dispositivo.
