"""Elegibilidade para retirada (RF-12 a RF-17, RF-19) — calculada SEMPRE no servidor.

Para cada produto responde: qual regra vale para este colaborador, quanto ele já
consumiu no mês, quando foi a última entrega, se há saldo livre no totem e, se o
pedido fugir da regra, por quê (motivos de exceção).
"""
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from ..models import Entrega, RegraFornecimento, SolicitacaoItem
from . import rh
from .estados import ESTADOS_AGUARDANDO, ESTADOS_APROVADOS

ANTECIPADA = "antecipada"
ACIMA_DA_COTA = "acima_da_cota"
EXIGE_JUSTIFICATIVA = "exige_justificativa"
TAMANHO_DIFERENTE = "tamanho_diferente"
HABILITACAO_VENCIDA = "habilitacao_vencida"
HABILITACAO_EXIGIDA = "habilitacao_exigida"

DESCRICAO_MOTIVO = {
    ANTECIPADA: "Substituição antecipada",
    ACIMA_DA_COTA: "Limite mensal excedido",
    EXIGE_JUSTIFICATIVA: "Produto exige justificativa",
    TAMANHO_DIFERENTE: "Tamanho inadequado",
    HABILITACAO_VENCIDA: "Habilitação/credencial vencida",
    HABILITACAO_EXIGIDA: "Habilitação/credencial não cadastrada",
}

PREFIXO_FUNCIONARIO = "MAT:"
PREFIXO_FUNCAO = "FUNC:"
PREFIXO_HABILITACAO = "HAB:"


@dataclass
class Regra:
    limite_mensal: int | None
    periodicidade_dias: int | None
    origem: str  # texto para a tela: "Funcionário: ...", "Habilitação: NR-35", "Função: Soldagem", "Cargo: Eletricista", "Setor: Manutenção", "Padrão do produto"
    habilitacao_vencida: str = ""
    habilitacao_exigida: str = ""


@dataclass
class Avaliacao:
    produto: object
    regra: Regra
    consumido_mes: int = 0
    saldo_cota: int | None = None
    ultima_entrega: object = None
    proxima_regular: object = None
    saldo_livre_totem: int = 0
    tem_pendente: bool = False
    motivos: list = field(default_factory=list)
    tamanho_recomendado: bool = False
    tamanho_esperado: str = ""

    @property
    def excepcional(self):
        return bool(self.motivos)

    @property
    def motivo_principal(self):
        return DESCRICAO_MOTIVO[self.motivos[0]] if self.motivos else "Retirada regular"


def _habilitacao_exigida_faltante(produto, mapa_hab):
    """Retorna o nome da habilitação/NR exigida pelo produto caso o colaborador não a possua."""
    regras_hab_produto = RegraFornecimento.objects.filter(
        produto=produto,
        ativo=True,
        cargo__istartswith=PREFIXO_HABILITACAO,
    )
    if not regras_hab_produto.exists():
        return ""
    nomes_habs = [r.cargo[len(PREFIXO_HABILITACAO):].strip() for r in regras_hab_produto]
    if any(nome.lower() in mapa_hab for nome in nomes_habs):
        return ""
    return nomes_habs[0]


def _avaliar_regra_candidata(regra, colaborador, cargo, funcao, mapa_hab, marcador_matricula):
    """Calcula `(peso, rotulo_escopo, hab_vencida)` de uma regra para o colaborador,
    ou `(None, "", "")` quando a regra não se aplica.

    Tabela de precedência:
      Funcionário (MAT:) = 8 > Habilitação/NR (HAB:) = 6 > Função (FUNC:) = 4 > Cargo = 2 > Setor = 1
      (+1 de bônus quando a regra também restringe pelo setor do colaborador).
    """
    alvo = (regra.cargo or "").strip()
    alvo_upper = alvo.upper()
    bonus_setor = 1 if regra.setor_id else 0

    if not alvo:
        if regra.setor_id and regra.setor_id == colaborador.setor_id:
            return 1, "", ""
        return None, "", ""

    if alvo_upper == marcador_matricula.upper():
        return 8 + bonus_setor, f"Funcionário: {colaborador.nome} ({colaborador.codigo_matricula})", ""

    if alvo_upper.startswith(PREFIXO_HABILITACAO):
        nome_hab = alvo[len(PREFIXO_HABILITACAO):].strip()
        info_hab = mapa_hab.get(nome_hab.lower())
        if info_hab is not None:
            vencida = info_hab["nome"] if info_hab.get("vencida") else ""
            return 6 + bonus_setor, f"Habilitação: {info_hab['nome']}", vencida
        return None, "", ""

    if alvo_upper.startswith(PREFIXO_FUNCAO):
        nome_func = alvo[len(PREFIXO_FUNCAO):].strip()
        if funcao and nome_func.lower() == funcao.lower():
            return 4 + bonus_setor, f"Função: {funcao}", ""
        return None, "", ""

    if cargo and alvo.lower() == cargo.lower():
        return 2 + bonus_setor, f"Cargo: {regra.cargo}", ""

    # Fallbacks para regras legadas cadastradas sem prefixo FUNC: ou HAB:
    if funcao and alvo.lower() == funcao.lower() and (not cargo or funcao.lower() != cargo.lower()):
        return 4 + bonus_setor, f"Função: {funcao}", ""

    if alvo.lower() in mapa_hab:
        info_hab = mapa_hab[alvo.lower()]
        vencida = info_hab["nome"] if info_hab.get("vencida") else ""
        return 6 + bonus_setor, f"Habilitação: {info_hab['nome']}", vencida

    return None, "", ""


