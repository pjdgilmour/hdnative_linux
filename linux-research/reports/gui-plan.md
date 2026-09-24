# Painel de configuração da 192: direção acordada

O proprietário pediu uma GUI depois da consolidação do driver, usando as
telas Hardware Setup do Pro Tools fornecidas em `prefs_protools` como
referência de organização. Esta é a especificação inicial, não uma GUI
implementada nem a promessa de controles já disponíveis no Linux.

## Organização

- Dispositivo e módulos instalados: lista de interfaces, porta DigiLink,
  inventário AD/DA/digital/DA deste exemplar, identificação e estado.
- Geral: clock, taxa, roteamento independente de entradas e saídas por par,
  distinguindo claramente Optical do gabinete e Digital do módulo.
- Analog In: canais 1–8, nível de referência, trim e Soft Clip, quando
  existir suporte validado a cada controle.
- Analog Out 1–8 e Analog Out 9–16: abas separadas conforme os módulos;
  trim e opções somente conforme suporte real.
- Digital: formato do módulo e SRC por par. A seleção de formato e o
  roteamento da aba Geral são operações diferentes.
- Diagnóstico: estado de reprodução/captura, XRUNs, erros e exportação de
  logs sem credenciais. Preferências salvas não devem aparecer como se
  fossem uma leitura atual do hardware.

As capturas 000458 e 000625 foram examinadas visualmente: a primeira mostra
roteamento por pares, clock e formato comum; a segunda mostra formato do
módulo e SRC. As capturas 000543 e 000600, descritas no relatório de
preferências, registram as opções analógicas. Não há print detalhado da
aba da segunda DA, portanto seu conteúdo ainda não foi presumido.

## Implementação após o driver

A GUI deve funcionar como usuário normal. O backend do driver precisa
expor uma interface explícita para consultar capacidades/estado e aplicar
somente controles suportados, preferindo controles ALSA para funções
apropriadas. Evitar comandos arbitrários ou execução da GUI inteira como
root. Não armazenar senhas sudo em arquivos, perfis ou código.

Enquanto o driver depender do estado Windows, apresentar isso claramente.
Leituras indisponíveis devem ser indicadas como desconhecidas, sem valores
inventados. Clock, SRC, trim e inicialização digital ainda precisam de
implementação/validação antes de oferecer controles ativos na GUI.

Aplicar alterações com verificação do estado e tratamento de falhas, sem
mudar clock ou rotas por simples abertura de uma aba. Salvar perfis somente
quando a restauração dos respectivos controles estiver implementada.

## Ordem

1. Concluir caminhos físicos e inicialização digital.
2. Validar transporte multicanal simultâneo e ciclo de vida do driver.
3. Expor capacidades/controles estáveis no backend.
4. Implementar e testar o painel com a organização acima.
