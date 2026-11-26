/* =====================================================================
   SupplyFlow — Configurações (dados da empresa · /api/empresa/)
   ---------------------------------------------------------------------
   Os dados ficam no servidor e valem para todo o sistema (Ficha de EPI
   NR-6, topo do backoffice). Só o Administrador altera; os demais perfis
   apenas consultam. Quem bloqueia de verdade é o servidor.
   ===================================================================== */

(function () {
  var aviso = document.getElementById("aviso-configuracoes");
  var form = document.getElementById("form-empresa");
  var campos = document.getElementById("campos-empresa");
  var erroEl = document.getElementById("erro-empresa");
  var btnSalvar = document.getElementById("btn-salvar-empresa");

  var CAMPOS = {
    razao_social: "empresa-razao",
    cnpj: "empresa-cnpj",
    nome_fantasia: "empresa-fantasia",
    estabelecimento: "empresa-estabelecimento",
    endereco: "empresa-endereco",
    cidade: "empresa-cidade",
    cep: "empresa-cep"
  };

  function campo(chave) {
    return document.getElementById(CAMPOS[chave]);
  }

  function somenteNumeros(texto) {
    return (texto || "").replace(/\D/g, "");
  }

  // Máscaras simples: formatam ao sair do campo (o servidor valida de novo).
  function formatarCnpj(texto) {
    var n = somenteNumeros(texto);
    if (n.length !== 14) {
      return texto;
    }
    return n.slice(0, 2) + "." + n.slice(2, 5) + "." + n.slice(5, 8) + "/" + n.slice(8, 12) + "-" + n.slice(12);
  }

  function formatarCep(texto) {
    var n = somenteNumeros(texto);
    if (n.length !== 8) {
      return texto;
    }
    return n.slice(0, 5) + "-" + n.slice(5);
  }

  campo("cnpj").addEventListener("blur", function () {
    this.value = formatarCnpj(this.value.trim());
  });
  campo("cep").addEventListener("blur", function () {
    this.value = formatarCep(this.value.trim());
  });

  function preencher(empresa) {
    Object.keys(CAMPOS).forEach(function (chave) {
      campo(chave).value = (empresa && empresa[chave]) || "";
    });
  }

  function mostrarErro(texto) {
    erroEl.textContent = texto;
    erroEl.classList.remove("d-none");
  }

  function carregar() {
    SF.api.get("/api/empresa/")
      .then(function (dados) {
        preencher(dados.empresa);
        campos.disabled = !dados.pode_editar;
        document.getElementById("somente-leitura").classList.toggle("d-none", !!dados.pode_editar);
        btnSalvar.classList.toggle("d-none", !dados.pode_editar);
      })
      .catch(function (erro) {
        SF.ui.mostrarAviso(aviso, erro.message, "danger");
      });
  }

  form.addEventListener("submit", function (evento) {
    evento.preventDefault();
    erroEl.classList.add("d-none");

    if (!campo("razao_social").value.trim()) {
      mostrarErro("Informe a razão social.");
      campo("razao_social").focus();
      return;
    }
    if (somenteNumeros(campo("cnpj").value).length !== 14) {
      mostrarErro("Informe o CNPJ com 14 números.");
      campo("cnpj").focus();
      return;
    }

    var dadosFormulario = {};
    Object.keys(CAMPOS).forEach(function (chave) {
      dadosFormulario[chave] = campo(chave).value.trim();
    });

    btnSalvar.disabled = true;
    SF.api.post("/api/empresa/salvar/", dadosFormulario)
      .then(function (resposta) {
        preencher(resposta.empresa);
        SF.ui.mostrarAviso(aviso, resposta.mensagem, "success");
        if (SF.atualizarNomeEmpresa) {
          SF.atualizarNomeEmpresa(resposta.empresa);
        }
      })
      .catch(function (erro) {
        mostrarErro(erro.message);
      })
      .finally(function () {
        btnSalvar.disabled = false;
      });
  });

  carregar();
})();
