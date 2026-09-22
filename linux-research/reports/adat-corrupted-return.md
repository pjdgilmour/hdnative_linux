# Retorno óptico com amostras alteradas — Q0e1ud

## Resultado

A sessão `adat-test-Q0e1ud` usou o mesmo módulo da tentativa anterior:
SHA256 `7a152ec40884911b771a07db4395ed1dba90e7aa89d566c9bf6f93f6ff169f7b`.
Houve zero XRUNs/erros, mute/rotas e cabeçalho PCI restaurados, módulo
removido e placa desvinculada. A captura falhou nos critérios existentes;
nenhum canal ADAT foi aprovado.

O usuário esclareceu que **apenas configurou ADAT no Pro Tools** na
passagem mais recente pelo Windows. Não foi registrada uma contraprova
Windows desse loopback. O funcionamento Windows relatado anteriormente
continua sendo informação do usuário; não equivale a essa gravação de controle.

Diferentemente de `ccAo1q` (dois frames não nulos), a nova captura tem
186002/180002 amostras não nulas por canal. O primeiro canal chegou a
−17,38 dBFS; o segundo, próximo de 0 dBFS, com sete amostras próximas do
limite. Não reproduzir esse arquivo nos monitores como teste de escuta.

## Comparação offline

`tools/adat_sample_diagnostic.py` reconstrói o padrão TX do
`native_capture_ring.h`, com a mesma tabela e divisão inteira C nas rampas.
O teste automatizado compila e executa a função C real `nc_tx_fill` e
compara todos os 480000 frames com a referência Python. Outros testes
cobrem retorno íntegro atrasado, bit removido, silêncio e entrada truncada.
Não há alteração de driver, aceitação ou correção das amostras.

A busca de offsets 0..128 frames nas rampas de início encontrou melhor
ajuste único em 16 frames (906 das 1952 amostras não nulas avaliadas).
Esse alinhamento é uma comparação de padrão, **não medição de latência**.

| Janela do padrão | Canal 1 | Canal 2 |
| --- | --- | --- |
| 1,2–2,8 s | frequência AC dominante 750 Hz, amostras alteradas | zero |
| 4,2–5,8 s | zero | frequência AC dominante 1500 Hz, amostras alteradas |
| 7,2–8,8 s | 750 Hz, amostras alteradas | forte distorção; maior componente em 10500 Hz |

As frequências e os intervalos de atividade ligam o retorno ao padrão TX.
Isso não prova o percurso físico sem a contraprova, nem revela em que
etapa os valores mudam. O detector de aceitação rejeitou corretamente a
forma/amplitude; encontrar as frequências na FFT não autoriza aprová-la.

Algumas amostras positivas chegam exatas (por exemplo `0147ae`, pico
positivo 83886 da referência). O canal 1 perde o bit 20 em 92998 amostras;
o canal 2 também apresenta alterações nos bits altos, diferentes durante
os tons isolados e simultâneos. Não é justificável aplicar ganho, trocar
bytes ou forçar extensão de sinal como correção: isso mascararia erros sem
localizar sua origem. Também não se pode atribuir o resultado somente ao
cabo, ao transmissor, ao receptor ou à extração DMA.

O relatório detalhado está em [comparação das amostras](adat-Q0e1ud-samples.json).
SHA256 do raw: `1e8afe7668ed09d576ff72875b10d6fd0f5cdc98538dab6c3336d3b5ac861b22`.

Reprodução (requer NumPy):

```sh
python3 linux-research/tools/test_adat_sample_diagnostic.py
python3 linux-research/tools/adat_sample_diagnostic.py \
  linux-research/reports/adat-test-Q0e1ud/capture.raw
```

O diagnóstico exige exatamente 10 s/48 kHz/S24_3LE estéreo do ensaio Linux.
Não passar um WAV ou exportação Windows arbitrária diretamente a ele.

## Próximo controle no Windows

Foi preparado `linux-research/prepared-audio/adat-reference-48k.wav`:
10 s, estéreo, PCM 24-bit/48 kHz, pico −40 dBFS, amostras idênticas ao TX.
750 Hz no canal esquerdo entre 1–3 s; 1500 Hz no direito entre 4–6 s;
ambos entre 7–9 s; rampas de 10 ms e silêncio nos demais intervalos.
SHA256: `bc110d8f6e06ac30a937b463ad3508f409c66cc2773b4746dbe153f0c85bc645`.
O WAV gerado é ignorado pelo Git. Para gerar outra cópia:

```sh
python3 linux-research/tools/adat_sample_diagnostic.py \
  --write-reference /caminho/novo/adat-reference-48k.wav
```

1. Copie o WAV de referência para um local acessível no Windows. Não use
   `capture.wav` da sessão com amostras alteradas como fonte.
2. Preserve o cabo OUT → IN nos conectores ópticos **fixos do gabinete**.
   No Pro Tools, use sessão 48 kHz, clock interno e formato óptico ADAT.
3. Importe a referência numa faixa estéreo, sem plugins, ganho/volume em
   0 dB. Roteie sua saída ao par **Optical 1–2 do gabinete**. Confirme o
   mapeamento físico em Hardware Setup/I/O; não confunda com Digital 1–2
   da placa modular nem com o número lógico de um bus.
4. Grave o retorno Optical 1–2 em outra faixa estéreo. Deixe a saída
   dessa faixa em **No Output**, sem send de retorno, para evitar feedback.
   Mantenha monitores mutados; a análise pode ser feita pelo arquivo.
5. Exporte apenas o trecho gravado como WAV estéreo, PCM 24-bit, 48 kHz,
   sem normalização, plugins ou conversão de taxa. Preserve algum silêncio
   antes e depois dos tons. Traga a gravação para `prefs_protools/` e informe
   o nome. O comprimento pode variar; analisaremos com alinhamento apropriado.

Essa contraprova mede o mesmo cabeamento e portas sob o driver Windows.
Uma gravação íntegra fortalecerá a hipótese de inicialização/transporte
incompleto no Linux. Se o problema também ocorrer ali, investigaremos
primeiro o caminho comum. Nenhuma nova escrita experimental na 192 foi
preparada com base somente nesta captura.


## Contraprova Windows recebida: PCM íntegro

O novo `adat_teste.wav`, informado como retorno óptico do gabinete, é
idêntico à referência em todos os 464523 frames exportados; somente parte
do silêncio final foi cortada. O print mostra entradas e saídas lógicas
9–16 em Optical 1–8, clock interno/48 kHz. O usuário manteve a 192 ligada
na transição para Linux. Veja a [comparação completa e próximo ensaio](windows-adat-loopback-confirmed.md).
Isso conclui a pendência da gravação de controle Windows; não aprova ainda
o ADAT Linux nem identifica a etapa que alterou as amostras em Q0e1ud.
