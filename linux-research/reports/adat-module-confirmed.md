# ADAT do módulo DIGITAL I/O: oito canais confirmados em pares

O cabo foi movido pelo proprietário para OUT → IN do módulo. Sem nova
passagem pelo Windows, o agente executou o primeiro par e depois os outros
15 cruzamentos com sudo autorizado, usando `--module-route`.

Todos os quatro retornos e 12 isolamentos passaram em 48 kHz/S24_3LE,
10 segundos por captura, sem XRUNs, clipping ou erros. Controles e duas
rotas restaurados, módulo removido e PCI restaurado/desvinculado em todas
as sessões. Os arquivos raw foram conferidos por tamanho e hash; as 12
capturas cruzadas são inteiramente zero. Ao final confirmou-se também a
ausência de módulo carregado e vínculo PCI.

| Par TX | Par RX | Sessão | Resultado |
| --- | --- | --- | --- |
| 1 | 1 | adat-test-zOLhyW | tons corretos |
| 1 | 2 | adat-test-yQ2IRK | zero em toda a captura |
| 1 | 3 | adat-test-GXStY7 | zero em toda a captura |
| 1 | 4 | adat-test-31WFSv | zero em toda a captura |
| 2 | 2 | adat-test-zevMkX | tons corretos |
| 2 | 1 | adat-test-PupH0a | zero em toda a captura |
| 2 | 3 | adat-test-mdOGET | zero em toda a captura |
| 2 | 4 | adat-test-8diZc2 | zero em toda a captura |
| 3 | 3 | adat-test-m82kOV | tons corretos |
| 3 | 1 | adat-test-WtECaz | zero em toda a captura |
| 3 | 2 | adat-test-PHtgF0 | zero em toda a captura |
| 3 | 4 | adat-test-BQDz0u | zero em toda a captura |
| 4 | 4 | adat-test-DUONt1 | tons corretos |
| 4 | 1 | adat-test-9mE96F | zero em toda a captura |
| 4 | 2 | adat-test-O18KPX | zero em toda a captura |
| 4 | 3 | adat-test-dXG5Rz | zero em toda a captura |

Par 1 = canais 1–2; 2 = 3–4; 3 = 5–6; 4 = 7–8.
Os quatro retornos tiveram picos de −40,00/−40,01 dBFS. A configuração
original de gabinete foi restaurada a cada execução, sem atualizar firmware
nem escrever formato, SRC, clock ou mute. [Perfis, hashes e métricas](adat-module-confirmed.json).

## Rotas confirmadas neste estado

| ADAT físico | Transporte lógico | Bytes PCM | RX selecionado | TX selecionado |
| --- | --- | --- | --- | --- |
| 1–2 | 9–10 | 36–41 | 0x45=17 | 0x51=5 |
| 3–4 | 11–12 | 42–47 | 0x46=18 | 0x52=6 |
| 5–6 | 13–14 | 48–53 | 0x47=19 | 0x53=7 |
| 7–8 | 15–16 | 54–59 | 0x48=20 | 0x54=8 |

Há diferenças no PCM e no pequeno ganho do segundo canal em relação ao
retorno do gabinete; não atribuímos bit-perfect ao módulo. As preferências
salvas mostram SRC habilitado, mas isso não foi estabelecido por leitura
atual nem teste A/B. A origem dessas diferenças permanece por investigar.

Foi possível validar o módulo sem voltar ao Windows, preservando a
configuração digital que já existia na 192. Isso não confirma inicialização
a frio: a interface ainda estava ligada desde uma sessão Windows anterior.
Os ensaios são sequenciais em pares, não oito canais simultâneos. AES/EBU,
S/PDIF e TDIF continuam fora do conjunto de formatos testados.
