"""Catálogo ocupacional: Cargos (RF-03), Funções/Atividades (RF-04) e Habilitações/NRs."""
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from ..auditoria import ip_da_requisicao
from ..models import RegraFornecimento, RegistroAuditoria, Usuario
from ..permissoes import api_backoffice
from ..servicos import rh
from ..servicos.elegibilidade import PREFIXO_FUNCIONARIO, PREFIXO_FUNCAO, PREFIXO_HABILITACAO
from .util import EntradaInvalida, erro, ler_json, texto
HABILITACOES_PADRAO = (
    ("NR-10", True, "Segurança em Instalações e Serviços em Eletricidade"),
    ("NR-11", True, "Operação de Empilhadeira, Ponte Rolante e Movimentação de Cargas"),
    ("NR-12", True, "Segurança no Trabalho em Máquinas e Equipamentos"),
    ("NR-33", True, "Segurança e Saúde nos Trabalhos em Espaços Confinados"),
    ("NR-35", True, "Trabalho em Altura (acima de 2,0m com risco de queda)"),
    ("Brigadista", True, "Brigada de Incêndio e Emergência Industrial"),
)


# ============================================================================
# CARGOS (RF-03), FUNÇÕES (RF-04) E HABILITAÇÕES DE RISCO / NRs
# ============================================================================
def _eh_prefixado_especial(valor):
    upper = (valor or "").strip().upper()
    return upper.startswith((PREFIXO_FUNCIONARIO, PREFIXO_FUNCAO, PREFIXO_HABILITACAO))


def _catalogo_cargos():
    """Devolve um dicionário {chave_lower: nome_exibicao} combinando o catálogo de
    cargos gerenciados, os cargos atribuídos a funcionários e as políticas de fornecimento."""
    catalogo = {}

    for evento in RegistroAuditoria.objects.filter(entidade="Cargo").order_by("data", "id"):
        detalhes = evento.detalhes if isinstance(evento.detalhes, dict) else {}
        nome = (detalhes.get("cargo") or "").strip()
        anterior = (detalhes.get("cargo_anterior") or "").strip()
        if evento.acao in ("CARGO_CADASTRADO", "CARGO_ATUALIZADO") and nome:
            if anterior and anterior.lower() in catalogo:
                catalogo.pop(anterior.lower(), None)
            catalogo[nome.lower()] = nome
        elif evento.acao == "CARGO_EXCLUIDO" and nome:
            catalogo.pop(nome.lower(), None)

    for cargo_func in Usuario.objects.filter(ativo=True).exclude(cargo__isnull=True).exclude(cargo="") \
            .values_list("cargo", flat=True):
        limpo = cargo_func.strip()
        if limpo:
            catalogo.setdefault(limpo.lower(), limpo)

    for cargo_regra in RegraFornecimento.objects.filter(ativo=True).exclude(cargo="") \
            .values_list("cargo", flat=True):
        limpo = cargo_regra.strip()
        if limpo and not _eh_prefixado_especial(limpo):
            catalogo.setdefault(limpo.lower(), limpo)

    return catalogo


def _normalizar_cargo_catalogo(cargo_informado):
    """Normaliza o cargo informado para a grafia canônica existente no catálogo
    (evitando duplicidades como 'Auxiliar de producao' vs 'Auxiliar de Produção').
    Se o cargo não existir no catálogo, retorna o texto original limpo."""
    if not cargo_informado:
        return cargo_informado
    limpo = str(cargo_informado).strip()
    if not limpo:
        return limpo
    catalogo = _catalogo_cargos()
    chave = limpo.lower()
    if chave in catalogo:
        return catalogo[chave]
    return limpo


def _normalizar_funcao_catalogo(funcao_informada):
    """Normaliza a função operacional informada para a grafia canônica existente no catálogo."""
    if not funcao_informada:
        return funcao_informada
    limpo = str(funcao_informada).strip()
    if not limpo:
        return limpo
    catalogo = _catalogo_funcoes()
    chave = limpo.lower()
    if chave in catalogo:
        return catalogo[chave]
    return limpo


