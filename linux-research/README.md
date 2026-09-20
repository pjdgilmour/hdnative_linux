# HD Native PCIe + 192: investigação Linux

**Captura analógica 1–2 confirmada:** teste ALSA separado, 10 segundos
a 48 kHz/24 bits, padrão de loopback por canal correspondente, zero XRUNs.
Veja [o registro](reports/first-capture-confirmed.md). Captura nos aplicativos
ainda não está integrada ao módulo de reprodução.

**Versão para aplicativos validada:** `avid_native_desktop.ko` funcionou com
Harrison MixBus 12, Audacious e áudio no navegador via PipeWire. Seis streams,
7201 voltas do buffer, zero erros/XRUNs registrados e restauração confirmada.
Acesso normal pelos aplicativos e reprodução sem limite artificial de sessão.
Veja [o marco confirmado](reports/desktop-apps-confirmed.md) e
[ativação, uso e desativação](desktop/README.md).

Estado em 20/09/2026: **primeiro áudio analógico confirmado pelo usuário no
Linux, pela HD Native PCIe e 192 I/O**. O teste `run-dma-tone.sh --route-192`
produziu cinco sinais audíveis a −40 dBFS no caminho ligado às saídas 1–2.
Mute, roteamento e PCI foram restaurados; o módulo foi removido.
Veja o [registro do primeiro áudio](reports/first-audible-playback.md).

**Novo marco:** [reprodução pelo ALSA confirmada no hardware](reports/first-alsa-playback.md).
Duas sessões de aproximadamente 8 segundos, 94 voltas do anel, nenhum erro
registrado pelo driver e restauração de mute, rota e cabeçalho PCI. O usuário
ouviu o som. O [protótipo ALSA](reports/alsa-playback-prototype.md) permanece
experimental: estéreo S24_3LE a 48 kHz, root e limite de 30 segundos por sessão.

**Ensaio prolongado confirmado:** [5 min 20 s de reprodução e reabertura](reports/alsa-stability-confirmed.md),
com 1922 voltas do anel somadas, nenhum erro registrado pelo driver e
restaurações verificadas. O modo `--stability` seleciona limite de 360 segundos;
o padrão permanece 30. A versão validada foi preservada em `milestones/`.

**Música real validada:** a faixa `Audio/03 Ink.mp3` tocou inteira por
`play-audio.sh`, convertida para 48 kHz/S24_3LE com pico −40 dBFS. O usuário
confirmou ausência de estalos; zero erros/XRUNs registrados, 1338 voltas do anel
e restaurações verificadas. Veja [o resultado](reports/music-playback-confirmed.md).

O snapshot DMA em memória continua esparso; a posição é acompanhada por MMIO.
Evidências em [transporte](reports/audio-transport.md),
[mute](reports/192-mute-findings.md) e [roteamento](reports/192-routing-findings.md).

## Resultado do primeiro experimento

O usuário executou `read-native-id` com sudo no terminal local e informou:

```text
device=0000:81:00.0
BAR0+0x00=0x0000d400
BAR0+0x04=0x01050040
HD_NATIVE_D400_MATCH=yes
```

A identificação coincide com a comparação encontrada nos binários Avid.
Isso confirma acesso ao hardware da HD Native pelo Linux, além da enumeração
PCI já existente. Não confirma comunicação DigiLink com a interface 192.

Uma captura posterior confirmou que os 64 bytes do cabeçalho PCI voltaram
exatamente ao estado inicial: COMMAND `0x0100`, sem memory decoding nem bus
mastering, sem driver associado. O firmware não foi atualizado.

O usuário confirmou que o conjunto funciona no Windows nesta mesma máquina;
seria necessário reiniciar para executar testes naquele sistema.

## O que foi criado

- `tools/snapshot.py`: captura metadados PCI e lista ALSA; não acessa BARs.
- `tools/pe_evidence.py`: analisa PE64 com Python padrão; indexa strings,
  exports e referências no disassembly do objdump. Não executa os binários.
