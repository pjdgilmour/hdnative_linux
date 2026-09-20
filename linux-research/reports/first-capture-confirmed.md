# Primeira captura analógica 1–2 confirmada

O usuário confirmou sucesso com `run-capture-test.sh --loopback`, usando o
teste de saída analógica 1 → entrada 1 e saída 2 → entrada 2 da 192 I/O.
Sessão local: `capture-test-pYSEYe`. O padrão de 750 Hz no canal 1, 1500 Hz
no canal 2 e ambos na última etapa correspondeu à análise automática.

## Resultado e conferência

- WAV e RAW: **480000 quadros estéreo**, exatamente 10 s nominais a 48 kHz,
  PCM de 24 bits em três bytes; conteúdo de áudio idêntico entre os arquivos.
- Análise refeita do RAW: igual ao JSON salvo, `loopback_pattern_matched=true`.
- Uma partida/parada, **zero XRUNs**, `last_error=0`, 29 voltas do anel RX.
- Driver recebeu 480299 quadros e registrou 480256 consumidos pelo ALSA;
  o arquivo contém os 480000 solicitados. Os quadros adicionais no fim da
  sessão não demonstram perda nem corrupção do arquivo.
- TX avançou 480309 quadros. Maior intervalo de polling: 1604 µs;
  esse número não mede a latência de ida e volta.
- Pico de entrada: canal 1 **−38,92 dBFS**, canal 2 **−39,95 dBFS**;
  nenhum sample próximo de saturação segundo o limiar do analisador.
  A diferença de aproximadamente 1 dB é uma observação deste caminho;
  o teste não determina sua causa nem constitui calibração.
- Mute e ambas as rotas restaurados; remoção do módulo e PCI sem driver
  registrados no log. Os 64 bytes dos cabeçalhos PCI antes/depois são iguais.
- Fontes, módulo e ferramentas conferidos contra o manifesto de build.

A rota `banco 1, 0x41=9`, inferida para AD 1–2 → computador, agora tem
confirmação funcional neste ensaio de loopback. A rota de saída `0x4d=1`
e o mute `controle 0: 2 → 0 → 2` mantiveram o comportamento esperado.

O módulo gera o sinal TX internamente e expõe somente captura ALSA. Este
ensaio confirma transporte de saída e entrada simultâneo nesse modo; ainda
**não valida streams ALSA independentes de reprodução e captura**, captura
nos aplicativos, estabilidade prolongada, taxas/canais adicionais, qualidade
metrológica ou partida a frio. Não houve alteração no módulo de reprodução.

[Resumo verificável e hashes](first-capture-validation.json).
[Como repetir o teste](capture-prototype.md).
Os WAV/RAW e logs brutos ficam na pasta local da sessão, ignorada pelo Git.
