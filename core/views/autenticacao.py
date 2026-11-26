"""Login, autenticação em dois fatores (2FA por e-mail), logout e sessão do backoffice (RF-08, RNF-03)."""
import hashlib
import hmac
import re
import secrets
import time

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import PasswordResetConfirmView
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from ..auditoria import registrar
from ..contas import garantir_conta
from ..models import Usuario
from ..permissoes import DESCRICAO_ACESSO, PERFIS, PERFIS_BACKOFFICE, acoes_do_perfil, usuario_da_requisicao
from ..seguranca import bloqueado, limpar_falhas, registrar_falha, senha_legada_confere
from .util import gerar_iniciais, ler_json

MENSAGEM_FALHA = "E-mail ou senha incorretos."

# Regras da autenticação em dois fatores (2FA) e dispositivo confiável
VALIDADE_CODIGO_2FA_SEGUNDOS = 60 * 60          # 1 hora
COOLDOWN_REENVIO_2FA_SEGUNDOS = 30              # evita disparo repetido de e-mails
TENTATIVAS_MAX_2FA = 5
LEMBRAR_DIAS = 30
LEMBRAR_SEGUNDOS = LEMBRAR_DIAS * 24 * 60 * 60
COOKIE_DISPOSITIVO_CONFIAVEL = "sf_2fa_confiavel"
SALT_COOKIE_2FA = "supplyflow-2fa-30d"
CHAVE_SESSAO_2FA = "pendente_2fa"


def dados_da_sessao(usuario):
    """O que o front precisa saber sobre quem está logado (sem dados sensíveis)."""
    return {
        "id": str(usuario.id),
        "nome": usuario.nome,
        "iniciais": gerar_iniciais(usuario.nome),
        "email": usuario.email,
        "matricula": usuario.codigo_matricula,
        "perfil_codigo": usuario.perfil,
        "perfil": PERFIS.get(usuario.perfil, usuario.perfil),
        "cargo": usuario.cargo,
        "acesso": DESCRICAO_ACESSO.get(usuario.perfil, ""),
        "acoes": sorted(acoes_do_perfil(usuario.perfil)),
    }


def _mascarar_email(email):
    """Transforma 'thiago@empresa.com' em 'th***@empresa.com' para exibir na tela."""
    if not email or "@" not in email:
        return "***"
    local, dominio = email.split("@", 1)
    prefixo = local[:2] if len(local) > 2 else local[:1]
    return f"{prefixo}***@{dominio}"


def _gerar_codigo_6_digitos():
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_codigo_2fa(desafio_id, codigo):
    chave = settings.SECRET_KEY.encode("utf-8")
    mensagem = f"{desafio_id}:{codigo}".encode("utf-8")
    return hmac.new(chave, mensagem, hashlib.sha256).hexdigest()


def _dispositivo_confiavel_valido(request, usuario):
    """Confere o cookie assinado de 30 dias para dispensar novo código 2FA neste navegador."""
    valor = request.COOKIES.get(COOKIE_DISPOSITIVO_CONFIAVEL)
    if not valor:
        return False
    signer = TimestampSigner(salt=SALT_COOKIE_2FA)
    try:
        usuario_id_assinado = signer.unsign(valor, max_age=LEMBRAR_SEGUNDOS)
    except (BadSignature, SignatureExpired):
        return False
    return hmac.compare_digest(str(usuario_id_assinado), str(usuario.id))


def _gravar_cookie_confiavel(response, usuario):
    signer = TimestampSigner(salt=SALT_COOKIE_2FA)
    valor_assinado = signer.sign(str(usuario.id))
    response.set_cookie(
        COOKIE_DISPOSITIVO_CONFIAVEL,
        valor_assinado,
        max_age=LEMBRAR_SEGUNDOS,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )


