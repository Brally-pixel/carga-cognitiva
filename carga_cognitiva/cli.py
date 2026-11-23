"""CLI `carga`: registrar eventos, pontuar, alertar, feedback, resumo e calibração."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import nucleo


def _momento(args) -> Optional[nucleo.datetime]:
    return nucleo.ler_ts(args.agora) if getattr(args, "agora", None) else None


def _imprimir_pontuacao(p: nucleo.Pontuacao) -> None:
    if not p.inicio:
        print("Sem sessão ativa: score 0 (verde).")
        return
    print(f"Score {p.score:g} -> {p.faixa.upper()}")
    print(f"  sessão: {p.minutos:.0f} min (fator de tempo x{p.fator_tempo:g})")
    print(f"  decisões: {p.decisoes} | trocas de thread: {p.trocas} | "
          f"retrabalhos: {p.retrabalhos} | linhas revisadas: {p.linhas}")
    if p.threads:
        print(f"  threads: {', '.join(p.threads)}")


def cmd_registrar(args) -> int:
    evento = nucleo.registrar(
        args.thread, args.linhas, args.decisao, args.retrabalho, args.dados, _momento(args)
    )
    print(evento.para_json())
    return 0


def cmd_pontuar(args) -> int:
    p = nucleo.pontuar(args.dados, _momento(args))
    if args.json:
        print(json.dumps(p.para_dict(), ensure_ascii=False))
    else:
        _imprimir_pontuacao(p)
    return 0


def cmd_alerta(args) -> int:
    mensagem = nucleo.verificar_alerta(args.dados, _momento(args))
    if mensagem:
        print(mensagem)
    return 0


def cmd_hook(args) -> int:
    """Lê um JSON do stdin: {"thread", "texto"?, "linhas"?, "decisao"?, "retrabalho"?}."""
    entrada = json.load(sys.stdin)
    if "thread" not in entrada:
        print('hook: campo "thread" é obrigatório', file=sys.stderr)
        return 2
    mensagem = nucleo.apos_resposta(
        thread=str(entrada["thread"]),
        texto=entrada.get("texto", ""),
        decisao=bool(entrada.get("decisao", False)),
        retrabalho=bool(entrada.get("retrabalho", False)),
        linhas=entrada.get("linhas"),
        dados=args.dados,
        momento=_momento(args),
    )
    if mensagem:
        print(mensagem)
    return 0


def cmd_feedback(args) -> int:
    evento = nucleo.registrar_feedback(args.nota, args.dados, _momento(args))
    print(f"Feedback {evento.nota}/5 registrado com score {evento.score:g} ({evento.faixa}).")
    return 0


def cmd_resumo(args) -> int:
    linhas = nucleo.resumo(args.dias, args.dados, _momento(args))
    if args.json:
        print(json.dumps(linhas, ensure_ascii=False))
        return 0
    if not linhas:
        print(f"Nenhuma sessão nos últimos {args.dias} dias.")
        return 0
    print(f"{'início':<17}{'min':>5}{'score':>8}  {'faixa':<9}{'dec':>4}{'troc':>5}"
          f"{'retr':>5}{'linhas':>7}{'alertas':>8}{'nota':>5}")
    for s in linhas:
        inicio = nucleo.ler_ts(s["inicio"]).astimezone().strftime("%Y-%m-%d %H:%M")
        nota = "-" if s["nota"] is None else s["nota"]
        print(f"{inicio:<17}{s['minutos']:>5.0f}{s['score']:>8g}  {s['faixa']:<9}"
              f"{s['decisoes']:>4}{s['trocas']:>5}{s['retrabalhos']:>5}{s['linhas']:>7}"
              f"{s['alertas']:>8}{nota:>5}")
    return 0


def cmd_calibrar(args) -> int:
    c = nucleo.calibracao(args.dados)
    if args.json:
        print(json.dumps(c, ensure_ascii=False))
        return 0
    if not c["amostras"]:
        print("Sem feedback registrado. Use `carga feedback NOTA` ao fim das sessões.")
        return 0
    print(f"Amostras de feedback: {c['amostras']}")
    for nota, media in c["media_score_por_nota"].items():
        print(f"  nota {nota}: score médio {media:g}")
    if c["concordancia"] is None:
        print("Ainda não há pares comparáveis (precisa de notas e scores diferentes).")
    else:
        print(f"Concordância nota x score: {c['concordancia']:.0%} "
              f"({c['inversoes']} inversões em {c['pares_comparaveis']} pares)")
        if c["amostras"] < 10:
            print("Menos de 10 amostras: ainda é cedo para mexer nos pesos.")
    return 0


def cmd_config(args) -> int:
    print(json.dumps(nucleo.carregar_config(args.dados), ensure_ascii=False, indent=2))
    return 0


def construir_parser() -> argparse.ArgumentParser:
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--dados", help="pasta dos dados (padrão: $CARGA_DIR ou ~/.carga-cognitiva)")
    comum.add_argument("--agora", help="instante ISO 8601 a usar no lugar do relógio (testes/simulação)")

    parser = argparse.ArgumentParser(prog="carga", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("registrar", parents=[comum], help="grava um evento de trabalho")
    p.add_argument("--thread", required=True, help="identificador da thread/frente de trabalho")
    p.add_argument("--linhas", type=int, default=0, help="linhas que o humano precisa revisar")
    p.add_argument("--decisao", action="store_true", help="a resposta pede uma decisão do humano")
    p.add_argument("--retrabalho", action="store_true", help="o humano corrigiu/refez algo")
    p.set_defaults(func=cmd_registrar)

    p = sub.add_parser("pontuar", parents=[comum], help="score e faixa da sessão em curso")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pontuar)

    p = sub.add_parser("alerta", parents=[comum], help="imprime o alerta se for hora de avisar")
    p.set_defaults(func=cmd_alerta)

    p = sub.add_parser("hook", parents=[comum], help="registra (JSON no stdin) e alerta")
    p.set_defaults(func=cmd_hook)

    p = sub.add_parser("feedback", parents=[comum], help="autoavaliação de cansaço, 1 a 5")
    p.add_argument("nota", type=int, choices=range(1, 6))
    p.set_defaults(func=cmd_feedback)

    p = sub.add_parser("resumo", parents=[comum], help="sessões dos últimos dias")
    p.add_argument("--dias", type=int, default=7)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_resumo)

    p = sub.add_parser("calibrar", parents=[comum], help="compara feedback com o score")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_calibrar)

    p = sub.add_parser("config", parents=[comum], help="mostra a configuração em vigor")
    p.set_defaults(func=cmd_config)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = construir_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
