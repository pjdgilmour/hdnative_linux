# Ensaio de estabilidade ALSA — preparado em 20/09/2026

**Atualização: ensaio executado com áudio confirmado pelo usuário.**
Sessão de 320 s e reabertura de 8 s concluídas, sem erros registrados.
Veja [resultado, logs e limites](alsa-stability-confirmed.md).
Parte da versão com [áudio ALSA confirmado](first-alsa-playback.md).

## Procedimento

Com a 192 no estado anterior de 48 kHz, volume baixo e trabalho salvo:

```sh
sudo /home/paulo/hdnative_linux/linux-research/run-alsa-test.sh --stability
```

Uma sessão de **320 segundos (5 min 20 s)** mantém o mesmo stream ALSA
aberto enquanto a sequência de teste de 8 segundos se repete 40 vezes.
Depois, uma segunda sessão de 8 segundos verifica a reabertura após o uso
prolongado. O sinal permanece estéreo S24_3LE/48 kHz, pico −40 dBFS, canal 1
(440 Hz), canal 2 (660 Hz) e ambos, com as pausas já conhecidas. As pausas
fazem parte do arquivo; não fecham nem suspendem o fluxo de PCM.

O script gera cerca de 94 MB de PCM no diretório de logs. Mostra progresso a
cada 10 segundos e grava `session-1.json`/`session-2.json`, além de logs e
cabeçalhos PCI antes/depois. Ao concluir ou encontrar erro, tenta remover o
módulo; a restauração da 192 continua a cargo do driver ao encerrar o PCM.
É possível interromper com Ctrl+C. Travamento do kernel/SIGKILL continuam
fora das garantias de limpeza do script.

## Mudanças

- O módulo recebe `max_stream_seconds`, somente leitura, padrão 30; valores
  fora de 30..360 são recusados antes de associar o driver. O ensaio longo
  escolhe 360 segundos; o teste curto continua escolhendo 30.
- Nenhuma mudança nas rotinas de DMA, formato dos quadros, polling, locks,
  mute, rota, clock ou firmware. O limite de duração e a mensagem que o
  informa são as únicas mudanças funcionais no módulo.
- O novo supervisor acompanha avanço de quadros, erro do driver e saída do
  `aplay`. Usa `--fatal-errors`; não reinicia sessões após uma falha.
- Falta de progresso por 3 segundos ou tempo total acima de 340 segundos
  encerra o player, com SIGKILL como último recurso após 3 segundos. Os
  limites menores de stall/polling do próprio driver permanecem ativos.
- Verifica uma partida/parada por sessão, nenhum erro registrado, mute/rota
  restaurados e ausência de quadros faltando. Permite no máximo 1024 quadros
  de cauda, a diferença observada no primeiro ensaio com `aplay`.
- Recusa uma reprodução concluída mais de 5% antes da duração nominal.
  Essa verificação ampla detecta anomalias grandes; não mede precisão de clock.

Os arquivos contêm 15360000 e 384000 quadros. O total esperado sem padding é
15744000; se o `aplay` repetir a cauda de 1024 por sessão observada antes, o
contador final será 15746048. Devem ocorrer cerca de 1921 voltas completas
somadas do anel nativo. Índices RX continuam sendo descartados, sem captura
ALSA ou validação de amostras de entrada.

## Verificação sem hardware

- Compilação `make -C linux-research/kernel -j2 W=1`, sem avisos, para o
  kernel `6.12.107+deb13-amd64`.
- Oito testes do supervisor com processo filho e parâmetros simulados:
  sucesso/cauda, erro do driver, timeout, stall, SIGTERM, saída não zero,
  quadros faltantes e falha de restauração. Processos filhos encerrados.
- Arquivo de 320 segundos gerado e conferido: exatamente 40 blocos iguais
  de 384000 quadros, cada um baseado no sinal já verificado a −40 dBFS.
- Sintaxe Bash verificada. Helpers de formato/ring/periférico mantidos
  idênticos ao marco ALSA audível, e rotinas DMA/limpeza sem alteração.

A versão anterior está preservada em
`milestones/first-alsa-audible-2026-09-20.tar.gz` com manifesto SHA256.
A execução longa ainda depende do terminal local do usuário por exigir sudo.
Não há instalação permanente ou liberação para aplicativos do desktop.
