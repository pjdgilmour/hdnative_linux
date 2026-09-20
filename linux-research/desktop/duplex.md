# Reprodução e captura nos aplicativos — versão duplex experimental

`avid_native_duplex.ko` oferece **saídas e entradas analógicas 1–2**, estéreo,
48 kHz/S24_3LE, com streams ALSA independentes. O transporte usa as rotas já
confirmadas nos testes separados de reprodução e loopback. **Integração confirmada no MixBus, com reprodução pelo próprio MixBus
e pelo navegador:** duas sessões, zero XRUNs/erros e restauração PCI
confirmada. Veja [o registro do ensaio](../reports/duplex-apps-confirmed.md).

Os módulos anteriores foram preservados. A mesma placa só pode estar
associada a um deles por vez. Não é necessário substituir a versão de
reprodução para voltar a usá-la.

## Ativar

Na raiz do repositório, compile quando necessário:

```sh
./linux-research/build-duplex.sh
```

Feche os aplicativos usando a 192 e salve o trabalho. Mantenha o volume de
monitoração baixo. Se ainda houver loopback físico de saída para entrada,
deixe a **monitoração de entrada desligada** no aplicativo; habilitá-la pode
realimentar a saída para a própria entrada. Para gravação com fonte externa,
retire o loopback e conecte a fonte em nível de linha.

```sh
sudo ./linux-research/desktop-driver.sh stop
sudo ./linux-research/duplex-driver.sh start
```

A nova ativação carrega o módulo, aplica uma regra específica e reinicia
brevemente o WirePlumber. Aguarda **ambos** os nós e só então imprime
`DUPLEX_READY=yes`:

- **Avid HD Native — 192 I/O Duplex (saídas 1–2)**
- **Avid HD Native — 192 I/O Duplex (entradas 1–2)**

A saída começa em −40 dB e a entrada em 0 dB de ganho de software. Não muda
os dispositivos padrão anteriores nem cria conexões de monitoração. A entrada
física é `avid_hd_native_duplex_in`; a fonte `.monitor` da saída não é a
captura analógica. Os aplicativos usam suas permissões normais, sem sudo.

## Primeiro teste no MixBus

Use a integração PipeWire ou JACK do PipeWire que já funcionou na reprodução.
Selecione/conecte a nova entrada e a nova saída da 192. Para o primeiro ensaio,
use uma sessão de 48 kHz e mantenha a monitoração das faixas de entrada
desligada. Grave 15–30 segundos enquanto reproduz uma faixa:

1. Confirme sinal nas entradas 1 e 2 e no arquivo gravado.
2. Pare e reinicie a gravação com a reprodução ainda ativa.
3. Verifique se a reprodução continuou sem cortes e se há estalos ou XRUNs.
4. Se estiver usando loopback, retire os cabos de retorno antes de habilitar
   monitoração de entrada. O módulo não aplica limitação de pico às amostras
   recebidas dos aplicativos; o nível inicial baixo é do PipeWire.

Consulte os contadores antes de encerrar:

```sh
./linux-research/duplex-driver.sh status
```

`playback_starts/stops`, `capture_starts/stops`, `playback_xruns`,
`capture_xruns`, `capture_frames` e `total_frames` distinguem as direções.
`starts/stops` contam o motor compartilhado. PipeWire pode manter streams
abertos ou silenciosos entre ações do aplicativo: esses contadores não são
necessariamente iguais ao número de cliques em gravar/reproduzir.
Mute e rotas só devem aparecer restaurados depois que ambas as direções
estiverem inativas; durante a sessão, `N` pode ser o estado esperado.

Para encerrar e conferir a restauração final:

```sh
sudo ./linux-research/duplex-driver.sh stop
```

Logs: `linux-research/reports/duplex-session-*/`. Envie a saída da ativação,
status e encerramento se o teste falhar. Não force remoção de módulo retido.
Para voltar à reprodução anterior, use `desktop-driver.sh start` na cópia
com build válido; no repositório novo, `build-desktop.sh` prepara esse build.

## Limites

- Acesso ALSA direto: `hw:AvidDuplex,0` nas duas direções, formato S24_3LE,
  48 kHz, período 1024 e buffer 4096, sem mmap. Não use simultaneamente com
  o PipeWire tentando abrir os mesmos dispositivos. JACK ALSA separado não
  foi validado; para este ensaio, use a integração PipeWire já existente.
- Sem firmware/clock novos, sem captura de outros canais/taxas e sem carga
  automática no boot. A 192 deve estar no mesmo estado de 48 kHz já testado.
- Se a reprodução começar durante uma captura, pode haver até 4096 quadros
  de silêncio já oferecidos ao hardware (cerca de 85 ms) antes do primeiro
  quadro novo. O driver informa esse adiantamento como atraso extra ALSA;
  a latência total/compensação de gravação ainda requer medição física.
- Buffer conservador e polling preservados. Esta versão não promete baixa
  latência para monitoração ao vivo. Desative antes de suspender/hibernar.

## Implementação e testes

Um worker mantém o DMA compartilhado. A entrada é descartada apenas quando
não há captura ativa; a saída é preenchida com silêncio quando não há
reprodução ativa. Preparar ou parar um stream não reseta o transporte do
outro. A última parada drena DMA e restaura mute, rotas e registradores.
Overrun/underrun individual encerra a direção afetada; perda de link,
falta de avanço ou atraso excessivo de polling encerra as duas e impede
recomeço automático nessa instância do módulo.

O mutex de I/O serializa estado, MMIO e validade dos buffers. Callbacks
desassociam os ponteiros antes de o ALSA liberar memória. Notificações são
feitas depois de soltar esse mutex, sob um lock de stream por vez, para
evitar inversão de locks entre reprodução e captura.

Validação automática: build `W=1`; parser SPA JSON; helpers de buffer com
ASan/UBSan e mais de 2,7 milhões de quadros; funções reais de trigger/poll/stop
em simulação com mais de um milhão de quadros, junção, parada/reabertura,
overrun de captura e falha compartilhada; sete cenários de limpeza e 11
testes do gerenciador, incluindo fonte ausente, monitor confundido com
entrada, estado prévio e falhas de restauração. O primeiro ensaio real da versão duplex também foi confirmado, conforme
o registro vinculado no início; outras máquinas e condições ainda exigem testes.

Referências das APIs: [ALSA e notificações de período](https://cdn.kernel.org/doc/html/latest/sound/kernel-api/writing-an-alsa-driver.html),
[exemplo de atraso extra no callback de posição](https://github.com/torvalds/linux/blob/master/sound/usb/pcm.c),
[propriedades ALSA do PipeWire](https://docs.pipewire.org/devel/page_man_pipewire-props_7.html).