def _normalizar_habilitacao_catalogo(hab_informada):
    """Normaliza a habilitação/NR informada para a grafia canônica existente no catálogo."""
    if not hab_informada:
        return hab_informada
    limpo = str(hab_informada).strip()
    if not limpo:
        return limpo
    catalogo = _catalogo_habilitacoes()
    chave = limpo.lower()
    if chave in catalogo:
        return catalogo[chave]["habilitacao"]
    return limpo


def _catalogo_funcoes(fichas_ativos=None):
    """Devolve um dicionário {chave_lower: nome_exibicao} com as Funções Operacionais (RF-04)."""
    catalogo = {}

    for evento in RegistroAuditoria.objects.filter(entidade="Funcao").order_by("data", "id"):
        detalhes = evento.detalhes if isinstance(evento.detalhes, dict) else {}
        nome = (detalhes.get("funcao") or "").strip()
        anterior = (detalhes.get("funcao_anterior") or "").strip()
        if evento.acao in ("FUNCAO_CADASTRADA", "FUNCAO_ATUALIZADA") and nome:
            if anterior and anterior.lower() in catalogo:
                catalogo.pop(anterior.lower(), None)
            catalogo[nome.lower()] = nome
        elif evento.acao == "FUNCAO_EXCLUIDA" and nome:
            catalogo.pop(nome.lower(), None)

    if fichas_ativos is None:
        fichas_ativos = [rh.obter_ficha_rh(u) for u in Usuario.objects.filter(ativo=True)]

    for ficha in fichas_ativos:
        fn = (ficha.get("funcao") or "").strip()
        if fn:
            catalogo.setdefault(fn.lower(), fn)

    for cargo_regra in RegraFornecimento.objects.filter(ativo=True).exclude(cargo="") \
            .values_list("cargo", flat=True):
        limpo = cargo_regra.strip()
        if limpo.upper().startswith(PREFIXO_FUNCAO):
            fn = limpo[len(PREFIXO_FUNCAO):].strip()
            if fn:
                catalogo.setdefault(fn.lower(), fn)

    return catalogo


def _catalogo_habilitacoes(fichas_ativos=None):
    """Devolve um dicionário {chave_lower: {"habilitacao": nome, "exige_validade": bool, "descricao": str}}."""
    catalogo = {
        nome.lower(): {
            "habilitacao": nome,
            "exige_validade": exige_val,
            "descricao": desc,
        }
        for nome, exige_val, desc in HABILITACOES_PADRAO
    }

    for evento in RegistroAuditoria.objects.filter(entidade="Habilitacao").order_by("data", "id"):
        detalhes = evento.detalhes if isinstance(evento.detalhes, dict) else {}
        nome = (detalhes.get("habilitacao") or "").strip()
        anterior = (detalhes.get("habilitacao_anterior") or "").strip()
        if evento.acao in ("HABILITACAO_CADASTRADA", "HABILITACAO_ATUALIZADA") and nome:
            if anterior and anterior.lower() in catalogo:
                catalogo.pop(anterior.lower(), None)
            catalogo[nome.lower()] = {
                "habilitacao": nome,
                "exige_validade": bool(detalhes.get("exige_validade", True)),
                "descricao": (detalhes.get("descricao") or "").strip(),
            }
        elif evento.acao == "HABILITACAO_EXCLUIDA" and nome:
            catalogo.pop(nome.lower(), None)

    if fichas_ativos is None:
        fichas_ativos = [rh.obter_ficha_rh(u) for u in Usuario.objects.filter(ativo=True)]

    for ficha in fichas_ativos:
        for h in ficha.get("habilitacoes") or []:
            nome = (h.get("nome") or "").strip()
            if nome:
                catalogo.setdefault(
                    nome.lower(),
                    {"habilitacao": nome, "exige_validade": True, "descricao": ""},
                )

    for cargo_regra in RegraFornecimento.objects.filter(ativo=True).exclude(cargo="") \
            .values_list("cargo", flat=True):
        limpo = cargo_regra.strip()
        if limpo.upper().startswith(PREFIXO_HABILITACAO):
            nome = limpo[len(PREFIXO_HABILITACAO):].strip()
            if nome:
                catalogo.setdefault(
                    nome.lower(),
                    {"habilitacao": nome, "exige_validade": True, "descricao": ""},
                )

    return catalogo


def _listar_catalogo_habilitacoes(fichas_ativos=None):
    cat = _catalogo_habilitacoes(fichas_ativos=fichas_ativos)
    return sorted(cat.values(), key=lambda x: x["habilitacao"].lower())


