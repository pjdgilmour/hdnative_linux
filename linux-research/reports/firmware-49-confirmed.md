# Firmware 4.9 confirmado e estado após os testes DigiTest

## Evidência visual e relato

Os prints `prefs_protools/192_firmware.png` e `firmware_version.png` foram
examinados diretamente. O primeiro mostra Connector 1, Primary (Channels
1–16), tipo selecionado `192, 192D, 96 I/O`, versão instalada **4.9** e
versão oferecida para atualização **4.9**. Portanto, esse pacote DigiTest
não oferece uma versão diferente para a unidade selecionada; isso não é
uma pesquisa da versão mais recente distribuída pela Avid.

O segundo mostra flash tipo **B**, FPGA do periférico **4.9**, módulos
192 AD / 192 DA / 192 Digital / 192 DA, e a placa HD Native com FPGA
**1.05.0 [0.02.0]**. A versão da placa PCIe é distinta da versão da 192.
O status mostra testes concluídos; não exibe a lista de resultados e,
sozinho, não prova que cada teste tenha passado.

O proprietário confirmou ter executado os diagnósticos do DigiTest e não
ter aberto o Pro Tools depois. A continuidade da alimentação da 192 não
foi confirmada nessa resposta; não classificar este estado como cold boot.
Hashes dos prints e observações estão em [evidência estruturada](post-digitest-state.json).

## Correção do foco de firmware

A hipótese inicial destacou DJAN/3.0 porque o nome corresponde à família
Django. A evidência real aponta agora para **DJII/4.9** como candidato
principal para esta unidade. O executável, cujo hash foi conferido de novo,
contém DJII / ID 104 / idioma 1033, RVA 0x139bc8, 131072 bytes, SHA-256:
`dfc77b16ae2314979823b60c12326e2909528a5c67b5ee187feeeadf32b0ba2f`.

No DigiTest (base PE 0x140000000), a tabela em RVA 0x7a100 tem entradas de
40 bytes. A entrada DJII começa em 0x7a1a0: dados de identificação
`0x000010ab000000d5`, ponteiro para DJII em 0x7a350, ID 104, ponteiro para
`4.9` em 0x7a35c, último campo 0x400. Isso distingue a entrada da DJAN/3.0,
que começa em 0x7a128.

A função RVA 0x39320 referencia essa tabela. O ramo a partir de 0x3939a
percorre suas entradas e consulta uma identificação via 0x2978 → 0x3c270;
recusa retornos 0/0xff, repete a consulta e compara com um byte da entrada
antes de escolhê-la. A seleção também possui outros ramos. A rotina
0x3c270 faz chamadas de controle, não é uma simples leitura inócua de BAR.
Não foi executada ou transcrita para hardware Linux.

O print tipo B/4.9 e a tabela DJII/4.9 são evidências convergentes. Ainda
não foi provado todo o caminho que identifica o chip dessa unidade nem
que o conteúdo da flash instalada seja byte a byte igual ao recurso.
Não tratamos isso como autorização ou necessidade de regravar firmware.

## Leitura atual, sem comandos WRITE ao periférico

Primeiro foi executado `identify-192 --inspect-transport`, que concluiu
com duas passagens estáveis, pré-condições correspondentes e todos os seis
campos de endereços DMA em zero. Não houve acesso DigiLink nesse snapshot.
Depois foi executado `--inspect-routing`, com os seguintes resultados:

| Campo | Após testes ADAT anteriores / restauração | Após DigiTest e retorno ao Linux |
| --- | --- | --- |
| Identidade / versão HD Native | d400 / 01050040 | iguais |
| IDs dos módulos | 14 13 15 13 | iguais |
| 0x11, 0x12, 0x13 | 49, 01, 01 no estado do módulo | 49, 01, 01 |
| Controles 0..3 | 00, 80, 00, 00 | 02, 00, 00, 00 |
| Rotas 0x40..0x5d | perfil Windows preservado | todas zero |
| Bases DMA inativas | 79062000 / 78e60000 / 79464000 | todas zero |

As duas passagens de controles/rotas concordam. PCI COMMAND foi restaurado.
[Saída de leitura](post-digitest-routing.txt). Nenhum teste de áudio ou
módulo foi iniciado sobre esse novo estado. A mudança é observada após o
DigiTest e a reinicialização do host; não atribuímos cada alteração a uma
operação específica do programa sem rastreamento.

O byte 0x49 em 0x11 é compatível com o texto 4.9, mas a regra de decodificação
não foi confirmada aqui. Também não se interpreta 0x12 como prova de lock.

## Próxima investigação para inicialização digital Linux

A diferença 0x00 → 0x80 no controle 1 é uma pista, não uma receita de
inicialização. No DSI já identificado (SHA-256 60af3e71…642f34), a função
RVA 0x1afbc0, ramo de máscara 2, constrói o controle 1:

- 0x1afc2a..0x1afc80 prepara o índice do controle e três campos;
- bits 0–2 vêm de uma transformação do campo de objeto +0x10;
- bits 3–6 vêm do campo +4 de uma entrada de tabela de configuração;
- bit 7 é produzido por comparação de word em +0x24 com 1
  (0x1afce3..0x1afd17);
- 0x1afd25 envia a construção por 0x1a5e80.

É necessário rastrear o significado desses campos e a ordem das chamadas,
as dependências do módulo digital e as condições de sincronismo antes de
adicionar uma escrita de inicialização. Não basta copiar 0x80 do estado
anterior. Carregar uma imagem FPGA e configurar seu funcionamento são
operações distintas; o firmware 4.9 já está presente.

Os drivers e suas listas de escritas não foram modificados neste estudo.
A partição Windows foi acessada em montagem temporária somente leitura;
nenhum executável Windows foi iniciado e nenhum firmware foi extraído
para o repositório ou enviado à 192.
