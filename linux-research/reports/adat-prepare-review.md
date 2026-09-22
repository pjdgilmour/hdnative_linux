# Recusa ALSA antes do START — sessão xuChRn

## Evidência

O perfil Windows passou no probe e a placa ALSA foi criada. O `arecord`
mostrou `Unable to install hw params`, com 48 kHz/S24_3LE, dois canais,
período 1024 e buffer 4096 frames. Estatísticas: starts=stops=0,
last_error=-16, nenhum frame transferido. Não há captura de áudio a aprovar.
Módulo removido, cabeçalho PCI restaurado e placa desvinculada.

Esses parâmetros correspondem aos anunciados pelo driver. A mensagem
não localiza sozinha a recusa: `snd_pcm_hw_params()` da alsa-lib chama
`snd_pcm_prepare()` automaticamente depois da configuração.
Referência primária: [alsa-lib pcm.c, v1.2.14, linhas 855–884](https://github.com/alsa-project/alsa-lib/blob/v1.2.14/src/pcm/pcm.c#L855-L884).
No núcleo, a preparação chama o callback do driver; a limpeza também pode
ser chamada ao falhar a configuração. Referência: [Linux pcm_native.c, v6.12](https://github.com/torvalds/linux/blob/v6.12/sound/core/pcm_native.c).

O registro disponível não distingue falha na limpeza inicial, na guarda
de estado quieto ou outra etapa. Não afirmar que o formato é incompatível
nem que a corrupção óptica anterior foi resolvida.

## Defeito corrigido e diagnóstico acrescentado

`finish_session()` chamava os verificadores do perfil Windows mesmo sem
sessão configurada ou escrita de controle a limpar. Diferentemente do
perfil antigo, esses verificadores fazem consultas DigiLink. Isso gerava
I/O desnecessário antes do prepare ou em close/hw_free repetidos, podendo
marcar falha por um problema novo de consulta durante uma operação que
não tinha trabalho a executar. **Esse defeito existe no código, mas o log
xuChRn não prova que ele originou o -16.**

A função agora retorna sem I/O quando não houve sessão e não há limpeza
pendente. Quarentena é verificada antes; DMA configurado, sessão em curso,
escritas tentadas e flags de restauração pendente continuam exigindo cleanup.
O caminho vazio não marca mute/rotas como aprovados nem apaga erros anteriores.

O prepare informa a etapa exata em toda saída de erro: cleanup inicial,
parâmetros PCM, estado quieto, verificação de rotas/controles ou readback de
buffers. O diagnóstico imprime PCI COMMAND, controles MMIO, caixa DigiLink
e endereços DMA; o callback hw_free também identifica falhas de cleanup.
Essas leituras não normalizam nem zeram o estado. Nenhuma guarda foi removida.
No modo Windows, todos os WRITE ao periférico continuam bloqueados.

## Verificação

Build W=1 e suíte ADAT completa aprovados. O teste de lifecycle agora injeta
falhas nos verificadores e confirma zero chamadas quando não há sessão,
close repetido sem I/O, e manutenção das falhas quando há cleanup pendente
ou quarentena. Testes existentes de 32 perfis, buffers novos, 4,096 milhões
de frames nos offsets 4/28, proibição de WRITE e aceitação também passaram.
Nenhum módulo foi carregado nesta preparação; duplex preservado.

Próxima execução, mantendo a 192 ligada, mesmo cabo óptico do gabinete,
48 kHz, monitores mutados e trabalho salvo:

```sh
sudo ./linux-research/run-adat-test.sh enclosure 1 1 --windows-state
```

Enviar a saída completa, principalmente `prepare refused: stage=...` caso
ocorra outra recusa. Não prometer áudio a partir do build: esta revisão
corrige a limpeza vazia e torna a próxima falha diagnosticável.
