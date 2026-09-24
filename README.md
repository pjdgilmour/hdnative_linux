# HD Native Linux

Driver experimental Linux para **Avid HD Native PCIe + Digidesign 192 I/O**.
**Reprodução e captura simultâneas nas entradas/saídas analógicas 1–2,
a 48 kHz/24 bits**, confirmadas no MixBus com reprodução pelo próprio MixBus
e pelo navegador, via PipeWire. A versão anterior de reprodução também foi
validada com Audacious. Veja [o marco duplex](linux-research/reports/duplex-apps-confirmed.md).

## Compilar e usar

Ambiente validado: Debian, kernel `6.12.107+deb13-amd64`, PipeWire 1.4.2 e
WirePlumber 0.5.8. A compilação exige GCC/make, headers do kernel em execução,
Python 3, kmod e `spa-json-dump`. A integração usa WirePlumber, `pactl`,
`wpctl`, systemd e sudo. Não é necessário instalar o driver Windows.

Na raiz deste repositório:

```sh
./linux-research/build-duplex.sh
sudo ./linux-research/desktop-driver.sh stop
sudo ./linux-research/duplex-driver.sh start
./linux-research/duplex-driver.sh status
```

Selecione **Avid HD Native — 192 I/O Duplex** como saída e entrada nos
aplicativos. A saída começa em −40 dB; aumente gradualmente. A entrada
começa em 0 dB de ganho de software. Com loopback físico conectado, mantenha
a monitoração de entrada desligada para evitar realimentação.
Para encerrar:

```sh
sudo ./linux-research/duplex-driver.sh stop
```

A compilação gera o módulo e o manifesto local de hashes exigido pelo
gerenciador. Recompile após mudar os arquivos verificados ou o kernel.
Não ative simultaneamente a cópia original e a deste repositório.
O gerenciador modifica temporariamente a configuração do WirePlumber e
reinicia esse serviço; o módulo não é instalado para carga automática no boot.

## Estado e limites

- Reprodução estéreo; PCM nativo ALSA `S24_3LE`, 48 kHz. O PipeWire converte
  os formatos dos aplicativos.
- Captura analógica 1–2 e operação duplex nos aplicativos confirmadas.
  A sessão duplex registrou mais de 12 minutos de PCM em cada direção,
  sem XRUNs ou erros. Os pares dos dois bancos analógicos também passaram
  no ensaio separado de roteamento descrito abaixo. Operação multicanal
  simultânea, outras taxas, partida a frio e medições de latência/qualidade
  ainda não foram validadas.
- A interface precisa estar no estado de 48 kHz utilizado nos testes;
  o módulo não carrega firmware nem configura clock.
- O endereço PCI padrão é `0000:81:00.0`; as verificações de identidade,
  firmware e estado são específicas do conjunto testado.
- Código experimental de kernel: salve o trabalho antes dos testes.
  Desative o módulo antes de suspender/hibernar.

Veja [uso e detalhes do módulo duplex](linux-research/desktop/duplex.md).
A [versão anterior de reprodução](linux-research/desktop/README.md) permanece
disponível como alternativa, com gerenciador e módulo próprios.

## Captura analógica confirmada

O [teste separado das entradas analógicas 1–2](linux-research/reports/capture-prototype.md)
gravou 10 segundos em loopback físico a 48 kHz/24 bits, com correspondência
dos tons por canal, zero XRUNs e restauração confirmada. Veja o
[registro da validação](linux-research/reports/first-capture-confirmed.md).
O módulo duplex separado também foi confirmado nos aplicativos, conforme
o [registro da sessão](linux-research/reports/duplex-apps-confirmed.md).

## Reprodução e captura simultâneas

A [versão duplex para aplicativos](linux-research/desktop/duplex.md) passou
nos testes simulados e no ensaio real informado pelo usuário: gravação no
MixBus durante reprodução pelo MixBus e pelo navegador, com zero XRUNs nas
duas direções. Os módulos anteriores permanecem preservados. Os contadores
não identificam o aplicativo de cada stream nem medem latência total.

## Mapeamento dos módulos e canais

Este exemplar possui 8 entradas e 16 saídas analógicas, além do módulo
DIGITAL I/O. O [teste de mapeamento por pares](linux-research/reports/channel-map.md)
permite conferir todos os pares analógicos em dois grupos de loopback,
com tons de −40 dBFS, gravação e restauração a cada execução.
Os dois bancos passaram nos [testes físicos por pares](linux-research/reports/analog-banks-confirmed.md):
16 saídas analógicas e 8 entradas a 48 kHz/24 bits, zero XRUNs e restauração
confirmada. A [contraprova de 1–2 e 3–4](linux-research/reports/analog-pair-isolation-confirmed.md)
também diferenciou seus caminhos com seleções cruzadas. A identificação dos
conectores depende do cabeamento informado; operação multicanal simultânea
nos aplicativos ainda não foi implementada. Os [oito canais ADAT do gabinete](linux-research/reports/adat-enclosure-confirmed.md)
passaram no Linux em quatro pares, com a [matriz completa de 12 contraprovas de isolamento](linux-research/reports/adat-enclosure-matrix.md),
zero XRUNs e estado Windows preservado. Os quatro retornos também foram
comparados byte a byte com o sinal gerado, após alinhamento de 16 frames. O [ADAT do módulo DIGITAL I/O](linux-research/reports/adat-module-confirmed.md)
também passou nos quatro pares e 12 isolamentos, sem nova passagem pelo Windows.
A inicialização digital a frio e os oito canais simultâneos continuam pendentes.

```sh
./linux-research/build-channelmap.sh
```

Veja as ligações e comandos no guia antes de executar os testes físicos.

## Organização

- `linux-research/kernel/`: módulo para aplicativos, protótipos e helpers.
- `linux-research/desktop/`: configuração do WirePlumber e instruções.
- `linux-research/tools/`: gerenciador, ferramentas de pesquisa e testes.
- `linux-research/reports/`: notas técnicas e registros resumidos dos marcos.
- [Histórico da pesquisa](linux-research/README.md).

O módulo de reprodução foi copiado sem alterações; o experimento de captura
foi adicionado depois, em arquivos separados. Os caminhos da documentação
foram adaptados para `/home/paulo/hdnative_linux/`. Os manifestos históricos
em `reports/` descrevem builds anteriores; não substituem o manifesto gerado
pelos scripts `build-desktop.sh` e `build-duplex.sh`. Os scripts antigos de pesquisa preservam seus
pré-requisitos e verificações dos experimentos originais.

Instaladores, binários/firmwares proprietários, dumps de disassembly,
músicas, logs brutos de sessões, arquivos compilados e backups históricos
não fazem parte desta cópia. Permanecem no diretório original. Referências
a evidências locais ausentes estão identificadas nas notas da pesquisa.

## Testes sem hardware

A compilação duplex executa testes de buffers, funções do driver, limpeza
e 11 testes do gerenciador com falhas simuladas.
Outros testes podem ser executados individualmente, por exemplo:

```sh
python3 linux-research/tools/test_pcm_ring.py
python3 linux-research/tools/test_digilink.py
python3 linux-research/tools/test_probe.py
```

Esses testes usam arquivos temporários e simuladores; não carregam o módulo.


A futura interface gráfica seguirá a organização do Hardware Setup da 192;
veja o [plano do painel](linux-research/reports/gui-plan.md).
