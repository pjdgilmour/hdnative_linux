# Reprodução do MP3 fornecido — preparado em 20/09/2026

Arquivo: `Audio/03 Ink.mp3`, estéreo a 44,1 kHz. A faixa completa foi
convertida sem modificar o original para `prepared-audio/music-48k-s24le.raw`:
estéreo S24_3LE, 48 kHz, 10961920 quadros, duração 228,373333 s.

A preparação primeiro decodifica/reamostra em ponto flutuante, mede o pico,
aplica ganho constante e ramps de 50 ms nas extremidades, e converte para
24 bits. Não há normalização dinâmica. Ganho aplicado: −40,447314 dB;
picos finais medidos: 83884 e 82777, pico máximo −40,000214 dBFS.
Todos os quadros de saída foram verificados. Hashes do original e do PCM
estão em `prepared-audio/music.json`. O original foi conferido novamente
após a conversão e não mudou.

`play-audio.sh` verifica o hash do PCM e o módulo exato validado no ensaio
longo antes de habilitar DMA. Usa o supervisor já testado, em uma única
sessão, com timeout de 244 s e limite do driver de 360 s. Ao terminar tenta
restaurar a 192, remover o módulo e comparar o cabeçalho PCI. Logs em
`reports/alsa-music-XXXXXX/`. Não altera a placa de som padrão.

```sh
sudo /home/paulo/hdnative_linux/linux-research/play-audio.sh
```

**Atualização: reprodução concluída pelo usuário, sem estalos ou XRUNs.**
Veja [resultado e evidências](music-playback-confirmed.md).
A execução foi feita no terminal local após a tentativa do agente com
`sudo -n` exigir senha; o agente não recebeu a senha.

Validação concluída: conversão e pico do arquivo real, integridade dos
arquivos, hash do módulo, preflight de mídia e sintaxe Bash. Nenhuma mudança
no driver foi necessária para este teste.
