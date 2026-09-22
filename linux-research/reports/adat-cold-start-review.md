# ADAT do gabinete: primeiro ensaio após desligar a 192

## Resultado observado em 2026-09-21

Sessão `adat-test-ccAo1q`, perfil `enclosure`, saída/entrada óptica 1–2,
48 kHz. O usuário esclareceu que desligou e religou a 192 entre a sessão
Windows e o ensaio Linux. Portanto, as preferências e os prints Windows
não descrevem necessariamente o estado digital presente neste ensaio.

A captura contém 480000 frames estéreo S24_3LE. Somente os frames 17470
e 17471 (~0,364 s) têm valores não nulos: 2056 no primeiro canal e 262658
no segundo, em ambos os frames. Todo o restante é zero, inclusive as
janelas dos tons. Esses dois frames não demonstram recepção de áudio ADAT.

O transporte completou com zero XRUNs/erros, mas o padrão não apareceu:
`ADAT_PAIR_TEST_PASSED=no`. Mute, rotas e cabeçalho PCI foram restaurados;
módulo removido e placa desvinculada. A sequência parou no primeiro par;
os outros cinco ensaios não foram executados.

- SHA256 da captura raw:
  `ecfa4561464c933a169153db3e0d7c0e2d5c0ff91cff0a98d07969d0d5bb247e`
- SHA256 do módulo usado:
  `7a152ec40884911b771a07db4395ed1dba90e7aa89d566c9bf6f93f6ff169f7b`

## Seleção óptica rastreada no DSI