def _enviar_email_codigo_2fa(usuario, codigo):
    assunto = f"SupplyFlow — Seu código de verificação: {codigo}"
    corpo = (
        f"Olá, {usuario.nome}.\n\n"
        f"Seu código de verificação em duas etapas para acessar o SupplyFlow é:\n\n"
        f"    {codigo}\n\n"
        f"Este código é válido por 1 hora e pode ser usado apenas uma vez.\n"
        f"Se você não tentou entrar no sistema, ignore este e-mail e considere alterar sua senha.\n\n"
        f"— Equipe SupplyFlow"
    )
    send_mail(
        assunto,
        corpo,
        getattr(settings, "DEFAULT_FROM_EMAIL", "SupplyFlow <nao-responda@supplyflow.local>"),
        [usuario.email],
        fail_silently=False,
    )


def _concluir_login(request, usuario, conta, lembrar_30_dias=False, metodo="senha", renovar_cookie_confiavel=False):
    """Abre a sessão autenticada no Django, aplica validade de 30 dias se solicitado e audita."""
    login(request, conta)
    request.session.set_expiry(LEMBRAR_SEGUNDOS if lembrar_30_dias else 0)
    usuario.ultimo_acesso = timezone.now()
    usuario.save(update_fields=["ultimo_acesso"])
    registrar(
        request,
        "LOGIN",
        usuario,
        "Entrou no backoffice",
        usuario=usuario,
        metodo=metodo,
        lembrar_30_dias=lembrar_30_dias,
    )
    response = JsonResponse({"autenticado": True, "usuario": dados_da_sessao(usuario)})
    if lembrar_30_dias or renovar_cookie_confiavel:
        _gravar_cookie_confiavel(response, usuario)
    return response


@require_POST
def api_login(request):
    """Passo 1 do login: valida e-mail + senha.
    Se o navegador já tiver cookie confiável de 30 dias, conclui o login direto;
    caso contrário, envia código 2FA de 6 dígitos (válido por 1 hora) por e-mail."""
    dados, erro = ler_json(request)
    if erro:
        return erro

    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""
    lembrar_30_dias = bool(dados.get("lembrar_30_dias"))
    if not email or not senha:
        return JsonResponse({"autenticado": False, "erro": "Informe e-mail e senha."}, status=400)

    if bloqueado("login", email):
        return JsonResponse(
            {"autenticado": False, "erro": "Muitas tentativas. Aguarde 15 minutos e tente de novo."},
            status=429,
        )

    usuario = (
        Usuario.objects.filter(email__iexact=email, ativo=True, perfil__in=PERFIS_BACKOFFICE)
        .select_related("conta")
        .first()
    )
    conta = None
    if usuario:
        conta = garantir_conta(usuario)
        if conta is not None and not conta.has_usable_password() and senha_legada_confere(usuario, senha):
            # Senha antiga em MD5 correta: passa para o hash forte e apaga o MD5.
            conta.set_password(senha)
            conta.save(update_fields=["password"])
            usuario.senha_hash = None
            usuario.save(update_fields=["senha_hash"])
        if conta is not None:
            conta = authenticate(request, username=conta.username, password=senha)

    if conta is None:
        registrar_falha("login", email)
        registrar(request, "LOGIN_FALHOU", descricao=f"Tentativa de login para {email}", usuario=usuario)
        return JsonResponse({"autenticado": False, "erro": MENSAGEM_FALHA}, status=401)

    limpar_falhas("login", email)

    # Se este navegador já foi lembrado nos últimos 30 dias, entra direto sem pedir 2FA.
    if _dispositivo_confiavel_valido(request, usuario):
        return _concluir_login(
            request,
            usuario,
            conta,
            lembrar_30_dias=lembrar_30_dias,
            metodo="dispositivo_confiavel",
            renovar_cookie_confiavel=lembrar_30_dias,
        )

    # Dispositivo novo ou cookie expirado: gera desafio 2FA de 6 dígitos válido por 1 hora.
    agora = int(time.time())
    desafio_id = secrets.token_urlsafe(24)
    codigo = _gerar_codigo_6_digitos()
    request.session[CHAVE_SESSAO_2FA] = {
        "desafio_id": desafio_id,
        "usuario_id": str(usuario.id),
        "codigo_hash": _hash_codigo_2fa(desafio_id, codigo),
        "expira_em": agora + VALIDADE_CODIGO_2FA_SEGUNDOS,
        "reenviar_apos": agora + COOLDOWN_REENVIO_2FA_SEGUNDOS,
        "lembrar_30_dias": lembrar_30_dias,
        "tentativas": 0,
    }
    request.session.modified = True

    _enviar_email_codigo_2fa(usuario, codigo)
    registrar(
        request,
        "LOGIN_2FA_ENVIADO",
        usuario,
        f"Código 2FA enviado para {_mascarar_email(usuario.email)}",
        usuario=usuario,
    )
    return JsonResponse({
        "autenticado": False,
        "requer_2fa": True,
        "desafio_id": desafio_id,
        "email_mascarado": _mascarar_email(usuario.email),
        "validade_minutos": VALIDADE_CODIGO_2FA_SEGUNDOS // 60,
        "lembrar_30_dias": lembrar_30_dias,
    })


