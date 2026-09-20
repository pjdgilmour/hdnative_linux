# HD Native + 192: teste nos aplicativos

Módulo `avid_native_desktop.ko`, compilado para o kernel local. A saída usa
a reprodução estéreo/48 kHz já validada. **Integração PipeWire confirmada
pelo usuário no Harrison MixBus 12, Audacious e áudio no navegador**, com
seis streams e zero erros registrados pelo driver. Veja
[o registro da validação](../reports/desktop-apps-confirmed.md). Não há captura.

## Ativar

Mantenha a 192 no estado de 48 kHz usado nos testes anteriores, salve o
trabalho e comece com o volume de monitoração baixo. No seu terminal:

```sh
sudo /home/paulo/hdnative_linux/linux-research/desktop-driver.sh start
```

O comando aplica a regra específica da placa, reinicia brevemente o
WirePlumber e carrega o módulo. Se a saída aparecer, imprime
`DESKTOP_READY=yes` e deixa o módulo ativo. A ativação exige sudo; depois
os aplicativos funcionam com seu usuário normal.

Selecione **Avid HD Native — 192 I/O (saídas 1–2)** no controle de som do
sistema ou na saída do aplicativo. O volume começa em −40 dB e pode ser
aumentado gradualmente pelo controle de som. Abra o MP3 original normalmente;
o PCM atenuado dos experimentos anteriores ficaria muito baixo com a nova
atenuação do sistema. A saída padrão anterior é preservada durante a ativação.

A integração foi preparada para PipeWire 1.4.2 e WirePlumber 0.5.8 encontrados
nesta máquina. Aplicativos que usam PulseAudio, PipeWire ou a camada JACK do
PipeWire podem selecionar essa saída. O PipeWire converte os formatos/taxas
dos aplicativos para o PCM nativo da placa.

ALSA direto também está disponível como `hw:AvidHDNative,0`, mas continua
restrito a S24_3LE, 48 kHz, dois canais, período 1024 e buffer 4096 quadros,
sem mmap. Para testes iniciais de aplicativos, escolha PipeWire/PulseAudio;
um servidor JACK ALSA separado precisaria de configuração própria e acesso
exclusivo. ALSA direto não passa pelo controle de volume do PipeWire.

## Status e desativação

Consultar, sem sudo:

```sh
/home/paulo/hdnative_linux/linux-research/desktop-driver.sh status
```

Para desativar, feche aplicativos que estejam usando ALSA diretamente:

```sh
sudo /home/paulo/hdnative_linux/linux-research/desktop-driver.sh stop
```

A desativação pausa o WirePlumber para fechar os dispositivos, tenta remover
o módulo, remove a regra criada por esta ativação e inicia novamente o
WirePlumber. Confere o cabeçalho PCI e salva diagnósticos. Nunca usa `rmmod -f`.
Se houver falha, o estado é preservado para análise; não force a remoção.

Logs: `linux-research/reports/desktop-session-AAAAmmdd-HHMMSS/`. Se a saída
não aparecer ou houver falhas, envie a saída do comando e esse caminho.

## Escopo e arquivos instalados durante o teste

- Permissões normais de `/dev/snd`; Paulo já pertence ao grupo `audio`.
- Reprodução sem limite artificial de duração. Watchdogs de falta de avanço,
  atraso excessivo de polling e perda de link permanecem ativos.
- Regra criada em
  `/etc/wireplumber/wireplumber.conf.d/90-avid-native-desktop.conf`.
  Combina o nome exato da nova placa com o tipo de dispositivo/nó; não se
  aplica à Yamaha, HDA Intel, NVIDIA ou ao módulo de pesquisa anterior.
- Estado temporário em `/run/avid-native-desktop/state.json`.
- Não copia o módulo para `/lib/modules` nem habilita carga no boot. Após
  reiniciar, use `start` novamente. Uma regra remanescente após reboot não
  carrega o módulo; só corresponde à placa quando ela é registrada.
- Fonte e binário anteriores `avid_native_alsa` foram mantidos. Não é
  possível usar os dois módulos simultaneamente na mesma placa.
- Firmware e clock não são programados. Partida a frio e qualidade/latência
  ainda não foram validadas; suspensão/hibernação é recusada enquanto este
  módulo estiver associado. Desative antes de suspender.

## Desenvolvimento e verificação

`avid_native_desktop.c` deriva do módulo que reproduziu música sem estalos.
As diferenças são nomes próprios, remoção da restrição de UID root e limite
de sessão padrão zero. As funções DMA, PCM, restauração e os dois helpers
foram comparados com a versão validada; permanecem iguais, exceto a condição
do watchdog de duração para permitir zero.

A regra evita ACP/UCM genéricos nesta placa, solicita S24LE (24 bits em três
bytes no PipeWire), força RW em vez de mmap, período 1024 e quatro períodos,
e desativa ajustes automáticos para dispositivos batch. Há 1024 quadros de
margem adicional para o escalonamento. A prioridade baixa evita que a nova
saída substitua automaticamente a Yamaha.

A semântica foi conferida nos arquivos locais do WirePlumber e na
[configuração ALSA oficial](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/alsa.html),
assim como no [backend ALSA do PipeWire 1.4.2](https://github.com/PipeWire/pipewire/blob/1.4.2/spa/plugins/alsa/alsa-pcm.c).

Validação: compilação com `W=1`, sintaxe da regra com `spa-json-dump`, nove
testes do gerenciador com falhas simuladas (incluindo rollback, módulo em uso,
regra alheia, restauração e diagnósticos indisponíveis), comparação do transporte
e confirmação de que o binário de pesquisa anterior não mudou. Isso não
substitui medições de qualidade/latência ou ensaios em outras configurações.
O primeiro uso real desta integração já foi confirmado, conforme o relatório
vinculado no início.

Para recompilar e regenerar os hashes usados na ativação, sem sudo:

```sh
/home/paulo/hdnative_linux/linux-research/build-desktop.sh
```
