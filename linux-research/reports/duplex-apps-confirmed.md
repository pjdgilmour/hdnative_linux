# Reprodução e captura simultâneas confirmadas — 20/09/2026

O usuário confirmou gravação de uma faixa reproduzida pelo próprio MixBus
e de outra reproduzida no navegador. A integração PipeWire expôs a saída
`avid_hd_native_duplex_out` e a entrada física `avid_hd_native_duplex_in`.
Sessão local: `duplex-session-20260920-195819`.

## Evidência conferida

- Dois inícios e duas paradas em cada direção, e dois ciclos do motor DMA.
- **Zero XRUNs** em reprodução e captura; **zero erros** registrados.
- Reprodução: **36321991 quadros**, equivalentes nominais a **12min36,71s**
  acumulados em 48 kHz, e 4433 voltas do anel. Última reprodução:
  34671804 quadros, aproximadamente 12min02,33s.
- Captura: **36576837 quadros**, equivalentes nominais a **12min42,02s**.
- 349 quadros recebidos foram descartados enquanto não havia captura ativa.
  A diferença entre durações RX/TX pode incluir silêncio e intervalos de
  abertura/fechamento; não mede atraso do áudio nem demonstra perda.
- Maior intervalo de polling: **2310 µs**, sem representar latência total.
- Mute e rotas restaurados ao ficar inativo. A desativação removeu o módulo;
  PCI ficou sem driver, os cabeçalhos de 64 bytes antes/depois são idênticos
  e `cleanup_errors` ficou vazio.
- Fontes, módulo e ferramentas conferidos contra o manifesto de build;
  hash do módulo igual ao registrado na sessão de hardware.

A origem das duas faixas e o sucesso da gravação vêm da confirmação do
usuário. Os contadores não atribuem streams a aplicativos, não delimitam
exatamente sua sobreposição nem analisam os arquivos gravados no MixBus.
Não se afirma a ausência de artefatos por medição acústica ou digital;
o dado objetivo disponível é ausência de XRUNs/erros nos contadores.

## Escopo validado

HD Native PCIe e 192 I/O, canais analógicos 1–2, 48 kHz/S24_3LE no hardware;
Debian com kernel 6.12.107+deb13-amd64 e PipeWire 1.4.2. Reprodução/captura
ALSA independentes utilizadas pela integração PipeWire, com acesso normal
pelos aplicativos. A sessão superou o antigo limite do protótipo de captura.

Permanece experimental. Outros canais/taxas, partida a frio, operação em
outras máquinas, compensação de latência e qualidade metrológica ainda
precisam ser validados. A validação não implica todos os casos possíveis
de parar/reabrir uma direção enquanto a outra continua; esses cenários
foram cobertos na simulação, e devem continuar sendo observados no uso real.

[Resumo e hashes das evidências](duplex-apps-validation.json).
[Ativação, uso e desativação](../desktop/duplex.md).
Os logs completos ficam na pasta local da sessão, ignorada pelo Git.
Nenhum código de driver foi alterado para registrar este marco.
