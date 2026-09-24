# ADAT do gabinete: matriz completa de quatro pares

Após autorização do proprietário, foram executados diretamente os 16 ensaios
com sudo: quatro retornos positivos e todas as 12 combinações cruzadas.
Nenhuma credencial foi gravada no projeto. O diagnóstico inicial confirmou
identidade, controles e 30 rotas do perfil Windows previamente validado.
O cabeamento mantido foi OUT → IN do óptico do gabinete; formato 48 kHz,
S24_3LE estéreo em cada ensaio, tons de −40 dBFS. Cada captura durou 10 s.

Todos os testes passaram com zero XRUNs, last_error=0, preservação de controles
e rotas, módulo removido, cabeçalho PCI restaurado e placa desvinculada.
Ao final também foi conferida a ausência do módulo e do vínculo PCI.
O maior max_poll_us foi 1794; isso não mede latência total de áudio.

| Par de saída | Par de entrada | Sessão | Verificação adicional |
| --- | --- | --- | --- |
| 1 | 1 | adat-test-CHZQma | retorno exato após alinhar 16 frames |
| 1 | 2 | adat-test-jbOgmc | 480000 frames inteiramente zero |
| 1 | 3 | adat-test-iT7rUh | 480000 frames inteiramente zero |
| 1 | 4 | adat-test-RrFa0s | 480000 frames inteiramente zero |
| 2 | 2 | adat-test-DpgUbe | retorno exato após alinhar 16 frames |
| 2 | 1 | adat-test-HoPTFb | 480000 frames inteiramente zero |
| 2 | 3 | adat-test-UQmDc2 | 480000 frames inteiramente zero |
| 2 | 4 | adat-test-BOoPJa | 480000 frames inteiramente zero |
| 3 | 3 | adat-test-Os8EWw | retorno exato após alinhar 16 frames |
| 3 | 1 | adat-test-fN8NdT | 480000 frames inteiramente zero |
| 3 | 2 | adat-test-lmcBRc | 480000 frames inteiramente zero |
| 3 | 4 | adat-test-7Rnuj8 | 480000 frames inteiramente zero |
| 4 | 4 | adat-test-suQdK7 | retorno exato após alinhar 16 frames |
| 4 | 1 | adat-test-INPrpk | 480000 frames inteiramente zero |
| 4 | 2 | adat-test-DdEwol | 480000 frames inteiramente zero |
| 4 | 3 | adat-test-HPvzBs | 480000 frames inteiramente zero |

Par 1 = canais 1–2; par 2 = 3–4; par 3 = 5–6; par 4 = 7–8.
Os perfis, análises, estatísticas, hashes e snapshots PCI foram conferidos
com `tools/verify_adat_matrix.py`. As 16 combinações têm IDs distintos e
foram confrontadas com os mesmos critérios de aceitação dos scripts.
[Evidência estruturada e hashes](adat-enclosure-matrix.json).

## Comparação exata do PCM

O gerador C real de `native_adat_ring.h`, conferido contra o manifesto do
build, produziu uma referência de 480000 frames. Em cada retorno positivo,
a primeira amostra não nula indicou atraso de 16 frames. Após esse único
alinhamento, os 479984 frames estéreo sobrepostos são idênticos byte a byte,
sem ajuste de ganho, correção de sinal ou normalização. Os 16 frames iniciais
da captura são silêncio. Os últimos 16 frames da referência ficam fora da
janela capturada e não são comparados.

Isso confirma PCM exato no trecho comparado dos quatro pares nesse teste.
Não equivale a garantia de todas as configurações ou durações. A comparação
foi também exercitada com corrupções deliberadas em silêncio, tom e último
frame, todas recusadas. Nas 12 capturas de isolamento, todos os bytes são zero.

Para reproduzir a análise sem acessar hardware:

```sh
python3 linux-research/tools/verify_adat_matrix.py \
  linux-research/reports/adat-test-CHZQma \
  linux-research/reports/adat-test-jbOgmc \
  linux-research/reports/adat-test-iT7rUh \
  linux-research/reports/adat-test-RrFa0s \
  linux-research/reports/adat-test-DpgUbe \
  linux-research/reports/adat-test-HoPTFb \
  linux-research/reports/adat-test-UQmDc2 \
  linux-research/reports/adat-test-BOoPJa \
  linux-research/reports/adat-test-Os8EWw \
  linux-research/reports/adat-test-fN8NdT \
  linux-research/reports/adat-test-lmcBRc \
  linux-research/reports/adat-test-7Rnuj8 \
  linux-research/reports/adat-test-suQdK7 \
  linux-research/reports/adat-test-INPrpk \
  linux-research/reports/adat-test-DdEwol \
  linux-research/reports/adat-test-HPvzBs
```

## Limites e próxima etapa

A matriz foi executada sequencialmente em pares; oito canais simultâneos
continuam pendentes, assim como inicialização digital a frio e transporte
multicanal nos aplicativos. Esse perfil não valida o ADAT do módulo DIGITAL
I/O, AES/EBU, S/PDIF ou TDIF.

Para o próximo caminho óptico, o proprietário precisa conectar OUT → IN do
módulo DIGITAL I/O e selecionar esse módulo no Windows, tanto no formato
quanto nas rotas de entrada/saída, conferir um retorno real e trazer o print.
A 192 deve permanecer ligada durante a volta ao Linux. Primeiro leremos o
perfil com `identify-192 --inspect-routing`; só então adaptaremos o teste.
O sudo autorizado permite executar os ensaios, mas não permite mover cabos
ou presumir que a seleção óptica do módulo esteja correta.

A direção para a futura GUI está registrada em [plano do painel](gui-plan.md).
