/* =====================================================================
   SupplyFlow — Gestão de Setores e Centros de Custo
   ---------------------------------------------------------------------
   Lista, cadastra, edita e ativa/inativa setores via /api/setores/.
   ===================================================================== */

(function () {
  var escapar = SF.escapar;
  var corpo = document.getElementById("tabela-setores-corpo");
  var modalEl = document.getElementById("modal-setor");
  var modalBs = modalEl ? new bootstrap.Modal(modalEl) : null;
  var form = document.getElementById("form-setor");
  var setoresCache = [];

  function criarLinhaSetorHtml(setor) {
    var badgeStatus = '<span class="badge bg-danger-subtle text-danger border border-danger-subtle">Inativo</span>';
    var corBotaoAlternar = "success";
    var rotuloAlternar = "Ativar";
    var iconeAlternar = "check-circle";

    if (setor.ativo) {
      badgeStatus = '<span class="badge bg-success-subtle text-success border border-success-subtle">Ativo</span>';
      corBotaoAlternar = "danger";
      rotuloAlternar = "Inativar";
      iconeAlternar = "slash-circle";
    }

    var htmlAcoes = "—";
    if (SF.sessao.pode("pessoas")) {
      htmlAcoes =
        '<button type="button" class="btn btn-sm btn-outline-secondary me-1 btn-edit-setor" data-id="' + escapar(setor.id) + '"' +
                ' aria-label="Editar ' + escapar(setor.nome) + '">' +
          '<i class="bi bi-pencil" aria-hidden="true"></i>' +
        "</button>" +
        '<button type="button" class="btn btn-sm btn-outline-' + corBotaoAlternar + ' btn-toggle-setor" data-id="' + escapar(setor.id) + '"' +
                ' aria-label="' + rotuloAlternar + " " + escapar(setor.nome) + '">' +
          '<i class="bi bi-' + iconeAlternar + '" aria-hidden="true"></i>' +
        "</button>";
    }

    return (
      "<tr>" +
        "<td><strong>" + escapar(setor.nome) + "</strong></td>" +
        '<td><span class="numero">' + escapar(setor.centro_custo) + "</span></td>" +
        '<td><i class="bi bi-people text-muted me-1" aria-hidden="true"></i> ' + escapar(setor.total_funcionarios) + " colaboradores</td>" +
        "<td>" + badgeStatus + "</td>" +
        '<td class="text-end text-nowrap">' + htmlAcoes + "</td>" +
      "</tr>"
    );
  }

  function carregarSetores() {
    SF.api.get("/api/setores/")
      .then(function (dados) {
        setoresCache = dados.setores || [];
        if (setoresCache.length === 0) {
          corpo.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">Nenhum setor cadastrado.</td></tr>';
          return;
        }
        corpo.innerHTML = setoresCache.map(criarLinhaSetorHtml).join("");

        document.querySelectorAll(".btn-edit-setor").forEach(function (botao) {
          botao.addEventListener("click", function () {
            var setor = setoresCache.find(function (item) {
              return item.id === botao.dataset.id;
            });
            if (!setor) {
              return;
            }
            document.getElementById("modalSetorTitulo").textContent = "Editar Setor";
            document.getElementById("setor-id").value = setor.id;
            document.getElementById("setor-nome").value = setor.nome;
            document.getElementById("setor-cc").value = (setor.centro_custo === "—") ? "" : setor.centro_custo;
            if (modalBs) {
              modalBs.show();
            }
          });
        });

        document.querySelectorAll(".btn-toggle-setor").forEach(function (botao) {
          botao.addEventListener("click", function () {
            SF.api.post("/api/setores/" + encodeURIComponent(botao.dataset.id) + "/toggle/")
              .then(function () {
                carregarSetores();
              })
              .catch(function (erro) {
                alert(erro.message);
              });
          });
        });
      })
      .catch(function (erro) {
        corpo.innerHTML =
          '<tr><td colspan="5" class="text-center py-4 text-danger">' +
            "Falha ao carregar setores: " + escapar(erro.message) +
          "</td></tr>";
      });
  }

  var btnNovo = document.getElementById("btn-novo-setor");
  if (btnNovo && !SF.sessao.pode("pessoas")) {
    btnNovo.classList.add("d-none");
  }
  if (btnNovo) {
    btnNovo.addEventListener("click", function () {
      form.reset();
      document.getElementById("modalSetorTitulo").textContent = "Novo Setor";
      document.getElementById("setor-id").value = "";
      if (modalBs) {
        modalBs.show();
      }
    });
  }

  if (form) {
    form.addEventListener("submit", function (evento) {
      evento.preventDefault();
      var payload = {
        id: document.getElementById("setor-id").value || null,
        nome: document.getElementById("setor-nome").value.trim(),
        centro_custo: document.getElementById("setor-cc").value.trim()
      };
      SF.api.post("/api/setores/salvar/", payload)
        .then(function (resposta) {
          if (!resposta.sucesso) {
            throw new Error(resposta.erro || "Falha ao salvar");
          }
          if (modalBs) {
            modalBs.hide();
          }
          carregarSetores();
        })
        .catch(function (erro) {
          alert(erro.message);
        });
    });
  }

  carregarSetores();
})();