@require_POST
def api_login_2fa(request):
    """Passo 2 do login: valida o código de 6 dígitos enviado por e-mail (válido por 1 hora)."""
    dados, erro = ler_json(request)
    if erro:
        return erro

    desafio_id = (dados.get("desafio_id") or "").strip()
    codigo = re.sub(r"\s+", "", str(dados.get("codigo") or ""))
    if not re.fullmatch(r"\d{6}", codigo):
        return JsonResponse({"autenticado": False, "erro": "Informe o código numérico de 6 dígitos."}, status=400)

    pendente = request.session.get(CHAVE_SESSAO_2FA)
    if not pendente or not hmac.compare_digest(str(pendente.get("desafio_id", "")), desafio_id):
        return JsonResponse(
            {"autenticado": False, "erro": "Verificação expirada ou inválida. Entre novamente com e-mail e senha."},
            status=400,
        )

    agora = int(time.time())
    if agora > int(pendente.get("expira_em", 0)):
        request.session.pop(CHAVE_SESSAO_2FA, None)
        return JsonResponse(
            {"autenticado": False, "erro": "Código expirado (validade de 1 hora). Faça login novamente."},
            status=400,
        )

    usuario = (
        Usuario.objects.filter(id=pendente.get("usuario_id"), ativo=True, perfil__in=PERFIS_BACKOFFICE)
        .select_related("conta")
        .first()
    )
    if usuario is None or usuario.conta is None:
        request.session.pop(CHAVE_SESSAO_2FA, None)
        return JsonResponse({"autenticado": False, "erro": "Usuário indisponível. Faça login novamente."}, status=401)

    hash_recebido = _hash_codigo_2fa(desafio_id, codigo)
    if not hmac.compare_digest(str(pendente.get("codigo_hash", "")), hash_recebido):
        tentativas = int(pendente.get("tentativas", 0)) + 1
        if tentativas >= TENTATIVAS_MAX_2FA:
            request.session.pop(CHAVE_SESSAO_2FA, None)
            registrar(request, "LOGIN_2FA_BLOQUEADO", usuario, "Excedeu tentativas do código 2FA", usuario=usuario)
            return JsonResponse(
                {"autenticado": False, "erro": "Muitas tentativas incorretas. Faça login novamente para gerar um novo código."},
                status=429,
            )
        pendente["tentativas"] = tentativas
        request.session[CHAVE_SESSAO_2FA] = pendente
        request.session.modified = True
        restantes = TENTATIVAS_MAX_2FA - tentativas
        registrar(request, "LOGIN_2FA_FALHOU", usuario, "Código 2FA incorreto", usuario=usuario, tentativas=tentativas)
        return JsonResponse(
            {"autenticado": False, "erro": f"Código incorreto. Restam {restantes} tentativa(s)."},
            status=401,
        )

    # Código válido: consome o desafio (uso único) e conclui o login.
    lembrar_30_dias = (
        bool(dados["lembrar_30_dias"])
        if "lembrar_30_dias" in dados
        else bool(pendente.get("lembrar_30_dias"))
    )
    request.session.pop(CHAVE_SESSAO_2FA, None)
    return _concluir_login(
        request,
        usuario,
        usuario.conta,
        lembrar_30_dias=lembrar_30_dias,
        metodo="2fa_email",
        renovar_cookie_confiavel=lembrar_30_dias,
    )


