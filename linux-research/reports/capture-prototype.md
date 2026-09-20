# Captura analógica 1–2: primeiro loopback confirmado

**Atualização:** o usuário executou o teste, e a gravação de 10 segundos
correspondeu ao padrão esperado nos dois canais, sem XRUNs ou erros.
Veja [o marco confirmado](first-capture-confirmed.md).

Módulo separado `avid_native_capture.ko`, derivado do transporte validado de
reprodução. Não altera `avid_native_desktop.c` nem a configuração PipeWire.
Expõe somente captura ALSA, acessível pelo teste com sudo, a 48 kHz, estéreo
S24_3LE, período 1024 e buffer de 4096 quadros. Não oferece captura nos
aplicativos ainda. O primeiro loopback dos canais 1–2 foi confirmado;
a integração com aplicativos e ensaios prolongados de captura permanecem pendentes.

## Executar

Na raiz do repositório, compile caso ainda não exista o build local:

```sh
./linux-research/build-capture.sh
```

Feche aplicações usando a 192 e desative a versão de reprodução, se ativa:

```sh
sudo ./linux-research/desktop-driver.sh stop
```

Salve o trabalho e mantenha monitores mutados: o teste carrega código novo
no kernel e muda temporariamente mute e roteamento. Preserve o estado de
48 kHz utilizado nos testes anteriores. O script recusa placa ocupada.

Escolha **um** dos modos:

### Loopback físico

Conecte a saída **analógica 1 à entrada analógica 1**, e a saída **2 à entrada
2**, usando cabos de linha adequados. Desconecte essas saídas do caminho de
monitoração para este teste. Não habilite monitoramento de entrada em apps.

```sh
sudo ./linux-research/run-capture-test.sh --loopback
```

O módulo gera uma sequência independente, com pico −40 dBFS: 750 Hz no canal
1 entre 1–3 s, 1500 Hz no canal 2 entre 4–6 s e ambos entre 7–9 s, com pausas
e rampas de 10 ms. A captura nunca é realimentada para a saída. A análise
verifica o padrão por canal e imprime `LOOPBACK_PATTERN_MATCHED=yes/no`.
Essa verificação é evidência funcional; não mede latência nem qualidade.

### Fonte externa

Conecte uma fonte de áudio **em nível de linha** às entradas analógicas 1–2
e mantenha-a reproduzindo durante o teste. Para distinguir os canais, use
sinais diferentes ou alterne esquerda/direita.

```sh
sudo ./linux-research/run-capture-test.sh --external
```

Neste modo o transporte envia silêncio à saída, sem monitoramento da entrada.

Ambos gravam 10 segundos em `reports/capture-test-*/capture.raw`, geram
`capture.wav` e um resumo `capture.json` com picos, RMS, DC e saturação por
canal. Não reproduzem o arquivo automaticamente. Ruído ou dados não nulos
não bastam para afirmar captura analógica correta. Examine a gravação e
compare com o sinal físico enviado. O script coleta contadores, remove o
módulo e compara o cabeçalho PCI antes/depois. Falhas interrompem o teste;
não há recuperação automática de XRUN nem repetição.

Para voltar ao áudio nos aplicativos, use o `desktop-driver.sh start` da
cópia com build de reprodução válido. Se estiver usando este repositório
pela primeira vez, execute `build-desktop.sh` antes. Após um erro de
restauração ou módulo preso, preserve os logs e não force `rmmod`.

## Hipótese de rota e formato

Análise local da DSI 26.4.1, RVA relativa a `0x180000000`:

- `0x1a88b0`: módulo AD tem metadados de origem 2 e destino 0.
- `0x1b1bf0`, trecho `0x1b1c1e..0x1b1c44`: quando há origem no módulo 0,
  inicializa `tabela[1..4] = 9..12`.
- O emissor em `0x1af1d0` mapeia o índice da tabela ao registro `0x40+índice`.
  Portanto **banco 1, registro 0x41 = 9** é o candidato para encaminhar o
  primeiro par AD ao computador. O primeiro loopback físico do par 1–2 confirmou o padrão previsto.
- A rota de saída `0x4d=1`, já validada, é usada para o loopback. Também é
  aplicada no modo externo, cujo buffer TX permanece silencioso.
- DirectIO `0x0fcd0`, trechos `0x0fe62` e `0x0ff95..0x10014`: lê quadros de
  256 bytes, dados a partir de +4, amostras de três bytes, grupos de 32 bytes.
  O helper copia os seis bytes do primeiro par, sem converter endian/sinal.

Não é feita carga de firmware nem programação de clock. As duas rotas são
verificadas antes do desmute e restauradas para zero depois do mute. Qualquer
escrita tentada obriga restaurar ambas, inclusive se o ACK se perder. O estado
inicial aceito continua sendo específico da 192 já identificada.

## Transporte e verificações

RX: 16384 quadros; produtor MMIO `0x40818`, consumidor `0x40858`. Lê o produtor,
aplica `dma_rmb()`, extrai PCM para o anel ALSA e só depois devolve os slots
com barreira DMA. TX: mantém 4096 quadros de silêncio/tom independente, sem
um stream de reprodução ALSA. Notificações de período preservam a ordem dos
locks do módulo validado. Índices ambíguos, overrun, falta de avanço RX/TX,
perda de link ou atraso de polling encerram a sessão. Há limite de 15 s no
módulo e timeout externo de 18 s; travamento do kernel não é coberto por
esses temporizadores. Falha de drenagem PCI mantém buffers/módulo presos.

Verificação antes do primeiro teste:

- Compilação `W=1` para `6.12.107+deb13-amd64`.
- Helpers C reais com UBSan: 2,74 milhões de quadros, wraps, contrapressão,
  ponteiros inválidos, bytes PCM, limites dos tons e silêncio.
- Simulador DigiLink: rota dupla, mute, ACK perdido, escrita ignorada,
  restauração incompleta e lista de escritas permitidas.
- Função real de limpeza com ASan/UBSan: cinco cenários, incluindo DMA não
  drenado e preparo parcial.
- Quatro testes do analisador: padrão correto, canais invertidos, silêncio,
  DC e arquivo truncado (inversão incluída no teste do padrão).

Referências de API: [ALSA](https://www.kernel.org/doc/html/v6.5/sound/kernel-api/writing-an-alsa-driver.html)
e [barreiras DMA](https://www.kernel.org/doc/html/next/core-api/dma-api-howto.html).
Essas fontes documentam as APIs Linux; a hipótese DigiLink vem da análise
local e não é validada por essa documentação.
