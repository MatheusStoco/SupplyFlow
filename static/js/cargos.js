/* =====================================================================
   SupplyFlow — Catálogo de Cargos (RH), Funções (SST) e Habilitações (NRs)
   ---------------------------------------------------------------------
   Compartilhado pelas 3 páginas dedicadas em Organização:
   - backoffice/cargos.html       (tabela-cargos-corpo)
   - backoffice/funcoes.html      (tabela-funcoes-corpo)
   - backoffice/habilitacoes.html (tabela-habilitacoes-corpo)
   Todas consomem /api/cargos/, /api/cargos/salvar/ e /api/cargos/excluir/.
   ===================================================================== */

(function () {
  var corpoCargos = document.getElementById("tabela-cargos-corpo");
  var corpoFuncoes = document.getElementById("tabela-funcoes-corpo");
  var corpoHabilitacoes = document.getElementById("tabela-habilitacoes-corpo");
  var corpoAtivo = corpoCargos || corpoFuncoes || corpoHabilitacoes;
  var campoBusca = document.getElementById("filtro-busca-catalogo");
  var metaCatalogo = document.getElementById("meta-catalogo");

  var escapar = SF.escapar;
  var modalEl = document.getElementById("modal-cargo");
  var modalBs = modalEl ? new bootstrap.Modal(modalEl) : null;
  var form = document.getElementById("form-cargo");
  var btnNovoCargo = document.getElementById("btn-novo-cargo");
  var btnNovaFuncao = document.getElementById("btn-nova-funcao");
  var btnNovaHabilitacao = document.getElementById("btn-nova-habilitacao");
  var podeGerenciar = SF.sessao.pode("pessoas");

  var catalogo = {
    cargos: [],
    funcoes: [],
    habilitacoes: []
  };

  if (!podeGerenciar) {
    if (btnNovoCargo) btnNovoCargo.classList.add("d-none");
    if (btnNovaFuncao) btnNovaFuncao.classList.add("d-none");
    if (btnNovaHabilitacao) btnNovaHabilitacao.classList.add("d-none");
  }

  function abrirModalOcupacional(tipo, dadosEdicao) {
    if (!form) return;
    form.reset();
    document.getElementById("cargo-tipo").value = tipo;
    var blocoHab = document.getElementById("bloco-campos-habilitacao");
    var labelNome = document.getElementById("label-cargo-nome");
    var inputNome = document.getElementById("cargo-nome");
    var tituloModal = document.getElementById("modalCargoTitulo");
    var ajuda = document.getElementById("ajuda-cargo");
    var inputHabDesc = document.getElementById("hab-descricao");
    var checkHabValidade = document.getElementById("hab-exige-validade");

    if (tipo === "FUNCAO") {
      if (blocoHab) blocoHab.classList.add("d-none");
      var nomeFuncao = dadosEdicao ? (dadosEdicao.funcao || dadosEdicao.nome || "") : "";
      tituloModal.textContent = nomeFuncao ? "Editar Função / Atividade (SST)" : "Nova Função / Atividade (SST)";
      labelNome.textContent = "Nome da Função / Atividade (SST) *";
      inputNome.placeholder = "Ex.: Soldagem MIG/MAG, Manutenção Elétrica";
      ajuda.textContent = "Define a atividade operacional exercida para vínculo com EPIs e regras de SST (RF-04).";
      document.getElementById("cargo-original").value = nomeFuncao;
      inputNome.value = nomeFuncao;
    } else if (tipo === "HABILITACAO") {
      if (blocoHab) blocoHab.classList.remove("d-none");
      var nomeHab = dadosEdicao ? (dadosEdicao.habilitacao || dadosEdicao.nome || "") : "";
      tituloModal.textContent = nomeHab ? "Editar Habilitação / NR" : "Nova Habilitação / NR";
      labelNome.textContent = "Código / Nome da Habilitação ou NR *";
      inputNome.placeholder = "Ex.: NR-35 Trabalho em Altura, NR-10";
      ajuda.textContent = "Credencial normativa ou licença exigida para liberação de EPIs de risco específico.";
      document.getElementById("cargo-original").value = nomeHab;
      inputNome.value = nomeHab;
      if (inputHabDesc) {
        inputHabDesc.value = (dadosEdicao && dadosEdicao.descricao) ? dadosEdicao.descricao : "";
      }
      if (checkHabValidade) {
        checkHabValidade.checked = dadosEdicao ? (dadosEdicao.exige_validade !== false) : true;
      }
    } else {
      if (blocoHab) blocoHab.classList.add("d-none");
      var nomeCargo = dadosEdicao ? (dadosEdicao.cargo || dadosEdicao.nome || "") : "";
      tituloModal.textContent = nomeCargo ? "Editar Cargo (RH)" : "Novo Cargo (RH)";
      labelNome.textContent = "Nome do Cargo (RH) *";
      inputNome.placeholder = "Ex.: Operador de Caldeira";
      ajuda.textContent = "Ao renomear um cargo existente, os funcionários e políticas vinculados são atualizados automaticamente.";
      document.getElementById("cargo-original").value = nomeCargo;
      inputNome.value = nomeCargo;
    }

    if (modalBs) {
      modalBs.show();
    }
  }

  function formatarProdutosVinculados(lista) {
    if (lista && lista.length > 0) {
      return escapar(lista.join(", "));
    }
    return '<span class="text-muted">Nenhuma política específica — vale o padrão de cada produto</span>';
  }

  function criarLinhaCargoHtml(itemCargo) {
    var textoSetores = (itemCargo.setores || []).join(", ") || "—";
    var htmlProdutosVinculados = formatarProdutosVinculados(itemCargo.produtos_vinculados);

    var htmlAcoes = "—";
    if (podeGerenciar) {
      var desabilitarExclusao = itemCargo.total_funcionarios > 0 ? " disabled" : "";
      var tituloExclusao = itemCargo.total_funcionarios > 0
        ? "Não é possível remover cargo com funcionários ativos"
        : "Remover " + escapar(itemCargo.cargo);
      htmlAcoes =
        '<button type="button" class="btn btn-sm btn-outline-secondary me-1 btn-edit-cargo" data-cargo="' + escapar(itemCargo.cargo) + '"' +
                ' aria-label="Editar ' + escapar(itemCargo.cargo) + '">' +
          '<i class="bi bi-pencil" aria-hidden="true"></i>' +
        "</button>" +
        '<button type="button" class="btn btn-sm btn-outline-danger btn-del-cargo" data-cargo="' + escapar(itemCargo.cargo) + '"' +
                ' aria-label="' + tituloExclusao + '" title="' + tituloExclusao + '"' + desabilitarExclusao + ">" +
          '<i class="bi bi-trash" aria-hidden="true"></i>' +
        "</button>";
    }

    return (
      "<tr>" +
        "<td><strong>" + escapar(itemCargo.cargo) + "</strong></td>" +
        "<td>" + escapar(textoSetores) + "</td>" +
        "<td>" + escapar(itemCargo.total_funcionarios) + "</td>" +
        '<td class="small">' + htmlProdutosVinculados + "</td>" +
        '<td class="text-end text-nowrap">' + htmlAcoes + "</td>" +
      "</tr>"
    );
  }

  function criarLinhaFuncaoHtml(itemFuncao) {
    var nomeFuncao = itemFuncao.funcao || itemFuncao.nome || "";
    var totalFunc = itemFuncao.total_funcionarios != null ? itemFuncao.total_funcionarios : (itemFuncao.total || 0);
    var textoSetores = (itemFuncao.setores || []).join(", ") || "—";
    var htmlProdutosVinculados = formatarProdutosVinculados(itemFuncao.produtos_vinculados);

    var htmlAcoes = "—";
    if (podeGerenciar) {
      var desabilitarExclusao = totalFunc > 0 ? " disabled" : "";
      var tituloExclusao = totalFunc > 0
        ? "Não é possível remover função com funcionários ativos"
        : "Remover " + escapar(nomeFuncao);
      htmlAcoes =
        '<button type="button" class="btn btn-sm btn-outline-secondary me-1 btn-edit-funcao" data-funcao="' + escapar(nomeFuncao) + '"' +
                ' aria-label="Editar função ' + escapar(nomeFuncao) + '">' +
          '<i class="bi bi-pencil" aria-hidden="true"></i>' +
        "</button>" +
        '<button type="button" class="btn btn-sm btn-outline-danger btn-del-funcao" data-funcao="' + escapar(nomeFuncao) + '"' +
                ' aria-label="' + tituloExclusao + '" title="' + tituloExclusao + '"' + desabilitarExclusao + ">" +
          '<i class="bi bi-trash" aria-hidden="true"></i>' +
        "</button>";
    }

    return (
      "<tr>" +
        "<td><strong>" + escapar(nomeFuncao) + "</strong></td>" +
        "<td>" + escapar(textoSetores) + "</td>" +
        "<td>" + escapar(totalFunc) + "</td>" +
        '<td class="small">' + htmlProdutosVinculados + "</td>" +
        '<td class="text-end text-nowrap">' + htmlAcoes + "</td>" +
      "</tr>"
    );
  }

  function criarLinhaHabilitacaoHtml(itemHab) {
    var nomeHab = itemHab.habilitacao || itemHab.nome || "";
    var descricao = itemHab.descricao || "";
    var exigeValidade = itemHab.exige_validade !== false;
    var totalFunc = itemHab.total_funcionarios != null ? itemHab.total_funcionarios : (itemHab.total || 0);
    var vencidas = itemHab.vencidas || 0;
    var htmlProdutosVinculados = formatarProdutosVinculados(itemHab.produtos_vinculados);

    var badgeValidade = exigeValidade
      ? '<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle">Controla validade</span>'
      : '<span class="badge bg-light text-secondary border">Sem vencimento</span>';

    var htmlDescricao = badgeValidade + (descricao ? '<div class="small text-muted mt-1">' + escapar(descricao) + "</div>" : "");

    var htmlFuncionarios = escapar(totalFunc);
    if (vencidas > 0) {
      htmlFuncionarios +=
        ' <span class="badge bg-danger-subtle text-danger border border-danger-subtle ms-1">' +
          '<i class="bi bi-exclamation-triangle-fill me-1" aria-hidden="true"></i>' + escapar(vencidas) + " vencida(s)" +
        "</span>";
    }

    var htmlAcoes = "—";
    if (podeGerenciar) {
      var desabilitarExclusao = totalFunc > 0 ? " disabled" : "";
      var tituloExclusao = totalFunc > 0
        ? "Não é possível remover habilitação com funcionários vinculados"
        : "Remover " + escapar(nomeHab);
      htmlAcoes =
        '<button type="button" class="btn btn-sm btn-outline-secondary me-1 btn-edit-hab"' +
                ' data-hab="' + escapar(nomeHab) + '"' +
                ' data-desc="' + escapar(descricao) + '"' +
                ' data-validade="' + (exigeValidade ? "1" : "0") + '"' +
                ' aria-label="Editar habilitação ' + escapar(nomeHab) + '">' +
          '<i class="bi bi-pencil" aria-hidden="true"></i>' +
        "</button>" +
        '<button type="button" class="btn btn-sm btn-outline-danger btn-del-hab" data-hab="' + escapar(nomeHab) + '"' +
                ' aria-label="' + tituloExclusao + '" title="' + tituloExclusao + '"' + desabilitarExclusao + ">" +
          '<i class="bi bi-trash" aria-hidden="true"></i>' +
        "</button>";
    }

    return (
      "<tr>" +
        "<td><strong>" + escapar(nomeHab) + "</strong></td>" +
        "<td>" + htmlDescricao + "</td>" +
        "<td>" + htmlFuncionarios + "</td>" +
        '<td class="small">' + htmlProdutosVinculados + "</td>" +
        '<td class="text-end text-nowrap">' + htmlAcoes + "</td>" +
      "</tr>"
    );
  }

  function textoBuscaDoItem(item) {
    var partes = [
      item.cargo || "",
      item.funcao || "",
      item.habilitacao || "",
      item.nome || "",
      item.descricao || "",
      (item.setores || []).join(" "),
      (item.produtos_vinculados || []).join(" ")
    ];
    return partes.join(" ").toLowerCase();
  }

  function filtrarLista(lista, termo) {
    if (!termo) return lista;
    return lista.filter(function (item) {
      return textoBuscaDoItem(item).indexOf(termo) !== -1;
    });
  }

  function atualizarContador(filtrados, total, termo) {
    if (!metaCatalogo) return;
    if (termo) {
      metaCatalogo.textContent = filtrados + " de " + total + " registro(s)";
    } else {
      metaCatalogo.textContent = total + (total === 1 ? " registro" : " registros");
    }
  }

  function renderizarTabelaCatalogo(corpo, listaCompleta, mensagemVazia, renderizadorLinha) {
    if (!corpo) return;
    var termo = campoBusca ? campoBusca.value.trim().toLowerCase() : "";
    var filtrada = filtrarLista(listaCompleta, termo);
    atualizarContador(filtrada.length, listaCompleta.length, termo);

    if (filtrada.length === 0) {
      var msg = termo ? "Nenhum registro encontrado para a busca informada." : mensagemVazia;
      corpo.innerHTML = '<tr><td colspan="5" class="tabela-solicitacoes__vazio">' + msg + "</td></tr>";
      return;
    }
    corpo.innerHTML = filtrada.map(renderizadorLinha).join("");
  }

  function conectarEventosAcoes() {
    document.querySelectorAll(".btn-edit-cargo").forEach(function (botao) {
      botao.addEventListener("click", function () {
        abrirModalOcupacional("CARGO", { cargo: botao.dataset.cargo });
      });
    });
    document.querySelectorAll(".btn-del-cargo").forEach(function (botao) {
      botao.addEventListener("click", function () {
        SF.api.post("/api/cargos/excluir/", { tipo: "CARGO", cargo: botao.dataset.cargo })
          .then(carregarCargos)
          .catch(function (erro) { alert(erro.message); });
      });
    });

    document.querySelectorAll(".btn-edit-funcao").forEach(function (botao) {
      botao.addEventListener("click", function () {
        abrirModalOcupacional("FUNCAO", { funcao: botao.dataset.funcao });
      });
    });
    document.querySelectorAll(".btn-del-funcao").forEach(function (botao) {
      botao.addEventListener("click", function () {
        SF.api.post("/api/cargos/excluir/", { tipo: "FUNCAO", funcao: botao.dataset.funcao, cargo: botao.dataset.funcao })
          .then(carregarCargos)
          .catch(function (erro) { alert(erro.message); });
      });
    });

    document.querySelectorAll(".btn-edit-hab").forEach(function (botao) {
      botao.addEventListener("click", function () {
        abrirModalOcupacional("HABILITACAO", {
          habilitacao: botao.dataset.hab,
          descricao: botao.dataset.desc || "",
          exige_validade: botao.dataset.validade !== "0"
        });
      });
    });
    document.querySelectorAll(".btn-del-hab").forEach(function (botao) {
      botao.addEventListener("click", function () {
        SF.api.post("/api/cargos/excluir/", { tipo: "HABILITACAO", habilitacao: botao.dataset.hab, cargo: botao.dataset.hab })
          .then(carregarCargos)
          .catch(function (erro) { alert(erro.message); });
      });
    });
  }

  function renderizarPaginaAtual() {
    renderizarTabelaCatalogo(corpoCargos, catalogo.cargos, "Nenhum cargo cadastrado.", criarLinhaCargoHtml);
    renderizarTabelaCatalogo(corpoFuncoes, catalogo.funcoes, "Nenhuma função/atividade cadastrada.", criarLinhaFuncaoHtml);
    renderizarTabelaCatalogo(corpoHabilitacoes, catalogo.habilitacoes, "Nenhuma habilitação ou NR cadastrada.", criarLinhaHabilitacaoHtml);
    conectarEventosAcoes();
  }

  function carregarCargos() {
    SF.api.get("/api/cargos/")
      .then(function (dados) {
        catalogo.cargos = dados.cargos || [];
        catalogo.funcoes = dados.funcoes || [];
        catalogo.habilitacoes = dados.habilitacoes || [];
        renderizarPaginaAtual();
      })
      .catch(function (erro) {
        if (metaCatalogo) metaCatalogo.textContent = "Erro ao carregar";
        if (corpoAtivo) {
          corpoAtivo.innerHTML = '<tr><td colspan="5" class="tabela-solicitacoes__vazio">' + escapar(erro.message) + "</td></tr>";
        }
      });
  }

  if (campoBusca) {
    campoBusca.addEventListener("input", renderizarPaginaAtual);
  }

  if (btnNovoCargo) {
    btnNovoCargo.addEventListener("click", function () {
      abrirModalOcupacional("CARGO", null);
    });
  }
  if (btnNovaFuncao) {
    btnNovaFuncao.addEventListener("click", function () {
      abrirModalOcupacional("FUNCAO", null);
    });
  }
  if (btnNovaHabilitacao) {
    btnNovaHabilitacao.addEventListener("click", function () {
      abrirModalOcupacional("HABILITACAO", null);
    });
  }

  if (form) {
    form.addEventListener("submit", function (evento) {
      evento.preventDefault();
      var tipo = document.getElementById("cargo-tipo").value || "CARGO";
      var nome = document.getElementById("cargo-nome").value.trim();
      var original = document.getElementById("cargo-original").value.trim();
      var payload = {
        tipo: tipo,
        cargo: nome,
        cargo_original: original
      };
      if (tipo === "FUNCAO") {
        payload.funcao = nome;
        payload.funcao_original = original;
      } else if (tipo === "HABILITACAO") {
        var inputHabDesc = document.getElementById("hab-descricao");
        var checkHabValidade = document.getElementById("hab-exige-validade");
        payload.habilitacao = nome;
        payload.habilitacao_original = original;
        payload.descricao = inputHabDesc ? inputHabDesc.value.trim() : "";
        payload.exige_validade = checkHabValidade ? checkHabValidade.checked : true;
      }

      SF.api.post("/api/cargos/salvar/", payload)
        .then(function () {
          if (modalBs) {
            modalBs.hide();
          }
          carregarCargos();
        })
        .catch(function (erro) {
          alert(erro.message);
        });
    });
  }

  carregarCargos();
})();