- `tools/read_native_id.c`: experimento limitado para a placa `11af:ef80`,
  subsystem `11af:ef80`, BAR0 de 4 MiB e nenhum driver associado.
- `read-native-id`: executável Linux compilado a partir desse código.
- `tools/test_probe.py`: dez testes com arquivos simulados e falhas injetadas;
  não acessam a placa. Verificam recusas, leitura, restauração de configuração,
  erro na habilitação, erro na verificação e sinais SIGTERM/SIGBUS.
- `reports/`: capturas, resultado informado pelo usuário e evidências estáticas.

## Limites do experimento executado

O programa mapeia somente a primeira página do BAR0 com `PROT_READ` e faz duas
leituras voláteis de 32 bits: offsets `0x00` e `0x04`.
Para habilitar a leitura, modifica temporariamente apenas o bit MEMORY do
registrador PCI COMMAND e restaura/verifica o valor original ao terminar.
Não escreve no BAR0, não habilita bus mastering, não configura DMA ou IRQs,
não reseta a placa, não envia comandos DigiLink e não atualiza firmware.

Portanto, “somente leitura” descreve os acessos MMIO; há uma escrita temporária
e explícita na configuração PCI. O código tenta restaurar a configuração em
falhas e sinais tratados, mas não pode garantir restauração após SIGKILL,
queda de energia ou falha do sistema. Não executar junto com outro software
que controle ou associe um driver à placa.

## Evidências recuperadas do driver 26.4.1.179

Endereços abaixo são RVAs, relativos à base da imagem PE. Base preferencial
de `dsi.dll`: `0x180000000`; de `Dalwdm.sys`: `0x140000000`.
Os nomes atribuídos às rotinas sem símbolos são interpretações da análise.

| Evidência | Localização | Conclusão |
|---|---|---|
| Construtor com string `HDNative` e vtable | DSI `0x0ab7c0`, vtable `0x766448` | Distingue a classe HD Native |
| Inicialização virtual dessa classe | DSI `0x0ab8f0` | Chama `0x193e90`, que cria objeto em `0x193a90` |
| Seleção dos tipos `0x26` e `0x2a` | DSI `0x193b80` | Caminho Native PCIe/Thunderbolt; mapeamento PCI também aparece em `0x0b19dd` |
| Base MMIO armazenada no objeto +`0x18` | DSI `0x19bc57` | Ponteiro usado pela inicialização seguinte |
| Leitura do offset zero e comparação dos 16 bits baixos com `0xd400`/`0xd700` | DSI `0x19dbea`–`0x19dc00` | Base para o teste de identificação |
| Mesma comparação no kernel Windows | DAL `0x0e540` | Segunda evidência independente no pacote |
| Leitura do offset `0x04` | DSI `0x19dc22`, DAL `0x0e94e` | Campo tratado como versão na inicialização |
| Limites numéricos de versão | DSI dados `0x774e18` e `0x774e1c` | `0x01000000` a `0x01050200`, em caminho condicional |
| Inicialização de hardware | DSI `0x19db90` | Após validar ID/versão, escreve controle e vários blocos MMIO |
| Identificador de modelo `192 I/O` | DSI string `0x765308`, uso em `0x087bbe` | O pacote contém suporte à família; não prova identificação do dispositivo conectado |

O valor observado `0x01050040` fica dentro dos limites encontrados, mas isso
não equivale a uma verificação completa de compatibilidade: há condições e
rotinas adicionais no driver. A codificação semântica da versão não foi
estabelecida; manter o valor hexadecimal bruto.

A sequência nativa encontrada usa acessos diretos à memória mapeada. Assim,
interceptar apenas DeviceIoControl no Windows provavelmente não capturará
todas as escritas relevantes. Os IOCTLs `0x8000220f`/`0x80002213` localizados
em outra parte da DLL não foram demonstrados como o caminho da HD Native e
não devem ser tratados automaticamente como seu protocolo.

