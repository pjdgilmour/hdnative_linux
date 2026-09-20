# HD Native Linux

Driver experimental Linux para **Avid HD Native PCIe + Digidesign 192 I/O**.
Reprodução nas **saídas analógicas 1–2, a 48 kHz**, confirmada no Harrison
MixBus 12, Audacious e navegador através do PipeWire.

## Compilar e usar

Ambiente validado: Debian, kernel `6.12.107+deb13-amd64`, PipeWire 1.4.2 e
WirePlumber 0.5.8. A compilação exige GCC/make, headers do kernel em execução,
Python 3, kmod e `spa-json-dump`. A integração usa WirePlumber, `pactl`,
`wpctl`, systemd e sudo. Não é necessário instalar o driver Windows.

Na raiz deste repositório:

```sh
./linux-research/build-desktop.sh
sudo ./linux-research/desktop-driver.sh start
./linux-research/desktop-driver.sh status
```

Selecione **Avid HD Native — 192 I/O (saídas 1–2)** no controle de som.
A ativação começa com volume de −40 dB; aumente gradualmente.
Para encerrar:

```sh
sudo ./linux-research/desktop-driver.sh stop
```

A compilação gera o módulo e o manifesto local de hashes exigido pelo
gerenciador. Recompile após mudar os arquivos verificados ou o kernel.
Não ative simultaneamente a cópia original e a deste repositório.
O gerenciador modifica temporariamente a configuração do WirePlumber e
reinicia esse serviço; o módulo não é instalado para carga automática no boot.

## Estado e limites

- Reprodução estéreo; PCM nativo ALSA `S24_3LE`, 48 kHz. O PipeWire converte
  os formatos dos aplicativos.
- Captura analógica 1–2 confirmada em loopback de 10 segundos pelo módulo
  de teste separado. Captura nos aplicativos, operação duplex ALSA, outros
  canais/taxas e partida a frio ainda não foram validados.
- A interface precisa estar no estado de 48 kHz utilizado nos testes;
  o módulo não carrega firmware nem configura clock.
- O endereço PCI padrão é `0000:81:00.0`; as verificações de identidade,
  firmware e estado são específicas do conjunto testado.
- Código experimental de kernel: salve o trabalho antes dos testes.
  Desative o módulo antes de suspender/hibernar.

Veja [uso e detalhes do módulo](linux-research/desktop/README.md) e
[a validação nos aplicativos](linux-research/reports/desktop-apps-confirmed.md).

## Captura analógica confirmada

O [teste separado das entradas analógicas 1–2](linux-research/reports/capture-prototype.md)
gravou 10 segundos em loopback físico a 48 kHz/24 bits, com correspondência
dos tons por canal, zero XRUNs e restauração confirmada. Veja o
[registro da validação](linux-research/reports/first-capture-confirmed.md).
A captura ainda não está integrada ao módulo de reprodução para aplicativos.

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
por `build-desktop.sh`. Os scripts antigos de pesquisa preservam seus
pré-requisitos e verificações dos experimentos originais.

Instaladores, binários/firmwares proprietários, dumps de disassembly,
músicas, logs brutos de sessões, arquivos compilados e backups históricos
não fazem parte desta cópia. Permanecem no diretório original. Referências
a evidências locais ausentes estão identificadas nas notas da pesquisa.

## Testes sem hardware

A compilação acima executa os nove testes do gerenciador com falhas simuladas.
Outros testes podem ser executados individualmente, por exemplo:

```sh
python3 linux-research/tools/test_pcm_ring.py
python3 linux-research/tools/test_digilink.py
python3 linux-research/tools/test_probe.py
```

Esses testes usam arquivos temporários e simuladores; não carregam o módulo.
