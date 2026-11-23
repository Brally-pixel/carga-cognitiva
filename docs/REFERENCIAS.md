# Referências e decisões de modelagem

Nenhum estudo valida uma fórmula composta como a deste projeto. O que existe é evidência separada para cada sinal, com forças diferentes. Este documento registra o que cada estudo diz, até onde ele sustenta a escolha feita no código, e o que continua sendo chute.

Os resumos abaixo são paráfrases; consulte os originais antes de citar números.

## Resumo

| Sinal no código | Evidência | Decisão |
| --- | --- | --- |
| Decisões (`peso_decisao`) | Fraca e contestada | Peso baixo (1) |
| Trocas de thread (`peso_troca`, `peso_troca_limpa`) | Moderada | Troca com pendência pesa o dobro da troca limpa |
| Volume e ritmo de revisão (`linhas_por_ponto`, `limite_ritmo`, `limite_linhas_resposta`) | Moderada, de um fornecedor | Limites de 200/400 linhas e 500 linhas/hora |
| Tempo de sessão (`tempo_*`) | Moderada | Multiplicador, não parcela própria |
| Pausas (`meia_vida_min`) | Boa (meta-análise) | Decaimento parcial em vez de zerar |
| Aprovação no automático (`limite_ritmo_aprovacao`) | Teoria sólida; dados com agentes mistos | Aviso, sem entrar no score |
| Autoavaliação (`carga feedback`) | Boa | Nota única de 1 a 5, com duas escalas opcionais |

## Decisões

**Danziger, Levav e Avnaim-Pesso (2011). Extraneous factors in judicial decisions. PNAS 108(17).**
<https://pmc.ncbi.nlm.nih.gov/articles/PMC3084045>

Analisa decisões de liberdade condicional de juízes experientes. A proporção de decisões favoráveis cai ao longo de cada sessão e volta ao patamar inicial depois de uma pausa. É o estudo mais citado sobre fadiga de decisão.

**Críticas e réplicas**

- Weinshall-Margel e Shapard (2011), com resposta dos autores: <https://pmc.ncbi.nlm.nih.gov/articles/PMC3198336>. A ordem dos casos não era aleatória (presos sem advogado ficavam para o fim de cada sessão), o que pode gerar o mesmo padrão.
- Glöckner (2016). The irrational hungry judge effect revisited. Judgment and Decision Making 11(6): <https://dlab.sauder.ubc.ca/sjdm/journal/16/16823/jdm16823.html>. Simulações indicam que o tamanho do efeito está superestimado.
- Estudo com audiências de custódia em um grande tribunal urbano: <https://par.nsf.gov//servlets/purl/10392253>. Encontra efeitos pequenos e que não combinam com a explicação por esgotamento.

**Hagger et al. (2016). A multilab preregistered replication of the ego-depletion effect. Perspectives on Psychological Science 11(4).** DOI 10.1177/1745691616652873

Replicação em 23 laboratórios (N = 2.141) do efeito de "esgotamento do autocontrole". O efeito medido ficou próximo de zero.

**Vohs et al. (2021). A multisite preregistered paradigmatic test of the ego-depletion effect. Psychological Science 32(10).**
<https://pubmed.ncbi.nlm.nih.gov/34520296/>

36 laboratórios (N = 3.531). As análises pré-registradas não encontraram o efeito. Em análise exploratória, ele foi maior entre quem relatou mais fadiga.

**No código:** decisões entram com o menor peso. O modelo não trata decisões como uma reserva que se esgota; elas contam como um sinal entre outros. A autoavaliação é mantida porque, no que sobrou do efeito, a fadiga relatada é o que parece importar.

## Trocas de thread

**Mark, Gudith e Klocke (2008). The cost of interrupted work: more speed and stress. CHI 2008.**
<https://www.ics.uci.edu/~gmark/chi08-mark.pdf> · DOI 10.1145/1357054.1357072

Experimento com tarefa de escritório interrompida. Pessoas interrompidas terminam mais rápido, mas relatam mais estresse, frustração, esforço e pressão de tempo (medidos com a escala da NASA). A quantidade de erros não mudou de forma significativa.

