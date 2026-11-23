"""Cálculo de carga cognitiva acumulada a partir de eventos de sessão.

Só biblioteca padrão. O score é uma ESTIMATIVA por sinais indiretos
(decisões, trocas de contexto, retrabalho, volume revisado, tempo),
não uma medição de cansaço.

    carga = (p_decisao * decisoes
             + p_troca * trocas_de_thread
             + p_retrabalho * retrabalhos
             + linhas_revisadas / linhas_por_ponto) * fator_tempo

    fator_tempo = 1.0 até `tempo_livre_min`; depois soma `tempo_incremento`
                  a cada `tempo_passo_min` completos.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

TIPOS = ("resposta", "retrabalho", "feedback", "alerta")
FAIXAS = ("verde", "amarelo", "vermelho")

CONFIG_PADRAO = {
    # pesos da soma
    "peso_decisao": 1.0,
    "peso_troca": 2.0,
    "peso_retrabalho": 3.0,
    "linhas_por_ponto": 200.0,
    # multiplicador de tempo
    "tempo_livre_min": 90,
    "tempo_passo_min": 30,
    "tempo_incremento": 0.25,
    # faixas
    "limite_amarelo": 30.0,
    "limite_vermelho": 60.0,
    # sessão: um intervalo sem eventos maior que isto encerra a sessão
    "pausa_min": 30,
    # alerta: não repetir a mesma faixa antes deste intervalo
    "cooldown_min": 20,
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
    nota: Optional[int] = None      # feedback: 1 (descansado) a 5 (exausto)
    score: Optional[float] = None   # feedback/alerta: score no momento
    faixa: Optional[str] = None     # feedback/alerta: faixa no momento

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
    """Eventos que representam trabalho (feedback e alerta não contam)."""
    return [e for e in eventos if e.tipo in ("resposta", "retrabalho")]


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

    def para_dict(self) -> dict:
        return asdict(self)


def pontuar_sessao(sessao: list[Evento], fim: datetime, config: dict) -> Pontuacao:
    """Aplica a fórmula a uma sessão (lista de eventos de trabalho em ordem)."""
    if not sessao:
        return Pontuacao(0.0, "verde", 0.0, 1.0, 0, 0, 0, 0)

    decisoes = sum(1 for e in sessao if e.tipo == "resposta" and e.decisao)
    retrabalhos = sum(1 for e in sessao if e.tipo == "retrabalho")
    linhas = sum(e.linhas for e in sessao)

    com_thread = [e.thread for e in sessao if e.thread]
    trocas = sum(1 for a, b in zip(com_thread, com_thread[1:]) if a != b)

    minutos = max(0.0, (fim - sessao[0].ts).total_seconds() / 60)
    fator = fator_tempo(minutos, config)

    base = (
        config["peso_decisao"] * decisoes
        + config["peso_troca"] * trocas
        + config["peso_retrabalho"] * retrabalhos
        + linhas / config["linhas_por_ponto"]
    )
    score = round(base * fator, 2)
    return Pontuacao(
        score=score,
        faixa=faixa_de(score, config),
        minutos=round(minutos, 1),
        fator_tempo=fator,
        decisoes=decisoes,
        trocas=trocas,
        retrabalhos=retrabalhos,
        linhas=linhas,
        threads=sorted(set(com_thread)),
        inicio=sessao[0].ts.isoformat(),
    )


def pontuar(
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    config: Optional[dict] = None,
) -> Pontuacao:
    """Score da sessão em curso (zero/verde se não há sessão ativa)."""
    momento = momento or agora()
    config = config or carregar_config(dados)
    sessao = sessao_ativa(ler_eventos(dados), momento, config)
    return pontuar_sessao(sessao, momento, config)


# --------------------------------------------------------------------------
# Registro, alerta e feedback
# --------------------------------------------------------------------------

def registrar(
    thread: str,
    linhas: int = 0,
    decisao: bool = False,
    retrabalho: bool = False,
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
) -> Evento:
    """Grava um evento de trabalho: resposta de thread ou retrabalho do humano."""
    evento = Evento(
        ts=momento or agora(),
        tipo="retrabalho" if retrabalho else "resposta",
        thread=thread,
        linhas=max(0, int(linhas)),
        decisao=bool(decisao) and not retrabalho,
    )
    return gravar_evento(evento, dados)


MENSAGENS = {
    "amarelo": (
        "Carga cognitiva em AMARELO (score {score:g}, {minutos:.0f} min de sessão): "
        "{decisoes} decisões, {trocas} trocas de thread, {retrabalhos} retrabalhos, "
        "{linhas} linhas revisadas. Agrupe as decisões pendentes e evite abrir nova frente."
    ),
    "vermelho": (
        "Carga cognitiva em VERMELHO (score {score:g}, {minutos:.0f} min de sessão): "
        "{decisoes} decisões, {trocas} trocas de thread, {retrabalhos} retrabalhos, "
        "{linhas} linhas revisadas. Salve um checkpoint, adie decisões irreversíveis "
        "e faça uma pausa de pelo menos {pausa_min} min."
    ),
}


def verificar_alerta(
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
    config: Optional[dict] = None,
) -> Optional[str]:
    """Devolve a mensagem de alerta se for hora de avisar; senão None.

    Avisa quando a faixa é amarelo/vermelho e (a) a faixa subiu desde o
    último alerta da sessão ou (b) o cooldown passou. Grava o alerta emitido.
    """
    momento = momento or agora()
    config = config or carregar_config(dados)
    eventos = ler_eventos(dados)
    sessao = sessao_ativa(eventos, momento, config)
    pontuacao = pontuar_sessao(sessao, momento, config)
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
    return MENSAGENS[pontuacao.faixa].format(
        pausa_min=config["pausa_min"], **pontuacao.para_dict()
    )


def apos_resposta(
    thread: str,
    texto: str = "",
    decisao: bool = False,
    retrabalho: bool = False,
    linhas: Optional[int] = None,
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
) -> Optional[str]:
    """Hook de uma chamada: registra a resposta da thread e devolve o alerta, se houver.

    `linhas` é o volume que o humano precisa ler; se omitido, conta as
    linhas não vazias de `texto`.
    """
    if linhas is None:
        linhas = sum(1 for linha in texto.splitlines() if linha.strip())
    registrar(thread, linhas, decisao, retrabalho, dados, momento)
    return verificar_alerta(dados, momento)


def registrar_feedback(
    nota: int,
    dados: Optional[os.PathLike] = None,
    momento: Optional[datetime] = None,
) -> Evento:
    """Autoavaliação de cansaço (1 descansado … 5 exausto) com o score do momento."""
    if not 1 <= int(nota) <= 5:
        raise ValueError("nota deve ser de 1 a 5")
    momento = momento or agora()
    pontuacao = pontuar(dados, momento)
    evento = Evento(
        ts=momento,
        tipo="feedback",
        nota=int(nota),
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
    eventos = ler_eventos(dados)
    corte = momento - timedelta(days=dias)
    linhas = []
    for sessao in separar_sessoes(eventos, config["pausa_min"]):
        inicio, fim = sessao[0].ts, sessao[-1].ts
        if fim < corte or inicio > momento:
            continue
        pontuacao = pontuar_sessao(sessao, fim, config)
        janela_fim = fim + timedelta(minutes=config["pausa_min"])
        extras = [e for e in eventos if inicio <= e.ts <= janela_fim]
        notas = [e.nota for e in extras if e.tipo == "feedback" and e.nota]
        linhas.append(
            {
                "inicio": inicio.isoformat(),
                "minutos": pontuacao.minutos,
                "score": pontuacao.score,
                "faixa": pontuacao.faixa,
                "decisoes": pontuacao.decisoes,
                "trocas": pontuacao.trocas,
                "retrabalhos": pontuacao.retrabalhos,
                "linhas": pontuacao.linhas,
                "threads": pontuacao.threads,
                "alertas": sum(1 for e in extras if e.tipo == "alerta"),
                "nota": notas[-1] if notas else None,
            }
        )
    return linhas


def calibracao(dados: Optional[os.PathLike] = None) -> dict:
    """Compara as notas de feedback com o score registrado na hora.

    Não ajusta pesos sozinho: mostra a média de score por nota e conta as
    inversões (nota maior com score menor) para o humano decidir.
    """
    pares = [
        (e.nota, e.score)
        for e in ler_eventos(dados)
        if e.tipo == "feedback" and e.nota is not None and e.score is not None
    ]
    por_nota: dict[int, list[float]] = {}
    for nota, score in pares:
        por_nota.setdefault(nota, []).append(score)
    medias = {nota: round(sum(v) / len(v), 2) for nota, v in sorted(por_nota.items())}

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
    }
