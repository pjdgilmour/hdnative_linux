# Música real reproduzida pela HD Native + 192 — 20/09/2026

O usuário confirmou: **“Tocou perfeito!! Sem estalos, sem xruns.”**
Faixa `Audio/03 Ink.mp3`, convertida de 44,1 kHz para estéreo S24_3LE/48 kHz,
com pico limitado a −40 dBFS. Duração do PCM: 228,373333 segundos.

Os arquivos locais confirmam uma partida/parada, player com retorno 0,
`PLAYBACK_VERIFIED=yes`, zero XRUNs e zero erros registrados pelo driver.
Foram enfileirados e consumidos **10962944 quadros**, com **1338 voltas**
completas do anel. O arquivo tem 10961920 quadros; a cauda de 1024 está dentro
da tolerância já observada nos testes com `aplay`.

Tempo do supervisor: 228,746 s. Maior intervalo de polling: 1703 µs; isso
não mede latência de áudio. Mute e rota restaurados, módulo removido e PCI
sem driver segundo o log. Os 64 bytes dos cabeçalhos PCI locais antes/depois
foram comparados e são idênticos, com COMMAND `0x0100`.

Módulo SHA256 (conferido):
`196417b11f10dd43424ec4a6d76d5ff78487ac054e905fe1708dd5f2ec7e1b44`.
É o mesmo módulo do ensaio prolongado, preservado no marco
`milestones/alsa-stability-confirmed-2026-09-20.tar.gz`.

Evidências: log (`alsa-music-20znsS/console.log`; evidência local não incluída),
relatório da sessão (`alsa-music-20znsS/session-1.json`; evidência local não incluída),
[preparação da faixa](music-playback-test.md).

Este resultado valida reprodução de música neste conjunto e configuração,
com confirmação auditiva de ausência de estalos. Permanecem pendentes
captura, taxas/canais adicionais, partida a frio, medições de qualidade e
latência, e integração com aplicativos comuns. A reprodução ainda usa o
script com sudo, buffer fixo e limite explícito de sessão.