def _registrar_evento_catalogo(request, entidade, acao, identificador, texto_auditoria, **detalhes):
    # O texto da auditoria tem nome próprio para não colidir com detalhes["descricao"]
    # (descrição da Habilitação/NR, lida depois pelo catálogo de habilitações).
    usuario = getattr(request, "usuario", None)
    RegistroAuditoria.objects.create(
        usuario=usuario,
        usuario_nome=usuario.nome if usuario else "",
        acao=acao,
        entidade=entidade,
        entidade_id=(identificador or "")[:64],
        descricao=texto_auditoria[:255],
        detalhes=detalhes,
        ip=ip_da_requisicao(request) if request is not None else None,
    )


def _registrar_evento_cargo(request, acao, descricao, **detalhes):
    _registrar_evento_catalogo(
        request, "Cargo", acao, detalhes.get("cargo") or "", descricao, **detalhes
    )


@require_GET
@api_backoffice("ver")
def api_listar_cargos(request):
    """Lista as 3 categorias ocupacionais da organização:
    1. Cargos contratuais (RF-03)
    2. Funções / Atividades operacionais (RF-04)
    3. Habilitações & Credenciais de Risco / NRs com validade."""
    usuarios_ativos = list(Usuario.objects.select_related("setor").filter(ativo=True))
    fichas_por_id = {u.id: rh.obter_ficha_rh(u) for u in usuarios_ativos}
    lista_fichas = list(fichas_por_id.values())

    catalogo_cargos = _catalogo_cargos()
    catalogo_funcoes = _catalogo_funcoes(fichas_ativos=lista_fichas)
    catalogo_hab = _catalogo_habilitacoes(fichas_ativos=lista_fichas)

    contagem_cargos = {
        chave: {"cargo": nome, "total": 0, "setores": set()}
        for chave, nome in catalogo_cargos.items()
    }
    contagem_funcoes = {
        chave: {"funcao": nome, "total": 0, "setores": set()}
        for chave, nome in catalogo_funcoes.items()
    }
    contagem_hab = {
        chave: {
            "habilitacao": info["habilitacao"],
            "exige_validade": info["exige_validade"],
            "descricao": info["descricao"],
            "total": 0,
            "vencidas": 0,
            "setores": set(),
        }
        for chave, info in catalogo_hab.items()
    }

    for u in usuarios_ativos:
        setor_nome = u.setor.nome if u.setor else None
        cargo_u = (u.cargo or "").strip()
        if cargo_u:
            ch_c = cargo_u.lower()
            item_c = contagem_cargos.setdefault(ch_c, {"cargo": cargo_u, "total": 0, "setores": set()})
            item_c["total"] += 1
            if setor_nome:
                item_c["setores"].add(setor_nome)

        ficha = fichas_por_id[u.id]
        funcao_u = (ficha.get("funcao") or "").strip()
        if funcao_u:
            ch_f = funcao_u.lower()
            item_f = contagem_funcoes.setdefault(ch_f, {"funcao": funcao_u, "total": 0, "setores": set()})
            item_f["total"] += 1
            if setor_nome:
                item_f["setores"].add(setor_nome)

        for h in ficha.get("habilitacoes") or []:
            nome_h = (h.get("nome") or "").strip()
            if not nome_h:
                continue
            ch_h = nome_h.lower()
            item_h = contagem_hab.setdefault(
                ch_h,
                {
                    "habilitacao": nome_h,
                    "exige_validade": True,
                    "descricao": "",
                    "total": 0,
                    "vencidas": 0,
                    "setores": set(),
                },
            )
            item_h["total"] += 1
            if h.get("vencida"):
                item_h["vencidas"] += 1
            if setor_nome:
                item_h["setores"].add(setor_nome)

    regras = RegraFornecimento.objects.filter(ativo=True).exclude(cargo="").select_related("produto")
    epis_cargo = {}
    epis_funcao = {}
    epis_hab = {}
    for r in regras:
        raw = (r.cargo or "").strip()
        up = raw.upper()
        if up.startswith(PREFIXO_FUNCIONARIO):
            continue
        if up.startswith(PREFIXO_HABILITACAO):
            chave = raw[len(PREFIXO_HABILITACAO):].strip().lower()
            epis_hab.setdefault(chave, set()).add(r.produto.nome)
        elif up.startswith(PREFIXO_FUNCAO):
            chave = raw[len(PREFIXO_FUNCAO):].strip().lower()
            epis_funcao.setdefault(chave, set()).add(r.produto.nome)
        else:
            epis_cargo.setdefault(raw.lower(), set()).add(r.produto.nome)

    return JsonResponse({
        "cargos": [
            {
                "cargo": c["cargo"],
                "total_funcionarios": c["total"],
                "setores": sorted(c["setores"]),
                "produtos_vinculados": sorted(epis_cargo.get(c["cargo"].lower(), set())),
            }
            for c in sorted(contagem_cargos.values(), key=lambda x: x["cargo"].lower())
        ],
        "funcoes": [
            {
                "funcao": f["funcao"],
                "total_funcionarios": f["total"],
                "setores": sorted(f["setores"]),
                "produtos_vinculados": sorted(epis_funcao.get(f["funcao"].lower(), set())),
            }
            for f in sorted(contagem_funcoes.values(), key=lambda x: x["funcao"].lower())
        ],
        "habilitacoes": [
            {
                "habilitacao": h["habilitacao"],
                "exige_validade": h["exige_validade"],
                "descricao": h["descricao"],
                "total_funcionarios": h["total"],
                "vencidas": h["vencidas"],
                "setores": sorted(h["setores"]),
                "produtos_vinculados": sorted(epis_hab.get(h["habilitacao"].lower(), set())),
            }
            for h in sorted(contagem_hab.values(), key=lambda x: x["habilitacao"].lower())
        ],
    })


