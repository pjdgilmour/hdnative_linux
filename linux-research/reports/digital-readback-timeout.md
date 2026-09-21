# Primeiro diagnóstico digital: timeout no controle candidato 0x30

O usuário executou `identify-192 --inspect-digital` depois dos ensaios
analógicos. Identidade, módulos e controles comuns responderam normalmente:
placa d400, firmware 01050040, 192 com módulos 14 13 15 13, controle0=2.

A primeira consulta do bloco digital retornou:

```text
digital pass=0 slot=0 module=2 bank=1 reg=0x30 result=1 response=0x000000 value=0x00 cleanup=0
```

`result=1` é timeout. `value=0x00` era somente o valor inicial do destino;
não houve resposta válida com esse conteúdo. `cleanup=0` significa que o
retorno ao comando neutro foi confirmado. O programa encerrou o diagnóstico
nesse ponto: 0x31 e 0x32 não foram consultados. A identificação da 192 e a
restauração PCI tiveram sucesso, mas a configuração digital não foi lida.
Não houve WRITE no periférico, áudio, reset ou alteração de clock/firmware.

## Revisão da evidência estática

DSI.dll do pacote Pro Tools 2026.4.1, SHA256
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`.
Endereços RVA, base PE 0x180000000:

- `0x1af740` calcula o endereço `0x20 + 8*módulo + subregistro` e encaminha
  a `0x1a5e80`, caminho de escrita. Para módulo 2 e subregistros 0–2, são
  0x30–0x32. Isso não prova suporte a leitura nesses endereços.
- `0x1aea30` obtém um bloco de 0x6c bytes por `0x0875b0`, decodifica parte
  dele com `0x1ae650` e fornece a cada módulo um segmento em
  `buffer+0x0f+8*módulo`, pela virtual +0x40.
- No módulo digital essa virtual é `0x1b1010`, que decodifica três bytes.
  A existência desse decodificador não demonstra uma leitura direta de
  0x30–0x32 por DigiLink. A origem completa do bloco ainda precisa ser
  rastreada; não deve ser assumida como leitura do hardware ou cache atual.

Não está demonstrado se 0x30 é somente escrita, se há outro mecanismo de
leitura ou se depende de estado adicional. O timeout, isoladamente, não
indica defeito do módulo digital nem falta de firmware.

## Diagnóstico revisado

O mesmo comando agora consulta os três endereços candidatos em duas
passagens. Continua depois de timeout somente quando a neutralização
terminou com sucesso. Erro de neutralização, transação ocupada ou
cancelamento interrompem a sequência. Não há varredura de outros registros
nem comandos WRITE no periférico.

A saída diferencia `value=unavailable` de um zero lido com sucesso.
`DIGITAL_READS_COMPLETE=no` e `DIGITAL_READS_STABLE=unavailable` impedem que
um conjunto de timeouts seja declarado estável. Mesmo uma leitura completa
não prova seleção de ADAT ou lock óptico.

O objetivo é determinar se 0x31 (seletor de fonte no caminho de escrita) e
0x32 oferecem leitura independentemente de 0x30. Se esses controles também
não responderem, não há estado anterior conhecido que permita afirmar uma
restauração ao testar mudanças de formato. Nesse caso será necessário
resolver outro caminho de leitura/estado antes de escrever nesses controles.

Os testes de protocolo simulam sucesso, timeout parcial com recuperação,
zero válido, timeout de todos os registros, dados instáveis, falha de
neutralização, transação ocupada e cancelamento. Nenhum teste de áudio
ADAT foi implementado ou declarado aprovado nesta etapa.

## Resultado da segunda execução

Os seis acessos terminaram em timeout com cleanup=0. Nenhum dos três
controles teve leitura válida. O próximo caminho investigado é o
[arquivo DSIPrefs](digital-preferences-findings.md); não há necessidade de
repetir o diagnóstico nesta configuração.
