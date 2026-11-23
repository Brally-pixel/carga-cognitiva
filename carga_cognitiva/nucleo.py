"""Cálculo de carga cognitiva acumulada a partir de eventos de sessão.

Só biblioteca padrão. O score é uma ESTIMATIVA por sinais indiretos
(decisões, trocas de contexto, retrabalho, volume e ritmo de revisão,
tempo), não uma medição de cansaço. As escolhas de modelagem e os estudos
que as motivam estão em docs/REFERENCIAS.md.

    base  = p_decisao * decisoes
          + p_troca * trocas_com_pendencia + p_troca_limpa * trocas_limpas
          + p_retrabalho * retrabalhos
          + linhas_revisadas / linhas_por_ponto
          + pontos_ritmo
    carga = base * fator_tempo + residual

    fator_tempo  = 1.0 até `tempo_livre_min`; depois soma `tempo_incremento`
                   a cada `tempo_passo_min` completos.
    pontos_ritmo = p_ritmo * excesso do ritmo (linhas/hora) sobre `limite_ritmo`,
                   limitado a 2x.
    residual     = score da sessão anterior, reduzido à metade a cada
                   `meia_vida_min` de pausa.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

TIPOS = ("resposta", "retrabalho", "aprovacao", "feedback", "alerta", "aviso")
TIPOS_DE_TRABALHO = ("resposta", "retrabalho", "aprovacao")
FAIXAS = ("verde", "amarelo", "vermelho")

CONFIG_PADRAO = {
    # pesos da soma
    "peso_decisao": 1.0,
    "peso_troca": 2.0,           # troca que deixa a thread anterior aberta
    "peso_troca_limpa": 1.0,     # troca depois de concluir a thread anterior
    "peso_retrabalho": 3.0,
    "linhas_por_ponto": 200.0,
    # ritmo de revisão (linhas por hora na sessão)
    "peso_ritmo": 5.0,
    "limite_ritmo": 500.0,
    "ritmo_min_minutos": 15,
    # multiplicador de tempo
    "tempo_livre_min": 90,
    "tempo_passo_min": 30,
    "tempo_incremento": 0.25,
    # faixas
    "limite_amarelo": 30.0,
    "limite_vermelho": 60.0,
    # sessão: um intervalo sem eventos maior que isto encerra a sessão
    "pausa_min": 30,
    # pausa: a carga da sessão anterior cai pela metade a cada meia-vida
    "meia_vida_min": 30,
    "residual_minimo": 1.0,
    # alerta: não repetir a mesma faixa antes deste intervalo
    "cooldown_min": 20,
    # aviso de resposta grande demais para revisar de uma vez
    "limite_linhas_resposta": 400,
    # aprovação no automático (hipótese a calibrar; não entra no score)
    "limite_ritmo_aprovacao": 1000.0,
    "linhas_min_aprovacao": 20,
    "aprovacoes_seguidas": 3,
}


# --------------------------------------------------------------------------
# Armazenamento
# --------------------------------------------------------------------------

def diretorio_dados(caminho: Optional[os.PathLike] = None) -> Path:
    """Pasta dos dados: argumento > $CARGA_DIR > ~/.carga-cognitiva."""
    if caminho:
        return Path(caminho)
    return Path(os.environ.get("CARGA_DIR") or Path.home() / ".carga-cognitiva")


def carregar_config(dados: Optional[os.PathLike] = None) -> dict:
    """Config padrão sobreposta por `config.json` da pasta de dados, se existir."""
    config = dict(CONFIG_PADRAO)
    arquivo = diretorio_dados(dados) / "config.json"
    if arquivo.exists():
        lido = json.loads(arquivo.read_text(encoding="utf-8"))
        desconhecidas = set(lido) - set(CONFIG_PADRAO)
        if desconhecidas:
            raise ValueError(f"chaves desconhecidas em {arquivo}: {sorted(desconhecidas)}")
        config.update(lido)
    return config


def agora() -> datetime:
    return datetime.now(timezone.utc)


def ler_ts(texto: str) -> datetime:
    """ISO 8601 -> datetime com fuso (sem fuso é tratado como UTC)."""
    ts = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


@dataclass
class Evento:
    ts: datetime
    tipo: str
    thread: str = ""
    linhas: int = 0
    decisao: bool = False
    concluida: bool = False            # resposta: a thread terminou o que fazia
    nota: Optional[int] = None         # feedback: 1 (descansado) a 5 (exausto)
    demanda: Optional[int] = None      # feedback: demanda mental, 1 a 5
    frustracao: Optional[int] = None   # feedback: frustração, 1 a 5
    score: Optional[float] = None      # feedback/alerta: score no momento
    faixa: Optional[str] = None        # feedback/alerta: faixa; aviso: tipo do aviso

    def para_json(self) -> str:
        bruto = asdict(self)
        bruto["ts"] = self.ts.isoformat()
        # omite só os valores-padrão; um score 0.0 de feedback/alerta é mantido
        enxuto = {
            k: v
            for k, v in bruto.items()
            if not (v is None or v == "" or v is False or (k == "linhas" and v == 0))
        }
        return json.dumps(enxuto, ensure_ascii=False)

    @classmethod
    def de_json(cls, linha: str) -> "Evento":
        bruto = json.loads(linha)
        bruto["ts"] = ler_ts(bruto["ts"])
        return cls(**bruto)


def arquivo_eventos(dados: Optional[os.PathLike] = None) -> Path:
    return diretorio_dados(dados) / "eventos.jsonl"


def ler_eventos(dados: Optional[os.PathLike] = None) -> list[Evento]:
    arquivo = arquivo_eventos(dados)
    if not arquivo.exists():
        return []
    eventos = []
    with arquivo.open(encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                eventos.append(Evento.de_json(linha))
    eventos.sort(key=lambda e: e.ts)
    return eventos


def gravar_evento(evento: Evento, dados: Optional[os.PathLike] = None) -> Evento:
    if evento.tipo not in TIPOS:
        raise ValueError(f"tipo inválido: {evento.tipo!r} (use um de {TIPOS})")
    arquivo = arquivo_eventos(dados)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with arquivo.open("a", encoding="utf-8") as f:
        f.write(evento.para_json() + "\n")
    return evento


# --------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------

def _de_trabalho(eventos: Iterable[Evento]) -> list[Evento]:
    """Eventos que representam trabalho (feedback, alerta e aviso não contam)."""
    return [e for e in eventos if e.tipo in TIPOS_DE_TRABALHO]


def separar_sessoes(eventos: Iterable[Evento], pausa_min: float) -> list[list[Evento]]:
    """Agrupa eventos de trabalho em sessões; pausa > `pausa_min` abre outra."""
    sessoes: list[list[Evento]] = []
    for evento in sorted(_de_trabalho(eventos), key=lambda e: e.ts):
        if sessoes and evento.ts - sessoes[-1][-1].ts <= timedelta(minutes=pausa_min):
            sessoes[-1].append(evento)
        else:
            sessoes.append([evento])
    return sessoes


def sessao_ativa(eventos: Iterable[Evento], momento: datetime, config: dict) -> list[Evento]:
    """Sessão em curso em `momento`, ou [] se a última já terminou por pausa."""
    anteriores = [e for e in eventos if e.ts <= momento]
    sessoes = separar_sessoes(anteriores, config["pausa_min"])
    if not sessoes:
        return []
    ultima = sessoes[-1]
    if momento - ultima[-1].ts > timedelta(minutes=config["pausa_min"]):
        return []
    return ultima


def fator_tempo(minutos: float, config: dict) -> float:
    excedente = minutos - config["tempo_livre_min"]
    if excedente <= 0:
        return 1.0
    passos = int(excedente // config["tempo_passo_min"])
    return 1.0 + config["tempo_incremento"] * passos


def faixa_de(score: float, config: dict) -> str:
    if score >= config["limite_vermelho"]:
        return "vermelho"
    if score >= config["limite_amarelo"]:
        return "amarelo"
    return "verde"


def decair(score: float, minutos: float, config: dict) -> float:
    """Carga que sobra de `score` depois de `minutos` de pausa (meia-vida)."""
    if score <= 0 or minutos < 0:
        return 0.0
    restante = score * 0.5 ** (minutos / config["meia_vida_min"])
    return round(restante, 2) if restante >= config["residual_minimo"] else 0.0


@dataclass
class Pontuacao:
    score: float
    faixa: str
    minutos: float
    fator_tempo: float
    decisoes: int
    trocas: int
    retrabalhos: int
    linhas: int
    threads: list[str] = field(default_factory=list)
    inicio: Optional[str] = None
    trocas_limpas: int = 0
    residual: float = 0.0
    ritmo: float = 0.0                 # linhas por hora na sessão
    pontos_ritmo: float = 0.0
    respostas_grandes: int = 0
    aprovacoes: int = 0                # aprovações avaliáveis na sessão
    aprovacoes_automaticas: int = 0
    aprovacao_no_automatico: bool = False

    def para_dict(self) -> dict:
        return asdict(self)


def _contar_trocas(sessao: list[Evento]) -> tuple[int, int]:
    """(trocas com pendência, trocas limpas) na sequência de threads da sessão.

    Sair de uma thread marcada como concluída é troca limpa; sair de uma
    thread ainda aberta deixa pendência. Uma nova resposta ou um retrabalho
    reabre a thread; uma aprovação não.
    """
    pendentes = limpas = 0
    concluidas: set[str] = set()
    anterior = ""
    for evento in sessao:
        if not evento.thread:
            continue
        if anterior and evento.thread != anterior:
            if anterior in concluidas:
                limpas += 1
            else:
                pendentes += 1
        if evento.concluida:
            concluidas.add(evento.thread)
        elif evento.tipo != "aprovacao":  # aprovar não reabre uma thread concluída
            concluidas.discard(evento.thread)
        anterior = evento.thread
    return pendentes, limpas


def _avaliar_aprovacoes(sessao: list[Evento], config: dict) -> list[bool]:
    """Para cada aprovação avaliável, True se foi rápida demais para o volume.

    Compara as linhas do pedido de decisão com o tempo até a aprovação na
    mesma thread. Pedidos com poucas linhas não são avaliados.
    """
    pedido: dict[str, Evento] = {}
    resultado: list[bool] = []
    for evento in sessao:
        if evento.tipo == "resposta" and evento.decisao:
            pedido[evento.thread] = evento
        elif evento.tipo == "aprovacao" and evento.thread in pedido:
            origem = pedido.pop(evento.thread)
            if origem.linhas < config["linhas_min_aprovacao"]:
                continue
            horas = (evento.ts - origem.ts).total_seconds() / 3600
            ritmo = float("inf") if horas <= 0 else origem.linhas / horas
            resultado.append(ritmo > config["limite_ritmo_aprovacao"])
    return resultado


def pontuar_sessao(
    sessao: list[Evento], fim: datetime, config: dict, residual: float = 0.0
) -> Pontuacao:
    """Aplica a fórmula a uma sessão (lista de eventos de trabalho em ordem)."""
    if not sessao:
        return Pontuacao(residual, faixa_de(residual, config), 0.0, 1.0, 0, 0, 0, 0,
                         residual=residual)

    respostas = [e for e in sessao if e.tipo == "resposta"]
    decisoes = sum(1 for e in respostas if e.decisao)
    retrabalhos = sum(1 for e in sessao if e.tipo == "retrabalho")
    linhas = sum(e.linhas for e in sessao)
    trocas, trocas_limpas = _contar_trocas(sessao)
    grandes = sum(1 for e in respostas if e.linhas > config["limite_linhas_resposta"])

    minutos = max(0.0, (fim - sessao[0].ts).total_seconds() / 60)
    fator = fator_tempo(minutos, config)

    ritmo = pontos_ritmo = 0.0
    if minutos >= config["ritmo_min_minutos"]:
        ritmo = linhas / (minutos / 60)
        excesso = min(max(0.0, ritmo / config["limite_ritmo"] - 1), 2.0)
        pontos_ritmo = config["peso_ritmo"] * excesso

    automaticas = _avaliar_aprovacoes(sessao, config)
    seguidas = config["aprovacoes_seguidas"]
    no_automatico = len(automaticas) >= seguidas and all(automaticas[-seguidas:])

    base = (
        config["peso_decisao"] * decisoes
        + config["peso_troca"] * trocas
        + config["peso_troca_limpa"] * trocas_limpas
        + config["peso_retrabalho"] * retrabalhos
        + linhas / config["linhas_por_ponto"]
        + pontos_ritmo
    )
    score = round(base * fator + residual, 2)
    return Pontuacao(
        score=score,
        faixa=faixa_de(score, config),
        minutos=round(minutos, 1),
        fator_tempo=fator,
        decisoes=decisoes,
        trocas=trocas,
        retrabalhos=retrabalhos,
        linhas=linhas,
        threads=sorted({e.thread for e in sessao if e.thread}),
        inicio=sessao[0].ts.isoformat(),
        trocas_limpas=trocas_limpas,
        residual=residual,
        ritmo=round(ritmo, 1),
        pontos_ritmo=round(pontos_ritmo, 2),
        respostas_grandes=grandes,
        aprovacoes=len(automaticas),
        aprovacoes_automaticas=sum(automaticas),
        aprovacao_no_automatico=no_automatico,
    )


def pontuar_cadeia(
    eventos: Iterable[Evento], config: dict, momento: Optional[datetime] = None
) -> list[tuple[list[Evento], Pontuacao]]:
    """Pontua todas as sessões em ordem, levando o residual de uma para a outra.

    Sessões encerradas são pontuadas no último evento; a última, se ainda
    estiver ativa em `momento`, é pontuada em `momento`.
    """
    eventos = [e for e in eventos if momento is None or e.ts <= momento]
    sessoes = separar_sessoes(eventos, config["pausa_min"])
    pausa = timedelta(minutes=config["pausa_min"])
    cadeia: list[tuple[list[Evento], Pontuacao]] = []
    residual = 0.0
    for indice, sessao in enumerate(sessoes):
        if cadeia:
            anterior, pontuacao_anterior = cadeia[-1]
            intervalo = (sessao[0].ts - anterior[-1].ts).total_seconds() / 60
            residual = decair(pontuacao_anterior.score, intervalo, config)
        fim = sessao[-1].ts
        ultima = indice == len(sessoes) - 1
        if ultima and momento is not None and momento - fim <= pausa:
            fim = momento
        cadeia.append((sessao, pontuar_sessao(sessao, fim, config, residual)))
    return cadeia


def pontuar(
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    config: Optional[dict] = None,
) -> Pontuacao:
    """Score em `momento`: sessão em curso, ou só o residual se ela já terminou."""
    momento = momento or agora()
    config = config or carregar_config(dados)
    cadeia = pontuar_cadeia(ler_eventos(dados), config, momento)
    if not cadeia:
        return pontuar_sessao([], momento, config)
    sessao, pontuacao = cadeia[-1]
    intervalo = (momento - sessao[-1].ts).total_seconds() / 60
    if intervalo > config["pausa_min"]:
        return pontuar_sessao([], momento, config, decair(pontuacao.score, intervalo, config))
    return pontuacao


# --------------------------------------------------------------------------
# Registro, alertas e feedback
# --------------------------------------------------------------------------

def registrar(
    thread: str,
    linhas: int = 0,
    decisao: bool = False,
    retrabalho: bool = False,
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    concluida: bool = False,
    aprovacao: bool = False,
) -> Evento:
    """Grava um evento de trabalho.

    Padrão: resposta de uma thread ao humano. `retrabalho=True`: o humano
    corrigiu a entrega. `aprovacao=True`: o humano aprovou o pedido de
    decisão pendente da thread.
    """
    if retrabalho and aprovacao:
        raise ValueError("um evento não pode ser retrabalho e aprovação ao mesmo tempo")
    tipo = "retrabalho" if retrabalho else "aprovacao" if aprovacao else "resposta"
    resposta = tipo == "resposta"
    evento = Evento(
        ts=momento or agora(),
        tipo=tipo,
        thread=thread,
        linhas=max(0, int(linhas)) if resposta else 0,
        decisao=bool(decisao) and resposta,
        concluida=bool(concluida) and resposta,
    )
    return gravar_evento(evento, dados)


MENSAGENS = {
    "amarelo": (
        "Carga cognitiva em AMARELO (score {score:g}, {minutos:.0f} min de sessão): "
        "{decisoes} decisões, {trocas_total} trocas de thread, {retrabalhos} retrabalhos, "
        "{linhas} linhas revisadas. Agrupe as decisões pendentes, anote o ponto de "
        "retomada de cada thread aberta e evite abrir nova frente."
    ),
    "vermelho": (
        "Carga cognitiva em VERMELHO (score {score:g}, {minutos:.0f} min de sessão): "
        "{decisoes} decisões, {trocas_total} trocas de thread, {retrabalhos} retrabalhos, "
        "{linhas} linhas revisadas. Salve um checkpoint, adie decisões irreversíveis "
        "e faça uma pausa: {meia_vida_min} min reduzem a carga estimada à metade."
    ),
    "automatico": (
        "As últimas {aprovacoes_seguidas} aprovações vieram mais rápido do que o volume "
        "pedido permite ler (acima de {limite_ritmo_aprovacao:g} linhas/hora). "
        "Vale reler o último pedido antes de seguir."
    ),
    "resposta_grande": (
        "Resposta com {linhas} linhas para revisar: acima de {limite_linhas_resposta} "
        "linhas a revisão perde eficácia. Divida em partes ou entregue um resumo primeiro."
    ),
}


def _formatar(chave: str, pontuacao: Pontuacao, config: dict) -> str:
    valores = {**config, **pontuacao.para_dict()}
    valores["trocas_total"] = pontuacao.trocas + pontuacao.trocas_limpas
    return MENSAGENS[chave].format(**valores)


def verificar_alerta(
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    config: Optional[dict] = None,
) -> Optional[str]:
    """Devolve o alerta de faixa se for hora de avisar; senão None.

    Avisa quando a faixa é amarelo/vermelho e (a) a faixa subiu desde o
    último alerta da sessão ou (b) o cooldown passou. Grava o alerta emitido.
    """
    momento = momento or agora()
    config = config or carregar_config(dados)
    eventos = ler_eventos(dados)
    sessao = sessao_ativa(eventos, momento, config)
    if not sessao:
        return None
    pontuacao = pontuar_cadeia(eventos, config, momento)[-1][1]
    if pontuacao.faixa == "verde":
        return None

    inicio = sessao[0].ts
    alertas = [e for e in eventos if e.tipo == "alerta" and inicio <= e.ts <= momento]
    if alertas:
        ultimo = alertas[-1]
        subiu = FAIXAS.index(pontuacao.faixa) > FAIXAS.index(ultimo.faixa or "verde")
        em_cooldown = momento - ultimo.ts < timedelta(minutes=config["cooldown_min"])
        if em_cooldown and not subiu:
            return None

    gravar_evento(
        Evento(ts=momento, tipo="alerta", score=pontuacao.score, faixa=pontuacao.faixa),
        dados,
    )
    return _formatar(pontuacao.faixa, pontuacao, config)


def verificar_aprovacao_automatica(
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    config: Optional[dict] = None,
) -> Optional[str]:
    """Aviso (uma vez por cooldown) quando as aprovações recentes foram rápidas demais.

    É uma hipótese a calibrar: não altera o score.
    """
    momento = momento or agora()
    config = config or carregar_config(dados)
    eventos = ler_eventos(dados)
    sessao = sessao_ativa(eventos, momento, config)
    if not sessao:
        return None
    pontuacao = pontuar_cadeia(eventos, config, momento)[-1][1]
    if not pontuacao.aprovacao_no_automatico:
        return None
    limite = momento - timedelta(minutes=config["cooldown_min"])
    recente = any(
        e.tipo == "aviso" and e.faixa == "automatico" and max(limite, sessao[0].ts) <= e.ts
        for e in eventos
    )
    if recente:
        return None
    gravar_evento(Evento(ts=momento, tipo="aviso", faixa="automatico"), dados)
    return _formatar("automatico", pontuacao, config)


def verificar_avisos(
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    config: Optional[dict] = None,
) -> list[str]:
    """Alerta de faixa e aviso de aprovação no automático que estiverem na hora."""
    momento = momento or agora()
    config = config or carregar_config(dados)
    avisos = [
        verificar_alerta(dados, momento, config),
        verificar_aprovacao_automatica(dados, momento, config),
    ]
    return [aviso for aviso in avisos if aviso]


def apos_resposta(
    thread: str,
    texto: str = "",
    decisao: bool = False,
    retrabalho: bool = False,
    linhas: Optional[int] = None,
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    concluida: bool = False,
    aprovacao: bool = False,
) -> Optional[str]:
    """Hook de uma chamada: registra o evento e devolve os avisos, se houver.

    `linhas` é o volume que o humano precisa ler; se omitido, conta as
    linhas não vazias de `texto`. Vários avisos vêm separados por linha.
    """
    momento = momento or agora()
    config = carregar_config(dados)
    if linhas is None:
        linhas = sum(1 for linha in texto.splitlines() if linha.strip())
    evento = registrar(
        thread, linhas, decisao, retrabalho, dados, momento,
        concluida=concluida, aprovacao=aprovacao,
    )
    avisos = verificar_avisos(dados, momento, config)
    if evento.tipo == "resposta" and evento.linhas > config["limite_linhas_resposta"]:
        avisos.append(MENSAGENS["resposta_grande"].format(linhas=evento.linhas, **config))
    return "\n".join(avisos) or None


def _escala(nome: str, valor: Optional[int]) -> Optional[int]:
    if valor is None:
        return None
    if not 1 <= int(valor) <= 5:
        raise ValueError(f"{nome} deve ser de 1 a 5")
    return int(valor)


def registrar_feedback(
    nota: int,
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    demanda: Optional[int] = None,
    frustracao: Optional[int] = None,
) -> Evento:
    """Autoavaliação de cansaço (1 descansado … 5 exausto) com o score do momento.

    `demanda` (demanda mental) e `frustracao` são opcionais, também de 1 a 5.
    """
    if nota is None:
        raise ValueError("nota é obrigatória")
    momento = momento or agora()
    pontuacao = pontuar(dados, momento)
    evento = Evento(
        ts=momento,
        tipo="feedback",
        nota=_escala("nota", nota),
        demanda=_escala("demanda", demanda),
        frustracao=_escala("frustracao", frustracao),
        score=pontuacao.score,
        faixa=pontuacao.faixa,
    )
    return gravar_evento(evento, dados)


# --------------------------------------------------------------------------
# Memória: resumo e calibração
# --------------------------------------------------------------------------

def resumo(
    dias: int = 7,
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    config: Optional[dict] = None,
) -> list[dict]:
    """Uma linha por sessão dos últimos `dias`: score final, faixa, alertas, feedback."""
    momento = momento or agora()
    config = config or carregar_config(dados)
    eventos = [e for e in ler_eventos(dados) if e.ts <= momento]
    corte = momento - timedelta(days=dias)
    linhas = []
    for sessao, pontuacao in pontuar_cadeia(eventos, config):
        inicio, fim = sessao[0].ts, sessao[-1].ts
        if fim < corte:
            continue
        janela_fim = fim + timedelta(minutes=config["pausa_min"])
        extras = [e for e in eventos if inicio <= e.ts <= janela_fim]
        notas = [e.nota for e in extras if e.tipo == "feedback" and e.nota]
        linhas.append(
            {
                "inicio": inicio.isoformat(),
                "minutos": pontuacao.minutos,
                "score": pontuacao.score,
                "faixa": pontuacao.faixa,
                "residual": pontuacao.residual,
                "decisoes": pontuacao.decisoes,
                "trocas": pontuacao.trocas,
                "trocas_limpas": pontuacao.trocas_limpas,
                "retrabalhos": pontuacao.retrabalhos,
                "linhas": pontuacao.linhas,
                "ritmo": pontuacao.ritmo,
                "respostas_grandes": pontuacao.respostas_grandes,
                "aprovacoes": pontuacao.aprovacoes,
                "aprovacoes_automaticas": pontuacao.aprovacoes_automaticas,
                "threads": pontuacao.threads,
                "alertas": sum(1 for e in extras if e.tipo == "alerta"),
                "nota": notas[-1] if notas else None,
            }
        )
    return linhas


def _media(valores: list) -> Optional[float]:
    return round(sum(valores) / len(valores), 2) if valores else None


def calibracao(dados: Optional[os.PathLike] = None) -> dict:
    """Compara as notas de feedback com o score registrado na hora.

    Não ajusta pesos sozinho: mostra a média de score por nota e conta as
    inversões (nota maior com score menor) para o humano decidir.
    """
    feedbacks = [
        e for e in ler_eventos(dados)
        if e.tipo == "feedback" and e.nota is not None and e.score is not None
    ]
    pares = [(e.nota, e.score) for e in feedbacks]
    por_nota: dict[int, list[float]] = {}
    for nota, score in pares:
        por_nota.setdefault(nota, []).append(score)
    medias = {nota: _media(v) for nota, v in sorted(por_nota.items())}

    comparaveis = inversoes = 0
    for i, (nota_a, score_a) in enumerate(pares):
        for nota_b, score_b in pares[i + 1:]:
            if nota_a == nota_b or score_a == score_b:
                continue
            comparaveis += 1
            if (nota_a - nota_b) * (score_a - score_b) < 0:
                inversoes += 1
    concordancia = None if not comparaveis else round(1 - inversoes / comparaveis, 2)

    return {
        "amostras": len(pares),
        "media_score_por_nota": medias,
        "pares_comparaveis": comparaveis,
        "inversoes": inversoes,
        "concordancia": concordancia,
        "media_demanda": _media([e.demanda for e in feedbacks if e.demanda is not None]),
        "media_frustracao": _media([e.frustracao for e in feedbacks if e.frustracao is not None]),
    }
