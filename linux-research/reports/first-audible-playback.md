# Primeiro áudio analógico confirmado no Linux — 20/09/2026

O usuário confirmou: **“Agora sim!!!! Escutei o som!!”** após executar
`sudo ./linux-research/run-dma-tone.sh --route-192`.

Caminho informado: HD Native PCIe → DigiLink → 192 I/O, saídas analógicas
1–2 → Yamaha AG06, entradas 1 e 2 → DEQ2496. Confirmação auditiva do usuário;
não houve medição elétrica, de distorção ou de separação dos canais.
Os dois canais recebem o mesmo tom.

## Condições do teste

- PCI `0000:81:00.0`, `11af:ef80`, identidade `0xd400`, firmware `0x01050040`.
- 192 no slot lógico 0, módulos `0x13151314`. Indicador de 48 kHz previamente
  informado pelo usuário; o teste preserva o clock, sem medir sua frequência.
- Cinco sinais de 6144 quadros, nominalmente 128 ms e 1 kHz em 48 kHz,
  pico −40 dBFS, canais lógicos 1–2, pausas de aproximadamente 300 ms.
- Mute, banco 1, registro 0: `2 → 0 → 2`.
- Roteamento, banco 1, registro `0x4d`: `0 → 1 → 0`.
- Kernel `6.12.107+deb13-amd64`; módulo SHA256
  `c1576a74c73abe2744e4636164fb87cc596104623be9bf35f2f4920486ea6994`.

O teste anterior já desmutava sem produzir som; a adição da rota foi a
mudança de configuração que permitiu ouvir o sinal neste conjunto.

## Resultado informado

```text
result=0
tx_consumed=0
rx_produced=0
status_sequence=2
tx_mmio_first=9
tx_mmio_last=7208
tx_mmio_changes=498
pci_restored=Y
mute_write_attempted=Y
control_before=2
control_during=0
control_after=2
mute_restored=Y
route_write_attempted=Y
route_before=0
route_during=1
route_after=0
route_restored=Y
EXPERIMENT_MODULE_REMOVED=yes
```

Amostras TX/RX no final das cinco transferências:
`0x1c2e/0x1c24`, `0x1c1e/0x1c14`, `0x1c40/0x1c36`,
`0x1c19/0x1c0f`, `0x1c28/0x1c1e`. Link `0x9e180101` em todas elas.
Restaurações de mute e roteamento: `restore_result=0` em ambas.

O snapshot DMA em memória continuou sem acompanhar TX. O avanço é observado
por MMIO; o som foi confirmado externamente. `rx_produced=0` não permite
concluir que a captura esteja funcionando ou ausente.

## Limites e próximo desenvolvimento

A prova de reprodução curta está concluída para este hardware e estado.
Ainda não há dispositivo ALSA, reprodução contínua, captura validada,
controle de taxa, ensaio de latência ou estabilidade. Falta testar partida
a frio sem estado eventualmente herdado do Windows.

O próximo desenvolvimento é alimentar o buffer continuamente, detectar
underruns e expor reprodução PCM via ALSA. O teste atual restaura mute/rota
e remove o módulo ao terminar; não deixa áudio disponível para aplicativos.
