"""Popula o banco de dados com registros iniciais essenciais (seed idempotente).

Uso:  python manage.py popular_banco

Projetado para rodar com segurança em qualquer ambiente (incluindo produção no
Render/PostgreSQL) após `migrate`: usa `get_or_create` e `update_or_create`
para não duplicar registros nem sobrescrever saldos de estoque ou senhas já
alteradas em uso.

Variáveis de ambiente opcionais:
  SEED_ADMIN_EMAIL  (padrão: admin@supplyflow.com)
  SEED_ADMIN_SENHA  (padrão: Admin@2026)
"""
import os
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.contas import garantir_conta
from core.models import (
    CategoriaProduto,
    EstoqueTotem,
    Fornecedor,
    Produto,
    RegraFornecimento,
    Setor,
    Totem,
    Usuario,
)
from core.seguranca import definir_pin

SETORES_INICIAIS = [
    ("Administração e TI", "CC-001"),
    ("Produção Industrial", "CC-100"),
    ("Manutenção Mecânica", "CC-200"),
]

COLABORADORES_TESTE = [
    {
        "codigo_matricula": "001245",
        "nome": "João da Silva",
        "cargo": "Operador de Produção",
        "setor_nome": "Produção Industrial",
        "pin": "1234",
    },
    {
        "codigo_matricula": "001246",
        "nome": "Maria Oliveira",
        "cargo": "Técnica de Manutenção",
        "setor_nome": "Manutenção Mecânica",
        "pin": "1234",
    },
]

CATEGORIAS_INICIAIS = [
    ("EPI", "Equipamentos de Proteção Individual com Certificado de Aprovação (CA)."),
    ("Consumível", "Materiais e insumos consumíveis de operação e manutenção."),
]

PRODUTOS_INICIAIS = [
    {
        "sku": "EPI-LUVA-01",
        "nome": "Luva de Proteção Anticorte",
        "categoria_nome": "EPI",
        "descricao": "Luva tricotada com fios de alta tenacidade, proteção anticorte nível 5.",
        "unidade_medida": "PAR",
        "custo_unitario": Decimal("35.00"),
        "limite_padrao_mensal": 2,
        "requer_justificativa": False,
        "ca": "12345",
        "validade_ca": date(2028, 12, 31),
        "tamanho": "M",
        "periodicidade_dias": 90,
        "estoque_inicial": 20,
        "estoque_minimo": 5,
        "slot_posicao": "A1",
        "lote": "LOTE-2026-01",
    },
    {
        "sku": "EPI-OCULOS-01",
        "nome": "Óculos de Proteção Incolor",
        "categoria_nome": "EPI",
        "descricao": "Óculos de segurança em policarbonato com lente incolor antiembaçante.",
        "unidade_medida": "UN",
        "custo_unitario": Decimal("18.50"),
        "limite_padrao_mensal": 1,
        "requer_justificativa": False,
        "ca": "45678",
        "validade_ca": date(2028, 12, 31),
        "tamanho": "Único",
        "periodicidade_dias": 120,
        "estoque_inicial": 25,
        "estoque_minimo": 5,
        "slot_posicao": "A2",
        "lote": "LOTE-2026-02",
    },
    {
        "sku": "EPI-AURIC-01",
        "nome": "Protetor Auricular Silicone",
        "categoria_nome": "EPI",
        "descricao": "Protetor auditivo tipo inserção em silicone hipoalergênico com cordão.",
        "unidade_medida": "UN",
        "custo_unitario": Decimal("4.50"),
        "limite_padrao_mensal": 2,
        "requer_justificativa": False,
        "ca": "23456",
        "validade_ca": date(2028, 12, 31),
        "tamanho": "Único",
        "periodicidade_dias": 60,
        "estoque_inicial": 50,
        "estoque_minimo": 10,
        "slot_posicao": "B1",
        "lote": "LOTE-2026-03",
    },
    {
        "sku": "CON-DISCO-01",
        "nome": 'Disco de Corte 4½"',
        "categoria_nome": "Consumível",
        "descricao": "Disco abrasivo de corte fino 115 x 1,0 x 22,2 mm para aço carbono e inox.",
        "unidade_medida": "UN",
        "custo_unitario": Decimal("8.90"),
        "limite_padrao_mensal": 10,
        "requer_justificativa": False,
        "ca": None,
        "validade_ca": None,
        "tamanho": None,
        "periodicidade_dias": None,
        "estoque_inicial": 40,
        "estoque_minimo": 10,
        "slot_posicao": "C1",
        "lote": "LOTE-2026-04",
    },
]

REGRAS_INICIAIS = [
    {
        "sku": "EPI-LUVA-01",
        "setor_nome": "Produção Industrial",
        "cargo": "",
        "limite_mensal": 2,
        "periodicidade_dias": 60,
    },
    {
        "sku": "EPI-OCULOS-01",
        "setor_nome": "Manutenção Mecânica",
        "cargo": "",
        "limite_mensal": 2,
        "periodicidade_dias": 90,
    },
    {
        "sku": "CON-DISCO-01",
        "setor_nome": "Manutenção Mecânica",
        "cargo": "",
        "limite_mensal": 15,
        "periodicidade_dias": None,
    },
]


