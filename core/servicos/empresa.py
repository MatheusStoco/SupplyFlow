"""Configuração cadastral do Tenant / Empresa empregadora (Zero-Migration).

Persiste os dados do cliente inicial (Razão Social, Nome Fantasia, CNPJ,
Estabelecimento, Endereço, Cidade/UF e CEP) em `RegistroAuditoria` com
`acao="EMPRESA_CONFIGURADA"` (o último evento vale), com fallback para
variáveis de ambiente (`EMPRESA_RAZAO_SOCIAL`, `EMPRESA_CNPJ`, etc.).
"""
import os
import re

from ..auditoria import registrar
from ..models import RegistroAuditoria

ACAO_TENANT = "EMPRESA_CONFIGURADA"


def validar_cnpj(cnpj):
    """Valida e formata um CNPJ brasileiro (retorna '00.000.000/0000-00' ou None)."""
    numeros = re.sub(r"\D", "", cnpj or "")
    if len(numeros) != 14 or numeros == numeros[0] * 14:
        return None

    def digito(base):
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(base):]
        resto = sum(int(n) * p for n, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    if digito(numeros[:12]) != numeros[12] or digito(numeros[:13]) != numeros[13]:
        return None
    return f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"


def validar_cep(cep):
    """Formata um CEP ('00000-000'); devolve '' se vazio e None se inválido."""
    numeros = re.sub(r"\D", "", cep or "")
    if not numeros:
        return ""
    if len(numeros) != 8:
        return None
    return f"{numeros[:5]}-{numeros[5:]}"


def _defaults_ambiente():
    return {
        "razao_social": os.getenv("EMPRESA_RAZAO_SOCIAL", "").strip() or "SupplyFlow Indústria e Comércio Ltda",
        "nome_fantasia": os.getenv("EMPRESA_NOME_FANTASIA", "").strip() or "SupplyFlow",
        "cnpj": os.getenv("EMPRESA_CNPJ", "").strip(),
        "estabelecimento": os.getenv("EMPRESA_ESTABELECIMENTO", "").strip() or "Matriz / Unidade Industrial",
        "endereco": os.getenv("EMPRESA_ENDERECO", "").strip(),
        "cidade": os.getenv("EMPRESA_CIDADE", "").strip(),
        "cep": os.getenv("EMPRESA_CEP", "").strip(),
    }


def obter_dados_empresa():
    """Retorna os dados atuais do Tenant/Empregador para cabeçalhos legais (NR-6)."""
    dados = _defaults_ambiente()
    registro = (
        # Busca pela ação: registrar() grava o campo `entidade` a partir de um objeto do banco,
        # e aqui não há objeto (a configuração vive só nos detalhes do evento).
        RegistroAuditoria.objects.filter(acao=ACAO_TENANT)
        .order_by("-data", "-id")
        .first()
    )
    if registro and isinstance(registro.detalhes, dict):
        det = registro.detalhes
        for chave in ("razao_social", "nome_fantasia", "cnpj", "estabelecimento", "endereco", "cidade", "cep"):
            if chave in det and det[chave] is not None:
                dados[chave] = str(det[chave]).strip()
    dados["configurada"] = bool(dados["razao_social"] and dados["cnpj"])
    return dados


def salvar_dados_empresa(request, razao_social, cnpj, nome_fantasia="", estabelecimento="", endereco="", cidade="", cep=""):
    """Salva a configuração do Tenant na trilha de auditoria e devolve o dicionário atualizado."""
    detalhes = {
        "razao_social": razao_social.strip(),
        "nome_fantasia": (nome_fantasia or "").strip(),
        "cnpj": cnpj,
        "estabelecimento": (estabelecimento or "").strip(),
        "endereco": (endereco or "").strip(),
        "cidade": (cidade or "").strip(),
        "cep": (cep or "").strip(),
    }
    registrar(
        request,
        ACAO_TENANT,
        descricao=f"Atualizou dados da empresa: {detalhes['razao_social']} ({cnpj})",
        **detalhes,
    )
    return obter_dados_empresa()
