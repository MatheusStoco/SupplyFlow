/* =====================================================================
   SupplyFlow — Tela de Login do Backoffice (com 2FA por e-mail e 30 dias)
   ---------------------------------------------------------------------
   Passo 1: envia e-mail, senha e "lembrar_30_dias" para /api/login/.
            Se o navegador já tiver cookie confiável de 30 dias, entra direto.
            Caso contrário, exibe o passo 2 para o código de 6 dígitos (1 h).
   Passo 2: envia o código para /api/login/2fa/ e conclui a autenticação.
   ===================================================================== */

(function () {
  var formLogin = document.getElementById("form-login");
  var campoEmail = document.getElementById("email");
  var campoSenha = document.getElementById("senha");
  var checkLembrar = document.getElementById("lembrar-30-dias");
  var caixaErro = document.getElementById("login-erro");
  var botaoEntrar = document.getElementById("btn-entrar");

  var form2fa = document.getElementById("form-2fa");
  var textoDestino2fa = document.getElementById("texto-2fa-destino");
  var campoCodigo2fa = document.getElementById("codigo-2fa");
  var checkLembrar2fa = document.getElementById("lembrar-30-dias-2fa");
  var caixaErro2fa = document.getElementById("erro-2fa");
  var caixaAviso2fa = document.getElementById("aviso-2fa");
  var botaoConfirmar2fa = document.getElementById("btn-confirmar-2fa");
  var botaoReenviar2fa = document.getElementById("btn-reenviar-2fa");
  var botaoVoltarLogin = document.getElementById("btn-voltar-login");

  var desafioAtualId = "";

  function mostrarErro(mensagem) {
    caixaErro.textContent = mensagem;
    caixaErro.classList.remove("d-none");
    campoSenha.setAttribute("aria-invalid", "true");
    campoSenha.value = "";
    campoSenha.focus();
  }

  function mostrarErro2fa(mensagem) {
    caixaAviso2fa.classList.add("d-none");
    caixaErro2fa.textContent = mensagem;
    caixaErro2fa.classList.remove("d-none");
    campoCodigo2fa.setAttribute("aria-invalid", "true");
    campoCodigo2fa.focus();
    campoCodigo2fa.select();
  }

  function mostrarAviso2fa(mensagem) {
    caixaErro2fa.classList.add("d-none");
    caixaAviso2fa.textContent = mensagem;
    caixaAviso2fa.classList.remove("d-none");
  }

  /* Regra de segurança (evita Open Redirect):
     Só aceita redirecionar para páginas internas dentro de /backoffice/*.html. */
  function destinoSeguro() {
    var parametrosUrl = new URLSearchParams(window.location.search);
    var proximo = parametrosUrl.get("proximo") || "";
    var padraoPaginaInterna = /^\/backoffice\/[a-z0-9-]+\.html(\?[^#]*)?$/i;

    if (padraoPaginaInterna.test(proximo)) {
      return proximo;
    }
    return "/backoffice/visao-geral.html";
  }

  function abrirEtapa2fa(resposta) {
    desafioAtualId = resposta.desafio_id || "";
    textoDestino2fa.textContent =
      "Enviamos um código de 6 dígitos para " + (resposta.email_mascarado || "seu e-mail") +
      ". Ele é válido por 1 hora.";
    checkLembrar2fa.checked = Boolean(resposta.lembrar_30_dias);
    caixaErro2fa.classList.add("d-none");
    caixaAviso2fa.classList.add("d-none");
    campoCodigo2fa.value = "";
    campoCodigo2fa.removeAttribute("aria-invalid");

    formLogin.classList.add("d-none");
    form2fa.classList.remove("d-none");
    campoCodigo2fa.focus();
  }

  function voltarParaLogin() {
    desafioAtualId = "";
    form2fa.classList.add("d-none");
    formLogin.classList.remove("d-none");
    caixaErro.classList.add("d-none");
    campoSenha.value = "";
    campoSenha.focus();
  }

  /* Mantém apenas dígitos no campo de 6 números */
  if (campoCodigo2fa) {
    campoCodigo2fa.addEventListener("input", function () {
      campoCodigo2fa.value = campoCodigo2fa.value.replace(/\D/g, "").slice(0, 6);
    });
  }

  formLogin.addEventListener("submit", function (evento) {
    evento.preventDefault();
    caixaErro.classList.add("d-none");
    campoSenha.removeAttribute("aria-invalid");

    var email = campoEmail.value.trim();
    var senha = campoSenha.value;
    var lembrar = Boolean(checkLembrar && checkLembrar.checked);
    if (!email || !senha) {
      mostrarErro("Informe e-mail e senha.");
      return;
    }

    botaoEntrar.disabled = true;
    SF.api.post("/api/login/", { email: email, senha: senha, lembrar_30_dias: lembrar }, { semRedirecionar: true })
      .then(function (resposta) {
        if (resposta.requer_2fa) {
          abrirEtapa2fa(resposta);
          return;
        }
        SF.sessao.iniciar(resposta.usuario);
        window.location.href = destinoSeguro();
      })
      .catch(function (erro) {
        mostrarErro(erro.message);
      })
      .finally(function () {
        botaoEntrar.disabled = false;
      });
  });

  if (form2fa) {
    form2fa.addEventListener("submit", function (evento) {
      evento.preventDefault();
      caixaErro2fa.classList.add("d-none");
      caixaAviso2fa.classList.add("d-none");
      campoCodigo2fa.removeAttribute("aria-invalid");

      var codigo = campoCodigo2fa.value.replace(/\D/g, "");
      if (codigo.length !== 6) {
        mostrarErro2fa("Digite os 6 dígitos do código enviado ao seu e-mail.");
        return;
      }

      botaoConfirmar2fa.disabled = true;
      SF.api.post(
        "/api/login/2fa/",
        {
          desafio_id: desafioAtualId,
          codigo: codigo,
          lembrar_30_dias: Boolean(checkLembrar2fa && checkLembrar2fa.checked)
        },
        { semRedirecionar: true }
      )
        .then(function (resposta) {
          SF.sessao.iniciar(resposta.usuario);
          window.location.href = destinoSeguro();
        })
        .catch(function (erro) {
          mostrarErro2fa(erro.message);
        })
        .finally(function () {
          botaoConfirmar2fa.disabled = false;
        });
    });
  }

  if (botaoReenviar2fa) {
    botaoReenviar2fa.addEventListener("click", function () {
      if (!desafioAtualId) return;
      botaoReenviar2fa.disabled = true;
      SF.api.post("/api/login/2fa/reenviar/", { desafio_id: desafioAtualId }, { semRedirecionar: true })
        .then(function (resposta) {
          mostrarAviso2fa("Novo código enviado para " + (resposta.email_mascarado || "seu e-mail") + ". Válido por 1 hora.");
          campoCodigo2fa.value = "";
          campoCodigo2fa.focus();
        })
        .catch(function (erro) {
          mostrarErro2fa(erro.message);
        })
        .finally(function () {
          botaoReenviar2fa.disabled = false;
        });
    });
  }

  if (botaoVoltarLogin) {
    botaoVoltarLogin.addEventListener("click", voltarParaLogin);
  }
})();