**Leroy (2009). Why is it so hard to do my work? The challenge of attention residue when switching between work tasks. Organizational Behavior and Human Decision Processes 109(2).**
Resumo da autora: <https://www.uwb.edu/business/faculty/sophie-leroy/attention-residue>

Ao trocar de tarefa, parte da atenção continua na anterior ("resíduo de atenção"), e o desempenho na tarefa seguinte cai. O efeito é maior quando a tarefa anterior ficou inacabada ou foi interrompida.

**Leroy e Glomb (2018). Tasks interrupted: how anticipating time pressure on resumption of an interrupted task causes attention residue and low performance on interrupting tasks and how a "ready-to-resume" plan mitigates the effects. Organization Science 29(3).**
Divulgação: <https://www.washington.edu/news/?p=56143>

Anotar, antes de trocar, onde parou e o que falta (um "plano de retomada") reduz o resíduo de atenção.

**No código:**

- A troca que deixa a thread anterior aberta pesa 2; a troca depois de `--concluida` pesa 1.
- O custo esperado é de carga sentida, não necessariamente de erro. Por isso o score é comparado com a autoavaliação, não com defeitos.
- A skill do coordenador pede o ponto de retomada de cada thread aberta já na faixa amarela.

## Volume e ritmo de revisão

**Cohen et al. (2006). Estudo de revisão de código na Cisco, publicado pela SmartBear em Best Kept Secrets of Peer Code Review.**
<https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/> · <https://agileconnection.com/article/largest-case-study-code-reviews-ever>

Dez meses, 2.500 revisões, 3,2 milhões de linhas, 50 desenvolvedores. Três achados usados aqui:

- A densidade de defeitos encontrados cai bastante acima de 200 linhas por revisão e fica perto de zero depois de 400.
- Revisar a mais de 500 linhas por hora reduz a detecção.
- Depois de cerca de 60 minutos de revisão contínua, o revisor deixa de encontrar defeitos.

**Limitações:** uma empresa, um produto, e o autor é um fornecedor de ferramenta de revisão. Os números são de revisão de código, não de leitura de resumos ou specs.

**No código:**

- `linhas_por_ponto = 200`: cada 200 linhas a revisar valem um ponto.
- `limite_linhas_resposta = 400`: uma resposta acima disso gera aviso para dividir.
- `limite_ritmo = 500` linhas/hora: o excesso sobre esse ritmo soma até `2 × peso_ritmo` pontos.
- O limite de 60 minutos não foi adotado como corte, porque a sessão mistura revisão com espera e outras atividades; o multiplicador de tempo começa em 90 minutos.

## Tempo de sessão

**Boksem e Tops (2008). Mental fatigue: costs and benefits. Brain Research Reviews 59(1).** DOI 10.1016/j.brainresrev.2008.07.001

Revisão que trata a fadiga mental como resultado de uma avaliação de custo e benefício do esforço, e não só de um recurso que acaba.

**Herlambang, Taatgen e Cnossen (2019). The role of motivation as a factor in mental fatigue. Human Factors.** DOI 10.1177/0018720819828569
<https://pmc.ncbi.nlm.nih.gov/articles/PMC6764012>

Em tarefa exigente prolongada, a precisão se mantém nos blocos com recompensa e cai nos blocos sem recompensa, embora os participantes relatem fadiga crescente nos dois casos.

**No código:** o tempo multiplica a carga dos outros sinais em vez de somar pontos sozinho. Uma sessão longa e tranquila não sobe de faixa só pelo relógio. O efeito da motivação não é modelado, o que é mais um motivo para calibrar por pessoa.

## Pausas

**Albulescu et al. (2022). "Give me a break!" A systematic review and meta-analysis on the efficacy of micro-breaks for increasing well-being and performance. PLOS ONE 17(8).**
<https://pmc.ncbi.nlm.nih.gov/articles/PMC9432722/>

Meta-análise de 22 amostras (N = 2.335) sobre pausas de até 10 minutos. Efeito pequeno e significativo em vigor e em fadiga; efeito não significativo em desempenho no geral, com ganho apenas em tarefas de baixa exigência cognitiva. Pausas mais longas rendem mais desempenho.

**No código:**

