# Transporte de áudio: estado após identificar a 192

**Atualização:** o teste com desmute e rota `0x4d=1` produziu áudio analógico
confirmado pelo usuário. [Registro do primeiro áudio](first-audible-playback.md).
Os experimentos sem som abaixo são etapas anteriores.

192 I/O confirmada no slot lógico 0, família 1, módulos `0x13151314`.
Usuário escolheu saídas **analógicas 1–2** para o teste audível.

Foi executada uma transferência **de silêncio por 20 ms**,
por módulo do kernel. Não foi implementado dispositivo ALSA. Resultado de
DMA recebido: execução real (`dma-silence-user-run.txt`; evidência local não incluída) retornou `result=0`,
`tx_consumed=9`, `rx_produced=0`, `status_sequence=2`, `pci_restored=Y` e
módulo removido. Isso comprova escrita de status DMA e avanço inicial de TX;
nenhuma reprodução audível foi confirmada. Os registradores diretos foram
`TX=0x402`, `RX=0x3f9`: não coincidem com o status em memória, possivelmente
por atualização esparsa do status na adaptação sem IRQs. Essa explicação
ainda é hipótese. Não tratar `rx_produced=0` como prova de ausência de captura.

## Evidências estáticas

RVA relativa a `0x180000000`, por DLL indicada:

| Fonte | RVA | Evidência |
|---|---|---|
| DSI | `0x19c8f0` | Aloca três buffers e programa seus endereços DMA |
| DSI | dados `0x9aeaa8` | Tamanhos 2 MiB + 4351, 4 MiB + 4351, 1279 bytes |
| DSI | `0x19ca02` | Alinha início dos buffers em 256 bytes |
| DSI | `0x19cafc` | Endereço de captura em BAR `0x40918/0x40958` |
| DSI | `0x19cb10` | Endereço de reprodução em BAR `0x41118/0x41158` |
| DSI | `0x19cb26` | Endereço de status em BAR `0x4093c/0x4097c` |
| DSI | `0x19f2b0` | Início de transporte, DMA/control bits |
| DSI | `0x19f4b0` | Parada de transporte e reset dos motores |
| DSI | `0x19d810` | Quatro registros de status de 256 bytes, sequência em +32 |
| DSI | `0x19db30`, `0x19d8c0` | Posições TX/RX em +4/+0 desses registros |
| DirectIO | `0x0f600`–`0x0f70f` | Reprodução: 8192 quadros; captura: 16384 |
| DirectIO | `0x0f960`, particularmente `0x0fbe2`–`0x0fc77` | Empacotamento de saída |
| DirectIO | `0x0fcd0` | Desempacotamento de entrada |

O DirectIO obtém buffers/ring managers de IBalance. Cada quadro tem 256
bytes, oito grupos de 32 bytes; os dados de cada grupo começam no offset 4
e contêm até oito amostras de três bytes. Incrementos de três bytes e
cópias diretas das amostras aparecem em `0x0fc40`. Isto contradiz a hipótese
inicial de 64 palavras de 32 bits por quadro: **não usar S32 intercalado**.
A função/significado completo dos bytes restantes ainda não está fechado.
O teste de silêncio usa buffers inteiramente zerados, como a alocação DSI.

## Experimento DMA

Fonte: `kernel/avid_native_dma_probe.c`. Compilou sem avisos com `W=1` para
`6.12.107+deb13-amd64`; `vermagic` confere. Compilação não valida o protocolo
de hardware. Os 11 testes do identificador DigiLink não testam este módulo.

```sh
make -C linux-research/kernel W=1
sudo ./linux-research/run-dma-silence.sh
```

O script carrega o módulo explicitamente, coleta seus parâmetros/resultados
e tenta removê-lo. Não instala o módulo em `/lib/modules`, não configura
autoload, nem muda o boot. A placa não permanece associada ao driver após
o experimento. O teste usa código experimental no kernel: salvar o trabalho
e mutar monitores antes de executá-lo, pois uma falha pode travar o sistema.

O módulo:

- Exige BDF, PCI/subsystem, BAR, identidade e firmware conhecidos.
- Exige predicado de link/lock e estado de controle quieto; recusa DMA
  previamente configurado ou bus mastering já ativo.
- Reserva três áreas coerentes usando a API DMA do Linux, com máscara de
  32 bits; valida o alinhamento em 256 bytes e zera toda a memória.
- Programa os motores a partir da rotina DSI e oferece 8191 quadros zerados.
  O experimento preserva as configurações de clock e periférico atuais.
- Habilita transferência por aproximadamente 20 ms e consulta o status.
  Pode durar mais sob atraso de escalonamento; não é um temporizador rígido.
- Mantém fontes de interrupção mascaradas e INTx desabilitada durante o teste.
  Essa adaptação por polling ainda não foi comprovada neste hardware.
- Para os motores, desliga bus mastering, espera transações pendentes,
  restaura os registradores salvos e a configuração PCI, então libera memória.
- Se não consegue drenar transações PCIe, mantém buffers e módulo presos,
  sem liberar memória ainda potencialmente usada. Nesse caso requer reboot.

