"""APIs de cadastro e ativação do catálogo de produtos e EPIs (RF-06, RF-07, RF-13, RF-36)."""
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from ..auditoria import registrar
from ..models import CategoriaProduto, EstoqueTotem, Fornecedor, Produto, Totem
from ..permissoes import api_backoffice
from .util import EntradaInvalida, decimal, erro, inteiro, ler_json, texto
# ============================================================================
# PRODUTOS (RF-06, RF-07, RF-13, RF-36)
# ============================================================================
def _produto_json(p):
    return {
        "id": str(p.id),
        "sku": p.sku,
        "nome": p.nome,
        "descricao": p.descricao or "",
        "categoria_id": str(p.categoria_id) if p.categoria_id else None,
        "categoria": p.categoria.nome if p.categoria else "Sem categoria",
        "tipo": "EPI" if p.eh_epi else "Consumível",
        "unidade_medida": p.unidade_medida,
        "custo_unitario": float(p.custo_unitario),
        "limite_padrao_mensal": p.limite_padrao_mensal,
        "periodicidade_dias": p.periodicidade_dias,
        "requer_justificativa": p.requer_justificativa,
        "ca": p.ca or "",
        "validade_ca": p.validade_ca.isoformat() if p.validade_ca else "",
        "tamanho": p.tamanho or "",
        "fornecedor_id": str(p.fornecedor_id) if p.fornecedor_id else None,
        "fornecedor": str(p.fornecedor) if p.fornecedor else None,
        "imagem_url": p.imagem_url or "",
        "ativo": p.ativo,
    }


@require_GET
@api_backoffice("ver")
def api_listar_produtos(request):
    todos = request.GET.get("todos", "false").lower() == "true"
    qs = Produto.objects.select_related("categoria", "fornecedor").order_by("nome")
    if not todos:
        qs = qs.filter(ativo=True)
    return JsonResponse({
        "produtos": [_produto_json(p) for p in qs],
        "categorias": [{"id": str(c.id), "nome": c.nome} for c in CategoriaProduto.objects.order_by("nome")],
        "fornecedores": [{"id": str(f.id), "nome": str(f)} for f in Fornecedor.objects.filter(ativo=True)],
    })


def _data_opcional(valor, campo):
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise EntradaInvalida(f"{campo}: use o formato AAAA-MM-DD.")


@require_POST
@api_backoffice("produtos")
def api_salvar_produto(request):
    """Cadastra ou edita um produto, com os dados específicos de EPI (CA, validade, tamanho, periodicidade)
    e garante vínculo inicial de estoque nos totens (RF-36)."""
    dados, erro_json = ler_json(request)
    if erro_json:
        return erro_json
    try:
        sku = texto(dados.get("sku"), "SKU", obrigatorio=True, maximo=50).upper()
        nome = texto(dados.get("nome"), "Nome", obrigatorio=True, maximo=150)
        descricao = texto(dados.get("descricao"), "Descrição", maximo=2000)
        unidade = (texto(dados.get("unidade_medida"), "Unidade", maximo=20) or "UN").upper()
        custo = decimal(dados.get("custo_unitario"), "Custo unitário", minimo=0, padrao="0")
        limite = inteiro(dados.get("limite_padrao_mensal"), "Limite mensal", minimo=0, maximo=10000) \
            if dados.get("limite_padrao_mensal") not in (None, "") else None
        periodicidade = inteiro(dados.get("periodicidade_dias"), "Periodicidade", minimo=1, maximo=3650) \
            if dados.get("periodicidade_dias") not in (None, "") else None
        ca = texto(dados.get("ca"), "CA", maximo=30) or None
        validade_ca = _data_opcional(dados.get("validade_ca"), "Validade do CA")
        tamanho = texto(dados.get("tamanho"), "Tamanho", maximo=30) or None
        imagem = texto(dados.get("imagem_url"), "Imagem", maximo=500)
    except EntradaInvalida as e:
        return erro(str(e))

    categoria = CategoriaProduto.objects.filter(id=dados.get("categoria_id")).first() if dados.get("categoria_id") else None
    fornecedor = Fornecedor.objects.filter(id=dados.get("fornecedor_id")).first() if dados.get("fornecedor_id") else None
    if categoria and "EPI" in categoria.nome.upper() and not ca:
        return erro("EPI precisa do número do Certificado de Aprovação (CA).")

    prod_id = dados.get("id")
    prod = Produto.objects.filter(id=prod_id).first() if prod_id else Produto(ativo=True)
    if prod_id and prod is None:
        return erro("Produto não encontrado.", status=404)
    if Produto.objects.filter(sku=sku).exclude(pk=prod.pk).exists():
        return erro("Já existe produto com este SKU.")

    prod.sku, prod.nome, prod.descricao, prod.categoria = sku, nome, descricao, categoria
    prod.unidade_medida, prod.custo_unitario = unidade, custo
    prod.limite_padrao_mensal, prod.periodicidade_dias = limite, periodicidade
    prod.requer_justificativa = bool(dados.get("requer_justificativa"))
    prod.ca, prod.validade_ca, prod.tamanho, prod.fornecedor = ca, validade_ca, tamanho, fornecedor
    if imagem:
        prod.imagem_url = imagem
    prod.save()

    # RF-36: garante que o produto possua registro de estoque em todos os totens cadastrados
    for totem in Totem.objects.all():
        EstoqueTotem.objects.get_or_create(
            totem=totem,
            produto=prod,
            defaults={"quantidade_disponivel": 0, "quantidade_minima": 5},
        )

    registrar(request, "PRODUTO_ATUALIZADO" if prod_id else "PRODUTO_CADASTRADO", prod, f"{prod.sku} — {prod.nome}")
    return JsonResponse({"sucesso": True, "mensagem": "Produto salvo com sucesso.", "id": str(prod.id)})


@require_POST
@api_backoffice("produtos")
def api_toggle_produto(request, produto_id):
    prod = Produto.objects.filter(id=produto_id).first()
    if prod is None:
        return erro("Produto não encontrado.", status=404)
    prod.ativo = not prod.ativo
    prod.save(update_fields=["ativo", "updated_at"])
    registrar(request, "PRODUTO_ATIVADO" if prod.ativo else "PRODUTO_INATIVADO", prod, prod.nome)
    return JsonResponse({"sucesso": True, "ativo": prod.ativo,
                         "mensagem": f"Produto {'ativado' if prod.ativo else 'inativado'}."})
