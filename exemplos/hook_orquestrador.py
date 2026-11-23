"""Exemplo de integração: hook chamado pelo orquestrador a cada resposta de thread.

Adapte `ao_enviar_resposta` ao ponto do seu orquestrador em que a resposta de
uma thread é entregue ao humano. A detecção de "pede decisão" abaixo é uma
heurística simples; se o orquestrador já sabe que há um gate pendente, passe
esse valor direto.
"""

from __future__ import annotations

import re
from typing import Optional

from carga_cognitiva import apos_resposta

PEDE_DECISAO = re.compile(
    r"\b(aprova|aprovar|confirma|confirmar|posso (seguir|prosseguir|aplicar)|"
    r"qual (opção|alternativa)|escolha|prefere)\b.*\?",
    re.IGNORECASE | re.DOTALL,
)


def ao_enviar_resposta(
    thread: str,
    texto: str,
    gate_pendente: Optional[bool] = None,
    linhas_para_revisar: Optional[int] = None,
    thread_concluida: bool = False,
) -> Optional[str]:
    """Registra a resposta e devolve os avisos (ou None).

    - thread: nome estável da frente de trabalho.
    - texto: resposta enviada ao humano.
    - gate_pendente: True/False se o orquestrador sabe; None usa a heurística.
    - linhas_para_revisar: diff/spec anexos; None conta as linhas do texto.
    - thread_concluida: a thread terminou o que fazia e não deixa pendência.
    """
    decisao = bool(PEDE_DECISAO.search(texto)) if gate_pendente is None else gate_pendente
    return apos_resposta(
        thread, texto, decisao=decisao, linhas=linhas_para_revisar, concluida=thread_concluida
    )


def ao_aprovar_gate(thread: str) -> Optional[str]:
    """Chame no momento em que o humano aprova o gate pendente da thread."""
    return apos_resposta(thread, aprovacao=True)


def ao_receber_correcao(thread: str) -> Optional[str]:
    """Chame quando o humano rejeitar ou corrigir uma entrega da thread."""
    return apos_resposta(thread, retrabalho=True)


if __name__ == "__main__":
    alerta = ao_enviar_resposta("implement-auth", "Migração pronta.\nPosso aplicar em staging?")
    print(alerta or "sem alerta")
