"""Configurações: dados da empresa usados como padrão no sistema (Ficha de EPI NR-6, topo do backoffice)."""
from django.test import Client

from core.models import RegistroAuditoria

from .base import BaseTeste

# Dados fictícios (o CNPJ tem dígitos verificadores válidos, mas não é de empresa real usada no teste).
EMPRESA = {
    "razao_social": "Empresa Teste Ltda",
    "nome_fantasia": "Empresa Teste",
    "cnpj": "10433218000193",
    "estabelecimento": "Matriz",
    "endereco": "Rua Exemplo, 100 - Centro",
    "cidade": "Curitiba - PR",
    "cep": "81070190",
}


class ConfiguracoesTeste(BaseTeste):
    def test_pagina_exige_login_e_abre_para_o_backoffice(self):
        self.assertEqual(Client().get("/backoffice/configuracoes.html").status_code, 302)
        self.entrar(self.gestor)
        self.assertEqual(self.client.get("/backoffice/configuracoes.html").status_code, 200)

    def test_admin_salva_dados_formatados_e_registra_auditoria(self):
        self.entrar(self.admin)
        r = self.post("/api/empresa/salvar/", EMPRESA)
        self.assertEqual(r.status_code, 200, r.content)
        empresa = self.client.get("/api/empresa/").json()["empresa"]
        self.assertEqual(empresa["cnpj"], "10.433.218/0001-93")
        self.assertEqual(empresa["cep"], "81070-190")
        self.assertEqual(empresa["nome_fantasia"], "Empresa Teste")
        self.assertTrue(empresa["configurada"])
        self.assertTrue(RegistroAuditoria.objects.filter(acao="EMPRESA_CONFIGURADA").exists())

    def test_dados_valem_para_a_ficha_de_epi(self):
        self.entrar(self.admin)
        self.post("/api/empresa/salvar/", EMPRESA)
        ficha = self.client.get(f"/api/funcionarios/{self.colaborador.id}/ficha/").json()
        self.assertEqual(ficha["empresa"]["razao_social"], "Empresa Teste Ltda")
        self.assertEqual(ficha["empresa"]["cep"], "81070-190")

    def test_valida_cnpj_e_cep(self):
        self.entrar(self.admin)
        r = self.post("/api/empresa/salvar/", dict(EMPRESA, cnpj="11.111.111/1111-11"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("CNPJ válido", r.json()["erro"])
        r = self.post("/api/empresa/salvar/", dict(EMPRESA, cep="123"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("CEP válido", r.json()["erro"])

    def test_somente_admin_altera(self):
        self.entrar(self.gestor)
        self.assertFalse(self.client.get("/api/empresa/").json()["pode_editar"])
        self.assertEqual(self.post("/api/empresa/salvar/", EMPRESA).status_code, 403)
