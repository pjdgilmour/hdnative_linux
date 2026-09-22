# Preferências Windows e ADAT — 2026-09-21

## Evidência recebida

Cópia local `prefs_protools/DSIPrefs`: 3088 bytes, SHA256
`823b7c8461a492086507d14d435c93484d97ddba2f637e718dea72e460d63558`.
O leitor validou DSETUP versão 1, nove registros, sem bytes residuais.
Não existe registro de 108 bytes nesta cópia. A configuração está no
registro **K016**, chave `4b30313600002200`, payload de 1024 bytes no
offset `0x6dc`. Os arquivos recebidos são entradas locais ignoradas pelo Git.

Prints `Captura de tela 2026-09-21 <hora>.png`:

| Hora | Observação na tela | SHA256 |
| --- | --- | --- |
| 000458 | 192 I/O #1, HD Native Port 1, clock Internal, 48 kHz; quatro abas de módulos | `d0c56c2cd1292ca6617c57f13be998879cb87c693e8317bf3f5008567d65119e` |
| 000543 | Analog In: oito canais +4 dBu, trim A, Soft Clip marcado | `563063348870935f22af0da6587e50aa360bb89571dfec29806e7bab2bb2ac5e` |
| 000600 | Analog Out 1–8: trim A nos oito canais | `a7ec1bf22f6b8ab4334aa6517b478921580533c24c9675a121ddfe5b3a67eca0` |
| 000625 | Digital: ADAT 1–8 selecionado, SRC marcado nos quatro pares | `657d606371c92ea3b770f08958b0a06dea9d959bd20abccaf9b7ad03cf679366` |

Não há print do conteúdo da aba Analog Out 9–16. Os prints documentam
configuração da interface gráfica, não passagem de áudio nem lock óptico.

## Caminho de leitura e campos salvos

Referência estática: DSI.dll do pacote local 2026.4.1, SHA256
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`.
RVAs relativos à base PE `0x180000000`:

- `0x1a5380`, chamada em `0x1a53e9`: busca 1024 bytes, prefixo `K`.
- `0x0875b0` usa formato `%c%03d` para compor o identificador do modelo.
  A chave contém `K016`, compatível com o modelo DSI 16 da 192.
- Depois de cinco pares nome/valor, `0x1a5659` chama virtual `+0x88`.
  A vtable `0x778390` contém `0x1aeae0` nesse slot (`0x778418`).
- `0x1aeae0` lê `sc`: quatro tipos de módulos e quatro valores comuns;
  `xp`: 30 entradas; depois `card`, via virtual `+0x38`, e `leg`.
- Vtable digital `0x7787d0 + 0x38` aponta para `0x1b1240`: cinco números
  lidos para campos do objeto `+0x18,+0x1c,+0x20,+0x24,+0x28`.

O leitor reconhece estritamente o layout observado `sc 3 4 5 4`,
compatível com AD/DA/digital/DA; outras topologias não são decodificadas.
O trecho digital é `card 2 0 0 3 15 1`:

| Campo do objeto | Valor salvo | Interpretação sustentada |
| --- | --- | --- |
| +0x18 | 0 | Campo bruto; sem novo significado atribuído |
| +0x1c | 0 | Campo bruto; sem novo significado atribuído |
| +0x20 | 3 | Seleção de fonte; associação a ADAT por correlação com print 000625 |
| +0x24 | 15 | Máscara SRC dos quatro pares, consistente com as quatro caixas marcadas |
| +0x28 | 1 | Campo bruto preservado no relatório |

São campos de software, **não os bytes dos registros `0x30..0x32`**.
O decoder de 108 bytes estudado antes é outro caminho; não aplicar seu
offset 0x1f a este texto. Preferências não são leitura do hardware atual.

## Seleção do módulo e roteamento óptico são distintos

Na aba Main, entradas lógicas 1–8 estão em Analog 1–8 e entradas 9–16 em
Optical 1–8 (ADAT). Saídas 1–8 mostram Analog 1–8 (a primeira tem prefixo
`+`); saídas 9–16 mostram Digital 1–8.

No estado salvo, `xp[1..4] = 9,10,11,12` e `xp[5..8] = 25,26,27,28`.
Os destinos `xp[13..16] = 1,2,3,4`, `xp[17..20] = 5,6,7,8`, e
`xp[21..24] = 0,0,0,0`, compatíveis com as seleções visíveis.
Demais entradas estão no JSON do leitor. Não copiar a tabela inteira
para hardware como receita de inicialização.

O mapeador `0x1aa0d0` associa endpoints 9–24 aos quatro módulos; o módulo
digital de índice 2 ocupa **17–20**. As fontes salvas **25–28** são outro
caminho. Pela correlação entre tabela, print e documentação, correspondem
ao óptico do gabinete, não ao input do módulo digital.

O [192 I/O Guide, páginas impressas 8–9](https://m.barryrudolph.com/recall/manuals/avid_192_manual.pdf)
distingue o ADAT dedicado do módulo do óptico do gabinete, que também pode
ser S/PDIF. O módulo dispõe de conversão de taxa na entrada; o gabinete não.
Selecionar ADAT na aba Digital não garante o roteamento desse input na Main.

## Validação e próximo ensaio

- Leitor executado no arquivo real; 13 testes offline passaram, incluindo
  truncamento, limites, ordem/topologia, padding e estado não verificado.
- Nenhum módulo carregado e nenhuma consulta ou escrita na placa nesta análise.
- O usuário esclareceu: a sessão dos prints foi apenas de configuração,
  mas ele já consegue capturar/reproduzir pelos dois conjuntos ópticos no
  Windows. Validação ADAT no Linux continua pendente.
- Foi preparado um [ensaio de rotas ópticas](adat-route-test.md) que
  preserva a seleção digital atual e testa separadamente gabinete e módulo.
  Inicialização digital continua fora do escopo; ausência de retorno é
  inconclusiva. Não repetir as seis consultas sem resposta como readback.

Reproduzir a análise local:

```sh
python3 linux-research/tools/inspect_dsi_prefs.py prefs_protools/DSIPrefs
python3 linux-research/tools/test_dsi_prefs.py
```