`result=0` significa avanço observado no índice TX MMIO em cada transferência,
**não** áudio analógico confirmado. O critério anterior usava somente o snapshot
DMA e produziu `-110` indevidamente no teste de desmute apesar do avanço MMIO;
isso foi corrigido após essa execução. Na versão atual, `-110` significa que
alguma transferência não mostrou avanço MMIO; `-16`, estado
ocupado ou falha de drenagem (consultar log); `-12`, falha de alocação;
`-67`, identidade/firmware/link incompatível com as pré-condições.

`tx_consumed`, `rx_produced` e `status_sequence` são observações do buffer
DMA. `pci_restored=Y` confirma somente PCI COMMAND; não afirma restauração
bit a bit de todo estado interno da FPGA. Contadores e eventos transitórios
não são reversíveis por uma simples cópia dos registradores.

## Referências de implementação Linux

Usa endereços retornados por `dma_alloc_coherent` e barreiras DMA; não usa
endereços físicos extraídos de processos. Referências primárias:
[DMA API](https://docs.kernel.org/core-api/dma-api-howto.html) e
[drivers PCI](https://docs.kernel.org/PCI/pci.html).

## Primeiro teste de tom executado

`run-dma-tone.sh` carrega o mesmo módulo com parâmetro `run_tone=1`.
Cinco transferências de 40 ms, separadas por 300 ms. Cada buffer tem um sinal
de 1024 quadros nos dois primeiros canais lógicos, com rampas de 128 quadros
e todo o restante zerado. Amplitude máxima 83886, aproximadamente **−40 dBFS**
em PCM de 24 bits. Frequência nominal 1 kHz e duração nominal 21,3 ms em
48 kHz; como a taxa existente é preservada, frequência e duração podem variar.

Não altera configuração de roteamento/mute da 192. Portanto, som nas saídas
1–2 é uma hipótese a verificar no teste; silêncio pode indicar configuração
de interface ainda pendente. A presença dos módulos `0x14,0x13,0x15,0x13`
foi associada por RTTI a AD, DA, Digital, DA, respectivamente, no construtor
DSI `0x1b05f0`. Isso não estabelece sozinho o roteamento ativo.

`tools/test_tone.py` compilou o helper C utilizado pelo kernel e verificou
vetores fixos S24_LE positivos/negativos, canal esquerdo/direito, zeros nos
demais canais e bytes reservados, rampas, cauda silenciosa e limite de pico.
O módulo recompilou sem avisos com `W=1`.

Parâmetros adicionais `tx_mmio_first`, `tx_mmio_last`, `tx_mmio_changes`
registram a evolução do registro de índice TX durante a transferência.
Servem para comparar com o status DMA esparso, não para afirmar som analógico.

### Resultado observado

O usuário executou o teste e **não ouviu som**. Informou posteriormente que
os LEDs dos canais 1–2 responderam, o indicador principal já estava verde e
o indicador de 48 kHz estava laranja. Confirmou explicitamente depois que
eram os medidores **OUTPUT 1–2**. Isso sustenta a hipótese de sinal chegando
ao caminho de saída da interface, mas não comprova sinal elétrico nos DACs.
Extrato informado (`dma-tone-user-run.txt`; evidência local não incluída).

`tx_mmio_first=9`, `tx_mmio_last=1906`: avanço durante a última transferência.
`tx_mmio_changes=130` acumula as cinco transferências. O status DMA em memória
continuou em TX=9, RX=0, sequência=2, apesar do avanço MMIO. O módulo foi
removido; os 64 bytes do cabeçalho PCI coincidem com o estado inicial.
Isso não comprova captura nem conversão analógica.

O manual original Digidesign, edição 10/07, página 6, distingue medidores
de entrada na fileira superior e saída na inferior; o primeiro segmento
marca −42 dB. O tom de −40 dBFS está pouco acima desse primeiro limiar.
Fonte: [192 I/O Guide, cópia do manual do fabricante](https://m.barryrudolph.com/recall/manuals/avid_192_manual.pdf).

### Segundo teste executado: sinais mais longos, mesma amplitude

`sudo ./linux-research/run-dma-tone.sh --long` seleciona `tone_long=1` junto
com `run_tone=1`. Mantém cinco repetições e −40 dBFS, mas usa 6144 quadros de
tom (128 ms em 48 kHz) com rampas de 128 quadros e cauda silenciosa. O modo
anterior de 1024 quadros continua disponível sem `--long`.

O buffer continua pré-carregado; não há refill nem mudanças de clock,
roteamento ou mute. A transferência longa termina quando o polling observa
TX >= 7168 ou alcança 160 ms. Essa margem pretende parar antes dos 8191
quadros oferecidos, inclusive em taxas mais altas, mas atrasos de escalonamento
podem ultrapassar o prazo; não é uma garantia de tempo real.

O teste do helper C passou para ambos os comprimentos, verificando todos os
quadros, amplitude, canais, rampas, bytes reservados e silêncio restante.
Compilação `W=1` sem avisos. Execução do modo longo: TX MMIO chegou a 7211;
LEDs OUTPUT 1–2 responderam, mas o usuário não ouviu som e o medidor do
DEQ2496, ligado após a AG06, não se moveu. A mesma ligação funciona no Windows.
Veja [resultado e investigação do mute](192-mute-findings.md).
Nesse teste, a reprodução analógica permaneceu sem confirmação. O teste
posterior com rota a confirmou; nenhum driver ALSA foi implementado.
