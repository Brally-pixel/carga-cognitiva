# carga-cognitiva

Estima a carga cognitiva acumulada de quem trabalha com várias threads de agentes e avisa quando ela passa de um limite. É um pacote Python sem dependências (cálculo, CLI e hook) mais duas skills que dizem ao agente como usar o resultado.

O score é uma estimativa por sinais indiretos da sessão. Ele não mede cansaço; os pesos são um ponto de partida e precisam ser calibrados com a autoavaliação de quem usa.

## Como funciona

```
thread A ─┐
thread B ─┼─> hook pós-resposta ─> eventos.jsonl ─> score ─> faixa ─> alerta
thread C ─┘   (1 evento por resposta)                        verde     nada
                                                             amarelo   agrupar decisões, não abrir frente nova
                                                             vermelho  checkpoint, adiar irreversíveis, pausa
```

### A conta

```
carga = (1 × decisões + 2 × trocas_de_thread + 3 × retrabalhos + linhas_revisadas / 200) × fator_tempo

fator_tempo = 1,0 até 90 min de sessão; +0,25 a cada 30 min completos depois disso
faixas:       verde < 30 ≤ amarelo < 60 ≤ vermelho
```

Exemplo: sessão de 2h30 com 12 decisões, 4 trocas, 3 retrabalhos e 800 linhas revisadas dá (12 + 8 + 9 + 4) × 1,5 = 49,5, faixa amarela.

| Sinal | Como é obtido |
| --- | --- |
| Decisões | respostas registradas com `decisao` |
| Trocas de thread | mudanças de `thread` entre eventos consecutivos (derivado, não se registra) |
| Retrabalhos | eventos registrados com `retrabalho` |
| Linhas revisadas | soma de `linhas` dos eventos |
| Tempo | do primeiro evento da sessão até agora |

Uma sessão termina após 30 minutos sem eventos; a seguinte começa do zero. O alerta de uma mesma faixa não se repete antes de 20 minutos, mas subir de faixa avisa na hora.

## Instalar

```bash
pip install -e .        # dentro do clone; instala o comando `carga`
```

Sem instalar, funciona a partir da raiz do repositório com `python -m carga_cognitiva`.

Os dados ficam em `$CARGA_DIR` (padrão `~/.carga-cognitiva`): `eventos.jsonl` e, opcionalmente, `config.json`.

## Usar no orquestrador

Em Python, uma chamada por resposta enviada ao humano:

```python
from carga_cognitiva import apos_resposta

alerta = apos_resposta(thread="implement-auth", texto=resposta, decisao=tem_gate_pendente)
if alerta:
    mostrar_ao_humano(alerta)          # e/ou injetar no contexto do coordenador
```

Fora de Python, o mesmo por stdin:

```bash
echo '{"thread": "implement-auth", "texto": "...", "decisao": true}' | carga hook
```

O comando imprime o alerta quando há um e nada caso contrário. `exemplos/hook_orquestrador.py` mostra uma integração com heurística para detectar pedido de decisão.

## Comandos

| Comando | O que faz |
| --- | --- |
| `carga registrar --thread T [--linhas N] [--decisao] [--retrabalho]` | grava um evento |
| `carga hook` | grava a partir de JSON no stdin e imprime o alerta, se houver |
| `carga pontuar [--json]` | score e faixa da sessão em curso |
| `carga alerta` | imprime o alerta se for hora de avisar |
| `carga feedback NOTA` | autoavaliação de 1 (descansado) a 5 (exausto) |
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
{"peso_troca": 3, "limite_amarelo": 25}
```

Chaves e padrões: `carga config`. Uma chave desconhecida é rejeitada com erro.

## Testar e validar

```bash
python -m unittest discover -s tests -v    # 19 testes, inclui o exemplo de 49,5
./exemplos/simular_sessao.sh               # sessão simulada pelo CLI, em pasta temporária
```

Para validar com uso real: rode o hook por algumas sessões, registre `carga feedback NOTA` ao fim de cada uma e, com dez ou mais amostras, veja `carga calibrar`. Concordância baixa entre nota e score indica que os pesos não servem para você.

## Limites conhecidos

- A carga não passa de uma sessão para a outra, nem soma sessões do mesmo dia.
- Trabalho fora das threads não aparece.
- Linhas revisadas mede volume, não dificuldade.
- Ainda não há linha de base pessoal nem detecção de aprovação no automático (respostas do humano cada vez mais curtas); os limites são fixos.
