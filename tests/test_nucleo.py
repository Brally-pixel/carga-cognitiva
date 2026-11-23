"""Testes do cálculo. Rodar com: python -m unittest discover -s tests -v"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from carga_cognitiva import cli, nucleo

T0 = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)


def minutos(n):
    return T0 + timedelta(minutes=n)


class BaseComPasta(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dados = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class TestFormula(unittest.TestCase):
    def test_fator_tempo_em_degraus(self):
        c = nucleo.CONFIG_PADRAO
        self.assertEqual(nucleo.fator_tempo(0, c), 1.0)
        self.assertEqual(nucleo.fator_tempo(90, c), 1.0)
        self.assertEqual(nucleo.fator_tempo(119, c), 1.0)
        self.assertEqual(nucleo.fator_tempo(120, c), 1.25)
        self.assertEqual(nucleo.fator_tempo(150, c), 1.5)
        self.assertEqual(nucleo.fator_tempo(210, c), 2.0)

    def test_faixas(self):
        c = nucleo.CONFIG_PADRAO
        self.assertEqual(nucleo.faixa_de(29.99, c), "verde")
        self.assertEqual(nucleo.faixa_de(30, c), "amarelo")
        self.assertEqual(nucleo.faixa_de(59.99, c), "amarelo")
        self.assertEqual(nucleo.faixa_de(60, c), "vermelho")

    def test_exemplo_da_conversa_da_49_5_amarelo(self):
        """2h30, 12 decisões, 4 trocas, 3 retrabalhos, 800 linhas -> (12+8+9+4) x 1,5."""
        # 5 blocos de thread alternados => 4 trocas
        blocos = ["A", "B", "A", "C", "A"]
        sessao = []
        t = 0
        decisoes_restantes, linhas_restantes = 12, 800
        for thread in blocos:
            for _ in range(4):  # 20 respostas, uma a cada 7 min
                decisao = decisoes_restantes > 0
                decisoes_restantes -= 1 if decisao else 0
                linhas = 40 if linhas_restantes else 0
                linhas_restantes -= linhas
                sessao.append(nucleo.Evento(minutos(t), "resposta", thread, linhas, decisao))
                t += 7
        # retrabalhos na mesma thread do bloco, para não criar trocas extras
        for instante, thread in ((1, "A"), (29, "B"), (57, "A")):
            sessao.append(nucleo.Evento(minutos(instante), "retrabalho", thread))
        sessao.sort(key=lambda e: e.ts)

        p = nucleo.pontuar_sessao(sessao, minutos(150), nucleo.CONFIG_PADRAO)
        self.assertEqual((p.decisoes, p.trocas, p.retrabalhos, p.linhas), (12, 4, 3, 800))
        self.assertEqual(p.fator_tempo, 1.5)
        self.assertEqual(p.score, 49.5)
        self.assertEqual(p.faixa, "amarelo")

    def test_sessao_vazia(self):
        p = nucleo.pontuar_sessao([], T0, nucleo.CONFIG_PADRAO)
        self.assertEqual((p.score, p.faixa), (0.0, "verde"))


class TestSessao(BaseComPasta):
    def test_pausa_encerra_a_sessao(self):
        nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(0))
        nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(10))
        # 31 min sem eventos: sessão terminou
        self.assertEqual(nucleo.pontuar(self.dados, minutos(41)).score, 0.0)
        # novo evento abre sessão nova, sem herdar as 2 decisões
        nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(60))
        p = nucleo.pontuar(self.dados, minutos(60))
        self.assertEqual(p.decisoes, 1)
        self.assertEqual(p.minutos, 0.0)

    def test_trocas_contam_mudanca_de_thread(self):
        for i, thread in enumerate(["A", "A", "B", "A", "C"]):
            nucleo.registrar(thread, dados=self.dados, momento=minutos(i))
        p = nucleo.pontuar(self.dados, minutos(5))
        self.assertEqual(p.trocas, 3)
        self.assertEqual(p.threads, ["A", "B", "C"])
        self.assertEqual(p.score, 6.0)

    def test_evento_sobrevive_ida_e_volta_no_arquivo(self):
        nucleo.registrar("A", linhas=120, decisao=True, dados=self.dados, momento=minutos(0))
        nucleo.registrar("A", retrabalho=True, dados=self.dados, momento=minutos(1))
        resposta, retrabalho = nucleo.ler_eventos(self.dados)
        self.assertEqual((resposta.tipo, resposta.linhas, resposta.decisao), ("resposta", 120, True))
        self.assertEqual((retrabalho.tipo, retrabalho.decisao), ("retrabalho", False))

    def test_config_json_sobrepoe_padrao_e_rejeita_chave_errada(self):
        (self.dados / "config.json").write_text('{"limite_amarelo": 5}', encoding="utf-8")
        self.assertEqual(nucleo.carregar_config(self.dados)["limite_amarelo"], 5)
        (self.dados / "config.json").write_text('{"limite_amarelho": 5}', encoding="utf-8")
        with self.assertRaises(ValueError):
            nucleo.carregar_config(self.dados)


class TestAlerta(BaseComPasta):
    def _decisoes(self, quantas, inicio, thread="A"):
        for i in range(quantas):
            nucleo.registrar(thread, decisao=True, dados=self.dados, momento=minutos(inicio + i))

    def test_verde_nao_alerta(self):
        self._decisoes(5, 0)
        self.assertIsNone(nucleo.verificar_alerta(self.dados, minutos(5)))

    def test_amarelo_alerta_uma_vez_e_respeita_cooldown(self):
        self._decisoes(30, 0)
        primeiro = nucleo.verificar_alerta(self.dados, minutos(30))
        self.assertIn("AMARELO", primeiro)
        self.assertIsNone(nucleo.verificar_alerta(self.dados, minutos(35)))
        # mantém a sessão viva e passa do cooldown de 20 min
        self._decisoes(1, 45)
        self.assertIn("AMARELO", nucleo.verificar_alerta(self.dados, minutos(51)))

    def test_subir_de_faixa_fura_o_cooldown(self):
        self._decisoes(30, 0)
        self.assertIn("AMARELO", nucleo.verificar_alerta(self.dados, minutos(30)))
        self._decisoes(30, 30)
        self.assertIn("VERMELHO", nucleo.verificar_alerta(self.dados, minutos(60)))

    def test_apos_resposta_conta_linhas_do_texto(self):
        texto = "linha 1\n\nlinha 2\n   \nlinha 3\n"
        self.assertIsNone(nucleo.apos_resposta("A", texto, dados=self.dados, momento=minutos(0)))
        self.assertEqual(nucleo.pontuar(self.dados, minutos(0)).linhas, 3)


class TestMemoria(BaseComPasta):
    def test_feedback_guarda_score_zero(self):
        nucleo.registrar("A", dados=self.dados, momento=minutos(0))
        nucleo.registrar_feedback(1, self.dados, minutos(1))
        feedback = [e for e in nucleo.ler_eventos(self.dados) if e.tipo == "feedback"][0]
        self.assertEqual((feedback.nota, feedback.score, feedback.faixa), (1, 0.0, "verde"))

    def test_feedback_rejeita_nota_fora_da_escala(self):
        with self.assertRaises(ValueError):
            nucleo.registrar_feedback(6, self.dados, minutos(0))

    def test_resumo_lista_sessoes_com_nota_e_alertas(self):
        for i in range(30):
            nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(i))
        nucleo.verificar_alerta(self.dados, minutos(30))
        nucleo.registrar_feedback(4, self.dados, minutos(31))
        nucleo.registrar("B", decisao=True, dados=self.dados, momento=minutos(200))

        sessoes = nucleo.resumo(7, self.dados, minutos(201))
        self.assertEqual(len(sessoes), 2)
        self.assertEqual((sessoes[0]["score"], sessoes[0]["faixa"]), (30.0, "amarelo"))
        self.assertEqual((sessoes[0]["alertas"], sessoes[0]["nota"]), (1, 4))
        self.assertEqual((sessoes[1]["decisoes"], sessoes[1]["nota"]), (1, None))

    def test_calibracao_conta_inversoes(self):
        for nota, score in ((1, 5.0), (3, 30.0), (5, 70.0), (4, 10.0)):
            nucleo.gravar_evento(
                nucleo.Evento(T0, "feedback", nota=nota, score=score, faixa="verde"), self.dados
            )
        c = nucleo.calibracao(self.dados)
        self.assertEqual(c["amostras"], 4)
        self.assertEqual(c["pares_comparaveis"], 6)
        self.assertEqual(c["inversoes"], 1)  # nota 4 com score 10 < nota 3 com score 30
        self.assertEqual(c["media_score_por_nota"], {1: 5.0, 3: 30.0, 4: 10.0, 5: 70.0})


class TestCLI(BaseComPasta):
    def _rodar(self, *args, stdin=None):
        saida = io.StringIO()
        with redirect_stdout(saida):
            if stdin is None:
                codigo = cli.main([*args, "--dados", str(self.dados)])
            else:
                with mock.patch("sys.stdin", io.StringIO(stdin)):
                    codigo = cli.main([*args, "--dados", str(self.dados)])
        return codigo, saida.getvalue()

    def test_hook_registra_e_alerta_ao_cruzar_o_limite(self):
        saida = ""
        for i in range(30):
            evento = json.dumps({"thread": "A", "texto": "ok?", "decisao": True})
            codigo, saida = self._rodar(
                "hook", "--agora", minutos(i).isoformat(), stdin=evento
            )
            self.assertEqual(codigo, 0)
            if i < 28:
                self.assertEqual(saida, "")
        # 30 decisões + 30 linhas/200 = 30,15
        self.assertIn("AMARELO", saida)

    def test_hook_sem_thread_falha(self):
        codigo, _ = self._rodar("hook", stdin="{}")
        self.assertEqual(codigo, 2)

    def test_pontuar_json(self):
        self._rodar("registrar", "--thread", "A", "--decisao", "--agora", minutos(0).isoformat())
        _, saida = self._rodar("pontuar", "--json", "--agora", minutos(1).isoformat())
        self.assertEqual(json.loads(saida)["score"], 1.0)


if __name__ == "__main__":
    unittest.main()
