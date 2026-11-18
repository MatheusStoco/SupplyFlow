"""APIs da estrutura organizacional: setores/centros de custo (RF-02), fornecedores (RF-05) e empresa."""
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from ..auditoria import registrar
from ..models import Fornecedor, Setor
from ..permissoes import api_backoffice, pode
from ..servicos.empresa import obter_dados_empresa, salvar_dados_empresa, validar_cnpj
from .util import EntradaInvalida, erro, ler_json, texto
# ============================================================================
# SETORES E CENTROS DE CUSTO (RF-02)
# ============================================================================
@require_GET
@api_backoffice("ver")
def api_listar_setores(request):
    setores = Setor.objects.annotate(total_funcionarios=Count("usuario", filter=Q(usuario__ativo=True))).order_by("nome")
    return JsonResponse({"setores": [
        {"id": str(s.id), "nome": s.nome, "centro_custo": s.centro_custo or "—", "ativo": s.ativo,
         "total_funcionarios": s.total_funcionarios}
        for s in setores
    ]})


@require_POST
@api_backoffice("pessoas")
def api_salvar_setor(request):
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    try:
        nome = texto(dados.get("nome"), "Nome do setor", obrigatorio=True, maximo=100)
        cc = texto(dados.get("centro_custo"), "Centro de custo", maximo=50)
    except EntradaInvalida as e:
        return erro(str(e))
    setor_id = dados.get("id")
    setor = Setor.objects.filter(id=setor_id).first() if setor_id else Setor(ativo=True)
    if setor_id and setor is None:
        return erro("Setor não encontrado.", status=404)
    if Setor.objects.filter(nome__iexact=nome).exclude(pk=setor.pk).exists():
        return erro("Já existe um setor com este nome.")
    setor.nome, setor.centro_custo = nome, cc
    setor.save()
    registrar(request, "SETOR_ATUALIZADO" if setor_id else "SETOR_CADASTRADO", setor, f"{nome} ({cc or 'sem CC'})")
    return JsonResponse({"sucesso": True, "mensagem": "Setor salvo com sucesso.", "id": str(setor.id)})


@require_POST
@api_backoffice("pessoas")
def api_toggle_setor(request, setor_id):
    setor = Setor.objects.filter(id=setor_id).first()
    if setor is None:
        return erro("Setor não encontrado.", status=404)
    setor.ativo = not setor.ativo
    setor.save(update_fields=["ativo"])
    registrar(request, "SETOR_ATIVADO" if setor.ativo else "SETOR_INATIVADO", setor, setor.nome)
    return JsonResponse({"sucesso": True, "ativo": setor.ativo,
                         "mensagem": f"Setor {'ativado' if setor.ativo else 'inativado'}."})


# ============================================================================
# FORNECEDORES (RF-05)
# ============================================================================
@require_GET
@api_backoffice("ver")
def api_listar_fornecedores(request):
    return JsonResponse({"fornecedores": [
        {"id": str(f.id), "razao_social": f.razao_social, "nome_fantasia": f.nome_fantasia, "cnpj": f.cnpj,
         "email": f.email, "telefone": f.telefone, "contato": f.contato, "ativo": f.ativo,
         "produtos": f.produto_set.count()}
        for f in Fornecedor.objects.order_by("razao_social")
    ]})


@require_POST
@api_backoffice("produtos")
def api_salvar_fornecedor(request):
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    try:
        razao = texto(dados.get("razao_social"), "Razão social", obrigatorio=True, maximo=150)
        fantasia = texto(dados.get("nome_fantasia"), "Nome fantasia", maximo=150)
        email = texto(dados.get("email"), "E-mail", maximo=150).lower()
        telefone = texto(dados.get("telefone"), "Telefone", maximo=30)
        contato = texto(dados.get("contato"), "Contato", maximo=100)
    except EntradaInvalida as e:
        return erro(str(e))
    cnpj = validar_cnpj(dados.get("cnpj"))
    if not cnpj:
        return erro("CNPJ inválido.")
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return erro("E-mail inválido.")
    forn_id = dados.get("id")
    forn = Fornecedor.objects.filter(id=forn_id).first() if forn_id else Fornecedor(ativo=True)
    if forn_id and forn is None:
        return erro("Fornecedor não encontrado.", status=404)
    if Fornecedor.objects.filter(cnpj=cnpj).exclude(pk=forn.pk).exists():
        return erro("Já existe fornecedor com este CNPJ.")
    forn.razao_social, forn.nome_fantasia, forn.cnpj = razao, fantasia, cnpj
    forn.email, forn.telefone, forn.contato = email, telefone, contato
    forn.save()
    registrar(request, "FORNECEDOR_ATUALIZADO" if forn_id else "FORNECEDOR_CADASTRADO", forn, f"{razao} ({cnpj})")
    return JsonResponse({"sucesso": True, "mensagem": "Fornecedor salvo com sucesso.", "id": str(forn.id)})


@require_POST
@api_backoffice("produtos")
def api_toggle_fornecedor(request, fornecedor_id):
    forn = Fornecedor.objects.filter(id=fornecedor_id).first()
    if forn is None:
        return erro("Fornecedor não encontrado.", status=404)
    forn.ativo = not forn.ativo
    forn.save(update_fields=["ativo"])
    registrar(request, "FORNECEDOR_ATIVADO" if forn.ativo else "FORNECEDOR_INATIVADO", forn, forn.razao_social)
    return JsonResponse({"sucesso": True, "ativo": forn.ativo})


# ============================================================================
# CONFIGURA??O DO TENANT / EMPRESA EMPREGADORA (NR-6)
# ============================================================================
@require_GET
@api_backoffice("ver")
def api_obter_empresa(request):
    """Retorna os dados cadastrais da empresa (tenant inicial) para documentos legais."""
    return JsonResponse({
        "empresa": obter_dados_empresa(),
        "pode_editar": pode(request.usuario, "auditoria"),
    })


@require_POST
@api_backoffice("auditoria")
def api_salvar_empresa(request):
    """Salva Raz?o Social, CNPJ e endere?o do tenant inicial (somente Administrador)."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    try:
        razao = texto(dados.get("razao_social"), "Raz?o social", obrigatorio=True, maximo=150)
        fantasia = texto(dados.get("nome_fantasia"), "Nome fantasia", maximo=150)
        estabelecimento = texto(dados.get("estabelecimento"), "Estabelecimento", maximo=150)
        endereco = texto(dados.get("endereco"), "Endere?o", maximo=250)
        cidade = texto(dados.get("cidade"), "Cidade/UF", maximo=100)
    except EntradaInvalida as e:
        return erro(str(e))
    cnpj = validar_cnpj(dados.get("cnpj"))
    if not cnpj:
        return erro("Informe um CNPJ v?lido no formato 00.000.000/0000-00.")
    empresa = salvar_dados_empresa(
        request,
        razao_social=razao,
        cnpj=cnpj,
        nome_fantasia=fantasia,
        estabelecimento=estabelecimento,
        endereco=endereco,
        cidade=cidade,
    )
    return JsonResponse({"sucesso": True, "mensagem": "Dados da empresa salvos com sucesso.", "empresa": empresa})