- A v0.1 zerava o score após 30 minutos sem eventos. A v0.2 troca isso por decaimento: a carga da sessão anterior cai pela metade a cada `meia_vida_min` e entra como `residual` na sessão seguinte.
- A meia-vida de 30 minutos é escolha do projeto, não número da meta-análise. Ela só garante a direção do achado: pausa curta alivia pouco, pausa longa alivia mais.
- Pausas dentro da sessão não são modeladas: um intervalo entre eventos não diz se a pessoa descansou ou trabalhou em outra coisa.

## Aprovação no automático

**Parasuraman e Manzey (2010). Complacency and bias in human use of automation: an attentional integration. Human Factors 52(3).**
<https://pubmed.ncbi.nlm.nih.gov/21077562/>

Revisão sobre complacência e viés de automação. A complacência aparece em novatos e em especialistas, não desaparece só com prática, e depende de como a atenção é distribuída entre tarefas.

**Catalan et al. (2026). "I'm not reading all of that": understanding software engineers' level of cognitive engagement with agentic coding assistants. Workshop do CHI 2026.**
<https://arxiv.org/abs/2603.14225>

Estudo formativo, pequeno. O engajamento cognitivo dos engenheiros cai conforme a tarefa avança.

**Hamza e Siemon (2026). Does working with AI agents change how developers code, test, and review? ESEM 2026.**
<https://drops.dagstuhl.de/storage/00lipics/lipics-vol394-esem2026/LIPIcs.ESEM.2026.67/LIPIcs.ESEM.2026.67.pdf>

Análise causal comparativa. Não encontra redução de esforço entre quem adota agentes; documentação e testes aumentam, e a queda aparente no rigor da revisão é atribuída a mudanças gerais da prática.

**Estudo longitudinal com engenheiros usando assistentes de código (2026).**
<https://arxiv.org/html/2605.23135>

Ganhos de produtividade convivem com piora da experiência relatada, em especial em estado de fluxo e carga cognitiva.

**No código:**

- O sinal compara as linhas de um pedido de decisão com o tempo até a aprovação. Três aprovações seguidas acima de `limite_ritmo_aprovacao` geram um aviso.
- O sinal não entra no score, porque os dados com agentes apontam em direções diferentes.
- O limite de 1.000 linhas/hora é o dobro do ritmo de revisão cuidadosa do estudo da Cisco. É ponto de partida arbitrário.
- O resumo registra quantas aprovações foram rápidas por sessão, para comparar depois com a autoavaliação.

## Autoavaliação

**Hart e Staveland (1988). Development of NASA-TLX (Task Load Index): results of empirical and theoretical research.**
<https://humansystems.arc.nasa.gov/publications/Hart_Staveland_ORIGINAL_1.pdf>

**Hart (2006). NASA-Task Load Index (NASA-TLX); 20 years later.**
<https://humansystems.arc.nasa.gov/publications/HFES_2006_Paper.pdf>

Escala de carga de trabalho subjetiva com seis dimensões (demanda mental, física e temporal, desempenho, esforço e frustração). A versão sem ponderação ("Raw TLX") é a mais usada.

**Avaliações recentes**

- Estudo sobre versões do TLX em tarefas de visualização: <https://arxiv.org/abs/2509.24643>. Cita evidência de que uma escala única já estima bem a carga individual.
- Revisão crítica do uso do TLX em interação humano-computador: <https://repository.tudelft.nl/file/File_0d9016fd-867b-4d1c-bd5a-5b76d1468c80>. Aponta falta de validade convergente e de sensibilidade nesse tipo de tarefa.

**No código:** `carga feedback NOTA` usa uma nota única de 1 a 5, pelo baixo atrito. `--demanda` e `--frustracao` são opcionais e ficam registradas para análise. Dadas as críticas, a nota serve para ordenar as sessões da mesma pessoa, não para comparar pessoas.

## O que continua sem base

- Os pesos relativos (1, 2, 3) e os limites de faixa (30 e 60).
- A forma do multiplicador de tempo (degraus de 0,25 a cada 30 minutos depois de 90).
- A meia-vida de 30 minutos.
- O limite de 1.000 linhas/hora para aprovação.
- A soma linear dos sinais: nada indica que eles se combinem assim.

A única validação possível desses pontos é a calibração com uso real (`carga calibrar`).