Há referências a `ProToolsNative_FW_d400.bin` e sua variante MSI, mas não
foi necessário obter ou carregar essas imagens para a primeira leitura.
Nenhum arquivo separado com esses nomes foi encontrado no CAB extraído.

**Atualização:** os dois arquivos D400 foram posteriormente encontrados na
instalação extraída do Pro Tools em Downloads. Seus checksums internos
conferem e correspondem às entradas da DSI.dll. Todos os 52 arquivos DIO_64
coincidem com o pacote do driver. Veja
[a análise dos firmwares](reports/protools-firmware-findings.md) e o
inventário com hashes (`reports/protools-inventory.json`; evidência local não incluída). Nenhum firmware foi
gravado ou carregado no hardware durante essa inspeção.

## Próxima etapa técnica

**Novo experimento executado:** `identify-192 --identify-192`, fundamentado
na cadeia CGreenCard → CGreenTDM2Node → CBalance. Consulta a família e os
quatro bytes de módulos que distinguem a 192. Passou por 11 testes simulados;
o usuário executou e obteve família 1, módulos `0x13151314`, modelo 16:
**192 I/O**, slot lógico 0. Veja a saída real (`reports/192-id-user-run.txt`; evidência local não incluída) e
[protocolo, limites e instruções](reports/digilink-protocol.md).

Antes de tentar áudio, reconstruir a inicialização de comunicação com os
periféricos e identificar a 192. A rotina `0x19db90` pertence a `CBalance`,
conforme RTTI referenciada pelo chamador. Ela depende de outros objetos e
escreve muitos registradores; não foi portada nem executada no Linux.

Pontos de investigação:

1. Separar reset, clock, comunicação e transporte dentro de `CBalance`.
2. Seguir os caminhos `Dhm_TDM2_Initialize`, `Dhm_TDM2_DSPHasHose`,
   `Dhm_Device_Comm_TDM2.cpp` e os tipos `C192XDPeripheral`/`C192XDCard`.
   A presença de nomes não estabelece, sozinha, a função de cada registrador.
3. Determinar a sequência mínima de enumeração DigiLink e seus timeouts,
   com endereços, máscaras e ordem fundamentados no código.
4. Se a análise estática não resolver, observar uma inicialização funcional
   no Windows, levando em conta as escritas MMIO diretas.
5. Somente após identificar a interface e estabilizar clock, implementar
   DMA/IRQs e um fluxo PCM ALSA de poucos canais.

## Reproduzir a compilação e as verificações

Na raiz do pacote:

```sh
gcc -std=c11 -O2 -Wall -Wextra -Werror -o linux-research/read-native-id linux-research/tools/read_native_id.c
python3 linux-research/tools/test_probe.py
python3 linux-research/tools/snapshot.py
```

O teste de hardware já foi realizado. Para repeti-lo intencionalmente:

```sh
sudo ./linux-research/read-native-id --read-id
```

O BDF pode ser passado como terceiro argumento caso a posição da placa mude.
O programa recusa outro modelo/subsystem, outro tamanho de BAR, driver
associado ou bus mastering ativo. Código de saída 0 significa ID esperado;
3 significa identificação diferente; 4 indica falha de restauração.

Para repetir a análise estática, extraia o `Data1.cab` do MSI com 7-Zip e seu
conteúdo com cabextract, sem executar o instalador. Nesta sessão, a extração
ficou em `/tmp/avid-hd-inspect/` (temporário, pode desaparecer após reboot).
Disassembly e índice podem ser regenerados com:

```sh
objdump -d -M intel --no-show-raw-insn /tmp/avid-hd-inspect/dsi.dll > /tmp/avid-hd-inspect/dsi.asm
python3 linux-research/tools/pe_evidence.py /tmp/avid-hd-inspect/dsi.dll --disasm /tmp/avid-hd-inspect/dsi.asm --output linux-research/reports/dsi-evidence.json
```

Referência pública utilizada para os recursos PCI via sysfs:
https://docs.kernel.org/PCI/sysfs-pci.html
