# carga-cognitiva

Estima a carga cognitiva acumulada de quem trabalha com várias threads de agentes e avisa quando ela passa de um limite. É um pacote Python sem dependências (cálculo, CLI e hook) mais duas skills que dizem ao agente como usar o resultado.

O score é uma estimativa por sinais indiretos da sessão. Ele não mede cansaço; os pesos são um ponto de partida e precisam ser calibrados com a autoavaliação de quem usa. Os estudos por trás de cada sinal, e o que continua sendo chute, estão em [docs/REFERENCIAS.md](docs/REFERENCIAS.md).

## Como funciona

```
thread A ─┐
thread B ─┼─> hook pós-resposta ─> eventos.jsonl ─> score ─> faixa ─> alerta
thread C ─┘   (1 evento por resposta)                        verde     nada
                                                             amarelo   agrupar decisões, anotar retomada
                                                             vermelho  checkpoint, adiar irreversíveis, pausa
```

### A conta

```
base  = 1 × decisões
      + 2 × trocas_com_pendência + 1 × trocas_limpas
      + 3 × retrabalhos
      + linhas_revisadas / 200
      + pontos_de_ritmo

carga = base × fator_tempo + residual

fator_tempo     = 1,0 até 90 min de sessão; +0,25 a cada 30 min completos depois disso
pontos_de_ritmo = 5 × excesso do ritmo sobre 500 linhas/hora (no máximo 10 pontos)
residual        = score da sessão anterior, pela metade a cada 30 min de pausa
faixas          = verde < 30 ≤ amarelo < 60 ≤ vermelho
```

Exemplo: sessão de 2h30 com 12 decisões, 4 trocas com pendência, 3 retrabalhos e 800 linhas revisadas (320 linhas/hora, sem residual) dá (12 + 8 + 9 + 4) × 1,5 = 49,5, faixa amarela.

| Sinal | Como é obtido |
| --- | --- |
| Decisões | respostas registradas com `decisao` |
| Trocas com pendência | mudança de `thread` saindo de uma thread ainda aberta (derivado) |
| Trocas limpas | mudança de `thread` saindo de uma thread marcada `concluida` (derivado) |
| Retrabalhos | eventos registrados com `retrabalho` |
| Linhas revisadas | soma de `linhas` das respostas |
| Ritmo | linhas por hora na sessão, contado depois de 15 min |
| Tempo | do primeiro evento da sessão até agora |
| Residual | score final da sessão anterior, reduzido pela pausa |

Uma sessão termina após 30 minutos sem eventos. A seguinte recomeça o relógio, mas herda o residual: uma pausa de 30 minutos deixa metade da carga, uma de 60 deixa um quarto.

### Avisos

| Aviso | Quando | Repetição |
| --- | --- | --- |
| Faixa amarela ou vermelha | o score cruza 30 ou 60 | a cada 20 min na mesma faixa; na hora se subir de faixa |
| Resposta grande | uma resposta tem mais de 400 linhas para revisar | a cada ocorrência |
| Aprovação no automático | as 3 últimas aprovações vieram mais rápido que 1.000 linhas/hora | a cada 20 min |

O aviso de aprovação no automático é uma hipótese: ele não entra no score e só avalia pedidos com 20 linhas ou mais.

## Instalar

```bash
pip install -e .        # dentro do clone; instala o comando `carga`
```

Sem instalar, funciona a partir da raiz do repositório com `python -m carga_cognitiva`.

Os dados ficam em `$CARGA_DIR` (padrão `~/.carga-cognitiva`): `eventos.jsonl` e, opcionalmente, `config.json`.

## Usar no orquestrador

Em Python, uma chamada por evento:

```python
from carga_cognitiva import apos_resposta

# a thread entregou uma resposta ao humano
aviso = apos_resposta(thread="implement-auth", texto=resposta,
                      decisao=tem_gate_pendente, concluida=thread_terminou)

# o humano aprovou o gate daquela thread
aviso = apos_resposta(thread="implement-auth", aprovacao=True)

# o humano rejeitou ou corrigiu a entrega
aviso = apos_resposta(thread="implement-auth", retrabalho=True)

if aviso:
    mostrar_ao_humano(aviso)          # e/ou injetar no contexto do coordenador
```

Fora de Python, o mesmo por stdin:

```bash
echo '{"thread": "implement-auth", "texto": "...", "decisao": true}' | carga hook
echo '{"thread": "implement-auth", "aprovacao": true}' | carga hook
```

O comando imprime os avisos quando há algum e nada caso contrário. `exemplos/hook_orquestrador.py` mostra uma integração com heurística para detectar pedido de decisão.

## Comandos

| Comando | O que faz |
| --- | --- |
| `carga registrar --thread T [--linhas N] [--decisao] [--concluida]` | grava uma resposta de thread |
| `carga registrar --thread T --aprovacao` | grava a aprovação do pedido pendente |
| `carga registrar --thread T --retrabalho` | grava uma correção do humano |
| `carga hook` | grava a partir de JSON no stdin e imprime os avisos, se houver |
| `carga pontuar [--json]` | score, faixa e componentes da sessão em curso |
| `carga alerta` | imprime os avisos que estiverem na hora |
| `carga feedback NOTA [--demanda N] [--frustracao N]` | autoavaliação de 1 (descansado) a 5 (exausto) |
| `carga resumo [--dias N] [--json]` | uma linha por sessão recente (score no último evento) |
| `carga calibrar [--json]` | compara as notas com o score |
| `carga config` | configuração em vigor |

Todos aceitam `--dados PASTA` e `--agora ISO8601` (para simular e testar).

## Skills

| Skill | Para quem | Conteúdo |
| --- | --- | --- |
| `skills/carga-cognitiva-coordenador` | o agente que leva pedidos ao humano | quando consultar o score e o que mudar em cada faixa |
| `skills/carga-cognitiva-memoria` | qualquer agente que registra ou lê histórico | como gravar eventos, feedback, resumo de início de sessão e calibração |

As duas chamam o CLI; copie as pastas para onde o seu harness carrega skills (por exemplo `.claude/skills/`).

## Configurar

Crie `config.json` na pasta de dados só com as chaves que quer mudar:

```json
{"peso_troca": 3, "limite_amarelo": 25, "meia_vida_min": 45}
```

Chaves e padrões: `carga config`. Uma chave desconhecida é rejeitada com erro.

## Testar e validar

```bash
python -m unittest discover -s tests -v    # inclui o exemplo de 49,5
./exemplos/simular_sessao.sh               # duas sessões simuladas pelo CLI, em pasta temporária
```

Para validar com uso real: rode o hook por algumas sessões, registre `carga feedback NOTA` ao fim de cada uma e, com dez ou mais amostras, veja `carga calibrar`. Concordância baixa entre nota e score indica que os pesos não servem para você.

## Limites conhecidos

- Trabalho fora das threads não aparece.
- Linhas revisadas mede volume, não dificuldade.
- Pausas dentro da sessão não são detectadas: um intervalo entre eventos não diz se houve descanso.
- Os limites são fixos; ainda não há linha de base pessoal.
- Pesos, faixas, meia-vida e limite de aprovação não vêm de estudo (ver a última seção de `docs/REFERENCIAS.md`).
