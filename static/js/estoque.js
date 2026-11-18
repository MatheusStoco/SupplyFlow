/* =====================================================================
   SupplyFlow — Controle de Estoque e Reposição de Totens
   ---------------------------------------------------------------------
   Exibe saldos por totem/produto e registra entradas via /api/estoque/.
   ===================================================================== */

(function () {
  var escapar = SF.escapar;
  var corpo = document.getElementById("tabela-estoque-corpo");
  var modalEl = document.getElementById("modal-repor");
  var modalBs = modalEl ? new bootstrap.Modal(modalEl) : null;
  var form = document.getElementById("form-repor");
  var estoqueCache = [];

  function criarLinhaEstoqueHtml(itemEstoque, podeRepor) {
    var badgeStatus = '<span class="badge bg-success-subtle text-success border border-success-subtle">Normal</span>';
    if (itemEstoque.status_estoque === "critico") {
      badgeStatus = '<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle">Estoque Baixo</span>';
    } else if (itemEstoque.status_estoque === "zerado") {
      badgeStatus = '<span class="badge bg-danger-subtle text-danger border border-danger-subtle">Esgotado</span>';
    }

    var htmlAcao = "—";
    if (podeRepor) {
      htmlAcao =
        '<button type="button" class="btn btn-sm btn-outline-primary btn-abrir-repor" data-id="' + escapar(itemEstoque.id) + '"' +
                ' aria-label="Registrar entrada de ' + escapar(itemEstoque.produto_nome) + '">' +
          '<i class="bi bi-box-arrow-in-down" aria-hidden="true"></i> Entrada' +
        "</button>";
    }

    return (
      "<tr>" +
        '<td><span class="badge bg-light text-dark border">' + escapar(itemEstoque.totem_codigo) + '</span> <span class="small text-muted d-block">' + escapar(itemEstoque.totem_nome) + "</span></td>" +
        "<td><strong>" + escapar(itemEstoque.produto_nome) + '</strong> <span class="small text-muted d-block">SKU: ' + escapar(itemEstoque.produto_sku) + "</span></td>" +
        "<td>" + escapar(itemEstoque.categoria) + "</td>" +
        '<td><strong class="fs-6">' + escapar(itemEstoque.quantidade_disponivel) + "</strong> un.</td>" +
        "<td>" + escapar(itemEstoque.quantidade_reservada) + " un.</td>" +
        "<td>" + escapar(itemEstoque.quantidade_livre) + " un.</td>" +
        "<td>" + escapar(itemEstoque.quantidade_minima) + " un.</td>" +
        '<td><span class="numero">' + escapar(itemEstoque.lote) + "</span></td>" +
        "<td>" + badgeStatus + "</td>" +
        '<td class="text-end">' + htmlAcao + "</td>" +
      "</tr>"
    );
  }

  function carregarEstoque() {
    SF.api.get("/api/estoque/")
      .then(function (dados) {
        estoqueCache = dados.estoque || [];
        document.getElementById("res-total-estoque").textContent = dados.resumo.total_registros || 0;
        document.getElementById("res-critico-estoque").textContent = dados.resumo.itens_criticos || 0;
        document.getElementById("res-zerado-estoque").textContent = dados.resumo.itens_zerados || 0;

        if (estoqueCache.length === 0) {
          corpo.innerHTML = '<tr><td colspan="10" class="text-center py-4 text-muted">Nenhum estoque cadastrado.</td></tr>';
          return;
        }

        corpo.innerHTML = estoqueCache.map(function (itemEstoque) {
          return criarLinhaEstoqueHtml(itemEstoque, dados.pode_repor);
        }).join("");

        document.querySelectorAll(".btn-abrir-repor").forEach(function (botao) {
          botao.addEventListener("click", function () {
            var item = estoqueCache.find(function (registro) {
              return registro.id === botao.dataset.id;
            });
            if (!item) {
              return;
            }
            document.getElementById("repor-id").value = item.id;
            document.getElementById("repor-prod-nome").textContent = item.produto_nome + " (SKU: " + item.produto_sku + ")";
            document.getElementById("repor-totem-nome").textContent = item.totem_nome + " (" + item.totem_codigo + ") · Lote atual: " + item.lote;
            document.getElementById("repor-qtd").value = "10";
            document.getElementById("repor-lote").value = "";
            document.getElementById("repor-obs").value = "";
            if (modalBs) {
              modalBs.show();
            }
          });
        });
      })
      .catch(function (erro) {
        corpo.innerHTML =
          '<tr><td colspan="10" class="text-center py-4 text-danger">' +
            "Falha ao carregar saldos de estoque: " + escapar(erro.message) +
          "</td></tr>";
      });
  }

  var btnRecarregar = document.getElementById("btn-recarregar-estoque");
  if (btnRecarregar) {
    btnRecarregar.addEventListener("click", carregarEstoque);
  }

  if (form) {
    form.addEventListener("submit", function (evento) {
      evento.preventDefault();
      var payload = {
        estoque_id: document.getElementById("repor-id").value,
        quantidade: document.getElementById("repor-qtd").value,
        lote: document.getElementById("repor-lote").value.trim(),
        observacao: document.getElementById("repor-obs").value.trim()
      };

      SF.api.post("/api/estoque/repor/", payload)
        .then(function () {
          if (modalBs) {
            modalBs.hide();
          }
          carregarEstoque();
        })
        .catch(function (erro) {
          alert(erro.message);
        });
    });
  }

  carregarEstoque();
})();
