/* =====================================================================
   SupplyFlow — Ficha de Fornecimento de EPI, Histórico Funcional e
   Termo de Nada Consta do Funcionário (RF-43)
   ---------------------------------------------------------------------
   Exibe o histórico individual de entregas de EPI de um colaborador,
   Cargo (RH), Função (SST), Habilitações/NRs com validade, grade de
   tamanhos (Calçado, Luva, Vestimenta), histórico funcional e
   declaração formal de Nada Consta de EPI para desligamento/auditoria.
   ===================================================================== */

(function () {
  var escapar = SF.escapar;
  var parametrosUrl = new URLSearchParams(window.location.search);
  var idFuncionario = parametrosUrl.get("id") || "";
  var exibirNadaConstaInicial = parametrosUrl.get("nada_consta") === "1";
  var checkboxMostrarTodos = document.getElementById("mostrar-todos");
  var btnNadaConsta = document.getElementById("btn-nada-consta");
  var secaoNadaConsta = document.getElementById("secao-nada-consta");
  var corpoNadaConsta = document.getElementById("corpo-nada-consta");
  var btnConfigEmpresa = document.getElementById("btn-config-empresa");
  var dadosCarregados = null;

  function formatarSetorFuncionario(funcionario) {
    if (!funcionario.setor) {
      return "—";
    }
    if (funcionario.centro_custo) {
      return funcionario.setor + " (" + funcionario.centro_custo + ")";
    }
    return funcionario.setor;
  }

  function obterTamanhosFuncionario(funcionario) {
    var tam = (funcionario && funcionario.tamanhos) || {};
    return {
      calcado: tam.calcado || (funcionario && funcionario.tamanho_calcado) || "",
      luva: tam.luva || (funcionario && funcionario.tamanho_luva) || "",
      vestimenta: tam.vestimenta || (funcionario && funcionario.tamanho_vestimenta) || ""
    };
  }

  function formatarHabilitacoesFichaHtml(funcionario) {
    var habs = (funcionario && funcionario.habilitacoes) || [];
    if (!Array.isArray(habs) || habs.length === 0) {
      return "—";
    }
    return habs.map(function (h) {
      var nome = typeof h === "string" ? h : (h.nome || h.habilitacao || "");
      var validade = (typeof h === "object" && h) ? (h.validade || "") : "";
      var vencida = Boolean(typeof h === "object" && h && h.vencida);
      if (!nome) {
        return "";
      }
      if (vencida) {
        return (
          '<span class="badge bg-danger-subtle text-danger border border-danger-subtle me-1">' +
            '<i class="bi bi-exclamation-triangle-fill me-1" aria-hidden="true"></i>' +
            escapar(nome) + (validade ? " (val. " + escapar(validade) + " — VENCIDA)" : " (VENCIDA)") +
          "</span>"
        );
      }
      return (
        '<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle me-1">' +
          '<i class="bi bi-shield-check me-1" aria-hidden="true"></i>' +
          escapar(nome) + (validade ? " (val. " + escapar(validade) + ")" : "") +
        "</span>"
      );
    }).join(" ");
  }

  var ROTULOS_EVENTO_FUNCIONAL = {
    ADMISSAO: "Admissão",
    MUDANCA_FUNCAO: "Mudança de Função",
    DESLIGAMENTO: "Desligamento",
    REATIVACAO: "Reativação",
    RH_METADADOS_ATUALIZADOS: "Atualização Cadastral"
  };

  function criarLinhaHistoricoFuncionalHtml(item) {
    var dataTxt = item.data || item.criado_em || item.registrado_em || "—";
    var chaveAcao = item.evento || item.tipo_rotulo || item.tipo || item.acao || "";
    var eventoTxt = ROTULOS_EVENTO_FUNCIONAL[chaveAcao] || chaveAcao || "Movimentação funcional";

    var cargoAnterior = item.cargo_anterior || item.de_cargo || "";
    var cargoNovo = item.cargo_novo || item.para_cargo || item.cargo || "";
    var htmlCargo = escapar(cargoNovo || cargoAnterior || "—");
    if (cargoAnterior && cargoNovo && cargoAnterior.toLowerCase() !== cargoNovo.toLowerCase()) {
      htmlCargo =
        '<span class="text-muted text-decoration-line-through me-1">' + escapar(cargoAnterior) + "</span>" +
        '<i class="bi bi-arrow-right mx-1 text-secondary" aria-hidden="true"></i>' +
        "<strong>" + escapar(cargoNovo) + "</strong>";
    }

    var funcaoAnterior = item.funcao_anterior || "";
    var funcaoNovo = item.funcao_novo || item.funcao || "";
    if (funcaoAnterior || funcaoNovo) {
      var htmlFuncao = escapar(funcaoNovo || funcaoAnterior);
      if (funcaoAnterior && funcaoNovo && funcaoAnterior.toLowerCase() !== funcaoNovo.toLowerCase()) {
        htmlFuncao =
          '<span class="text-muted text-decoration-line-through me-1">' + escapar(funcaoAnterior) + "</span>" +
          '<i class="bi bi-arrow-right mx-1 text-secondary" aria-hidden="true"></i>' +
          "<strong>" + escapar(funcaoNovo) + "</strong>";
      }
      htmlCargo += '<div class="small text-secondary mt-1">Função (SST): ' + htmlFuncao + "</div>";
    }

    var setorAnterior = item.setor_anterior || item.de_setor || "";
    var setorNovo = item.setor_novo || item.para_setor || item.setor || "";
    var htmlSetor = escapar(setorNovo || setorAnterior || "—");
    if (setorAnterior && setorNovo && setorAnterior.toLowerCase() !== setorNovo.toLowerCase()) {
      htmlSetor =
        '<span class="text-muted text-decoration-line-through me-1">' + escapar(setorAnterior) + "</span>" +
        '<i class="bi bi-arrow-right mx-1 text-secondary" aria-hidden="true"></i>' +
        "<strong>" + escapar(setorNovo) + "</strong>";
    }

    var obs = item.observacao || item.motivo || item.descricao || "";
    /* Limpa descrições legadas redundantes como "Mudança funcional: X → X" */
    var mRedundante = /^Mudança funcional:\s*(.+?)\s*→\s*\1$/i.exec(obs.trim());
    if (mRedundante) {
      obs = "Atualização de função/setor";
    }
    var resp = item.responsavel || item.registrado_por || item.usuario || "";
    var htmlObs = obs ? escapar(obs) : "—";
    if (resp) {
      htmlObs += '<span class="small text-muted d-block">Por: ' + escapar(resp) + "</span>";
    }

    return (
      "<tr>" +
        '<td class="text-nowrap">' + escapar(dataTxt) + "</td>" +
        '<td class="text-nowrap"><span class="badge bg-light text-dark border">' + escapar(eventoTxt) + "</span></td>" +
        "<td>" + htmlCargo + "</td>" +
        "<td>" + htmlSetor + "</td>" +
        "<td>" + htmlObs + "</td>" +
      "</tr>"
    );
  }

  function renderizarHistoricoFuncional(dados) {
    var corpoHistorico = document.getElementById("corpo-historico-funcional");
    if (!corpoHistorico) {
      return;
    }
    var lista = dados.historico_funcional || [];
    if (!Array.isArray(lista) || lista.length === 0) {
      corpoHistorico.innerHTML =
        '<tr><td colspan="5" class="tabela-solicitacoes__vazio">Nenhum evento de transição ou histórico funcional registrado.</td></tr>';
      return;
    }
    corpoHistorico.innerHTML = lista.map(criarLinhaHistoricoFuncionalHtml).join("");
  }

  function renderizarTermoNadaConsta(dados) {
    if (!corpoNadaConsta) {
      return;
    }
    var funcionario = dados.funcionario || {};
    var nadaConsta = dados.nada_consta || {};
    var emitidaEm = dados.emitida_em || "";

    var itensPendentes = [];
    if (Array.isArray(nadaConsta.pendentes)) {
      itensPendentes = nadaConsta.pendentes;
    } else if (Array.isArray(nadaConsta.devolucoes_pendentes)) {
      itensPendentes = nadaConsta.devolucoes_pendentes;
    } else if (Array.isArray(nadaConsta.epis_pendentes)) {
      itensPendentes = nadaConsta.epis_pendentes;
    }

    var qtdPendentes = typeof nadaConsta.total_pendentes === "number"
      ? nadaConsta.total_pendentes
      : (typeof nadaConsta.devolucoes_pendentes === "number"
          ? nadaConsta.devolucoes_pendentes
          : itensPendentes.length);

    var possuiPendencias = Boolean(
      nadaConsta.possui_pendencias ||
      (nadaConsta.nada_consta_apto === false) ||
      (nadaConsta.apto === false) ||
      (nadaConsta.liberado === false) ||
      qtdPendentes > 0
    );

    var bannerStatusHtml = "";
    if (possuiPendencias) {
      bannerStatusHtml =
        '<div class="alert alert-warning border mb-3">' +
          '<div class="fw-bold mb-1"><i class="bi bi-exclamation-triangle-fill me-1" aria-hidden="true"></i>Pendência de Devolução de EPI Constatada</div>' +
          '<div class="small">' +
            "O colaborador <strong>" + escapar(funcionario.nome || "") + "</strong> (Matrícula <strong>" + escapar(funcionario.matricula || "") + "</strong>) " +
            "possui <strong>" + escapar(String(qtdPendentes || itensPendentes.length || 1)) + "</strong> registro(s) com devolução obrigatória pendente no almoxarifado." +
          "</div>" +
        "</div>";
    } else {
      bannerStatusHtml =
        '<div class="alert alert-success border mb-3">' +
          '<div class="fw-bold mb-1"><i class="bi bi-patch-check-fill me-1" aria-hidden="true"></i>NADA CONSTA — Situação Regular de Devolução de EPIs</div>' +
          '<div class="small">' +
            "Declaramos, para fins de desligamento, transferência ou auditoria interna, que o(a) colaborador(a) " +
            "<strong>" + escapar(funcionario.nome || "") + "</strong>" +
            (funcionario.cpf ? (", CPF <strong>" + escapar(funcionario.cpf) + "</strong>") : "") +
            ", matrícula <strong>" + escapar(funcionario.matricula || "") + "</strong>, " +
            "cargo <strong>" + escapar(funcionario.cargo || "—") + "</strong>, lotado(a) no setor <strong>" + escapar(formatarSetorFuncionario(funcionario)) + "</strong>, " +
            "<strong>não possui pendências obrigatórias de devolução de Equipamentos de Proteção Individual (EPI)</strong> registradas no SupplyFlow até " + escapar(emitidaEm) + "." +
          "</div>" +
        "</div>";
    }

    var listaPendentesHtml = "";
    if (itensPendentes.length > 0) {
      listaPendentesHtml =
        '<div class="mb-3">' +
          '<div class="small fw-bold text-secondary mb-1">Itens pendentes de devolução / baixa:</div>' +
          '<ul class="small mb-0">' +
            itensPendentes.map(function (item) {
              var prod = item.produto || item.produto_nome || item.nome || "EPI";
              var sol = item.solicitacao || item.codigo || "";
              var dt = item.data || item.data_entrega || "";
              return "<li><strong>" + escapar(prod) + "</strong>" +
                (sol ? " — Solicitação " + escapar(sol) : "") +
                (dt ? " (" + escapar(dt) + ")" : "") +
                "</li>";
            }).join("") +
          "</ul>" +
        "</div>";
    }

    var assinaturasHtml =
      '<div class="row g-4 pt-3 mt-2 border-top text-center small">' +
        '<div class="col-12 col-md-6">' +
          '<div class="border-top border-dark pt-2 mt-4 mx-3">' +
            "<strong>" + escapar(funcionario.nome || "Colaborador") + "</strong><br>" +
            '<span class="text-muted">Matrícula: ' + escapar(funcionario.matricula || "—") +
            (funcionario.cpf ? (" · CPF: " + escapar(funcionario.cpf)) : "") + "</span>" +
          "</div>" +
        "</div>" +
        '<div class="col-12 col-md-6">' +
          '<div class="border-top border-dark pt-2 mt-4 mx-3">' +
            "<strong>Responsável Almoxarifado / SESMT / RH</strong><br>" +
            '<span class="text-muted">Emitido em ' + escapar(emitidaEm) + "</span>" +
          "</div>" +
        "</div>" +
      "</div>";

    corpoNadaConsta.innerHTML = bannerStatusHtml + listaPendentesHtml + assinaturasHtml;
  }

  function atualizarAvisoConformidadeNR6(dados) {
    var avisoEl = document.getElementById("aviso-conformidade-nr6");
    if (!avisoEl || !dados) return;
    var emp = dados.empresa || {};
    var func = dados.funcionario || {};
    var pendencias = [];
    if (!emp.cnpj) pendencias.push("CNPJ da empresa");
    if (!emp.endereco) pendencias.push("Endereço do estabelecimento");
    if (!func.cpf) pendencias.push("CPF do colaborador");

    if (pendencias.length === 0) {
      avisoEl.classList.add("d-none");
      avisoEl.innerHTML = "";
      return;
    }
    avisoEl.innerHTML =
      '<i class="bi bi-exclamation-triangle-fill me-1" aria-hidden="true"></i>' +
      "<strong>Pendências para validade plena em fiscalização NR-6:</strong> preencha " +
      escapar(pendencias.join(", ")) +
      " (em <em>Configurações</em> e no cadastro do colaborador) antes de emitir o PDF oficial.";
    avisoEl.classList.remove("d-none");
  }

  function renderizarCabecalhoNR6(dados) {
    var el = document.getElementById("ficha-nr6-cabecalho");
    if (!el) { return; }
    var emp = (dados && dados.empresa) || {};
    var razao = emp.razao_social || "Não informado";
    var cnpj = emp.cnpj || "Não informado";
    var estab = emp.estabelecimento || "—";
    var end = [emp.endereco, emp.cidade, emp.cep ? "CEP " + emp.cep : ""].filter(Boolean).join(" — ") || "Não informado";
    el.innerHTML =
      '<div class="ficha-nr6-cabecalho__topo">' +
        '<div>' +
          '<div class="ficha-nr6-cabecalho__titulo">FICHA DE CONTROLE E FORNECIMENTO DE EPI — NR-6</div>' +
          '<div class="ficha-nr6-cabecalho__sub">NR-6 (Portaria MTP nº 2.175/2022, itens 6.5.1 e 6.5.1.1) · Autenticação Eletrônica: Lei nº 14.063/2020</div>' +
        '</div>' +
        '<div class="ficha-nr6-cabecalho__emissao">Emissão: ' + escapar((dados && dados.emitida_em) || "") + '</div>' +
      '</div>' +
      '<div class="ficha-nr6-cabecalho__grid">' +
        '<div><strong>Empregador:</strong> ' + escapar(razao) + '</div>' +
        '<div><strong>CNPJ:</strong> ' + escapar(cnpj) + '</div>' +
        '<div><strong>Estabelecimento:</strong> ' + escapar(estab) + '</div>' +
        '<div><strong>Endereço:</strong> ' + escapar(end) + '</div>' +
      '</div>';
    atualizarAvisoConformidadeNR6(dados);
  }

  function renderizarRodapeNR6(dados) {
    var el = document.getElementById("ficha-nr6-rodape");
    if (!el) { return; }
    var emp = (dados && dados.empresa) || {};
    var func = (dados && dados.funcionario) || {};
    var emitidaEm = (dados && dados.emitida_em) || "";
    var localData = emp.cidade
      ? (emp.cidade + ", emitida em " + emitidaEm)
      : ("Emitida em " + emitidaEm);
    var identColab = "Matrícula: " + (func.matricula || "—") + (func.cpf ? (" · CPF: " + func.cpf) : "");
    el.innerHTML =
      '<div class="ficha-nr6-rodape__local">' + escapar(localData) + '</div>' +
      '<div class="ficha-nr6-rodape__assinaturas">' +
        '<div class="ficha-nr6-rodape__bloco">' +
          '<div class="ficha-nr6-rodape__linha"></div>' +
          '<strong>' + escapar(func.nome || "Colaborador") + '</strong>' +
          '<span>' + escapar(identColab) + ' · Assinatura do Colaborador</span>' +
        '</div>' +
        '<div class="ficha-nr6-rodape__bloco">' +
          '<div class="ficha-nr6-rodape__linha"></div>' +
          '<strong>Responsável pelo Almoxarifado / SESMT</strong>' +
          '<span>Assinatura e Carimbo</span>' +
        '</div>' +
      '</div>';
  }

  function criarLinhaEntregaFichaHtml(entrega) {
    var htmlDevolucao = "—";
    if (entrega.devolvido_em) {
      htmlDevolucao =
        escapar(entrega.devolvido_em) +
        '<span class="small text-muted d-block">' + escapar(entrega.condicao_devolucao) + "</span>";
    }

    var htmlComprovacao = "";
    if (entrega.autenticacao_pin) {
      var detalheHash = entrega.hash_autenticacao ? (" · #" + escapar(entrega.hash_autenticacao)) : "";
      htmlComprovacao =
        '<span class="d-block fw-semibold">Autenticado via PIN</span>' +
        '<span class="ficha-nr6-selo-hash">' + escapar(entrega.solicitacao || "") + detalheHash + "</span>";
    } else {
      htmlComprovacao = '<span class="ficha-nr6-rubrica">Rubrica: ____________</span>';
    }

    return (
      "<tr>" +
        '<td class="text-nowrap">' + escapar(entrega.data_hora || entrega.data) + "</td>" +
        "<td>" +
          escapar(entrega.produto) +
          '<span class="small text-muted d-block text-nowrap">' + escapar(entrega.solicitacao) + "</span>" +
        "</td>" +
        '<td class="text-nowrap">' + escapar(entrega.ca || "—") + "</td>" +
        '<td class="text-nowrap">' + escapar(entrega.lote || "—") + "</td>" +
        '<td class="text-nowrap">' + escapar(entrega.quantidade) + "</td>" +
        "<td>" + escapar(entrega.motivo) + "</td>" +
        "<td>" + escapar(entrega.almoxarife || "—") + "</td>" +
        '<td class="text-nowrap">' + htmlDevolucao + "</td>" +
        '<td class="solo-impressao-celula ficha-nr6-comprovacao">' + htmlComprovacao + "</td>" +
      "</tr>"
    );
  }

  function carregar() {
    var incluirConsumiveis = checkboxMostrarTodos.checked;
    var sufixoQuery = incluirConsumiveis ? "&todos=1" : "";
    var queryApi = incluirConsumiveis ? "todos=1" : "";
    var baseEndpoint = "/api/funcionarios/" + encodeURIComponent(idFuncionario) + "/ficha/";

    document.getElementById("btn-csv").href = baseEndpoint + "?formato=csv" + sufixoQuery;

    SF.api.get(baseEndpoint + "?" + queryApi)
      .then(function (dados) {
        var funcionario = dados.funcionario;
        var tamanhos = obterTamanhosFuncionario(funcionario);
        document.title = "Ficha de EPI — " + funcionario.nome + " · SupplyFlow";
        document.getElementById("ficha-emissao").textContent =
          "Registro individual das entregas de EPI (RF-43). Emitida em " + dados.emitida_em + ".";

        var paresDadosFuncionario = [
          ["Nome", escapar(funcionario.nome)],
          ["CPF", escapar(funcionario.cpf || "Não informado")],
          ["Matrícula", escapar(funcionario.matricula)],
          ["Admissão", escapar(funcionario.data_admissao || "—")],
          ["Cargo (RH)", escapar(funcionario.cargo || "—")],
          ["Função (SST)", escapar(funcionario.funcao || "—")],
          ["Habilitações / NRs", formatarHabilitacoesFichaHtml(funcionario)],
          ["Setor", escapar(formatarSetorFuncionario(funcionario))],
          ["Situação", escapar(funcionario.ativo ? "Ativo" : "Inativo")],
          ["Calçado", escapar(tamanhos.calcado || "—")],
          ["Luva", escapar(tamanhos.luva || "—")],
          ["Vestimenta", escapar(tamanhos.vestimenta || "—")]
        ];

        document.getElementById("dados-funcionario").innerHTML = paresDadosFuncionario.map(function (par) {
          return "<div><dt>" + escapar(par[0]) + "</dt><dd>" + par[1] + "</dd></div>";
        }).join("");

        dadosCarregados = dados;
        if (btnConfigEmpresa) {
          btnConfigEmpresa.classList.toggle("d-none", !dados.pode_editar_empresa);
        }
        renderizarCabecalhoNR6(dados);
        renderizarRodapeNR6(dados);
        renderizarHistoricoFuncional(dados);
        renderizarTermoNadaConsta(dados);

        if (exibirNadaConstaInicial && secaoNadaConsta) {
          secaoNadaConsta.classList.remove("d-none");
        }

        var listaEntregas = dados.entregas || [];
        var corpoFicha = document.getElementById("corpo-ficha");
        if (listaEntregas.length === 0) {
          corpoFicha.innerHTML = '<tr><td colspan="8" class="tabela-solicitacoes__vazio">Nenhuma entrega registrada.</td></tr>';
          return;
        }
        corpoFicha.innerHTML = listaEntregas.map(criarLinhaEntregaFichaHtml).join("");
      })
      .catch(function (erro) {
        var caixaErro = document.getElementById("erro-ficha");
        if (erro.status === 404) {
          caixaErro.textContent = "Funcionário não encontrado. Volte à lista e abra a ficha por lá.";
        } else {
          caixaErro.textContent = erro.message;
        }
        caixaErro.classList.remove("d-none");
        document.getElementById("corpo-ficha").innerHTML = "";
        var corpoHistorico = document.getElementById("corpo-historico-funcional");
        if (corpoHistorico) {
          corpoHistorico.innerHTML = "";
        }
      });
  }

  if (btnNadaConsta && secaoNadaConsta) {
    btnNadaConsta.addEventListener("click", function () {
      secaoNadaConsta.classList.remove("d-none");
      secaoNadaConsta.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  document.querySelectorAll('[data-acao="imprimir"]').forEach(function (botao) {
    botao.addEventListener("click", function () {
      window.print();
    });
  });

  checkboxMostrarTodos.addEventListener("change", carregar);
  carregar();
})();
