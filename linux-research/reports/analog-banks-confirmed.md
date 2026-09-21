# Bancos analógicos: 16 saídas e 8 entradas testadas por pares

Os dois bancos completaram o loopback analógico a 48 kHz/S24_3LE com tons
de −40 dBFS. O proprietário informou o DB25 ligando primeiro saídas 1–8
às entradas 1–8 e depois saídas 9–16 às mesmas entradas. Cada execução
usa somente dois canais lógicos de transporte, remapeados ao par escolhido.

| Saídas | Entradas | Sessão | Picos capturados (dBFS) |
|---|---|---|---|
| 1–2 | 1–2 | U9pDts | −38,92 / −39,95 |
| 3–4 | 3–4 | R5p8FP | −40,24 / −39,88 |
| 5–6 | 5–6 | HIR9Qi | −39,87 / −40,07 |
| 7–8 | 7–8 | RMdHhM | −39,93 / −39,94 |
| 9–10 | 1–2 | pGhHm1 | −38,99 / −39,99 |
| 11–12 | 3–4 | xUuQ7j | −39,97 / −39,86 |
| 13–14 | 5–6 | igzqIX | −39,88 / −40,06 |
| 15–16 | 7–8 | gQk6lP | −39,97 / −39,95 |

As sessões estão em `reports/channelmap-test-<identificador>/` (artefatos
locais ignorados no Git). Todas retornaram `ANALOG_PAIR_TEST_PASSED=yes`,
correspondência do padrão, `xruns=0`, `last_error=0`, mute/rotas restaurados,
módulo removido, cabeçalho PCI restaurado e dispositivo desvinculado.
Os quatro arquivos raw do banco 2 tiveram os SHA256 conferidos contra seus
`session.json`. O relatório agregado não apresenta canais analógicos pendentes.

No banco 2, o destino de saída variou de `0x55` a `0x58` (valor 1), enquanto
`0x41` selecionou fontes de entrada 9 a 12. No banco 1, os destinos foram
`0x4d..0x50`. A contraprova anterior [diferenciou os caminhos selecionados
1–2 e 3–4](analog-pair-isolation-confirmed.md) por retornos positivos e
seleções cruzadas com ausência dos tons.

## LEDs e alcance do resultado

O proprietário observou apenas os LEDs físicos 1–2 nas duas direções,
inclusive no teste do segundo módulo de saída. Como os canais de transporte
permaneceram 1–2, isso é compatível com medidores associados aos canais
lógicos. O ponto de medição não foi identificado diretamente; a hipótese
não deve ser apresentada como especificação confirmada do hardware.

A validação cobre retorno dos tons sob as rotas selecionadas e o cabeamento
informado. Não é verificação independente da numeração de cada pino DB25,
nem medição de THD, crosstalk de todos os pares, latência ou precisão do clock.
Não foram testados todos os canais simultaneamente; o driver dos aplicativos
permanece estéreo. Não houve mudança de firmware, clock ou calibração.

## Próximo passo: ADAT

O usuário dispõe de ADAT. Antes do teste óptico, obter o estado inicial
com todos os drivers Avid parados:

```sh
sudo ./linux-research/identify-192 --inspect-digital
```

O diagnóstico apenas consulta identidade/controles candidatos e restaura
PCI COMMAND; não configura ADAT nem inicia áudio. Ainda é necessário
validar a seleção de formato do módulo DIGITAL I/O e o loopback óptico.
