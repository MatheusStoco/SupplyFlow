/* =====================================================================
   SupplyFlow — Entregas (RF-40 a RF-42 · /api/entregas/)
   ---------------------------------------------------------------------
   O almoxarife confirma a retirada física do item aprovado; o servidor
   dá baixa na reserva de estoque e impede a entrega caso ainda exista
   uma devolução obrigatória pendente para aquela solicitação.
   ===================================================================== */

(function () {
  var escapar = SF.escapar;
  var aviso = document.getElementById("aviso-entregas");
  var inputBusca = document.getElementById("filtro-busca-entregas");
  var modalConfEl = document.getElementById("modal-confirmar-entrega");
  var bsModalConf = modalConfEl ? new bootstrap.Modal(modalConfEl) : null;
  var btnConfirmarModal = document.getElementById("btn-confirmar-entrega-ok");
  var pendentesCache = [];
  var podeEntregarAtual = false;
  var pendenciaSelecionada = null;

  function mostrarAviso(texto, tipo) {
    SF.ui.mostrarAviso(aviso, texto, tipo);
  }

  function criarLinhaTabelaVazia(quantidadeColunas, mensagem) {
    return '<tr><td colspan="' + quantidadeColunas + '" class="tabela-solicitacoes__vazio">' + escapar(mensagem) + "</td></tr>";
  }

  /* Monta a coluna de ação da tabela de entregas pendentes */
  function criarHtmlAcaoPendente(pendencia, podeEntregar) {
    if (!podeEntregar) {
      return "—";
    }
    if (pendencia.bloqueio) {
      return '<a class="btn btn-sm btn-outline-secondary" href="devolucoes.html" title="Registrar devolução obrigatória antes da entrega">Resolver devolução</a>';
    }
    return (
      '<button type="button" class="btn btn-sm btn-success" data-confirmar="' + escapar(pendencia.id) + '"' +
              ' aria-label="Conferir e confirmar entrega da solicitação ' + escapar(pendencia.codigo) + '">' +
        '<i class="bi bi-box-arrow-up" aria-hidden="true"></i> Confirmar entrega' +
      "</button>"
    );
  }

  function criarLinhaEntregaPendenteHtml(pendencia, podeEntregar) {
    var classeSelo = pendencia.bloqueio ? "selo--aguardando" : "selo--aprovado";
    var textoSelo = pendencia.bloqueio || pendencia.status_rotulo;
    var htmlAcao = criarHtmlAcaoPendente(pendencia, podeEntregar);

    var detalhesProduto = [];
    if (pendencia.tamanho) detalhesProduto.push("Tam. " + pendencia.tamanho);
    if (pendencia.ca) detalhesProduto.push("CA " + pendencia.ca);
    var htmlDetalhesProduto = detalhesProduto.length > 0
      ? '<br><span class="text-muted small">' + escapar(detalhesProduto.join(" · ")) + "</span>"
      : "";

    return (
      "<tr>" +
        '<td><a class="numero" href="solicitacao.html?id=' + encodeURIComponent(pendencia.id) + '">' + escapar(pendencia.codigo) + "</a></td>" +
        '<td class="text-nowrap">' + escapar(pendencia.data) + "</td>" +
        "<td>" +
          escapar(pendencia.colaborador) +
          '<br><span class="text-muted small">' + escapar(pendencia.matricula) + " · " + escapar(pendencia.setor) + "</span>" +
        "</td>" +
        "<td>" + escapar(pendencia.produto) + htmlDetalhesProduto + "</td>" +
        "<td>" + escapar(pendencia.quantidade) + "</td>" +
        '<td><span class="selo ' + classeSelo + '">' + escapar(textoSelo) + "</span></td>" +
        '<td class="tabela-solicitacoes__acao">' + htmlAcao + "</td>" +
      "</tr>"
    );
  }

  function criarLinhaEntregaConfirmadaHtml(entrega) {
    var textoSetor = escapar(entrega.setor);
    if (entrega.centro_custo && entrega.centro_custo !== "—") {
      textoSetor += " (" + escapar(entrega.centro_custo) + ")";
    }

    return (
      "<tr>" +
        '<td class="text-nowrap">' + escapar(entrega.data) + "</td>" +
        '<td><span class="numero">' + escapar(entrega.codigo) + "</span></td>" +
        "<td>" + escapar(entrega.colaborador) + "</td>" +
        "<td>" + textoSetor + "</td>" +
        "<td>" + escapar(entrega.produto) + "</td>" +
        "<td>" + escapar(entrega.quantidade) + "</td>" +
        "<td>" + escapar(entrega.ca) + "</td>" +
        "<td>" + escapar(entrega.lote) + "</td>" +
        "<td>" + escapar(entrega.almoxarife) + "</td>" +
      "</tr>"
    );
  }

  function renderizarPendentesFiltrados() {
    var corpoPendentes = document.getElementById("corpo-pendentes");
    var termo = inputBusca ? inputBusca.value.trim().toLowerCase() : "";
    var filtradas = pendentesCache.filter(function (p) {
      if (!termo) return true;
      var texto = [p.codigo, p.colaborador, p.matricula, p.setor, p.produto, p.ca].join(" ").toLowerCase();
      return texto.indexOf(termo) !== -1;
    });

    document.getElementById("meta-pendentes").textContent = termo
      ? (filtradas.length + " de " + pendentesCache.length + " pendente(s)")
      : (pendentesCache.length + " pendente(s)");

    if (filtradas.length === 0) {
      var msgVazia = termo
        ? "Nenhuma entrega pendente encontrada para “" + termo + "”."
        : "Nenhuma entrega aguardando retirada.";
      corpoPendentes.innerHTML = criarLinhaTabelaVazia(7, msgVazia);
      return;
    }

    corpoPendentes.innerHTML = filtradas.map(function (pendencia) {
      return criarLinhaEntregaPendenteHtml(pendencia, podeEntregarAtual);
    }).join("");
  }

  function carregar() {
    SF.api.get("/api/entregas/")
      .then(function (dados) {
        pendentesCache = dados.pendentes || [];
        podeEntregarAtual = Boolean(dados.pode_entregar);
        var listaConfirmadas = dados.entregas || [];

        renderizarPendentesFiltrados();

        var corpoConfirmadas = document.getElementById("corpo-confirmadas");
        if (listaConfirmadas.length === 0) {
          corpoConfirmadas.innerHTML = criarLinhaTabelaVazia(9, "Nenhuma entrega confirmada ainda.");
        } else {
          corpoConfirmadas.innerHTML = listaConfirmadas.map(criarLinhaEntregaConfirmadaHtml).join("");
        }
      })
      .catch(function (erro) {
        mostrarAviso(erro.message, "danger");
      });
  }

  function abrirModalConferenciaEntrega(pendencia) {
    pendenciaSelecionada = pendencia;
    if (!bsModalConf) {
      executarConfirmacaoEntrega(pendencia.id);
      return;
    }
    var pares = [
      ["Solicitação", pendencia.codigo],
      ["Colaborador", pendencia.colaborador + " (" + pendencia.matricula + ")"],
      ["Setor", pendencia.setor],
      ["Produto", pendencia.produto],
      ["Quantidade", pendencia.quantidade + " un."]
    ];
    if (pendencia.tamanho) pares.push(["Tamanho", pendencia.tamanho]);
    if (pendencia.ca) pares.push(["CA", pendencia.ca]);
    if (pendencia.totem) pares.push(["Totem", pendencia.totem]);

    document.getElementById("resumo-conferencia-entrega").innerHTML = pares.map(function (par) {
      return "<div><dt>" + escapar(par[0]) + "</dt><dd>" + escapar(par[1]) + "</dd></div>";
    }).join("");

    if (btnConfirmarModal) btnConfirmarModal.disabled = false;
    bsModalConf.show();
  }

  function executarConfirmacaoEntrega(idSolicitacao) {
    if (btnConfirmarModal) btnConfirmarModal.disabled = true;
    var urlConfirmar = "/api/entregas/" + encodeURIComponent(idSolicitacao) + "/confirmar/";

    SF.api.post(urlConfirmar)
      .then(function (resposta) {
        if (bsModalConf) bsModalConf.hide();
        mostrarAviso(resposta.mensagem, "success");
        carregar();
      })
      .catch(function (erro) {
        if (bsModalConf) bsModalConf.hide();
        mostrarAviso(erro.message, "danger");
      })
      .finally(function () {
        if (btnConfirmarModal) btnConfirmarModal.disabled = false;
      });
  }

  if (inputBusca) {
    inputBusca.addEventListener("input", renderizarPendentesFiltrados);
  }

  if (btnConfirmarModal) {
    btnConfirmarModal.addEventListener("click", function () {
      if (pendenciaSelecionada) {
        executarConfirmacaoEntrega(pendenciaSelecionada.id);
      }
    });
  }

  document.getElementById("corpo-pendentes").addEventListener("click", function (evento) {
    var botaoConfirmar = evento.target.closest("[data-confirmar]");
    if (!botaoConfirmar) {
      return;
    }
    var idAlvo = botaoConfirmar.dataset.confirmar;
    var pendencia = pendentesCache.find(function (item) { return item.id === idAlvo; });
    if (pendencia) {
      abrirModalConferenciaEntrega(pendencia);
    }
  });

  aviso.setAttribute("tabindex", "-1");
  carregar();
})();
