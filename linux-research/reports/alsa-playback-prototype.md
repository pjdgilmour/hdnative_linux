# Protótipo ALSA de reprodução — 20/09/2026

**Atualização: reprodução audível pelo ALSA confirmada no hardware.**
Duas sessões concluídas, 94 voltas do anel e nenhuma falha registrada pelo driver.
Veja [o resultado e os limites da validação](first-alsa-playback.md).
A descrição abaixo preserva o projeto e o procedimento do primeiro teste;
as referências a verificações pendentes descrevem o estado anterior à execução.

## Escopo desta versão

`kernel/avid_native_alsa.c` cria uma placa ALSA `AvidNative` com uma saída PCM:
48 kHz, dois canais, `S24_3LE`, período de 1024 quadros e buffer ALSA de 4096
quadros. A aplicação escreve no buffer ALSA; o callback `ack` converte os
quadros para o anel nativo de 8192 quadros de 256 bytes. Os seis bytes dos
canais 1–2 ficam nos offsets 4–9; cabeçalho, outros canais e padding são zero.

O módulo é separado do `avid_native_dma_probe` já validado. As funções de
configuração e parada DMA foram copiadas sem mudança funcional. O módulo
original continua com SHA256
`c1576a74c73abe2744e4636164fb87cc596104623be9bf35f2f4920486ea6994`.
O marco anterior também está preservado em
`milestones/first-audible-2026-09-20.tar.gz` e seu arquivo `.sha256`.

Não há instalação permanente, autoload, alteração da placa padrão, captura
ALSA, controle de volume, pausa, mmap, ajuste de clock ou firmware. O acesso
PCM exige UID efetivo root nesta primeira versão, evitando reprodução por
aplicativos do desktop durante o experimento. Cada sessão tem limite de
30 segundos; o teste usa apenas 8 segundos por sessão. Ainda não é um driver
para uso diário ou áudio de baixa latência.

## Hardware e estado exigidos

Somente `0000:81:00.0`, vendor/device e subsystem `11af:ef80`, BAR0 de 4 MiB,
identidade `d400` e firmware `01050040`. Bus mastering precisa estar desligado
antes de associar o módulo. Os controles PCIe devem corresponder ao estado
ocioso conhecido. A identificação e os controles da 192 precisam coincidir
com a unidade já testada: slot 0, módulos `13151314`, controle 0 = 2, controles
1–3 = 0 e tabela de rotas vazia.

O módulo preserva o clock. A declaração ALSA de 48 kHz depende do estado de
48 kHz observado nesta 192; ainda não existe medição independente nem
programação da frequência. Rota `4d=1` e desmute `0=0` são verificados antes
de permitir a reprodução; o encerramento tenta restaurar `0=2` e `4d=0`.

## Transporte e sincronização

- Usa o consumidor TX MMIO `0x41058`; os snapshots DMA em memória ficaram
  estagnados nos testes anteriores e não são usados como posição ALSA.
- Publica dados disponíveis por `0x41018` após barreira DMA. Recusa rewinds,
  saltos e preenchimentos que excedam o espaço disponível.
- Uma thread consulta o hardware aproximadamente a cada 1–1,5 ms; notifica
  períodos ALSA e acompanha voltas completas. Isto não é garantia de tempo real.
- Descarta entrada publicando o índice RX em `0x40858`. Evidência estática:
  DSI RVA `0x19f060` fornece esse endereço ao gerenciador; `0x19f080` fornece
  `0x41018` para TX; `0x19ecb0` publica o índice do gerenciador. **A atualização
  contínua de RX ainda precisa ser validada neste experimento.**
- Lacuna de polling de 80 ms, ausência de avanço por 100 ms, perda dos bits
  de presença/lock, avanço além dos dados enviados fora do drain ou limite de
  30 segundos encerram a sessão. No EOF, a posição entregue ao ALSA é limitada
  aos quadros realmente enviados. Não há reabertura automática no script.
- Ordem de locks: mutex de stream ALSA (`nonatomic`) antes de `io_lock`.
  Notificações ALSA ocorrem sem `io_lock`, pois podem chamar `pointer`/`STOP`.
- STOP, `hw_free`, close e remoção convergem para limpeza repetível. Falhas
  de restauração impedem novas sessões. Se transações PCI não drenarem, o
  módulo e as alocações ficam retidos para evitar liberar memória ainda em uso.
- Suspensão/hibernação é recusada enquanto o módulo estiver associado.

As rotinas ALSA foram conferidas nos headers locais 6.12.107 e nas fontes
primárias de [pcm_lib.c](https://github.com/torvalds/linux/blob/v6.12/sound/core/pcm_lib.c)
e [pcm_native.c](https://github.com/torvalds/linux/blob/v6.12/sound/core/pcm_native.c).
A referência geral é [Writing an ALSA Driver](https://docs.kernel.org/sound/kernel-api/writing-an-alsa-driver.html).

## Verificações realizadas sem acessar os BARs

- Compilação com `make -C linux-research/kernel -j2 W=1`, sem avisos, para
  `6.12.107+deb13-amd64`. Dependências: `snd` e `snd-pcm`.
- `test_pcm_ring.py`: sete testes do helper C realmente usado pelo driver,
  compilado com UBSan. Inclui mais de 700 mil quadros e 80 voltas do anel,
  verificação byte a byte, canais distintos, fronteira ALSA de 64 bits,
  escritas curtas, overfill, rewind, underrun e EOF.
- `test_alsa_lifecycle.py`: função de limpeza real extraída do driver, com
  falhas injetadas; verifica restauração em ordem, fechamento repetido, falha
  de mute, falha de rota, preparo parcial e retenção após falha de drain.
  ASan e UBSan ativos; detecção de leaks desabilitada porque o sandbox usa
  ptrace e esse teste não aloca heap.
- `test_192_control.py`: testes existentes de protocolo/restore passaram.
- `make_alsa_tone.py`: geração e verificação de 384000 quadros, pico −40 dBFS,
  canais isolados e ramps de 10 ms nas bordas.
- Sintaxe Bash do script e recusa de execução sem root verificadas.
- As funções DMA setup/stop foram comparadas com o módulo audível anterior.

Essas verificações não comprovam posicionamento DMA, continuidade, latência,
estabilidade ou áudio analógico no novo módulo. Isso depende da execução local.

## Próximo teste no hardware

Com volume baixo, 192 no estado anterior de 48 kHz e trabalho salvo:

```sh
sudo /home/paulo/hdnative_linux/linux-research/run-alsa-test.sh
```

O script gera áudio a −40 dBFS e chama `aplay` diretamente na placa vinculada
a este PCI, com erros fatais e timeout. Faz duas aberturas independentes de
8 segundos; cada uma contém canal 1 (440 Hz), canal 2 (660 Hz) e ambos, com
silêncio entre trechos. O volume analógico depende da cadeia de monitoração.

Ao final, imprime contagens de quadros/voltas, erros e restaurações, tenta
remover o módulo e compara os 64 bytes do cabeçalho PCI com a captura anterior.
Salva áudio e logs em `reports/alsa-test-XXXXXX/`. Esperamos duas partidas e
paradas, nenhum erro/underrun e restaurações confirmadas. `rx_discarded` é
apenas avanço de índice; não comprova captura de áudio válida.

O teste não pode garantir limpeza após travamento do kernel, desligamento ou
SIGKILL. O próximo resultado necessário é o log completo e a observação dos
canais audíveis e de eventuais cortes/repetições.