@require_POST
@api_backoffice("pessoas")
def api_salvar_funcao(request):
    """Cadastra uma nova função operacional (RF-04) ou renomeia uma existente."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    try:
        nome = texto(
            dados.get("funcao") or dados.get("nome") or dados.get("cargo"),
            "Nome da função operacional",
            obrigatorio=True,
            maximo=100,
        )
        original = texto(
            dados.get("funcao_original") or dados.get("cargo_original") or dados.get("original"),
            "Função original",
            maximo=100,
        )
    except EntradaInvalida as e:
        return erro(str(e))

    if _eh_prefixado_especial(nome):
        return erro("Nome de função reservado pelo sistema.")

    catalogo = _catalogo_funcoes()
    chave_nova = nome.lower()
    chave_original = original.lower() if original else ""

    if not original:
        if chave_nova in catalogo:
            return erro("Já existe uma função operacional cadastrada com este nome.")
        _registrar_evento_catalogo(
            request,
            "Funcao",
            "FUNCAO_CADASTRADA",
            nome,
            f"Cadastrou a função operacional '{nome}'",
            funcao=nome,
        )
        return JsonResponse({"sucesso": True, "mensagem": "Função operacional cadastrada com sucesso.", "funcao": nome})

    if chave_nova != chave_original and chave_nova in catalogo:
        return erro("Já existe outra função operacional com este nome.")

    with transaction.atomic():
        regras_afetadas = RegraFornecimento.objects.filter(
            cargo__iexact=f"{PREFIXO_FUNCAO}{original}"
        ).update(cargo=f"{PREFIXO_FUNCAO}{nome}")
        funcionarios_afetados = 0
        for u in Usuario.objects.filter(ativo=True):
            ficha = rh.obter_ficha_rh(u)
            if (ficha.get("funcao") or "").strip().lower() == chave_original:
                rh.salvar_metadados_rh(request, u, funcao=nome)
                funcionarios_afetados += 1

        _registrar_evento_catalogo(
            request,
            "Funcao",
            "FUNCAO_ATUALIZADA",
            nome,
            f"Renomeou a função operacional '{original}' para '{nome}'",
            funcao=nome,
            funcao_anterior=original,
            funcionarios_afetados=funcionarios_afetados,
            regras_afetadas=regras_afetadas,
        )
    return JsonResponse({"sucesso": True, "mensagem": "Função operacional atualizada com sucesso.", "funcao": nome})


@require_POST
@api_backoffice("pessoas")
def api_excluir_funcao(request):
    """Remove uma função operacional do catálogo desde que não possua colaboradores ativos vinculados."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    try:
        nome = texto(
            dados.get("funcao") or dados.get("nome") or dados.get("cargo"),
            "Função operacional",
            obrigatorio=True,
            maximo=100,
        )
    except EntradaInvalida as e:
        return erro(str(e))

    chave = nome.lower()
    for u in Usuario.objects.filter(ativo=True):
        ficha = rh.obter_ficha_rh(u)
        if (ficha.get("funcao") or "").strip().lower() == chave:
            return erro("Não é possível remover uma função que possui colaboradores ativos vinculados.", status=409)

    with transaction.atomic():
        RegraFornecimento.objects.filter(cargo__iexact=f"{PREFIXO_FUNCAO}{nome}").delete()
        _registrar_evento_catalogo(
            request,
            "Funcao",
            "FUNCAO_EXCLUIDA",
            nome,
            f"Removeu a função operacional '{nome}'",
            funcao=nome,
        )
    return JsonResponse({"sucesso": True, "mensagem": f"Função operacional '{nome}' removida."})


