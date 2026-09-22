# Teste ADAT de rotas ópticas — ainda sem validação Linux

**Primeiro resultado:** o perfil `enclosure`, par 1–2, não recebeu os tons
na sessão `adat-test-ccAo1q`. A 192 havia sido desligada e religada depois
do Windows. Transporte e restauração passaram, mas o ensaio óptico falhou.
Veja a [análise do estado após desligamento](adat-cold-start-review.md)
e a comparação proposta mantendo a interface ligada. Os demais pares e
o perfil `module` continuam pendentes.

O usuário confirmou funcionamento de reprodução/captura pelos dois conjuntos
ópticos no Windows, e esclareceu que na sessão das preferências apenas
configurou a interface. O ensaio Linux preparado aqui usa rotas distintas
para testar esses caminhos físicos com um cabo óptico OUT → IN.

## Escopo

- Módulo separado `avid_native_adat`, manual e temporário. O duplex validado
  e os testes analógicos não foram alterados.
- 48 kHz, S24_3LE, transporte lógico estéreo; um par físico por execução.
- Tons de 750/1500 Hz, separados no tempo e depois juntos, pico −40 dBFS.
  Gravação de 10 s, watchdog do módulo 15 s, timeout do gravador 18 s.
- Sem monitoração da entrada, atualização de firmware, escrita de clock,
  seleção ADAT/S/PDIF/AES ou alteração de SRC. Não instala serviço/ALSA
  permanente nem modifica PipeWire.
- Usa a seleção digital existente. Preferências Windows não são aplicadas
  à placa. Retorno ausente pode indicar formato, lock ou roteamento ainda
  não inicializado, não um defeito da porta.

## Perfis candidatos

| Argumento | Cabo físico | RX lógico 1–2: reg. 0x41 | Destino TX lógico 1–2 |
| --- | --- | --- | --- |
| `enclosure` | OUT → IN, óptico fixo do gabinete | 25..28 (pares 1..4) | reg. 0x59..0x5c = 1 |
| `module` | OUT → IN, placa DIGITAL I/O | 17..20 (pares 1..4) | reg. 0x51..0x54 = 1 |

Base estática: tabela de 30 rotas, registro `0x40 + destino`, DSI RVA
`0x1af1d0`; endpoints modulares 9..24 em `0x1aa0d0`; preferências reais e
prints em [Windows/ADAT](windows-adat-preferences.md). A correspondência
óptica final depende deste ensaio com cabeamento conhecido. Não confundir
índices internos de pares com canais físicos individuais.

O helper aceita apenas os IDs `14 13 15 13`, os controles comuns do estado
quieto já observado (2,0,0,0), e uma tabela de rotas inicialmente zerada.
Verifica os registros em duas passagens. Se encontrar estado diferente,
recusa o ensaio, registra o último valor esperado/observado e não tenta
normalizar a interface. A lista de escritas permite somente mute 0↔2,
RX 0↔fonte do par e TX 0↔1. Não permite acesso aos controles `0x30..0x32`.
As rotas são restauradas mesmo após perda de ACK; falhas de restauração
invalidam o resultado. Falha de drenagem PCI mantém módulo/memória presos
para impedir liberação de buffers ainda em uso.

## Execução

Feche os aplicativos usando a placa. Salve o trabalho, deixe os monitores
mutados e a 192 em 48 kHz com clock interno. É código experimental de kernel.
Pare o duplex se estiver ativo; o teste recusa placa ocupada:

```sh
sudo ./linux-research/duplex-driver.sh stop
```

Conecte OUT → IN no **óptico do gabinete** e execute:

```sh
sudo ./linux-research/run-adat-bank-test.sh enclosure
```

A sequência testa 1→1, 2→1 (isolamento), 1→2 (isolamento), 2→2, 3→3 e
4→4, sem mover o cabo. São seis execuções de 10 s com restauração e remoção
entre elas; a primeira falha interrompe tudo. Pares 1..4 significam canais
1–2, 3–4, 5–6 e 7–8. Depois de concluir e remover o módulo, mova o cabo
para OUT → IN **da placa DIGITAL I/O**, e use:

```sh
sudo ./linux-research/run-adat-bank-test.sh module
```

Diagnóstico limitado a um par (saída, entrada):

```sh
sudo ./linux-research/run-adat-test.sh enclosure 1 1
sudo ./linux-research/run-adat-test.sh module 1 1
```

Se um teste falhar, preserve o relatório; não interprete silêncio como
sucesso. A configuração automática do módulo digital é trabalho posterior.

## Aceitação e limites

Cada execução salva perfil, WAV/raw, análise, estatísticas, hashes,
log do módulo e cabeçalhos PCI antes/depois em `reports/adat-test-*/`.

Um par positivo exige padrão temporal/frequências correto e amplitude dos
tons entre −43 e −37 dBFS. As contraprovas exigem ausência dos tons e RMS
inferior a −65 dBFS no intervalo 1–9 s; transientes nas bordas são relatados
separadamente, e clipping invalida o teste. Também são obrigatórios zero
XRUN/erro, um start/stop, mute/rotas restaurados, módulo removido, cabeçalho
PCI igual e placa desvinculada. A mensagem final é emitida após cleanup.

`ADAT_BANK_SEQUENCE_PASSED=yes` cobre quatro pares sequenciais e as duas
contraprovas, vinculados ao cabo informado. Não prova oito canais
simultâneos, operação bit-perfect, latência, jitter, todos os cruzamentos,
inicialização a frio ou todos os formatos digitais.

## Validação offline

Compilado com W=1 para 6.12.107+deb13-amd64. Simulações dos 32 perfis
(2 caminhos × 4 saídas × 4 entradas), lista de escritas, ACK perdido,
escrita ignorada, falha de restauração, controles/topologia inesperados;
ring/tons e lifecycle herdados testados; cinco testes de análise/aceitação
incluem silêncio, canais trocados, retorno fraco e restauração incompleta.
Sintaxe dos scripts validada. Não houve carregamento ou teste físico nesta etapa.

Para outro kernel ou depois de editar dependências:

```sh
./linux-research/build-adat.sh
```

O manifesto de build confere hashes e kernel antes de carregar o módulo.
