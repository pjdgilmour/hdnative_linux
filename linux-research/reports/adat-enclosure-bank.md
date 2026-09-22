# ADAT do gabinete: par 1–2 confirmado e expansão do ensaio

**Atualização:** a sequência completa passou no hardware; veja
o [registro dos oito canais e duas contraprovas](adat-enclosure-confirmed.md).
O texto abaixo conserva o histórico de preparação deste teste.

## Resultado físico confirmado em 21/09/2026

Sessão `adat-test-UYG7iv`, executada pelo proprietário com o cabo óptico
OUT → IN do gabinete e a 192 mantida ligada após a configuração Windows.
O perfil foi conferido sem comandos WRITE ao periférico. O módulo usado
teve SHA-256 `edd0c37d79cc4811632021cd6a076b3be921a31c5364e29bcdb8b73936cf5ed0`.

- 480000 frames gravados, estéreo S24_3LE, 48 kHz, 10 segundos.
- Tons 750/1500 Hz identificados nos canais corretos e nas três janelas.
- Picos −40,00 dBFS nos dois canais, RMS −47,02 dBFS e nenhum clipping.
- Zero XRUNs e last_error=0; max_poll_us=1625.
- Controles e rotas preservados; módulo removido, PCI restaurado e livre.
- `ADAT_PAIR_TEST_PASSED=yes`.

O hash do arquivo raw e os snapshots PCI foram conferidos localmente:
`188cc270af7138e2d2f3a3d6959140602c6cf8cc7f44dfebfae7cf6ffbda7933`.
Esse resultado confirma o loopback do par físico 1–2 informado no gabinete,
utilizando canais lógicos 9–10 e bytes 36–41. Não estabelece inicialização
a frio, oito canais simultâneos, bit-perfect ou funcionamento do óptico do
módulo. Os resultados e arquivos originais não foram modificados.

## Expansão para quatro pares, mantendo o mesmo perfil

As 30 rotas observadas no Windows continuam sendo exigidas integralmente;
não houve flexibilização dos valores esperados. Agora a seleção dos pares
muda os offsets TX/RX nos buffers Linux, independentemente por direção:

| ADAT físico | Transporte lógico | Bytes PCM no frame | Registro RX / seletor | Registro TX / seletor |
| --- | --- | --- | --- | --- |
| 1–2 | 9–10 | 36–41 | 0x45 / 25 | 0x59 / 5 |
| 3–4 | 11–12 | 42–47 | 0x46 / 26 | 0x5a / 6 |
| 5–6 | 13–14 | 48–53 | 0x47 / 27 | 0x5b / 7 |
| 7–8 | 15–16 | 54–59 | 0x48 / 28 | 0x5c / 8 |

Somente o primeiro par tem resultado físico aprovado neste registro.
O arquivo de perfil registra `transport_channels` para RX e
`output_transport_channels` para TX; a aceitação exige ambos coerentes
com os pares solicitados. Os relatórios antigos mantêm seu esquema original.

## Próximo comando

```sh
sudo ./linux-research/run-adat-bank-test.sh enclosure --windows-state
```

Manter a 192 ligada, em 48 kHz, mesmo cabo OUT → IN do gabinete, aplicativos
fechados, monitores mutados e trabalho salvo. Não reproduzir nem monitorar
as capturas durante o teste. São seis gravações de 10 segundos:

1. TX 1–2 / RX 1–2: retorno positivo de controle.
2. TX 3–4 / RX 1–2: isolamento.
3. TX 1–2 / RX 3–4: isolamento inverso.
4. TX 3–4 / RX 3–4: retorno positivo.
5. TX 5–6 / RX 5–6: retorno positivo.
6. TX 7–8 / RX 7–8: retorno positivo.

A sequência para na primeira falha. Cada etapa valida e preserva o mesmo
perfil, usa buffers DMA próprios do Linux, remove o módulo e confere a
restauração PCI. Não muda clock, ADAT/SRC, mute ou rotas da 192.
A saída final aprova apenas os testes em pares e as duas contraprovas;
não equivale a isolamento de todas as combinações ou operação simultânea.

## Verificação antes da execução física

Build W=1 para 6.12.107+deb13-amd64, testes de controle, lifecycle, DMA
residual e análise aprovados. O teste de transporte usa as macros reais
do driver e offsets de referência independentes: cobre o legado, as 16
combinações TX/RX, zeros nos demais canais e 34,816 milhões de frames RX
simulados com voltas do buffer, ASan e UBSan. Todos os 65536 comandos
WRITE possíveis são recusados em cada combinação de pares Windows.

A sequência de shell foi exercitada com um substituto sem hardware:
confere os seis comandos, propagação da opção, parada na segunda etapa
quando ela falha e recusa de argumentos inválidos. Nenhum módulo foi
carregado durante essas verificações. O módulo duplex validado e seu
helper de captura compartilhado permanecem inalterados.
