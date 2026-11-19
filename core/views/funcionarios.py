"""APIs de cadastro de funcionários operacionais (Totem) e usuários administrativos (Backoffice)."""
import csv
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from ..auditoria import registrar
from ..contas import enviar_link_de_senha, garantir_conta
from ..models import Setor, Solicitacao, Usuario
from ..permissoes import PERFIS, PERFIS_BACKOFFICE, api_backoffice
from ..seguranca import definir_pin, validar_novo_pin
from ..servicos import RegraViolada, estados, rh
from ..servicos import solicitacoes as servico_solicitacoes
from .cargos import (
    _catalogo_funcoes,
    _listar_catalogo_habilitacoes,
    _normalizar_cargo_catalogo,
    _normalizar_funcao_catalogo,
    _normalizar_habilitacao_catalogo,
)
from .util import EntradaInvalida, erro, fmt, gerar_iniciais, ler_json, texto
def _func_json(u, ficha_rh=None):
    ficha = ficha_rh if isinstance(ficha_rh, dict) else rh.obter_ficha_rh(u)
    habilitacoes = ficha.get("habilitacoes", [])
    return {
        "id": str(u.id),
        "matricula": u.codigo_matricula,
        "nome": u.nome,
        "iniciais": gerar_iniciais(u.nome),
        "email": u.email or "—",
        "cargo": u.cargo or "Colaborador",
        "funcao": ficha.get("funcao", ""),
        "cpf": ficha.get("cpf", ""),
        "data_admissao": ficha.get("data_admissao", ""),
        "habilitacoes": habilitacoes,
        "tem_habilitacao_vencida": any(h.get("vencida") for h in habilitacoes),
        "perfil": u.perfil,
        "perfil_rotulo": PERFIS.get(u.perfil, u.perfil),
        "dominio": "OPERACIONAL" if u.eh_operacional else "ADMINISTRATIVO",
        "possui_pin": u.possui_pin_totem,
        "possui_acesso_backoffice": u.possui_acesso_backoffice,
        "setor_id": str(u.setor.id) if u.setor else None,
        "setor_nome": u.setor.nome if u.setor else "Sem setor",
        "centro_custo": u.setor.centro_custo if u.setor else "—",
        "ativo": u.ativo,
        "created_at": fmt(u.created_at, "%d/%m/%Y") if u.created_at else "—",
        "tamanhos": ficha["tamanhos"],
        "pin_provisorio": ficha["pin_provisorio"],
        "historico_funcional": ficha["historico_funcional"],
    }


# ============================================================================
# DOMÍNIO 1: GESTÃO DE FUNCIONÁRIOS OPERACIONAIS (TOTEM)
# DOMÍNIO 2: GESTÃO DE USUÁRIOS ADMINISTRATIVOS (BACKOFFICE / RBAC)
# ============================================================================
@require_GET
@api_backoffice("pessoas")
def api_listar_funcionarios(request):
    """Lista os funcionários cadastrados com filtros por setor, busca textual e domínio."""
    setor_filtro = request.GET.get("setor")
    dominio_filtro = (request.GET.get("dominio") or "").strip().lower()
    termo = request.GET.get("q", "").strip()

    qs = Usuario.objects.select_related("setor", "conta").all().order_by("nome")
    if setor_filtro:
        qs = qs.filter(setor_id=setor_filtro)
    if dominio_filtro == "operacional":
        qs = qs.filter(perfil="COLABORADOR")
    elif dominio_filtro == "administrativo":
        qs = qs.filter(perfil__in=PERFIS_BACKOFFICE)
    if termo:
        qs = qs.filter(Q(nome__icontains=termo) | Q(codigo_matricula__icontains=termo) | Q(email__icontains=termo))

    return JsonResponse({
        "funcionarios": [_func_json(u) for u in qs],
        "funcoes": sorted(_catalogo_funcoes().values()),
        "habilitacoes_catalogo": _listar_catalogo_habilitacoes(),
    })