@require_POST
def api_login_2fa_reenviar(request):
    """Gera e reenvia um novo código de 6 dígitos para o desafio 2FA em andamento."""
    dados, erro = ler_json(request)
    if erro:
        return erro

    desafio_id = (dados.get("desafio_id") or "").strip()
    pendente = request.session.get(CHAVE_SESSAO_2FA)
    if not pendente or not hmac.compare_digest(str(pendente.get("desafio_id", "")), desafio_id):
        return JsonResponse({"sucesso": False, "erro": "Sessão de verificação expirada. Volte e entre novamente."}, status=400)

    agora = int(time.time())
    aguardar = int(pendente.get("reenviar_apos", 0)) - agora
    if aguardar > 0:
        return JsonResponse(
            {"sucesso": False, "erro": f"Aguarde {aguardar} segundo(s) antes de solicitar outro código."},
            status=429,
        )

    usuario = Usuario.objects.filter(id=pendente.get("usuario_id"), ativo=True, perfil__in=PERFIS_BACKOFFICE).first()
    if usuario is None:
        request.session.pop(CHAVE_SESSAO_2FA, None)
        return JsonResponse({"sucesso": False, "erro": "Usuário indisponível."}, status=401)

    novo_codigo = _gerar_codigo_6_digitos()
    pendente["codigo_hash"] = _hash_codigo_2fa(desafio_id, novo_codigo)
    pendente["expira_em"] = agora + VALIDADE_CODIGO_2FA_SEGUNDOS
    pendente["reenviar_apos"] = agora + COOLDOWN_REENVIO_2FA_SEGUNDOS
    pendente["tentativas"] = 0
    request.session[CHAVE_SESSAO_2FA] = pendente
    request.session.modified = True

    _enviar_email_codigo_2fa(usuario, novo_codigo)
    registrar(request, "LOGIN_2FA_REENVIADO", usuario, f"Novo código 2FA enviado para {_mascarar_email(usuario.email)}", usuario=usuario)
    return JsonResponse({
        "sucesso": True,
        "email_mascarado": _mascarar_email(usuario.email),
        "validade_minutos": VALIDADE_CODIGO_2FA_SEGUNDOS // 60,
    })


@require_POST
def api_logout(request):
    usuario = usuario_da_requisicao(request)
    if usuario:
        registrar(request, "LOGOUT", usuario, "Saiu do backoffice", usuario=usuario)
    logout(request)
    return JsonResponse({"sucesso": True})


@require_GET
def api_sessao(request):
    """Quem está logado agora. 401 se a sessão expirou."""
    usuario = usuario_da_requisicao(request)
    if usuario is None:
        return JsonResponse({"autenticado": False}, status=401)
    return JsonResponse({"autenticado": True, "usuario": dados_da_sessao(usuario)})


class RedefinirSenhaView(PasswordResetConfirmView):
    """Tela do link recebido por e-mail: a pessoa cria a própria senha."""

    template_name = "registration/nova-senha.html"
    success_url = "/senha/concluida/"

    def form_valid(self, form):
        resposta = super().form_valid(form)
        usuario = getattr(form.user, "usuario", None)
        if usuario is not None:
            usuario.senha_hash = None  # descarta qualquer hash MD5 antigo
            usuario.save(update_fields=["senha_hash"])
        registrar(self.request, "SENHA_DEFINIDA", usuario, "Senha criada/redefinida pelo link", usuario=usuario)
        return resposta


__all__ = [
    "api_login",
    "api_login_2fa",
    "api_login_2fa_reenviar",
    "api_logout",
    "api_sessao",
    "RedefinirSenhaView",
]
