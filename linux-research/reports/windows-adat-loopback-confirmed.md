# Controle Windows: loopback óptico do gabinete

## Arquivos recebidos e contexto

O usuário forneceu `prefs_protools/adat_teste.wav` e `adat do chassi.png`,
relatando gravação no ADAT do gabinete e que manteve a 192 ligada ao voltar
do Windows para o Linux. Esta é uma nova gravação de controle; substitui
a pendência da etapa anterior, em que apenas havia configurado ADAT.
Os arquivos originais permanecem em `prefs_protools/`, ignorado pelo Git.

## Resultado da comparação PCM

- WAV estéreo PCM 24-bit/48 kHz, 464523 frames (9,6775625 s).
- **Os 929046 valores de amostra são idênticos à referência**, sem aplicar
  ganho, deslocamento temporal, troca de canais ou conversão de formato.
- A diferença de duração para a referência de 480000 frames é de 15477
  frames (0,3224375 s), todos no silêncio final. Todos os tons estão completos.
- Pico de ambos os canais: −40,000008 dBFS; nenhuma amostra próxima de clipping.
- O WAV de referência é o padrão C do módulo previamente verificado.

A igualdade refere-se ao payload PCM, não ao arquivo WAV inteiro: o Pro
Tools acrescentou metadados e o silêncio final foi encurtado. A comparação
não mede latência, pois o arquivo pode ter sido editado/alinhado na exportação.
A identificação do percurso físico depende do relato do usuário e do print;
a igualdade de um arquivo isolado não prova por si só o cabeamento.

Resultado reproduzível, parâmetros e hashes em
[windows-adat-loopback-result.json](windows-adat-loopback-result.json).

## Configuração visível

O print mostra 192 I/O #1, HD Native Port 1, clock **Internal**, 48 kHz:

| Transporte lógico | Entradas | Saídas |
| --- | --- | --- |
| 1–8 | Analog 1–8 | Analog 1–8 |
| 9–16 | Optical 1–8 (ADAT) | Optical 1–8 |

Digital Format está em AES/EBU, compatível com os ópticos do gabinete em
ADAT conforme o caminho DSI rastreado. Ext. Clock Output: Word Clock (48 kHz).
O print anterior mostrava saídas 9–16 em **Digital 1–8**; o novo mostra
**Optical 1–8**. Não confundir o módulo DIGITAL I/O com o óptico do gabinete.

O arquivo DSIPrefs recebido anteriormente continua com SHA256
`823b7c8461a492086507d14d435c93484d97ddba2f637e718dea72e460d63558`:
não foi substituído por novas preferências. Portanto, aquele roteamento
salvo não deve ser apresentado como a configuração deste novo print.

## Implicação e próximo ensaio

O retorno Windows fornecido é íntegro. Sob o percurso físico informado,
isso confirma que esse par de portas/cabo consegue transportar o padrão
corretamente. Fortalece a investigação da inicialização/transporte Linux;
não localiza ainda a causa das amostras alteradas em `adat-test-Q0e1ud`.
Não atribuir o problema a um defeito do cabo, nem tentar corrigir as
amostras por máscaras ou ganho com base somente nesses dados.

Com a 192 ainda ligada e o mesmo cabo, repetir **um único par** com o
mesmo módulo e os mesmos critérios permite avaliar a nova condição após
reprodução/captura efetiva do gabinete no Windows:

```sh
cd /home/paulo/hdnative_linux
sudo ./linux-research/run-adat-test.sh enclosure 1 1
```

Preservar 48 kHz e OUT → IN dos conectores fixos, monitores mutados e
aplicativos fechados; não iniciar o duplex antes. O ensaio dura 10 s e
restaura rotas/mute/PCI ao terminar. Caso recuse o estado inicial, enviar a
saída sem forçar a execução. A pré-condição é verificada pelo próprio teste.

O build foi conferido pelo manifesto de hashes. Nenhum módulo foi
recompilado, carregado ou modificado nesta análise. O resultado Linux
permanece pendente; a contraprova Windows não aprova canais Linux.
