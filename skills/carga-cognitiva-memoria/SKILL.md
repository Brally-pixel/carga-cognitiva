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
| A thread terminou o que fazia | acrescente `--concluida` |
| O humano aprovou o pedido pendente da thread | `carga registrar --thread NOME --aprovacao` |
| O humano corrigiu ou mandou refazer algo | `carga registrar --thread NOME --retrabalho` |

Como preencher:

- `--thread`: um nome estável por frente de trabalho (`specify`, `implement-auth`, `review-pr-12`). Trocar de nome entre eventos consecutivos conta como troca de contexto, então não varie o nome da mesma frente.
- `--linhas`: quantas linhas o humano precisa ler para responder (resumo, diff, spec). Não conte o que ele não vai ler.
- `--decisao`: só quando a resposta espera uma escolha dele. Pergunta retórica ou "posso continuar?" de rotina não conta.
- `--concluida`: quando a thread chegou a um ponto de fechamento e não deixa nada pendente. Uma nova resposta ou um retrabalho na mesma thread a reabre.
- `--aprovacao`: registre no momento em que ele aprova, não depois. O tempo entre o pedido e a aprovação é o que permite detectar aprovação sem leitura.
- `--retrabalho`: quando ele rejeita ou corrige o que foi entregue. Um ajuste de preferência novo, que ele não tinha dito antes, não é retrabalho.

## Autoavaliação

Ao fim de uma sessão (ou quando o coordenador pedir, na faixa vermelha):

```bash
carga feedback 4                              # 1 descansado … 5 exausto
carga feedback 4 --demanda 5 --frustracao 2   # opcionais, também de 1 a 5
```

As notas vêm do humano. Nunca escolha uma nota por ele nem a deduza do tom das mensagens. O comando grava as notas junto com o score do momento.

`--demanda` é o quanto a sessão exigiu de raciocínio; `--frustracao`, o quanto irritou ou travou. Pergunte por elas só se ele quiser dar mais detalhe; a nota principal basta para calibrar.

## Início de sessão

Antes de começar um trabalho longo, leia o histórico e o estado atual:

```bash
carga resumo --dias 7
carga pontuar
```

`resumo` traz uma linha por sessão: duração, score final, faixa, residual herdado, contagens, aprovações rápidas (`auto`), alertas emitidos e a nota (se houve). `pontuar`, sem sessão ativa, mostra a carga residual da sessão anterior: se ela terminou há pouco, a nova já começa com parte daquela carga.

Use para planejar. Exemplos: se as últimas sessões terminaram em vermelho com muitas trocas de thread, proponha trabalhar em menos frentes ao mesmo tempo; se há residual alto, comece pelo que exige menos decisões. Não comente o histórico se ele não mudar o plano.

## Calibração

Os pesos padrão são um ponto de partida, não um resultado medido (`docs/REFERENCIAS.md` lista o que tem base em estudo e o que não tem). Para saber se servem para esta pessoa:

```bash
carga calibrar
```

O comando mostra o score médio por nota e a concordância entre nota e score (quantos pares de sessões estão na ordem esperada: nota maior, score maior).

Como ler:

- Menos de 10 amostras: não conclua nada. Continue coletando.
- Concordância alta (acima de ~80%): os pesos estão ordenando bem as sessões. Ajuste, no máximo, os limites das faixas para que "amarelo" comece perto do score médio da nota 3.
- Concordância baixa: olhe as sessões fora de ordem com `carga resumo --json` e veja qual componente as distingue (por exemplo, sessões nota 5 com poucas decisões e muitas trocas sugerem `peso_troca` baixo).
- Aprovação no automático: compare `aprovacoes_automaticas` com a nota. Se as sessões com muitas aprovações rápidas não forem as de nota alta, o limite `limite_ritmo_aprovacao` está baixo demais para esta pessoa, ou o sinal não diz nada sobre ela.

Proponha a mudança ao humano com os números. Só ele altera `config.json` na pasta de dados (ou autoriza você a alterar). Chaves aceitas e valores em vigor: `carga config`.

## Limites conhecidos

- A carga cai pela metade a cada 30 minutos de pausa. Esse ritmo é uma escolha do projeto, não uma medida da pessoa.
- Trabalho feito fora das threads (reunião, leitura, outro projeto) não aparece.
- Linhas revisadas é um chute de volume, não de dificuldade: 50 linhas de migração de banco pesam mais que 50 de README.
- Um intervalo entre eventos dentro da sessão não é contado como descanso.
