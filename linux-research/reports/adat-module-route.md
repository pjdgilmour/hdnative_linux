# Loopback do módulo DIGITAL I/O sem nova passagem pelo Windows

**Resultado:** os 16 ensaios físicos passaram. Veja a [matriz confirmada](adat-module-confirmed.md).

O proprietário moveu o cabo óptico OUT → IN para o módulo e autorizou a
continuidade dos ensaios. A leitura inicial mostrou IDs 14/13/15/13,
controles 0/0x80/0/0, status 0x11=0x49, 0x12=1, 0x13=1 e as mesmas 30 rotas
do ensaio do gabinete. O status 0x12 passou de 3 para 1; sua semântica de
lock/formato não está confirmada.

Foi implementada a opção separada:

```sh
sudo ./linux-research/run-adat-test.sh module 1 1 --module-route
```

Ela exige esse perfil exato em duas passagens, com DMA parado, e utiliza
canais lógicos 9–10 no byte 36. Para cada par de entrada i e saída o,
as únicas escritas permitidas são:

- RX 0x44+i: 24+i → 16+i → 24+i (fontes gabinete → módulo → gabinete).
- TX 0x50+o: 0 → 4+o → 0 (destino modular recebe o par lógico selecionado).

Todos os controles e as outras 28 rotas são preservados. Não escreve
mute, formato digital, SRC, clock ou firmware. A rota do gabinete continua
configurada; somente o cabo informado pelo proprietário muda de porta.
Nenhuma captura é copiada para TX. Tons limitados a −40 dBFS, 10 s de
captura, limite do driver 15 s, mesmas guardas PCI/DMA.

As duas rotas são marcadas para restauração antes da primeira tentativa,
inclusive para ACK perdido. A restauração tenta ambas, confere a tabela
completa e controles, com no máximo três tentativas. Qualquer falha impede
aceitação. O modo --windows-state do gabinete permanece sem WRITE periférico;
--module-route não pode ser combinado com ele na CLI.

Build W=1 e testes anteriores passaram. Novo teste compila o helper real:
16 combinações, lista de escritas limitada a dois registros, perda de ACK,
escrita ignorada, restauração recusada, estados/rotas inesperados e mailbox
ocupado. Formato do módulo permanece desconhecido até o retorno físico.
Um resultado negativo não distingue formato, sincronismo e roteamento.
