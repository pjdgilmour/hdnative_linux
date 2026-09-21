# Pares analógicos 1–2 e 3–4: retornos e isolamento cruzado

A comparação foi concluída com as duas execuções individuais restantes.
O cabeamento informado foi um DB25 analógico em loopback, saídas 1–8 para
entradas 1–8, mantido durante os testes. O transporte de áudio continuou nos
canais lógicos 1–2 a 48 kHz/S24_3LE.

| Saídas → entradas selecionadas | Sessão | Avaliação do sinal |
|---|---|---|
| 1–2 → 1–2 | channelmap-test-eYBk4q | padrão dos tons reconhecido |
| 3–4 → 1–2 | channelmap-test-fbJprf | RMS estável −112,78 / −105,97 dBFS; reanálise v2 aprovada |
| 1–2 → 3–4 | channelmap-test-7j2dI0 | RMS estável −107,07 / −112,93 dBFS; isolamento aprovado |
| 3–4 → 3–4 | channelmap-test-wDLeNh | padrão dos tons reconhecido; picos −40,24 / −39,88 dBFS |

A segunda sessão ficou originalmente reprovada por incluir um transiente
inicial no RMS. Seu `session.json` original continua com `passed=false`.
A [revisão separada](isolation-startup-review.json) registra o resultado
recalculado sobre a mesma gravação; não houve nova execução dessa etapa.
As duas últimas sessões já usaram a análise v2 (RMS em 1–9 s, tons abaixo
de −80 dBFS nas janelas de isolamento, proteção contra clipping em todo o
arquivo). As quatro condições foram reunidas de execuções distintas,
não de uma execução completa do script em lote.

Cada execução registrou `xruns=0`, `last_error=0`, mute e rotas restaurados,
módulo removido, cabeçalho PCI restaurado e dispositivo desvinculado. Os
hashes dos arquivos raw foram conferidos contra os respectivos relatórios.

## Conclusão e limites

Mudar somente a seleção de saída suprimiu o retorno no primeiro par de
entrada. Mudar somente a seleção de entrada também suprimiu o retorno do
primeiro par de saída. Selecionar o segundo par nas duas direções recuperou
os tons. Isso diferencia os dois caminhos selecionados e afasta a hipótese
de que as quatro combinações estivessem sempre usando o mesmo par.

O proprietário observou apenas os LEDs físicos 1–2 de entrada e saída.
Os medidores acompanharem os canais lógicos é compatível com o resultado,
mas o ponto exato de medição não foi confirmado. Os conectores físicos são
identificados pelo roteamento reconstruído e pelo cabeamento informado;
não houve medição individual dos pinos do DB25. Também não se trata de uma
medição completa de crosstalk ou de funcionamento multicanal simultâneo.

Os pares 5–6 e 7–8 já tiveram retorno positivo no banco 1, mas não foram
incluídos nessa contraprova cruzada. O banco 2 (saídas 9–16) e os canais
digitais ainda aguardam testes. O driver para aplicativos continua estéreo.
