---
name: carga-cognitiva-memoria
description: Registro e histórico da carga cognitiva do humano entre sessões. Use para gravar eventos quando não há hook, registrar a autoavaliação de cansaço, ler o resumo das últimas sessões no início de um trabalho, ou verificar se os pesos da fórmula estão calibrados.
---

# Carga cognitiva — memória

Esta skill cuida do que fica gravado: os eventos de cada sessão, as autoavaliações do humano e o histórico que permite comparar o score com o que ele de fato sentiu.

Tudo fica em um arquivo JSONL na pasta de dados (`$CARGA_DIR`, ou `~/.carga-cognitiva` se a variável não existir). Um evento por linha. Não edite o arquivo à mão; use o CLI.

Sem `carga` no PATH, troque `carga` por `python -m carga_cognitiva`, a partir da raiz do repositório.

## Registrar eventos

Quando o orquestrador tem hook pós-resposta, ele já grava. Use estes comandos só quando não houver hook, ou para eventos que o hook não enxerga.

| Aconteceu | Comando |
| --- | --- |
| Uma thread entregou uma resposta ao humano | `carga registrar --thread NOME --linhas N` |
| A resposta pede decisão ou aprovação | acrescente `--decisao` |
| O humano corrigiu ou mandou refazer algo | `carga registrar --thread NOME --retrabalho` |

Como preencher:

- `--thread`: um nome estável por frente de trabalho (`specify`, `implement-auth`, `review-pr-12`). Trocar de nome entre eventos consecutivos conta como troca de contexto, então não varie o nome da mesma frente.
- `--linhas`: quantas linhas o humano precisa ler para responder (resumo, diff, spec). Não conte o que ele não vai ler.
- `--decisao`: só quando a resposta espera uma escolha dele. Pergunta retórica ou "posso continuar?" de rotina não conta.
- `--retrabalho`: quando ele rejeita ou corrige o que foi entregue. Um ajuste de preferência novo, que ele não tinha dito antes, não é retrabalho.

## Autoavaliação

Ao fim de uma sessão (ou quando o coordenador pedir, na faixa vermelha):

```bash
carga feedback 4      # 1 descansado … 5 exausto
```

A nota vem do humano. Nunca escolha uma nota por ele nem a deduza do tom das mensagens. O comando grava a nota junto com o score do momento.

## Início de sessão

Antes de começar um trabalho longo, leia o histórico:

```bash
carga resumo --dias 7
```

Uma linha por sessão: duração, score final, faixa, contagens, alertas emitidos e a nota (se houve). Use para planejar, por exemplo: se as últimas sessões terminaram em vermelho com muitas trocas de thread, proponha trabalhar em menos frentes ao mesmo tempo. Não comente o histórico se ele não mudar o plano.

## Calibração

Os pesos padrão são um ponto de partida, não um resultado medido. Para saber se servem para esta pessoa:

```bash
carga calibrar
```

O comando mostra o score médio por nota e a concordância entre nota e score (quantos pares de sessões estão na ordem esperada: nota maior, score maior).

Como ler:

- Menos de 10 amostras: não conclua nada. Continue coletando.
- Concordância alta (acima de ~80%): os pesos estão ordenando bem as sessões. Ajuste, no máximo, os limites das faixas para que "amarelo" comece perto do score médio da nota 3.
- Concordância baixa: olhe as sessões fora de ordem com `carga resumo --json` e veja qual componente as distingue (por exemplo, sessões nota 5 com poucas decisões e muitas trocas sugerem `peso_troca` baixo).

Proponha a mudança ao humano com os números. Só ele altera `config.json` na pasta de dados (ou autoriza você a alterar). Chaves aceitas e valores em vigor: `carga config`.

## Limites conhecidos

- O score zera depois de 30 minutos sem eventos. Cansaço real não zera assim; a carga de sessões anteriores no mesmo dia não é somada.
- Trabalho feito fora das threads (reunião, leitura, outro projeto) não aparece.
- Linhas revisadas é um chute de volume, não de dificuldade: 50 linhas de migração de banco pesam mais que 50 de README.
