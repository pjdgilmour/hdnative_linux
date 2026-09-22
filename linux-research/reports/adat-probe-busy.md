# ADAT: recusa de probe após uso no Windows

Sessão `adat-test-phjU44`: `insmod` falhou com `-16` (`EBUSY`), antes
anunciar ALSA ready e antes de iniciar a captura. Não existe gravação nova.
O cabeçalho PCI foi restaurado e a placa ficou desvinculada. Não confundir
essa recusa com um novo resultado de áudio corrompido ou com XRUN.

## Por que a mensagem é insuficiente

O probe de `avid_native_adat` pode receber EBUSY de várias etapas:
verificação de PCI bus master, reserva de recursos, `quiet_state`, transação
DigiLink e chamadas subsequentes do kernel. O log registra apenas o código.
A mensagem de habilitação PCI mostra que a recusa ocorreu depois da
verificação inicial de bus master. Não é possível localizar a etapa exata
somente pela mensagem `probe failed: -16`.

`quiet_state` exige controle do núcleo `0xa00`, reset/DigiLink/DMA/IRQ
zerados e seis registradores de endereço DMA zerados. O controle do
periférico também exige a caixa de comandos do slot 0 ociosa. Ter placa
PCI desvinculada não garante esses estados. Um endereço residual é uma
possibilidade a medir, não um diagnóstico já confirmado.

## Diagnóstico preparado

```sh
cd /home/paulo/hdnative_linux
sudo ./linux-research/identify-192 --inspect-transport
```

O novo modo lê 17 registros MMIO fixos em duas passagens, exibindo nome,
valor, máscara e valor esperado pelas guardas existentes. Inclui identidade,
firmware, núcleo/reset, link, DMA/IRQ, seis campos de endereço DMA e a caixa
de comandos do slot 0. `match=no` localiza uma pré-condição atualmente
diferente. A estabilidade compara os valores inteiros das duas leituras.

Esse modo não consulta a 192 pelo DigiLink e não escreve no BAR, não
inicia DMA/áudio, não zera endereços nem faz reset. Reutiliza as guardas
PCI, identidade/firmware e restauração já existentes no utilitário. O único
ajuste temporário de configuração PCI é habilitar acesso à memória, se
necessário, com restauração de PCI COMMAND. Recusa driver vinculado ou
bus mastering previamente ativo.

As leituras completas terminam com `TRANSPORT_SNAPSHOT_COMPLETE=yes`.
`TRANSPORT_PRECONDITIONS_MATCH` trata apenas dos registros listados: não
confirma lock óptico, controles da 192, estabilidade futura nem todas as
condições para o probe. Também não determina retroativamente a causa de
um EBUSY. Se todas corresponderem, será necessário instrumentar a etapa
de recusa; não remover as guardas para tentar passar.

## Validação

Compilado com `-std=c11 -O2 -Wall -Wextra -Werror`. Teste com backend MMIO
simulado verifica as 34 leituras e seus endereços, inverte individualmente
todos os bits de cada registro e confere as máscaras. A função de snapshot
não recebe backend de escrita. Conferida a saída do ramo especial para a
restauração PCI antes das consultas DigiLink normais.

Nenhum módulo de áudio, guarda do kernel, firmware ou critério de aceitação
foi alterado. Nenhum acesso ao BAR foi executado para esta preparação.
O usuário deve manter a 192 ligada e enviar a saída completa, sem repetir
o teste de áudio ou normalizar o estado antes dessa leitura.

Reprodução offline:

```sh
python3 linux-research/tools/test_transport_snapshot.py
cc -std=c11 -O2 -Wall -Wextra -Werror \
  linux-research/tools/identify_192.c -o /tmp/identify-192
```