def regra_para(colaborador, produto, ficha_rh=None):
    """Seleciona a regra de fornecimento mais específica aplicável ao colaborador e produto."""
    ficha_rh = ficha_rh if isinstance(ficha_rh, dict) else rh.obter_ficha_rh(colaborador)
    cargo = (colaborador.cargo or "").strip()
    funcao = (ficha_rh.get("funcao") or "").strip()
    mapa_hab = {
        (h.get("nome") or "").strip().lower(): h
        for h in (ficha_rh.get("habilitacoes") or [])
        if (h.get("nome") or "").strip()
    }
    marcador_matricula = f"{PREFIXO_FUNCIONARIO}{(colaborador.codigo_matricula or '').strip()}"

    hab_exigida_detectada = _habilitacao_exigida_faltante(produto, mapa_hab)
    candidatas = (
        RegraFornecimento.objects.select_related("setor")
        .filter(produto=produto, ativo=True)
        .filter(Q(setor__isnull=True) | Q(setor_id=colaborador.setor_id))
    )

    melhor = None
    hab_vencida_detectada = ""

    for r in candidatas:
        peso, rotulo_escopo, hab_vencida_regra = _avaliar_regra_candidata(
            r, colaborador, cargo, funcao, mapa_hab, marcador_matricula
        )
        if hab_vencida_regra:
            hab_vencida_detectada = hab_vencida_regra
        if peso is not None and (melhor is None or peso > melhor[0]):
            melhor = (peso, r, rotulo_escopo, hab_vencida_regra)

    if melhor:
        _, r, rotulo_escopo, hab_vencida_regra = melhor
        partes = []
        if r.setor_id and r.setor:
            partes.append(f"Setor: {r.setor.nome}")
        if rotulo_escopo:
            partes.append(rotulo_escopo)
        return Regra(
            limite_mensal=r.limite_mensal if r.limite_mensal is not None else produto.limite_padrao_mensal,
            periodicidade_dias=(
                r.periodicidade_dias if r.periodicidade_dias is not None else produto.periodicidade_dias
            ),
            origem=" · ".join(partes) or "Política geral",
            habilitacao_vencida=hab_vencida_regra or hab_vencida_detectada,
            habilitacao_exigida=hab_exigida_detectada,
        )

    return Regra(
        produto.limite_padrao_mensal,
        produto.periodicidade_dias,
        "Padrão do produto",
        habilitacao_vencida=hab_vencida_detectada,
        habilitacao_exigida=hab_exigida_detectada,
    )


def consumo_no_mes(colaborador, produto, agora=None):
    """Quantidade aprovada ou entregue neste mês (as aprovadas já ocupam a cota)."""
    agora = agora or timezone.now()
    inicio = timezone.localtime(agora).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    itens = SolicitacaoItem.objects.filter(
        solicitacao__solicitante=colaborador,
        produto=produto,
        solicitacao__data_solicitacao__gte=inicio,
        solicitacao__status__in=list(ESTADOS_APROVADOS) + ["RETIRADA"],
    )
    total = 0
    for item in itens.only("quantidade_aprovada", "quantidade_solicitada"):
        total += item.quantidade_aprovada if item.quantidade_aprovada is not None else item.quantidade_solicitada
    return total


def ultima_entrega(colaborador, produto):
    return Entrega.objects.filter(colaborador=colaborador, produto=produto).order_by("-data").first()


def avaliar(colaborador, produto, quantidade=1, estoque=None, agora=None):
    agora = agora or timezone.now()
    ficha_rh = rh.obter_ficha_rh(colaborador)
    regra = regra_para(colaborador, produto, ficha_rh=ficha_rh)
    av = Avaliacao(produto=produto, regra=regra)

    av.saldo_livre_totem = max(estoque.livre, 0) if estoque else 0
    av.tem_pendente = SolicitacaoItem.objects.filter(
        solicitacao__solicitante=colaborador, produto=produto,
        solicitacao__status__in=list(ESTADOS_AGUARDANDO) + list(ESTADOS_APROVADOS),
    ).exists()

    av.consumido_mes = consumo_no_mes(colaborador, produto, agora)
    if regra.limite_mensal is not None:
        av.saldo_cota = max(regra.limite_mensal - av.consumido_mes, 0)
        if av.consumido_mes + quantidade > regra.limite_mensal:
            av.motivos.append(ACIMA_DA_COTA)

    entrega = ultima_entrega(colaborador, produto)
    if entrega:
        av.ultima_entrega = entrega.data
        if produto.eh_epi and regra.periodicidade_dias:
            av.proxima_regular = entrega.data + timedelta(days=regra.periodicidade_dias)
            if agora < av.proxima_regular:
                av.motivos.insert(0, ANTECIPADA)

    if regra.habilitacao_vencida and HABILITACAO_VENCIDA not in av.motivos:
        av.motivos.append(HABILITACAO_VENCIDA)
    elif regra.habilitacao_exigida and HABILITACAO_EXIGIDA not in av.motivos:
        av.motivos.append(HABILITACAO_EXIGIDA)

    if produto.eh_epi and (produto.tamanho or "").strip():
        _, esperado = rh.tamanho_esperado_para_produto(ficha_rh, produto)
        if esperado:
            av.tamanho_esperado = esperado
            if produto.tamanho.strip().upper() == esperado.strip().upper():
                av.tamanho_recomendado = True
            else:
                av.motivos.append(TAMANHO_DIFERENTE)

    if produto.requer_justificativa:
        av.motivos.append(EXIGE_JUSTIFICATIVA)
    return av