def _extrair_tamanhos(dados):
    """Extrai o dicionário de tamanhos do JSON (suporta `tamanhos` aninhado ou campos planos)."""
    tamanhos_in = dados.get("tamanhos") if isinstance(dados.get("tamanhos"), dict) else {}
    tamanhos = {}
    for chave, plano in (("calcado", "tam_calcado"), ("luva", "tam_luva"), ("vestimenta", "tam_vestimenta")):
        if chave in tamanhos_in and tamanhos_in[chave] is not None:
            tamanhos[chave] = texto(tamanhos_in[chave], f"Tamanho ({chave})", maximo=20)
        elif plano in dados and dados.get(plano) is not None:
            tamanhos[chave] = texto(dados.get(plano), f"Tamanho ({chave})", maximo=20)
        elif chave in dados and dados.get(chave) is not None:
            tamanhos[chave] = texto(dados.get(chave), f"Tamanho ({chave})", maximo=20)
    return tamanhos


@require_POST
@api_backoffice("pessoas")
def api_salvar_funcionario(request):
    """Cadastra ou atualiza um funcionário (RF-01) e, se o perfil for administrativo,
    a conta de acesso ao backoffice (RF-08, RF-09)."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json

    try:
        nome = texto(dados.get("nome"), "Nome", obrigatorio=True, maximo=150)
        matricula = texto(dados.get("matricula"), "Matrícula", obrigatorio=True, maximo=30).upper()
        email = texto(dados.get("email"), "E-mail", maximo=150).lower() or None
        cargo = texto(dados.get("cargo"), "Cargo", maximo=100)
        cargo = _normalizar_cargo_catalogo(cargo)
        funcao_informada = "funcao" in dados
        funcao = texto(dados.get("funcao"), "Função", maximo=100) if funcao_informada else None
        funcao = _normalizar_funcao_catalogo(funcao) if funcao else funcao
        perfil = texto(dados.get("perfil"), "Perfil").upper() or "COLABORADOR"
        pin = texto(dados.get("pin"), "PIN")
        cpf_informado = "cpf" in dados
        cpf_bruto = texto(dados.get("cpf"), "CPF", maximo=20) if cpf_informado else None
        admissao_informada = "data_admissao" in dados
        data_admissao_bruta = texto(dados.get("data_admissao"), "Data de admissão", maximo=10) if admissao_informada else None
        tamanhos = _extrair_tamanhos(dados)
    except EntradaInvalida as e:
        return erro(str(e))

    cpf = None
    if cpf_informado:
        if cpf_bruto:
            cpf = rh.validar_cpf(cpf_bruto)
            if cpf is None:
                return erro("CPF inválido. Informe 11 dígitos válidos (ex.: 000.000.000-00).")
        else:
            cpf = ""

    data_admissao = None
    if admissao_informada:
        if data_admissao_bruta:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_admissao_bruta):
                return erro("Data de admissão inválida. Use o formato AAAA-MM-DD.")
            data_admissao = data_admissao_bruta
        else:
            data_admissao = ""

    habilitacoes_raw = dados.get("habilitacoes") if "habilitacoes" in dados else None
    if habilitacoes_raw is not None and isinstance(habilitacoes_raw, list):
        habilitacoes = []
        for h in habilitacoes_raw:
            if isinstance(h, dict):
                nome_h = _normalizar_habilitacao_catalogo(h.get("nome") or h.get("habilitacao") or "")
                habilitacoes.append({"nome": nome_h, "validade": h.get("validade") or ""})
            elif isinstance(h, str):
                habilitacoes.append({"nome": _normalizar_habilitacao_catalogo(h), "validade": ""})
    else:
        habilitacoes = habilitacoes_raw

    if not re.fullmatch(r"[A-Z0-9-]+", matricula):
        return erro("Matrícula: use apenas letras, números e hífen.")
    if perfil not in PERFIS:
        return erro("Perfil de acesso inválido.")
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return erro("E-mail inválido.")
    if perfil in PERFIS_BACKOFFICE and not email:
        return erro("Perfis com acesso ao backoffice precisam de e-mail (para receber o link de senha).")
    if pin:
        problema = validar_novo_pin(pin)
        if problema:
            return erro(problema)

    setor_id = dados.get("setor_id")
    setor = Setor.objects.filter(id=setor_id).first() if setor_id else None

    func_id = dados.get("id")
    if func_id:
        func = Usuario.objects.select_related("setor").filter(id=func_id).first()
        if func is None:
            return erro("Funcionário não encontrado.", status=404)
    else:
        func = Usuario(ativo=True)
        if not pin:
            return erro("Defina um PIN de 4 a 6 números para o colaborador usar no totem.")

    if Usuario.objects.filter(codigo_matricula=matricula).exclude(pk=func.pk).exists():
        return erro("Já existe colaborador com esta matrícula.")
    if email and Usuario.objects.filter(email__iexact=email).exclude(pk=func.pk).exists():
        return erro("Já existe colaborador com este e-mail.")
    if func.pk == request.usuario.pk and perfil != "ADMIN":
        return erro("Você não pode remover o seu próprio perfil de Administrador.")

    ficha_anterior = rh.obter_ficha_rh(func) if func.pk else {"funcao": "", "habilitacoes": []}
    perfil_anterior = func.perfil if func.pk else None
    cargo_anterior = (func.cargo or "").strip() if func.pk else ""
    funcao_anterior = (ficha_anterior.get("funcao") or "").strip() if func.pk else ""
    setor_anterior = (func.setor.nome if func.setor else "") if func.pk else ""
    setor_id_anterior = func.setor_id if func.pk else None
    tinha_acesso = bool(func.pk and func.conta_id and func.conta.has_usable_password())

    func.nome = nome
    func.codigo_matricula = matricula
    func.email = email
    func.cargo = cargo
    func.perfil = perfil
    func.setor = setor
    if pin:
        definir_pin(func, pin)
    func.save()

    conta = garantir_conta(func)
    convite_enviado = False
    if conta is not None and not tinha_acesso and not conta.has_usable_password():
        convite_enviado = enviar_link_de_senha(request, func)

    exigir_troca_pin = bool(dados.get("exigir_troca_pin"))
    gerar_kit = bool(dados.get("gerar_kit"))
    if pin:
        pin_provisorio = True if exigir_troca_pin else False
    else:
        pin_provisorio = True if exigir_troca_pin else None

    cargo_novo = (func.cargo or "").strip()
    funcao_nova = funcao if funcao is not None else funcao_anterior
    setor_novo = func.setor.nome if func.setor else ""
    evento_funcional = None
    if not func_id:
        evento_funcional = {
            "acao": "ADMISSAO",
            "descricao": f"Admissão de {func.nome} ({cargo_novo or 'Colaborador'})",
            "cargo_anterior": "",
            "cargo_novo": cargo_novo,
            "funcao_anterior": "",
            "funcao_novo": funcao_nova,
            "setor_anterior": "",
            "setor_novo": setor_novo,
        }
    elif (
        cargo_anterior.lower() != cargo_novo.lower()
        or funcao_anterior.lower() != funcao_nova.lower()
        or setor_id_anterior != func.setor_id
    ):
        partes_mudanca = []
        if cargo_anterior.lower() != cargo_novo.lower():
            partes_mudanca.append(f"Cargo: {cargo_anterior or '—'} → {cargo_novo or '—'}")
        if funcao_anterior.lower() != funcao_nova.lower():
            partes_mudanca.append(f"Função: {funcao_anterior or '—'} → {funcao_nova or '—'}")
        if setor_id_anterior != func.setor_id:
            partes_mudanca.append(f"Setor: {setor_anterior or '—'} → {setor_novo or '—'}")
        evento_funcional = {
            "acao": "MUDANCA_FUNCAO",
            "descricao": " · ".join(partes_mudanca) or "Atualização funcional",
            "cargo_anterior": cargo_anterior,
            "cargo_novo": cargo_novo,
            "funcao_anterior": funcao_anterior,
            "funcao_novo": funcao_nova,
            "setor_anterior": setor_anterior,
            "setor_novo": setor_novo,
        }

    if (
        evento_funcional is not None
        or tamanhos
        or pin_provisorio is not None
        or funcao is not None
        or habilitacoes is not None
        or cpf is not None
        or data_admissao is not None
    ):
        rh.salvar_metadados_rh(
            request,
            func,
            tamanhos=tamanhos or None,
            pin_provisorio=pin_provisorio,
            evento_funcional=evento_funcional,
            funcao=funcao,
            habilitacoes=habilitacoes,
            cpf=cpf,
            data_admissao=data_admissao,
        )

    kit = None
    if gerar_kit:
        kit = rh.gerar_kit_admissional(
            func,
            request.usuario,
            motivo="Kit de Mudança de Função" if func_id else "Kit Admissional",
        )

    registrar(
        request,
        "FUNCIONARIO_ATUALIZADO" if func_id else "FUNCIONARIO_CADASTRADO",
        func,
        f"{'Atualizou' if func_id else 'Cadastrou'} {func.nome} ({func.codigo_matricula})",
        perfil=perfil,
        perfil_anterior=perfil_anterior,
        pin_alterado=bool(pin),
        convite_enviado=convite_enviado,
    )

    msg = "Funcionário atualizado com sucesso." if func_id else "Funcionário cadastrado com sucesso."
    if convite_enviado:
        msg += f" Enviamos para {email} o link para criar a senha de acesso."
    if kit and kit.get("gerado"):
        msg += f" Kit com {kit['quantidade_itens']} EPI(s) gerado e reservado para entrega."

    resposta = {
        "sucesso": True,
        "mensagem": msg,
        "id": str(func.id),
        "convite_enviado": convite_enviado,
    }
    if kit is not None:
        resposta["kit_gerado"] = kit
    return JsonResponse(resposta)


@require_POST
@api_backoffice("pessoas")
def api_mudar_funcao_funcionario(request, funcionario_id):
    """Registra promoção/mudança de cargo, função operacional, habilitações ou transferência
    de setor, gravando no histórico da Ficha de EPI e opcionalmente gerando o kit."""
    func = Usuario.objects.select_related("setor").filter(id=funcionario_id).first()
    if func is None:
        return erro("Funcionário não encontrado.", status=404)

    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json

    cargo_in = dados.get("novo_cargo") if "novo_cargo" in dados else dados.get("cargo")
    funcao_in = dados.get("nova_funcao") if "nova_funcao" in dados else dados.get("funcao")

    try:
        novo_cargo = (
            texto(cargo_in, "Novo cargo", maximo=100)
            if cargo_in is not None
            else (func.cargo or "").strip()
        )
        novo_cargo = _normalizar_cargo_catalogo(novo_cargo)
        nova_funcao = (
            texto(funcao_in, "Nova função", maximo=100)
            if funcao_in is not None
            else None
        )
        nova_funcao = _normalizar_funcao_catalogo(nova_funcao) if nova_funcao else nova_funcao
        observacao = texto(dados.get("observacao"), "Observação", maximo=255)
    except EntradaInvalida as e:
        return erro(str(e))

    if not novo_cargo and not (nova_funcao or ""):
        return erro("Informe o novo cargo ou a nova função operacional.")

    novo_setor_id = dados.get("novo_setor_id") if "novo_setor_id" in dados else dados.get("setor_id")
    if novo_setor_id:
        novo_setor = Setor.objects.filter(id=novo_setor_id).first()
        if novo_setor is None:
            return erro("Setor não encontrado.", status=404)
    else:
        novo_setor = func.setor

    ficha_atual = rh.obter_ficha_rh(func)
    cargo_anterior = (func.cargo or "").strip()
    funcao_anterior = (ficha_atual.get("funcao") or "").strip()
    funcao_final = nova_funcao if nova_funcao is not None else funcao_anterior
    setor_anterior = func.setor.nome if func.setor else ""
    setor_novo = novo_setor.nome if novo_setor else ""

    func.cargo = novo_cargo
    func.setor = novo_setor
    func.save(update_fields=["cargo", "setor", "updated_at"])

    partes_desc = []
    if cargo_anterior.lower() != novo_cargo.lower() or not nova_funcao:
        partes_desc.append(f"{cargo_anterior or 'Colaborador'} → {novo_cargo or 'Colaborador'}")
    if nova_funcao is not None and funcao_anterior.lower() != funcao_final.lower():
        partes_desc.append(f"Função: {funcao_anterior or '—'} → {funcao_final or '—'}")
    descricao = "Mudança de função: " + (" · ".join(partes_desc) if partes_desc else novo_cargo)
    if observacao:
        descricao = f"{descricao} ({observacao})"

    habilitacoes_in = dados.get("habilitacoes") if "habilitacoes" in dados else None

    rh.salvar_metadados_rh(
        request,
        func,
        funcao=nova_funcao,
        habilitacoes=habilitacoes_in,
        evento_funcional={
            "acao": "MUDANCA_FUNCAO",
            "descricao": descricao,
            "cargo_anterior": cargo_anterior,
            "cargo_novo": novo_cargo,
            "funcao_anterior": funcao_anterior,
            "funcao_novo": funcao_final,
            "setor_anterior": setor_anterior,
            "setor_novo": setor_novo,
            "observacao": observacao,
        },
    )

    gerar_kit = bool(dados.get("gerar_kit"))
    kit = (
        rh.gerar_kit_admissional(func, request.usuario, motivo="Kit de Mudança de Função")
        if gerar_kit
        else {"gerado": False, "quantidade_itens": 0, "codigos": [], "itens": []}
    )

    registrar(
        request,
        "FUNCIONARIO_MUDANCA_FUNCAO",
        func,
        descricao,
        cargo_anterior=cargo_anterior,
        cargo_novo=novo_cargo,
        funcao_anterior=funcao_anterior,
        funcao_novo=funcao_final,
        setor_anterior=setor_anterior,
        setor_novo=setor_novo,
    )

    msg = f"Função de {func.nome} atualizada para {novo_cargo or funcao_final}."
    if kit.get("gerado"):
        msg += f" Kit com {kit['quantidade_itens']} EPI(s) gerado para entrega."
    return JsonResponse({"sucesso": True, "mensagem": msg, "kit_gerado": kit})


@require_GET
@api_backoffice("pessoas")
def api_resumo_desligamento(request, funcionario_id):
    """Retorna o checklist de Nada Consta de EPIs e solicitações abertas do colaborador."""
    func = Usuario.objects.select_related("setor").filter(id=funcionario_id).first()
    if func is None:
        return erro("Funcionário não encontrado.", status=404)
    resumo = rh.resumo_desligamento(func)
    return JsonResponse({
        "sucesso": True,
        "funcionario": {
            "id": str(func.id),
            "nome": func.nome,
            "matricula": func.codigo_matricula,
            "cargo": func.cargo or "Colaborador",
            "setor": func.setor.nome if func.setor else "Sem setor",
            "ativo": func.ativo,
        },
        **resumo,
    })


@require_POST
@api_backoffice("pessoas")
def api_toggle_funcionario(request, funcionario_id):
    """Ativa ou inativa um funcionário (e no desligamento cancela reservas pendentes e gera Nada Consta)."""
    func = Usuario.objects.select_related("setor").filter(id=funcionario_id).first()
    if func is None:
        return erro("Funcionário não encontrado.", status=404)
    if func.pk == request.usuario.pk:
        return erro("Você não pode inativar o seu próprio usuário.")

    inativando = bool(func.ativo)
    resumo = None
    reservas_canceladas = 0
    ficha_atual = rh.obter_ficha_rh(func)
    funcao_atual = ficha_atual.get("funcao", "")

    with transaction.atomic():
        if inativando:
            resumo = rh.resumo_desligamento(func)
            abertas = list(
                Solicitacao.objects.filter(
                    solicitante=func,
                    status__in=list(estados.ESTADOS_AGUARDANDO) + list(estados.ESTADOS_APROVADOS),
                )
            )
            for s in abertas:
                try:
                    servico_solicitacoes.cancelar(
                        s,
                        request.usuario,
                        motivo="Cancelada automaticamente por desligamento do colaborador",
                    )
                    reservas_canceladas += 1
                except RegraViolada:
                    pass

        func.ativo = not func.ativo
        func.save(update_fields=["ativo", "updated_at"])
        garantir_conta(func)

        if inativando:
            rh.salvar_metadados_rh(
                request,
                func,
                evento_funcional={
                    "acao": "DESLIGAMENTO",
                    "descricao": (
                        f"Desligamento/inativação de {func.nome} "
                        f"({reservas_canceladas} solicitação(ões) pendente(s) cancelada(s))"
                    ),
                    "cargo_anterior": func.cargo or "",
                    "cargo_novo": func.cargo or "",
                    "funcao_anterior": funcao_atual,
                    "funcao_novo": funcao_atual,
                    "setor_anterior": func.setor.nome if func.setor else "",
                    "setor_novo": func.setor.nome if func.setor else "",
                    "resumo_desligamento": resumo,
                },
            )
        else:
            rh.salvar_metadados_rh(
                request,
                func,
                evento_funcional={
                    "acao": "REATIVACAO",
                    "descricao": f"Reativação do cadastro de {func.nome}",
                    "cargo_anterior": func.cargo or "",
                    "cargo_novo": func.cargo or "",
                    "funcao_anterior": funcao_atual,
                    "funcao_novo": funcao_atual,
                    "setor_anterior": func.setor.nome if func.setor else "",
                    "setor_novo": func.setor.nome if func.setor else "",
                },
            )

    status_txt = "ativado" if func.ativo else "inativado"
    registrar(
        request,
        "FUNCIONARIO_ATIVADO" if func.ativo else "FUNCIONARIO_INATIVADO",
        func,
        f"{func.nome} {status_txt}",
        reservas_canceladas=reservas_canceladas,
    )
    resposta = {
        "sucesso": True,
        "ativo": func.ativo,
        "mensagem": f"Colaborador {status_txt}.",
        "reservas_canceladas": reservas_canceladas,
    }
    if resumo is not None:
        resposta["resumo_desligamento"] = resumo
    return JsonResponse(resposta)


@require_POST
@api_backoffice("pessoas")
def api_importar_funcionarios_csv(request):
    """Importa colaboradores em lote a partir de linhas CSV
    (`matricula;nome;cargo;setor;pin_inicial;calcado;luva;vestimenta;funcao;habilitacoes`)."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json

    csv_texto = (dados.get("csv_texto") or "").strip()
    if not csv_texto:
        return erro("Informe o conteúdo CSV para importação.")

    exigir_troca_pin = bool(dados.get("exigir_troca_pin", True))
    gerar_kit = bool(dados.get("gerar_kit", False))

    linhas_brutas = [l.strip() for l in csv_texto.splitlines() if l.strip()]
    if not linhas_brutas:
        return erro("Nenhuma linha encontrada no CSV.")

    criados = 0
    atualizados = 0
    erros = []

    for idx, linha in enumerate(linhas_brutas, start=1):
        delimitador = ";" if ";" in linha else ","
        try:
            colunas = [c.strip() for c in next(csv.reader([linha], delimiter=delimitador))]
        except Exception:
            erros.append(f"Linha {idx}: formato CSV inválido.")
            continue

        if not colunas or not any(colunas):
            continue

        primeira = colunas[0].lstrip("\ufeff").strip().lower()
        if primeira in ("matricula", "matrícula", "codigo_matricula"):
            continue

        (
            matricula,
            nome,
            cargo,
            setor_txt,
            pin_inicial,
            calcado,
            luva,
            vestimenta,
            funcao_csv,
            habilitacoes_csv,
        ) = (colunas + [""] * 10)[:10]

        matricula = matricula.strip().upper()
        nome = nome.strip()
        cargo = _normalizar_cargo_catalogo(cargo.strip())
        setor_txt = setor_txt.strip()
        pin_inicial = pin_inicial.strip()
        funcao_csv = funcao_csv.strip()
        habilitacoes_csv = habilitacoes_csv.strip()

        if not matricula or not nome:
            erros.append(f"Linha {idx}: matrícula e nome são obrigatórios.")
            continue
        if not re.fullmatch(r"[A-Z0-9-]+", matricula):
            erros.append(f"Linha {idx} ({matricula}): matrícula inválida.")
            continue

        func = Usuario.objects.select_related("setor").filter(codigo_matricula__iexact=matricula).first()
        eh_novo = func is None

        pin_para_definir = pin_inicial or ("8392" if eh_novo else "")
        if pin_para_definir:
            problema_pin = validar_novo_pin(pin_para_definir)
            if problema_pin:
                erros.append(f"Linha {idx} ({matricula}): {problema_pin}")
                continue

        setor = None
        if setor_txt:
            setor = Setor.objects.filter(
                Q(nome__iexact=setor_txt) | Q(centro_custo__iexact=setor_txt)
            ).first()
            if setor is None:
                sigla = re.sub(r"[^A-Z0-9]", "", setor_txt.upper())[:10] or "SETOR"
                setor = Setor.objects.create(nome=setor_txt[:100], centro_custo=f"CC-{sigla}", ativo=True)

        if eh_novo:
            func = Usuario(
                codigo_matricula=matricula,
                nome=nome[:150],
                cargo=cargo[:100] or "Colaborador",
                setor=setor,
                perfil="COLABORADOR",
                ativo=True,
            )
            definir_pin(func, pin_para_definir)
            func.save()
            criados += 1
            evento = {
                "acao": "ADMISSAO",
                "descricao": f"Admissão via importação CSV ({func.cargo})",
                "cargo_anterior": "",
                "cargo_novo": func.cargo or "",
                "funcao_anterior": "",
                "funcao_novo": funcao_csv[:100],
                "setor_anterior": "",
                "setor_novo": setor.nome if setor else "",
            }
        else:
            ficha_ant = rh.obter_ficha_rh(func)
            cargo_ant = func.cargo or ""
            funcao_ant = ficha_ant.get("funcao", "")
            setor_ant = func.setor.nome if func.setor else ""
            func.nome = nome[:150]
            if cargo:
                func.cargo = cargo[:100]
            if setor:
                func.setor = setor
            func.ativo = True
            if pin_para_definir:
                definir_pin(func, pin_para_definir)
            func.save()
            atualizados += 1
            if (
                (cargo and cargo.lower() != cargo_ant.lower())
                or (funcao_csv and funcao_csv.lower() != funcao_ant.lower())
                or (setor and setor.nome != setor_ant)
            ):
                evento = {
                    "acao": "MUDANCA_FUNCAO",
                    "descricao": f"Atualização funcional via CSV: {cargo_ant or '—'} → {func.cargo or '—'}",
                    "cargo_anterior": cargo_ant,
                    "cargo_novo": func.cargo or "",
                    "funcao_anterior": funcao_ant,
                    "funcao_novo": funcao_csv[:100] if funcao_csv else funcao_ant,
                    "setor_anterior": setor_ant,
                    "setor_novo": func.setor.nome if func.setor else "",
                }
            else:
                evento = None

        tamanhos_csv = {}
        if calcado:
            tamanhos_csv["calcado"] = calcado[:20]
        if luva:
            tamanhos_csv["luva"] = luva[:20]
        if vestimenta:
            tamanhos_csv["vestimenta"] = vestimenta[:20]

        rh.salvar_metadados_rh(
            request,
            func,
            tamanhos=tamanhos_csv or None,
            pin_provisorio=bool(exigir_troca_pin) if (eh_novo or pin_para_definir) else None,
            evento_funcional=evento,
            funcao=funcao_csv[:100] if funcao_csv else None,
            habilitacoes=habilitacoes_csv if habilitacoes_csv else None,
        )

        if gerar_kit:
            rh.gerar_kit_admissional(func, request.usuario, motivo="Kit Admissional (CSV)")

    registrar(
        request,
        "IMPORTACAO_FUNCIONARIOS_CSV",
        descricao=f"Importação CSV: {criados} criados, {atualizados} atualizados",
        criados=criados,
        atualizados=atualizados,
        erros=len(erros),
    )
    return JsonResponse({
        "sucesso": True,
        "criados": criados,
        "atualizados": atualizados,
        "erros": erros,
        "mensagem": f"Importação concluída: {criados} criado(s), {atualizados} atualizado(s).",
    })


