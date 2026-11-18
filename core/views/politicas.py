"""APIs de políticas/regras de fornecimento por setor, cargo, função, habilitação ou funcionário (RF-12 a RF-14)."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from ..auditoria import registrar
from ..models import Produto, RegraFornecimento, Setor, Usuario
from ..permissoes import api_backoffice
from ..servicos.elegibilidade import PREFIXO_FUNCIONARIO, PREFIXO_FUNCAO, PREFIXO_HABILITACAO
from .cargos import (
    _catalogo_cargos,
    _catalogo_funcoes,
    _listar_catalogo_habilitacoes,
    _normalizar_cargo_catalogo,
    _normalizar_funcao_catalogo,
    _normalizar_habilitacao_catalogo,
)
from .util import EntradaInvalida, erro, inteiro, ler_json, texto
# ============================================================================
# POLÍTICAS DE FORNECIMENTO (RF-12, RF-13, RF-14)
# ============================================================================
def _regra_json(r, mapa_funcionarios=None):
    cargo_raw = (r.cargo or "").strip()
    upper = cargo_raw.upper()
    eh_funcionario = upper.startswith(PREFIXO_FUNCIONARIO)
    eh_habilitacao = upper.startswith(PREFIXO_HABILITACAO)
    eh_funcao = upper.startswith(PREFIXO_FUNCAO)

    funcionario_id = None
    funcionario_nome = None
    cargo_exibicao = None
    funcao_exibicao = None
    habilitacao_exibicao = None
    escopo_tipo = "SETOR"

    if eh_funcionario:
        escopo_tipo = "FUNCIONARIO"
        matricula = cargo_raw[len(PREFIXO_FUNCIONARIO):].strip().upper()
        func = (
            mapa_funcionarios.get(matricula)
            if mapa_funcionarios is not None
            else Usuario.objects.filter(codigo_matricula__iexact=matricula).first()
        )
        if func:
            funcionario_id = str(func.id)
            funcionario_nome = f"{func.nome} ({func.codigo_matricula})"
        else:
            funcionario_nome = f"Matrícula {matricula}"
    elif eh_habilitacao:
        escopo_tipo = "HABILITACAO"
        habilitacao_exibicao = cargo_raw[len(PREFIXO_HABILITACAO):].strip()
    elif eh_funcao:
        escopo_tipo = "FUNCAO"
        funcao_exibicao = cargo_raw[len(PREFIXO_FUNCAO):].strip()
    elif cargo_raw:
        escopo_tipo = "CARGO"
        cargo_exibicao = cargo_raw

    return {
        "id": str(r.id),
        "produto_id": str(r.produto_id),
        "produto": r.produto.nome,
        "tipo": "EPI" if r.produto.eh_epi else "Consumível",
        "setor_id": str(r.setor_id) if r.setor_id else None,
        "setor": r.setor.nome if r.setor else None,
        "escopo_tipo": escopo_tipo,
        "cargo": cargo_exibicao,
        "funcao": funcao_exibicao,
        "habilitacao": habilitacao_exibicao,
        "funcionario_id": funcionario_id,
        "funcionario": funcionario_nome,
        "limite_mensal": r.limite_mensal,
        "periodicidade_dias": r.periodicidade_dias,
        "padrao_limite": r.produto.limite_padrao_mensal,
        "padrao_periodicidade": r.produto.periodicidade_dias,
        "ativo": r.ativo,
    }


@require_GET
@api_backoffice("ver")
def api_listar_regras(request):
    regras = RegraFornecimento.objects.select_related("produto__categoria", "setor").order_by("produto__nome", "cargo")
    funcionarios_ativos = list(Usuario.objects.filter(ativo=True).order_by("nome"))
    mapa_func = {u.codigo_matricula.upper(): u for u in funcionarios_ativos}
    hab_catalogo = _listar_catalogo_habilitacoes()
    return JsonResponse({
        "regras": [_regra_json(r, mapa_func) for r in regras],
        "produtos": [{"id": str(p.id), "nome": p.nome} for p in Produto.objects.filter(ativo=True).order_by("nome")],
        "setores": [
            {"id": str(s.id), "nome": f"{s.nome} ({s.centro_custo})" if s.centro_custo else s.nome}
            for s in Setor.objects.filter(ativo=True).order_by("nome")
        ],
        "cargos": sorted(_catalogo_cargos().values()),
        "funcoes": sorted(_catalogo_funcoes().values()),
        "habilitacoes": [h["habilitacao"] for h in hab_catalogo],
        "habilitacoes_catalogo": hab_catalogo,
        "funcionarios": [
            {"id": str(u.id), "matricula": u.codigo_matricula, "nome": f"{u.nome} ({u.codigo_matricula})"}
            for u in funcionarios_ativos
        ],
    })


@require_POST
@api_backoffice("produtos")
def api_salvar_regra(request):
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    produto = Produto.objects.filter(id=dados.get("produto_id")).first() if dados.get("produto_id") else None
    if produto is None:
        return erro("Escolha o produto.")
    setor = Setor.objects.filter(id=dados.get("setor_id")).first() if dados.get("setor_id") else None
    funcionario = Usuario.objects.filter(id=dados.get("funcionario_id")).first() if dados.get("funcionario_id") else None
    try:
        cargo = texto(dados.get("cargo"), "Cargo", maximo=100)
        cargo = _normalizar_cargo_catalogo(cargo)
        funcao = texto(dados.get("funcao"), "Função", maximo=100)
        funcao = _normalizar_funcao_catalogo(funcao)
        habilitacao = texto(dados.get("habilitacao"), "Habilitação", maximo=100)
        habilitacao = _normalizar_habilitacao_catalogo(habilitacao)
        limite = inteiro(dados.get("limite_mensal"), "Limite mensal", minimo=0, maximo=10000) \
            if dados.get("limite_mensal") not in (None, "") else None
        periodicidade = inteiro(dados.get("periodicidade_dias"), "Periodicidade", minimo=1, maximo=3650) \
            if dados.get("periodicidade_dias") not in (None, "") else None
    except EntradaInvalida as e:
        return erro(str(e))

    if funcionario is not None:
        alvo_cargo = f"{PREFIXO_FUNCIONARIO}{funcionario.codigo_matricula}"
    elif habilitacao:
        alvo_cargo = (
            habilitacao
            if habilitacao.upper().startswith(PREFIXO_HABILITACAO)
            else f"{PREFIXO_HABILITACAO}{habilitacao}"
        )
    elif funcao:
        alvo_cargo = (
            funcao
            if funcao.upper().startswith(PREFIXO_FUNCAO)
            else f"{PREFIXO_FUNCAO}{funcao}"
        )
    else:
        alvo_cargo = cargo

    if not setor and not alvo_cargo:
        return erro("Defina o escopo: um setor, um cargo, uma função, uma habilitação ou um funcionário.")
    if limite is None and periodicidade is None:
        return erro("Informe o limite mensal, a periodicidade ou ambos.")

    regra_id = dados.get("id")
    regra = RegraFornecimento.objects.filter(id=regra_id).first() if regra_id else RegraFornecimento(ativo=True)
    if regra_id and regra is None:
        return erro("Regra não encontrada.", status=404)
    duplicada = RegraFornecimento.objects.filter(produto=produto, setor=setor, cargo__iexact=alvo_cargo, ativo=True) \
        .exclude(pk=regra.pk).exists()
    if duplicada:
        return erro("Já existe uma regra ativa para este produto com o mesmo escopo.")
    regra.produto, regra.setor, regra.cargo = produto, setor, alvo_cargo
    regra.limite_mensal, regra.periodicidade_dias = limite, periodicidade
    regra.save()
    registrar(request, "REGRA_ATUALIZADA" if regra_id else "REGRA_CADASTRADA", regra, str(regra),
              limite_mensal=limite, periodicidade_dias=periodicidade)
    return JsonResponse({"sucesso": True, "mensagem": "Política salva.", "id": str(regra.id)})


@require_POST
@api_backoffice("produtos")
def api_toggle_regra(request, regra_id):
    regra = RegraFornecimento.objects.filter(id=regra_id).first()
    if regra is None:
        return erro("Regra não encontrada.", status=404)
    regra.ativo = not regra.ativo
    regra.save(update_fields=["ativo"])
    registrar(request, "REGRA_ATIVADA" if regra.ativo else "REGRA_INATIVADA", regra, str(regra))
    return JsonResponse({"sucesso": True, "ativo": regra.ativo})
