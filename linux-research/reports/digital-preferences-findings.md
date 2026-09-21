# Controles digitais: consultas sem resposta e investigação do DSIPrefs

## Resultado real do diagnóstico revisado

Os registros candidatos banco 1, `0x30`, `0x31` e `0x32` retornaram timeout
nas duas passagens: seis tentativas, todas com `result=1`,
`value=unavailable`, `cleanup=0`. Identidade e controles comuns da 192
continuaram respondendo, com módulos `14 13 15 13` e controle0=2.
PCI COMMAND foi restaurado. Não houve WRITE no periférico.

Não há configuração digital válida obtida por esse caminho no estado
atual. Não repetir as mesmas consultas como tentativa de inicialização.
Esse resultado não prova que os registros sejam sempre somente escrita,
que o módulo tenha defeito ou que precise de atualização de firmware.

## Origem do bloco de configuração Windows

DSI.dll do pacote Pro Tools 2026.4.1, SHA256
`60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34`.
Endereços são RVAs, base PE 0x180000000:

1. `0x1aea30` solicita 0x6c bytes a `0x0875b0`.
2. `0x0875b0` chama `0x080910`, que obtém a estrutura singleton por
   `0x08a9c0` e consulta por `0x08aa40`.
3. `0x08aa40` carrega a estrutura por `0x08ae00`, busca uma chave na árvore,
   confere o tamanho do bloco e copia seus bytes para o destino.
4. `0x08a770` chama o import CFnd `GetPreferencesFolderLoc`, constrói o nome
   **DSIPrefs** (constante em `0x08a7f8`) e cria `Sys_File` para esse caminho.
5. `0x08ae00` usa os imports `Sys_FileBasedInStream`,
   `Sys_LittleEndianInStream` e `Sys_StdStreamHeaderReader` com tag **DSETUP**
   (ponteiro global em RVA 0x9ae008 → string RVA 0x7654d4).

Isso identifica preferências persistidas como origem desse caminho, e não
leitura direta dos controles pelo DigiLink. Um arquivo encontrado pode
estar antigo, conter outros dispositivos ou refletir outra sessão. Ele é
evidência auxiliar e não basta, sozinho, para prometer restauração do
estado digital atual da 192.

A [documentação Avid sobre preferências](https://kb.avid.com/pkb/articles/en_US/How_To/How-to-Trash-Pro-Tools-Preferences)
localiza a pasta Windows em `Users/<usuário>/AppData/Roaming/Avid/Pro Tools`.
Aqui buscamos apenas ler DSIPrefs; os procedimentos de exclusão/reset
citados nessa página não fazem parte desta investigação.

## Leitor offline

`tools/inspect_dsi_prefs.py` não acessa hardware nem altera arquivos:

```sh
python3 linux-research/tools/inspect_dsi_prefs.py /caminho/para/DSIPrefs
```

Formato rastreado: tag de seis bytes `DSETUP`, versão uint16, tamanho uint32;
payload contendo contagem uint32 e registros com tamanho uint32, chave
uint64 e bytes. Todos os inteiros são little endian. No CFnd.dll,
`Sys_StdStreamHeaderReader` (RVA 0x31b000) lê tag, versão e tamanho;
`SkipTheRest` (0x31b3c0) calcula o final a partir do início do payload.
O laço DSI em `0x08ae00` lê contagem, tamanho, chave e conteúdo dos registros.

O leitor verifica limites, truncamento e duplicatas; informa a versão,
chaves, tamanhos e hashes. Só considera candidatos os registros de 108
bytes, exibindo os três bytes em offset 0x1f (0x0f + 8*2), usados pelo
módulo de índice 2 no decodificador já rastreado. Tamanho não identifica
uma 192: os campos de identidade e estado atual permanecem explicitamente
não verificados. O formato ainda precisa ser confrontado com um DSIPrefs
real. Testes sintéticos passaram; nada é escrito na interface.

## Acesso pendente

`lsblk` identificou uma partição NTFS com label Windows em `/dev/sde3`,
sem ponto de montagem. A tentativa via udisks com opção `ro` não foi
concluída: a autenticação polkit precisa do terminal local. O usuário foi
orientado a montar somente para leitura. Não houve montagem para escrita,
leitura de preferências nem reinicialização automática.

Os controles digitais continuam sem escrita até obter evidência suficiente
sobre a configuração e a sequência de seleção. A validação analógica e os
módulos de áudio permanecem preservados.