@require_POST
@api_backoffice("pessoas")
def api_salvar_habilitacao(request):
    """Cadastra ou edita uma Habilitação / Credencial de Risco (NR / Licença)."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    try:
        nome = texto(
            dados.get("habilitacao") or dados.get("nome") or dados.get("cargo"),
            "Habilitação / NR",
            obrigatorio=True,
            maximo=80,
        )
        original = texto(
            dados.get("habilitacao_original") or dados.get("cargo_original") or dados.get("original"),
            "Habilitação original",
            maximo=80,
        )
        descricao = texto(dados.get("descricao"), "Descrição", maximo=200)
    except EntradaInvalida as e:
        return erro(str(e))

    if _eh_prefixado_especial(nome):
        return erro("Nome reservado pelo sistema.")

    exige_validade = bool(dados.get("exige_validade", True))
    catalogo = _catalogo_habilitacoes()
    chave_nova = nome.lower()
    chave_original = original.lower() if original else ""

    if not original:
        _registrar_evento_catalogo(
            request,
            "Habilitacao",
            "HABILITACAO_CADASTRADA",
            nome,
            f"Cadastrou a habilitação/NR '{nome}'",
            habilitacao=nome,
            exige_validade=exige_validade,
            descricao=descricao,
        )
        return JsonResponse({
            "sucesso": True,
            "mensagem": "Habilitação / NR salva com sucesso.",
            "habilitacao": nome,
        })

    if chave_nova != chave_original and chave_nova in catalogo:
        return erro("Já existe outra habilitação cadastrada com este nome.")

    with transaction.atomic():
        if chave_nova != chave_original:
            RegraFornecimento.objects.filter(
                cargo__iexact=f"{PREFIXO_HABILITACAO}{original}"
            ).update(cargo=f"{PREFIXO_HABILITACAO}{nome}")
            for u in Usuario.objects.filter(ativo=True):
                ficha = rh.obter_ficha_rh(u)
                habs = ficha.get("habilitacoes") or []
                if any((h.get("nome") or "").strip().lower() == chave_original for h in habs):
                    novas = [
                        {"nome": nome if (h.get("nome") or "").strip().lower() == chave_original else h["nome"],
                         "validade": h.get("validade") or ""}
                        for h in habs
                    ]
                    rh.salvar_metadados_rh(request, u, habilitacoes=novas)

        _registrar_evento_catalogo(
            request,
            "Habilitacao",
            "HABILITACAO_ATUALIZADA",
            nome,
            f"Atualizou a habilitação/NR '{original}' para '{nome}'",
            habilitacao=nome,
            habilitacao_anterior=original,
            exige_validade=exige_validade,
            descricao=descricao,
        )
    return JsonResponse({
        "sucesso": True,
        "mensagem": "Habilitação / NR atualizada com sucesso.",
        "habilitacao": nome,
    })


@require_POST
@api_backoffice("pessoas")
def api_excluir_habilitacao(request):
    """Remove uma Habilitação / NR do catálogo desde que não possua colaboradores ativos vinculados."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    try:
        nome = texto(
            dados.get("habilitacao") or dados.get("nome") or dados.get("cargo"),
            "Habilitação / NR",
            obrigatorio=True,
            maximo=80,
        )
    except EntradaInvalida as e:
        return erro(str(e))

    chave = nome.lower()
    for u in Usuario.objects.filter(ativo=True):
        ficha = rh.obter_ficha_rh(u)
        if any((h.get("nome") or "").strip().lower() == chave for h in (ficha.get("habilitacoes") or [])):
            return erro(
                "Não é possível remover uma habilitação que possui colaboradores ativos vinculados.",
                status=409,
            )

    with transaction.atomic():
        RegraFornecimento.objects.filter(cargo__iexact=f"{PREFIXO_HABILITACAO}{nome}").delete()
        _registrar_evento_catalogo(
            request,
            "Habilitacao",
            "HABILITACAO_EXCLUIDA",
            nome,
            f"Removeu a habilitação/NR '{nome}'",
            habilitacao=nome,
        )
    return JsonResponse({"sucesso": True, "mensagem": f"Habilitação / NR '{nome}' removida."})


