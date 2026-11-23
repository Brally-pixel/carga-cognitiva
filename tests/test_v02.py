"""Testes das mudanças da v0.2 (ver docs/REFERENCIAS.md)."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from carga_cognitiva import cli, nucleo

T0 = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
C = nucleo.CONFIG_PADRAO


def minutos(n):
    return T0 + timedelta(minutes=n)


def segundos(n):
    return T0 + timedelta(seconds=n)


class BaseComPasta(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dados = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class TestDecaimento(BaseComPasta):
    def test_meia_vida(self):
        self.assertEqual(nucleo.decair(30, 30, C), 15.0)
        self.assertEqual(nucleo.decair(30, 60, C), 7.5)
        self.assertEqual(nucleo.decair(30, 0, C), 30.0)
        self.assertEqual(nucleo.decair(30, 150, C), 0.0)  # 0,94 fica abaixo do mínimo
        self.assertEqual(nucleo.decair(0, 10, C), 0.0)

    def _sessao_de_40(self):
        for i in range(40):
            nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(i))

    def test_pausa_nao_zera_a_carga(self):
        self._sessao_de_40()  # termina no minuto 39 com score 40
        # 31 min depois: sessão encerrada, sobra o residual
        p = nucleo.pontuar(self.dados, minutos(70))
        self.assertIsNone(p.inicio)
        self.assertEqual(p.score, 19.54)
        self.assertEqual(p.faixa, "verde")
        # 60 min depois do último evento: um quarto
        self.assertEqual(nucleo.pontuar(self.dados, minutos(99)).score, 10.0)

    def test_sessao_seguinte_herda_o_residual(self):
        self._sessao_de_40()
        nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(70))
        p = nucleo.pontuar(self.dados, minutos(70))
        self.assertEqual((p.decisoes, p.residual, p.score), (1, 19.54, 20.54))
        self.assertEqual(p.minutos, 0.0)  # o relógio da sessão recomeça

    def test_residual_pode_disparar_alerta_na_volta(self):
        for i in range(70):
            nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(i))
        # volta 31 min depois com 34,2 de residual: já começa em amarelo
        nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(100))
        self.assertIn("AMARELO", nucleo.verificar_alerta(self.dados, minutos(100)))

    def test_resumo_mostra_residual(self):
        self._sessao_de_40()
        nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(70))
        primeira, segunda = nucleo.resumo(7, self.dados, minutos(71))
        self.assertEqual((primeira["residual"], primeira["score"]), (0.0, 40.0))
        self.assertEqual((segunda["residual"], segunda["score"]), (19.54, 20.54))


class TestTrocas(unittest.TestCase):
    def _pontuar(self, *passos):
        sessao = [
            nucleo.Evento(minutos(i), "resposta", thread, concluida=concluida)
            for i, (thread, concluida) in enumerate(passos)
        ]
        return nucleo.pontuar_sessao(sessao, minutos(len(passos)), C)

    def test_sair_de_thread_concluida_e_troca_limpa(self):
        p = self._pontuar(("A", True), ("B", False))
        self.assertEqual((p.trocas, p.trocas_limpas, p.score), (0, 1, 1.0))

    def test_sair_de_thread_aberta_deixa_pendencia(self):
        p = self._pontuar(("A", False), ("B", False))
        self.assertEqual((p.trocas, p.trocas_limpas, p.score), (1, 0, 2.0))

    def test_novo_evento_reabre_a_thread(self):
        # A conclui -> B (limpa); B aberta -> A (pendente); A reaberta -> B (pendente)
        p = self._pontuar(("A", True), ("B", False), ("A", False), ("B", False))
        self.assertEqual((p.trocas, p.trocas_limpas), (2, 1))


class TestRitmo(unittest.TestCase):
    def test_ritmo_acima_do_limite_soma_pontos_ate_o_teto(self):
        sessao = [
            nucleo.Evento(minutos(0), "resposta", "A", linhas=300),
            nucleo.Evento(minutos(30), "resposta", "A", linhas=300),
        ]
        # 600 linhas em 60 min = 600 l/h; excesso de 20% sobre 500 -> +1 ponto
        p = nucleo.pontuar_sessao(sessao, minutos(60), C)
        self.assertEqual((p.ritmo, p.pontos_ritmo, p.score), (600.0, 1.0, 4.0))
        # 2000 l/h: excesso limitado a 2x -> +10 pontos
        sessao[0].linhas = sessao[1].linhas = 1000
        p = nucleo.pontuar_sessao(sessao, minutos(60), C)
        self.assertEqual((p.ritmo, p.pontos_ritmo, p.score), (2000.0, 10.0, 20.0))

    def test_ritmo_nao_conta_em_sessao_curta(self):
        sessao = [nucleo.Evento(minutos(0), "resposta", "A", linhas=1000)]
        p = nucleo.pontuar_sessao(sessao, minutos(10), C)
        self.assertEqual((p.ritmo, p.pontos_ritmo, p.score), (0.0, 0.0, 5.0))


class TestRespostaGrande(BaseComPasta):
    def test_aviso_acima_de_400_linhas(self):
        aviso = nucleo.apos_resposta("A", linhas=450, dados=self.dados, momento=minutos(0))
        self.assertIn("450 linhas", aviso)
        self.assertEqual(nucleo.pontuar(self.dados, minutos(0)).respostas_grandes, 1)

    def test_sem_aviso_ate_400_linhas(self):
        self.assertIsNone(
            nucleo.apos_resposta("A", linhas=400, dados=self.dados, momento=minutos(0))
        )


class TestAprovacaoNoAutomatico(BaseComPasta):
    def _ciclo(self, inicio_s, espera_s, linhas=100, thread="A"):
        """Pedido de decisão e aprovação `espera_s` segundos depois; devolve o aviso."""
        nucleo.apos_resposta(
            thread, linhas=linhas, decisao=True, dados=self.dados, momento=segundos(inicio_s)
        )
        return nucleo.apos_resposta(
            thread, aprovacao=True, dados=self.dados, momento=segundos(inicio_s + espera_s)
        )

    def test_tres_aprovacoes_rapidas_seguidas_avisam_uma_vez(self):
        self.assertIsNone(self._ciclo(0, 10))
        self.assertIsNone(self._ciclo(60, 10))
        aviso = self._ciclo(120, 10)  # 100 linhas em 10 s = 36.000 l/h
        self.assertIn("aprovações", aviso)
        self.assertIsNone(self._ciclo(180, 10))  # dentro do cooldown
        p = nucleo.pontuar(self.dados, segundos(200))
        self.assertEqual((p.aprovacoes, p.aprovacoes_automaticas), (4, 4))
        self.assertTrue(p.aprovacao_no_automatico)

    def test_aprovacao_com_tempo_de_leitura_nao_avisa(self):
        for i in range(4):  # 100 linhas em 10 min = 600 l/h, abaixo de 1000
            self.assertIsNone(self._ciclo(i * 700, 600))
        p = nucleo.pontuar(self.dados, segundos(2800))
        self.assertEqual((p.aprovacoes, p.aprovacoes_automaticas), (4, 0))
        self.assertFalse(p.aprovacao_no_automatico)

    def test_uma_aprovacao_lida_quebra_a_sequencia(self):
        self._ciclo(0, 10)
        self._ciclo(60, 10)
        self.assertIsNone(self._ciclo(120, 600))
        self.assertFalse(nucleo.pontuar(self.dados, segundos(720)).aprovacao_no_automatico)

    def test_pedido_pequeno_nao_e_avaliado(self):
        for i in range(4):
            self.assertIsNone(self._ciclo(i * 60, 5, linhas=10))
        self.assertEqual(nucleo.pontuar(self.dados, segundos(300)).aprovacoes, 0)

    def test_sinal_nao_altera_o_score(self):
        for i in range(3):
            self._ciclo(i * 60, 10)
        p = nucleo.pontuar(self.dados, segundos(130))
        # 3 decisões + 300 linhas/200; sessão curta demais para contar ritmo
        self.assertEqual(p.score, 4.5)

    def test_retrabalho_e_aprovacao_juntos_sao_rejeitados(self):
        with self.assertRaises(ValueError):
            nucleo.registrar("A", retrabalho=True, aprovacao=True, dados=self.dados)


class TestFeedbackEMensagens(BaseComPasta):
    def test_feedback_com_demanda_e_frustracao(self):
        nucleo.registrar("A", dados=self.dados, momento=minutos(0))
        nucleo.registrar_feedback(4, self.dados, minutos(1), demanda=5, frustracao=2)
        nucleo.registrar_feedback(2, self.dados, minutos(2), demanda=3)
        c = nucleo.calibracao(self.dados)
        self.assertEqual((c["amostras"], c["media_demanda"], c["media_frustracao"]), (2, 4.0, 2.0))
        with self.assertRaises(ValueError):
            nucleo.registrar_feedback(3, self.dados, minutos(3), demanda=9)

    def test_alerta_vermelho_cita_a_meia_vida(self):
        for i in range(60):
            nucleo.registrar("A", decisao=True, dados=self.dados, momento=minutos(i / 2))
        alerta = nucleo.verificar_alerta(self.dados, minutos(30))
        self.assertIn("VERMELHO", alerta)
        self.assertIn("30 min reduzem a carga estimada à metade", alerta)


class TestCLI(BaseComPasta):
    def _rodar(self, *args):
        saida = io.StringIO()
        with redirect_stdout(saida):
            codigo = cli.main([*args, "--dados", str(self.dados)])
        return codigo, saida.getvalue()

    def test_registrar_concluida_e_aprovacao(self):
        self._rodar("registrar", "--thread", "A", "--linhas", "50", "--decisao",
                    "--concluida", "--agora", minutos(0).isoformat())
        self._rodar("registrar", "--thread", "A", "--aprovacao", "--agora", minutos(5).isoformat())
        self._rodar("registrar", "--thread", "B", "--agora", minutos(6).isoformat())
        _, saida = self._rodar("pontuar", "--json", "--agora", minutos(6).isoformat())
        p = json.loads(saida)
        # aprovar não reabre A, então sair dela para B é troca limpa
        self.assertEqual((p["trocas"], p["trocas_limpas"], p["aprovacoes"]), (0, 1, 1))

    def test_feedback_com_escalas_extras(self):
        codigo, saida = self._rodar("feedback", "3", "--demanda", "4", "--frustracao", "1")
        self.assertEqual(codigo, 0)
        self.assertIn("Feedback 3/5", saida)


if __name__ == "__main__":
    unittest.main()