DSI.dll local 2026.4.1, SHA256
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`.
Endereços abaixo são RVAs, base PE `0x180000000`.

- O setter `0x1af340`, ramo `0x1af41b`, salva a seleção óptica em
  `this+0x4a`; seu log usa ADAT quando zero e SPDIF quando não zero.
  Solicita atualização com máscara `0x200`, via virtual `+0xb0`.
- O dispatcher `0x1afef0` solicita a atualização do controle comum 0;
  `0x1afbc0` delega essa escrita a `0x1af960`.
- O escritor `0x1af960` recebe o objeto primário, oito bytes antes do
  ponteiro dos métodos anteriores. Combina a seleção óptica (`+0x52`) e
  digital (`+0x50`) em um campo de dois bits, posições 4–5 do controle 0.
  Com seleção óptica ADAT, o campo é 0 se a seleção digital for 1 (AES),
  e 1 caso contrário; com seleção óptica S/PDIF, o campo é 2.
- O decoder `0x1ae650` faz a transformação inversa do campo: a seleção
  óptica é S/PDIF quando o campo é 2.
- A tabela de rotas continua independente: `0x1af1d0` escreve o valor da
  entrada de software no registro `0x40 + índice`. O ensaio usou
  `0x41=25` e `0x59=1`, com leitura posterior conferida.

O teste recebeu controle 0 = `0x02` antes e escreveu `0x00` durante.
**Os bits 4–5 já eram zero nos dois valores**, compatíveis com a seleção
ADAT + AES nesse caminho do DSI. Não há base para afirmar que a 192 estava
em S/PDIF ou para simplesmente trocar um bit como correção.

Essa é evidência estática da construção dos comandos pelo driver Windows,
não confirmação de lock, inicialização completa nem de todos os efeitos
do registro no hardware. O ciclo de energia impede presumir retenção do
estado Windows; não prova, por si só, a causa da falha.

## Próxima comparação: preservar a alimentação da 192

1. No Windows/Pro Tools, configure 48 kHz, clock interno e ADAT nos
   conectores ópticos **fixos do gabinete**. Use OUT → IN nesse mesmo
   conjunto de portas e confirme o retorno de áudio no Pro Tools, sem
   monitoração que realimente a entrada. A seleção da aba do módulo
   DIGITAL I/O é outro caminho.
2. Encerre o Pro Tools normalmente. Reinicie o computador no Linux,
   mantendo a 192 ligada durante toda a transição e preservando o cabo.
3. Antes de iniciar o duplex ou os ensaios de áudio, leia o estado:

   ```sh
   cd /home/paulo/hdnative_linux
   sudo ./linux-research/identify-192 --inspect-routing
   ```

O utilitário consulta identificação, controles comuns e rotas, sem WRITE
no periférico, reset, áudio, clock ou firmware. Usa transações de leitura
pelo DigiLink e habilitação temporária do acesso PCI, com restauração de
PCI COMMAND. Precisa de sudo no terminal local. Se recusar o estado do
transporte ou encontrar placa vinculada, preserve a saída; não force o
acesso nem carregue outro módulo para tentar normalizar o estado.

O encerramento do Pro Tools e a reinicialização do host também podem
modificar o estado: esta comparação não é um dump do hardware durante a
reprodução Windows. Valores iguais não descartam inicialização não lida;
valores diferentes orientarão a próxima investigação. O ensaio de áudio
atual exige controles e rotas iniciais específicos, por isso não deve ser
repetido automaticamente sobre um estado diferente.

Nenhum driver, lista de escritas ou critério de aceitação foi alterado
nesta revisão. O duplex analógico validado permanece preservado.


## Retorno da comparação solicitada

O usuário forneceu nova saída de `identify-192 --inspect-routing` após a
orientação de voltar do Windows mantendo a 192 ligada. A saída não contém
registro da alimentação nem confirmação separada de áudio no Pro Tools;
a condição física depende do procedimento seguido pelo usuário.

As duas passagens concordam e são iguais às leituras anteriores:

| Campo | Antes | Nova leitura |
| --- | --- | --- |
| Identidade / firmware PCIe | d400 / 01050040 | d400 / 01050040 |
| IDs dos módulos | 14 13 15 13 | 14 13 15 13 |
| Registros 0x11, 0x12, 0x13 | 49, 01, 01 | 49, 01, 01 |
| Controles 0..3 | 02, 00, 00, 00 | 02, 00, 00, 00 |
| Rotas 0x40..0x5d | todas zero | todas zero |

`ROUTING_READS_STABLE=yes`, identificação confirmada e PCI COMMAND
restaurado. Nenhuma escrita de controle do periférico foi enviada.
Isso não demonstra retenção de toda a configuração Windows, nem exclui
estado digital fora das consultas. Também não confirma lock ADAT.

Como os valores consultados correspondem às pré-condições do ensaio já
compilado, o próximo passo é repetir somente o par 1–2 do gabinete, sem
novo ciclo de energia ou inicialização do duplex:

```sh
sudo ./linux-research/run-adat-test.sh enclosure 1 1
```

Manter OUT → IN nos conectores ópticos fixos do gabinete, 48 kHz e
monitores mutados. O teste dura 10 s e confere novamente suas pré-condições;
a leitura acima não substitui as verificações de segurança do módulo.
Usar o mesmo código e os mesmos critérios permite comparar com a sessão
`adat-test-ccAo1q`. Sucesso demonstrará retorno nesse estado, ainda sem
provar inicialização a frio. Nova falha não deve gerar repetições idênticas:
será necessário investigar outra hipótese de inicialização/roteamento.


## Nova captura: retorno alterado, ainda sem aprovação ADAT

A sessão `adat-test-Q0e1ud` trouxe atividade correspondente ao padrão TX,
mas com amostras alteradas, DC e sete amostras próximas do limite digital.
Zero XRUNs e restauração completa não tornam esse áudio válido. A análise
identificou 750/1500 Hz nas janelas isoladas e diferenças de bits frente ao
gerador C. O usuário esclareceu que na última ida ao Windows apenas
configurou ADAT; falta a gravação de controle desse loopback no Pro Tools.
Veja [evidência e procedimento com WAV de referência](adat-corrupted-return.md).
