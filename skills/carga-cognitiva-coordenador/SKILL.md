---
name: carga-cognitiva-coordenador
description: Para quem coordena threads/agentes com um humano no loop. Use antes de pedir uma decisão ao humano, ao receber um alerta de carga cognitiva, ou quando perguntarem "como está minha carga?". Consulta o score da sessão e ajusta o ritmo por faixa (verde, amarelo, vermelho).
---

# Carga cognitiva — coordenador

Você coordena o trabalho de uma ou mais threads e é quem leva pedidos ao humano. Esta skill diz como consultar a carga cognitiva acumulada dele na sessão e o que mudar no seu comportamento em cada faixa.

O score é uma estimativa por sinais indiretos (decisões pedidas, trocas de thread, retrabalho, linhas revisadas, tempo de sessão). Ele não mede cansaço. Apresente-o sempre como estimativa e deixe a decisão final com o humano.

## Consultar

```bash
carga pontuar --json
```

Resposta (campos principais):

```json
{"score": 49.5, "faixa": "amarelo", "minutos": 150.0, "fator_tempo": 1.5,
 "decisoes": 12, "trocas": 4, "retrabalhos": 3, "linhas": 800, "threads": ["A", "B", "C"]}
```

Sem `carga` no PATH, use `python -m carga_cognitiva pontuar --json` a partir da raiz do repositório.

Consulte:

- antes de levar ao humano um pedido de decisão ou aprovação;
- antes de abrir uma thread ou frente nova;
- quando o hook do orquestrador entregar um alerta (texto que começa com "Carga cognitiva em AMARELO/VERMELHO");
- quando o humano perguntar pela carga.

## O que fazer em cada faixa

### Verde (abaixo de 30)

Trabalhe normalmente. Não mencione a carga.

### Amarelo (30 a 59)

1. Avise uma vez, em uma linha, com o score e o componente que mais pesa (por exemplo: "carga em 49,5, puxada por 4 trocas de thread e 3 retrabalhos").
2. Junte as decisões pendentes em um único pedido, em vez de uma por resposta.
3. Não abra thread nova; termine ou estacione as que estão abertas.
4. Reduza o que o humano precisa ler: resumo primeiro, diff completo só se ele pedir.

### Vermelho (60 ou mais)

1. Avise com o score e os números da sessão.
2. Não peça decisões irreversíveis (merge em branch principal, deploy, exclusão de dados, envio externo). Deixe-as registradas como pendentes.
3. Grave um checkpoint: estado de cada thread, o que está pendente e qual é a próxima ação de cada uma.
4. Proponha uma pausa de pelo menos 30 minutos. Uma pausa desse tamanho sem eventos encerra a sessão e zera o score.
5. Peça a autoavaliação: `carga feedback NOTA` (1 descansado … 5 exausto). Isso alimenta a calibração.

Se o humano disser para continuar mesmo assim, continue. Mantenha os itens 2 e 3 até ele liberar explicitamente uma decisão irreversível específica.

## Regras

- Não repita o alerta a cada resposta. O comando `carga alerta` já aplica um intervalo mínimo de 20 minutos por faixa; se ele não imprimir nada, não há alerta novo.
- Não altere `config.json` nem os pesos por conta própria. Mudança de peso é decisão do humano (ver a skill `carga-cognitiva-memoria`, seção de calibração).
- Não atribua causa ao score ("você está cansado porque…"). Relate os números.

## Se os eventos não estão sendo gravados

Se `carga pontuar` responder "Sem sessão ativa" no meio do trabalho, o hook do orquestrador não está registrando. Registre você mesmo a cada resposta que levar ao humano, conforme a skill `carga-cognitiva-memoria`.