class Command(BaseCommand):
    help = "Popula o banco de dados com registros iniciais de forma idempotente."

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Setores / Centros de Custo
        setores = {}
        for nome, centro_custo in SETORES_INICIAIS:
            setor, _ = Setor.objects.update_or_create(
                nome=nome,
                defaults={"centro_custo": centro_custo, "ativo": True},
            )
            setores[nome] = setor

        # 2. Conta Administrativa Principal (Backoffice)
        admin_email = (os.getenv("SEED_ADMIN_EMAIL") or "admin@supplyflow.com").strip().lower()
        admin_senha = os.getenv("SEED_ADMIN_SENHA") or "Admin@2026"

        admin_usuario, _ = Usuario.objects.update_or_create(
            codigo_matricula="A-001",
            defaults={
                "nome": "Administrador SupplyFlow",
                "email": admin_email,
                "perfil": "ADMIN",
                "cargo": "Administrador do Sistema",
                "setor": setores["Administração e TI"],
                "ativo": True,
            },
        )
        conta_admin = garantir_conta(admin_usuario)
        if conta_admin is not None and not conta_admin.has_usable_password():
            conta_admin.set_password(admin_senha)
            conta_admin.save(update_fields=["password"])

        # 3. Colaboradores Operacionais de Teste (Totem)
        for dados_colab in COLABORADORES_TESTE:
            colaborador, _ = Usuario.objects.update_or_create(
                codigo_matricula=dados_colab["codigo_matricula"],
                defaults={
                    "nome": dados_colab["nome"],
                    "perfil": "COLABORADOR",
                    "cargo": dados_colab["cargo"],
                    "setor": setores[dados_colab["setor_nome"]],
                    "email": None,
                    "ativo": True,
                },
            )
            if not colaborador.pin_hash:
                definir_pin(colaborador, dados_colab["pin"])
                colaborador.save(update_fields=["pin_hash"])
            garantir_conta(colaborador)

        # 4. Totem, Fornecedor, Categorias, Produtos e Estoque Inicial
        totem, _ = Totem.objects.update_or_create(
            codigo="TOTEM-01",
            defaults={
                "nome": "Totem Principal - Fábrica",
                "localizacao": "Almoxarifado Central — Fábrica",
                "status_online": True,
            },
        )

        fornecedor, _ = Fornecedor.objects.update_or_create(
            cnpj="12.345.678/0001-90",
            defaults={
                "razao_social": "SafeWork Equipamentos de Proteção Ltda",
                "nome_fantasia": "SafeWork EPIs",
                "email": "vendas@safework.com.br",
                "telefone": "(44) 3025-1000",
                "contato": "Roberto Almeida",
                "ativo": True,
            },
        )

        categorias = {}
        for nome, descricao in CATEGORIAS_INICIAIS:
            categoria, _ = CategoriaProduto.objects.update_or_create(
                nome=nome,
                defaults={"descricao": descricao},
            )
            categorias[nome] = categoria

        produtos = {}
        for item in PRODUTOS_INICIAIS:
            produto, _ = Produto.objects.update_or_create(
                sku=item["sku"],
                defaults={
                    "nome": item["nome"],
                    "categoria": categorias[item["categoria_nome"]],
                    "descricao": item["descricao"],
                    "unidade_medida": item["unidade_medida"],
                    "custo_unitario": item["custo_unitario"],
                    "limite_padrao_mensal": item["limite_padrao_mensal"],
                    "requer_justificativa": item["requer_justificativa"],
                    "ca": item["ca"],
                    "validade_ca": item["validade_ca"],
                    "tamanho": item["tamanho"],
                    "periodicidade_dias": item["periodicidade_dias"],
                    "fornecedor": fornecedor,
                    "ativo": True,
                },
            )
            produtos[item["sku"]] = produto

            EstoqueTotem.objects.get_or_create(
                totem=totem,
                produto=produto,
                defaults={
                    "quantidade_disponivel": item["estoque_inicial"],
                    "quantidade_reservada": 0,
                    "quantidade_minima": item["estoque_minimo"],
                    "slot_posicao": item["slot_posicao"],
                    "lote": item["lote"],
                },
            )

        # 5. Políticas de Fornecimento iniciais
        for regra in REGRAS_INICIAIS:
            RegraFornecimento.objects.get_or_create(
                produto=produtos[regra["sku"]],
                setor=setores[regra["setor_nome"]],
                cargo=regra["cargo"],
                defaults={
                    "limite_mensal": regra["limite_mensal"],
                    "periodicidade_dias": regra["periodicidade_dias"],
                    "ativo": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Banco de dados populado com sucesso (seed idempotente concluído)."
            )
        )