@require_POST
@api_backoffice("pessoas")
def api_enviar_link_senha(request, funcionario_id):
    """Reenvia o link para o usuário criar/redefinir a própria senha (o ADMIN não vê senhas)."""
    func = Usuario.objects.filter(id=funcionario_id, ativo=True).first()
    if func is None or func.perfil not in PERFIS_BACKOFFICE or not func.email:
        return erro("Este colaborador não tem acesso ao backoffice ou está sem e-mail.")
    garantir_conta(func)
    if not enviar_link_de_senha(request, func):
        return erro("Não foi possível enviar o e-mail. Verifique o cadastro.")
    registrar(request, "LINK_SENHA_ENVIADO", func, f"Link de senha enviado para {func.email}")
    return JsonResponse({"sucesso": True, "mensagem": f"Link enviado para {func.email}."})


def _gerar_matricula_administrativa():
    """Gera um código funcional único ADM-XXXX quando o usuário é estritamente administrativo."""
    sequencia = Usuario.objects.filter(codigo_matricula__startswith="ADM-").count() + 1
    while True:
        candidato = f"ADM-{sequencia:04d}"
        if not Usuario.objects.filter(codigo_matricula=candidato).exists():
            return candidato
        sequencia += 1


@require_POST
@api_backoffice("pessoas")
def api_salvar_usuario_backoffice(request):
    """Cadastra ou atualiza um usuário administrativo do Backoffice / RBAC (RF-08, RF-09)."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json

    try:
        nome = texto(dados.get("nome"), "Nome", obrigatorio=True, maximo=150)
        email = texto(dados.get("email"), "E-mail corporativo", obrigatorio=True, maximo=150).lower()
        perfil = texto(dados.get("perfil"), "Perfil administrativo", obrigatorio=True).upper()
        matricula = texto(dados.get("matricula"), "Matrícula / ID funcional", maximo=30).upper()
        cargo = texto(dados.get("cargo"), "Cargo / função", maximo=100)
        pin = texto(dados.get("pin"), "PIN")
    except EntradaInvalida as e:
        return erro(str(e))

    if perfil not in PERFIS_BACKOFFICE:
        return erro("Selecione um perfil administrativo válido do backoffice (RBAC).")
    try:
        validate_email(email)
    except ValidationError:
        return erro("E-mail corporativo inválido.")
    if pin:
        problema = validar_novo_pin(pin)
        if problema:
            return erro(problema)

    usu_id = dados.get("id")
    if usu_id:
        usu = Usuario.objects.filter(id=usu_id).first()
        if usu is None:
            return erro("Usuário administrativo não encontrado.", status=404)
        if not matricula:
            matricula = usu.codigo_matricula
    else:
        usu = Usuario(ativo=True)
        if not matricula:
            matricula = _gerar_matricula_administrativa()

    if not re.fullmatch(r"[A-Z0-9-]+", matricula):
        return erro("Matrícula / ID funcional: use apenas letras, números e hífen.")
    if Usuario.objects.filter(codigo_matricula=matricula).exclude(pk=usu.pk).exists():
        return erro("Já existe registro com esta matrícula / ID funcional.")
    if Usuario.objects.filter(email__iexact=email).exclude(pk=usu.pk).exists():
        return erro("Já existe usuário cadastrado com este e-mail corporativo.")
    if usu.pk == request.usuario.pk and perfil != "ADMIN":
        return erro("Você não pode remover o seu próprio perfil de Administrador.")

    setor_id = dados.get("setor_id")
    setor = Setor.objects.filter(id=setor_id).first() if setor_id else usu.setor

    perfil_anterior = usu.perfil if usu.pk else None
    tinha_acesso = bool(usu.pk and usu.conta_id and usu.conta.has_usable_password())
    usu.nome = nome
    usu.codigo_matricula = matricula
    usu.email = email
    usu.perfil = perfil
    usu.cargo = cargo or PERFIS.get(perfil, perfil)
    usu.setor = setor
    if pin:
        definir_pin(usu, pin)
    usu.save()

    conta = garantir_conta(usu)
    convite_enviado = False
    if conta is not None and not tinha_acesso and not conta.has_usable_password():
        convite_enviado = enviar_link_de_senha(request, usu)

    registrar(
        request,
        "USUARIO_ADMIN_ATUALIZADO" if usu_id else "USUARIO_ADMIN_CADASTRADO",
        usu,
        f"{'Atualizou' if usu_id else 'Cadastrou'} usuário administrativo {usu.nome} ({PERFIS.get(perfil, perfil)})",
        perfil=perfil,
        perfil_anterior=perfil_anterior,
        convite_enviado=convite_enviado,
    )

    msg = "Usuário administrativo atualizado com sucesso." if usu_id else "Usuário administrativo cadastrado com sucesso."
    if convite_enviado:
        msg += f" Enviamos para {email} o link para criação da senha pessoal."
    return JsonResponse({"sucesso": True, "mensagem": msg, "id": str(usu.id), "convite_enviado": convite_enviado})
