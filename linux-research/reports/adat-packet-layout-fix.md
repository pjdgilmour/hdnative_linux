# Correção do mapeamento DMA dos canais 9–10

## Resultado E1eorI

O ensaio `adat-test-E1eorI` completou 10 s, um START/STOP, zero XRUNs e
last_error=0. Controles/rotas Windows foram preservados; módulo removido,
cabeçalho PCI restaurado e placa desvinculada. O áudio foi corretamente
rejeitado pelo analisador. Esse resultado não aprova ADAT Linux.

A captura de 480000 frames apresentou:

- canal 1 somente com valores brutos `0x000000` (475038 vezes) e
  `0x800000` (4962 vezes);
- byte baixo do canal 2 zero em todas as 480000 amostras;
- incremento do canal 2 exatamente 256, módulo 2^24, nas **479999
  transições**, inclusive durante o silêncio do padrão TX.

O segundo valor é compatível com bytes de contador interpretados como
PCM. SHA256 do raw:
`da91e11540d75c4b03a1a6a148c34ad2a3d3cc884778759f0fd626a181cc5d4f`.
Não reproduzir essa captura nos monitores.

## Erro de implementação

O modo Windows usou incorretamente `4 + 8*3 = 28` para o primeiro canal
do segundo grupo. Essa extrapolação ignorou os grupos de 32 bytes, já
registrados em `audio-transport.md`. Foi um erro do código preparado aqui,
não evidência de defeito da 192 ou do cabo. Os testes anteriores também
usavam 28 na referência, validando consistência interna em vez da fronteira
real do pacote; por isso não detectaram o erro.

O layout é de oito grupos de 32 bytes em cada frame de 256 bytes. Cada
grupo tem os dados PCM no byte 4 e até oito amostras de três bytes:

| Canais lógicos | Bytes PCM no frame |
| --- | --- |
| 1–8 | 4..27 |
| 9–16 | 36..59 |
| 17–24 | 68..91 |
| ... | ... |
| 57–64 | 228..251 |

Para um índice de canal zero-based `c`, o offset é
`32*(c/8) + 4 + 3*(c%8)` com divisão inteira. O par 9–10 ocupa bytes
**36..41**. Os bytes 28..33 lidos pelo ensaio anterior atravessam a região
entre grupos, fora das amostras PCM. A transmissão também usava o offset
errado. O arquivo estéreo já extraído não contém os seis bytes corretos;
não é possível recuperar essa gravação apenas mudando o decoder do WAV.

## Conferência no binário da Avid

DirectIO.dll 2026.4.1 local, SHA256
`5f8c6ecb37cdefda0039ba3f7ecafc061292b99257a4e3f2c10f1044c74bafc0`.
RVAs relativos à base 0x180000000:

- TX: 0xfbb8..0xfbbd limita a oito amostras por grupo;
  0xfbf5 posiciona em +4, 0xfbf9 multiplica frame por 256;
  0xfc4d avança três bytes por amostra, 0xfc56 avança 32 por grupo.
- RX: 0xffa2 avança 256 bytes entre frames, 0xffd1 avança três por
  amostra e 0xffe2 avança 32 por grupo.

A geometria foi conferida diretamente nessas instruções, além da
consistência do contador observado fora do payload.

## Mudança e validação

`native_adat_ring.h` passa a definir a geometria agrupada, e o driver usa
canal zero-based 8 no modo Windows, ou 0 no perfil original. A alteração
corrige TX e RX. A tabela dos 64 offsets do teste é independente da fórmula
usada pelo driver; há um frame artificial com metadados nos bytes 28..33 e
amostras conhecidas em 36..41. O extrator deve ignorar os primeiros.

Uma contraprova offline com a antiga fórmula linear deliberadamente
reintroduzida falhou na asserção de fronteira. A versão corrigida passou
por essa prova, pelos testes de payload/zeros nos demais canais, 4,096
milhões de frames com wraps, e por toda a suíte ADAT de DMA, controles,
cleanup e aceitação. Build W=1 para o kernel atual.

Os critérios do analisador não mudaram. O modo Windows continua bloqueando
todos os WRITE ao periférico, preservando o controle 1=0x80 e as 30 rotas.
O duplex analógico e o helper compartilhado permaneceram intactos.
Nenhum módulo foi carregado durante essa revisão.

Esta correção explica a extração inválida de E1eorI; não comprova a causa
da distorção anterior de Q0e1ud, que usava o primeiro par no byte 4.
Ainda é necessária uma captura física com o offset correto:

```sh
sudo ./linux-research/run-adat-test.sh enclosure 1 1 --windows-state
```

Manter a 192 ligada, OUT → IN nos ópticos do gabinete, 48 kHz, monitores
mutados e trabalho salvo. Código experimental de kernel. Enviar o log
completo; não escutar o WAV se o analisador voltar a rejeitá-lo.
