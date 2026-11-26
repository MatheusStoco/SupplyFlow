/* =====================================================================
   SupplyFlow — Botão "olhinho" para mostrar/ocultar senhas e PINs
   ---------------------------------------------------------------------
   Basta incluir este arquivo na página: todo <input type="password">
   ganha um botão com ícone de olho ao lado. Ao clicar, o campo alterna
   entre texto visível e oculto. Acessível: o botão tem nome ("Mostrar
   senha" / "Ocultar senha") e aria-pressed para leitores de tela.
   Por segurança, o campo volta a ficar oculto ao enviar ou limpar o
   formulário.
   ===================================================================== */

(function () {
  function ocultar(campo, botao) {
    campo.type = "password";
    botao.setAttribute("aria-pressed", "false");
    botao.setAttribute("aria-label", "Mostrar senha");
    botao.title = "Mostrar senha";
    botao.innerHTML = '<i class="bi bi-eye" aria-hidden="true"></i>';
  }

  function mostrar(campo, botao) {
    campo.type = "text";
    botao.setAttribute("aria-pressed", "true");
    botao.setAttribute("aria-label", "Ocultar senha");
    botao.title = "Ocultar senha";
    botao.innerHTML = '<i class="bi bi-eye-slash" aria-hidden="true"></i>';
  }

  function adicionarOlho(campo) {
    if (campo.dataset.olhoSenha) {
      return;
    }
    campo.dataset.olhoSenha = "1";

    var envoltorio = document.createElement("div");
    envoltorio.className = "campo-senha";
    campo.parentNode.insertBefore(envoltorio, campo);
    envoltorio.appendChild(campo);

    var botao = document.createElement("button");
    botao.type = "button";
    botao.className = "campo-senha__olho";
    if (campo.id) {
      botao.setAttribute("aria-controls", campo.id);
    }
    envoltorio.appendChild(botao);
    ocultar(campo, botao);

    botao.addEventListener("click", function () {
      if (campo.type === "password") {
        mostrar(campo, botao);
      } else {
        ocultar(campo, botao);
      }
      campo.focus();
    });

    if (campo.form) {
      campo.form.addEventListener("submit", function () {
        ocultar(campo, botao);
      });
      campo.form.addEventListener("reset", function () {
        ocultar(campo, botao);
      });
    }
  }

  function iniciar() {
    var campos = document.querySelectorAll('input[type="password"]');
    Array.prototype.forEach.call(campos, adicionarOlho);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