@require_POST
@api_backoffice("pessoas")
def api_salvar_cargo(request):
    """Cadastra um novo cargo (RF-03) ou delega para Função/Habilitação quando `tipo` é informado."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json

    tipo = (dados.get("tipo") or "CARGO").strip().upper()
    if tipo == "FUNCAO":
        return api_salvar_funcao(request)
    if tipo == "HABILITACAO":
        return api_salvar_habilitacao(request)

    try:
        nome = texto(dados.get("cargo"), "Nome do cargo / função", obrigatorio=True, maximo=100)
        original = texto(dados.get("cargo_original"), "Cargo original", maximo=100)
    except EntradaInvalida as e:
        return erro(str(e))

    if _eh_prefixado_especial(nome):
        return erro("Nome de cargo reservado pelo sistema.")

    catalogo = _catalogo_cargos()
    chave_nova = nome.lower()
    chave_original = original.lower() if original else ""

    if not original:
        if chave_nova in catalogo:
            return erro("Já existe um cargo/função cadastrado com este nome.")
        _registrar_evento_cargo(
            request,
            "CARGO_CADASTRADO",
            f"Cadastrou o cargo/função '{nome}'",
            cargo=nome,
        )
        return JsonResponse({"sucesso": True, "mensagem": "Cargo / função cadastrado com sucesso.", "cargo": nome})

    if chave_nova != chave_original and chave_nova in catalogo:
        return erro("Já existe outro cargo/função com este nome.")

    with transaction.atomic():
        funcionarios_afetados = Usuario.objects.filter(cargo__iexact=original).update(cargo=nome)
        regras_afetadas = RegraFornecimento.objects.filter(cargo__iexact=original).update(cargo=nome)
        _registrar_evento_cargo(
            request,
            "CARGO_ATUALIZADO",
            f"Renomeou o cargo/função '{original}' para '{nome}'",
            cargo=nome,
            cargo_anterior=original,
            funcionarios_afetados=funcionarios_afetados,
            regras_afetadas=regras_afetadas,
        )
    return JsonResponse({"sucesso": True, "mensagem": "Cargo / função atualizado com sucesso.", "cargo": nome})


@require_POST
@api_backoffice("pessoas")
def api_excluir_cargo(request):
    """Remove um cargo do catálogo desde que não possua funcionários ativos vinculados (RF-03)."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json

    tipo = (dados.get("tipo") or "CARGO").strip().upper()
    if tipo == "FUNCAO":
        return api_excluir_funcao(request)
    if tipo == "HABILITACAO":
        return api_excluir_habilitacao(request)

    try:
        nome = texto(dados.get("cargo"), "Cargo / função", obrigatorio=True, maximo=100)
    except EntradaInvalida as e:
        return erro(str(e))

    if Usuario.objects.filter(ativo=True, cargo__iexact=nome).exists():
        return erro("Não é possível remover um cargo que possui funcionários ativos vinculados.", status=409)

    with transaction.atomic():
        Usuario.objects.filter(cargo__iexact=nome).update(cargo="")
        RegraFornecimento.objects.filter(cargo__iexact=nome).delete()
        _registrar_evento_cargo(
            request,
            "CARGO_EXCLUIDO",
            f"Removeu o cargo/função '{nome}'",
            cargo=nome,
        )
    return JsonResponse({"sucesso": True, "mensagem": f"Cargo / função '{nome}' removido."})
