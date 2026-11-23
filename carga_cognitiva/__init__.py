"""Estimativa de carga cognitiva acumulada em sessões com agentes."""

from .nucleo import (
    CONFIG_PADRAO,
    Evento,
    Pontuacao,
    apos_resposta,
    calibracao,
    carregar_config,
    pontuar,
    pontuar_sessao,
    registrar,
    registrar_feedback,
    resumo,
    verificar_alerta,
)

__version__ = "0.1.0"

__all__ = [
    "CONFIG_PADRAO",
    "Evento",
    "Pontuacao",
    "apos_resposta",
    "calibracao",
    "carregar_config",
    "pontuar",
    "pontuar_sessao",
    "registrar",
    "registrar_feedback",
    "resumo",
    "verificar_alerta",
]
