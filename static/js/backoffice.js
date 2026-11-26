/* =====================================================================
   SupplyFlow — Estrutura Comum do Backoffice (Barra Lateral e Topo)
   ---------------------------------------------------------------------
   Monta a barra lateral (#sidebar) e o topo (#topbar) em todas as páginas
   do backoffice, evitando repetir o mesmo HTML em cada arquivo.

   Como cada página informa onde está:
   - data-pagina="..." no <body> identifica o arquivo atual.
   - data-menu="..." (opcional) indica qual item do menu lateral deve
     ficar marcado como ativo (usado em subpáginas como Detalhe ou Ficha).
   - data-trilha="..." (opcional) define o texto exibido na trilha de
     navegação do topo e no título da aba do navegador.
   ===================================================================== */

(function () {
  var LINK_TOTEM = "/totem/";
  var CHAVE_TEMA = "sf_tema";

  /* ---------- Tema Visual (Escuro padrão / Claro opcional) ---------- */
  function lerTemaSalvo() {
    try {
      return localStorage.getItem(CHAVE_TEMA) === "claro" ? "claro" : "escuro";
    } catch (erro) {
      return "escuro";
    }
  }

  function aplicarTema(tema) {
    var temaNormalizado = tema === "claro" ? "claro" : "escuro";
    document.documentElement.setAttribute("data-tema", temaNormalizado);
    try {
      localStorage.setItem(CHAVE_TEMA, temaNormalizado);
    } catch (erro) {
      /* Ignora indisponibilidade de storage em modo restrito */
    }
    atualizarBotaoTema(temaNormalizado);
    return temaNormalizado;
  }

  function atualizarBotaoTema(tema) {
    var botao = document.getElementById("btn-alternar-tema");
    if (!botao) return;
    var ehClaro = tema === "claro";
    botao.setAttribute("aria-label", ehClaro ? "Alternar para tema escuro" : "Alternar para tema claro");
    botao.setAttribute("title", ehClaro ? "Alternar para tema escuro" : "Alternar para tema claro");
    botao.innerHTML = ehClaro
      ? '<i class="bi bi-moon-stars" aria-hidden="true"></i><span class="btn-tema__texto">Escuro</span>'
      : '<i class="bi bi-sun" aria-hidden="true"></i><span class="btn-tema__texto">Claro</span>';
  }

  SF.tema = {
    atual: lerTemaSalvo,
    aplicar: aplicarTema,
    alternar: function () {
      return aplicarTema(lerTemaSalvo() === "claro" ? "escuro" : "claro");
    }
  };

  /* Aplica imediatamente ao carregar para evitar flash de tema incorreto */
  aplicarTema(lerTemaSalvo());

  /* Símbolo SupplyFlow: o S é o caminho do material (ponto = estoque, seta = entrega) */
  var ICONE_MARCA =
    '<svg viewBox="6.5 7 51 51" fill="none">' +
      '<path d="M43 13H27a9 9 0 0 0 0 18h10a9 9 0 0 1 0 18H25" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<path d="M26 41.5L15.5 49 26 56.5z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>' +
      '<circle cx="43" cy="13" r="5.5" fill="currentColor"/>' +
    "</svg>";

  /* ---------- Funções Utilitárias ---------- */

  /* Escapa caracteres especiais (&, <, >, ", ') para evitar XSS ao montar HTML */
  function escapar(texto) {
    var divTemporaria = document.createElement("div");
    if (texto == null) {
      divTemporaria.textContent = "";
    } else {
      divTemporaria.textContent = String(texto);
    }
    return divTemporaria.innerHTML;
  }
  SF.escapar = escapar;

  /* ---------- Helpers Compartilhados de UI (SF.ui) ---------- */
  SF.ui = {
    /* Exibe um alerta Bootstrap padrão e move o foco quando o container é focável */
    mostrarAviso: function (elementoOuId, texto, tipo) {
      var el = typeof elementoOuId === "string"
        ? document.getElementById(elementoOuId)
        : elementoOuId;
      if (!el) return;
      el.className = "alert alert-" + (tipo || "info");
      el.textContent = texto;
      if (el.hasAttribute("tabindex")) {
        el.focus();
      }
    },

    /* Preenche um <select> com strings ou objetos de catálogo (Cargo, Função, NR),
       preservando um valor pré-existente fora do catálogo em edições legadas */
    preencherSelectCatalogo: function (selectEl, listaItens, placeholder, valorSelecionado, chaveProp) {
      if (!selectEl) return;
      var chave = chaveProp || "nome";
      var opcoes = ['<option value="">' + escapar(placeholder || "Selecione...") + "</option>"];
      var valorEncontrado = false;

      (listaItens || []).forEach(function (item) {
        var nome = typeof item === "string" ? item : (item[chave] || item.nome || "");
        if (!nome) return;
        var selecionado = Boolean(
          valorSelecionado && nome.toLowerCase() === String(valorSelecionado).toLowerCase()
        );
        if (selecionado) {
          valorEncontrado = true;
        }
        opcoes.push(
          '<option value="' + escapar(nome) + '"' + (selecionado ? " selected" : "") + ">" +
            escapar(nome) +
          "</option>"
        );
      });

      if (valorSelecionado && !valorEncontrado) {
        opcoes.push(
          '<option value="' + escapar(valorSelecionado) + '" selected>' +
            escapar(valorSelecionado) +
          "</option>"
        );
      }
      selectEl.innerHTML = opcoes.join("");
      if (valorSelecionado) {
        selectEl.value = valorSelecionado;
      }
    },

    /* Seleciona um valor em um <select>, inserindo a opção caso seja um valor legado */
    selecionarOuAdicionar: function (selectEl, valor) {
      if (!selectEl) return;
      if (valor) {
        var existe = Array.from(selectEl.options).some(function (opt) { return opt.value === valor; });
        if (!existe) {
          var opt = document.createElement("option");
          opt.value = valor;
          opt.textContent = valor;
          selectEl.appendChild(opt);
        }
      }
      selectEl.value = valor || "";
    }
  };

  /* Transforma um título como "Centros de custo" em um ID válido "centros-de-custo" */
  function converterParaIdHtml(texto) {
    return texto
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "");
  }

  /* Monta o endereço (href) de um item do menu */
  function obterLinkDoItem(item) {
    if (item.pagina) {
      return item.pagina + ".html";
    }
    return "em-construcao.html?p=" + encodeURIComponent(item.rotulo);
  }

  /* Verifica se o perfil do usuário pode ver determinado item do menu */
  function itemPermitido(usuario, item) {
    var acaoExigida = item.acao || "ver";
    if (!usuario || !Array.isArray(usuario.acoes)) {
      return acaoExigida === "ver";
    }
    return usuario.acoes.indexOf(acaoExigida) !== -1;
  }

  /* ---------- Descoberta da Página Aberta ---------- */
  var chavePagina = document.body.dataset.pagina;
  var chaveMenu = document.body.dataset.menu || chavePagina;
  var trilhaPropria = document.body.dataset.trilha || null;
  var rotuloAtual = null;
  var grupoAtual = null;

  if (chavePagina === "em-construcao") {
    var parametrosUrl = new URLSearchParams(window.location.search);
    rotuloAtual = parametrosUrl.get("p") || "Tela em construção";
  }

  SF.menu.forEach(function (entrada) {
    if (entrada.itens) {
      entrada.itens.forEach(function (subitem) {
        if (subitem.pagina === chaveMenu || subitem.rotulo === rotuloAtual) {
          rotuloAtual = subitem.rotulo;
          grupoAtual = entrada.grupo;
        }
      });
    } else if (entrada.pagina === chaveMenu || entrada.rotulo === rotuloAtual) {
      rotuloAtual = entrada.rotulo;
    }
  });

  SF.paginaAtual = {
    rotulo: rotuloAtual,
    grupo: grupoAtual,
    trilha: trilhaPropria
  };

  var tituloAba = trilhaPropria || rotuloAtual || "Backoffice";
  document.title = tituloAba + " · SupplyFlow";

  /* ---------- Construção da Barra Lateral ---------- */
  function criarHtmlLinkMenu(item, estaDentroDeGrupo) {
    var atributoAtivo = "";
    if (item.rotulo === rotuloAtual) {
      atributoAtivo = ' aria-current="page"';
    }

    var classeIcone = item.icone;
    if (estaDentroDeGrupo) {
      classeIcone = "bi-chevron-right";
    }

    return (
      "<li>" +
        '<a class="menu__link" href="' + obterLinkDoItem(item) + '"' + atributoAtivo + ">" +
          '<i class="bi ' + classeIcone + '" aria-hidden="true"></i>' +
          escapar(item.rotulo) +
        "</a>" +
      "</li>"
    );
  }

  function criarHtmlEntradaMenu(entrada, usuario) {
    /* Caso 1: Item simples (sem submenu) */
    if (!entrada.itens) {
      if (!itemPermitido(usuario, entrada)) {
        return "";
      }
      return criarHtmlLinkMenu(entrada, false);
    }

    /* Caso 2: Grupo expansível com subitens */
    var subitensVisiveis = entrada.itens.filter(function (subitem) {
      return itemPermitido(usuario, subitem);
    });

    if (subitensVisiveis.length === 0) {
      return "";
    }

    var idGrupoHtml = "grupo-" + converterParaIdHtml(entrada.grupo);
    var grupoAberto = entrada.grupo === grupoAtual;
    var htmlSubitens = subitensVisiveis.map(function (subitem) {
      return criarHtmlLinkMenu(subitem, true);
    }).join("");

    return (
      "<li>" +
        '<button class="menu__grupo' + (grupoAberto ? "" : " collapsed") + '" type="button" data-bs-toggle="collapse" data-bs-target="#' + idGrupoHtml + '"' +
                ' aria-expanded="' + (grupoAberto ? "true" : "false") + '" aria-controls="' + idGrupoHtml + '">' +
          '<i class="bi ' + entrada.icone + '" aria-hidden="true"></i>' +
          escapar(entrada.grupo) +
          '<i class="bi bi-chevron-up menu__seta" aria-hidden="true"></i>' +
        "</button>" +
        '<ul class="submenu collapse' + (grupoAberto ? " show" : "") + '" id="' + idGrupoHtml + '">' +
          htmlSubitens +
        "</ul>" +
      "</li>"
    );
  }

  function montarLateral(usuario) {
    var itensMenuHtml = SF.menu.map(function (entrada) {
      return criarHtmlEntradaMenu(entrada, usuario);
    }).join("");

    var textoAcessoRodape = "";
    if (usuario && usuario.acesso) {
      textoAcessoRodape = usuario.acesso;
    }

    document.getElementById("sidebar").innerHTML =
      '<header class="sidebar__cabecalho">' +
        '<a class="marca" href="visao-geral.html">' +
          '<span class="marca__icone" aria-hidden="true">' + ICONE_MARCA + "</span>" +
          '<span><span class="marca__nome">Supply<span class="marca__destaque">Flow</span></span><span class="marca__sub">Gestão de EPIs</span></span>' +
        "</a>" +
        '<button type="button" class="btn-close btn-close-white d-lg-none" data-bs-dismiss="offcanvas"' +
                ' data-bs-target="#sidebar" aria-label="Fechar menu"></button>' +
      "</header>" +
      '<nav class="sidebar__nav" aria-label="Menu principal">' +
        '<ul class="menu">' + itensMenuHtml + "</ul>" +
      "</nav>" +
      '<footer class="sidebar__rodape">' + escapar(textoAcessoRodape) + "</footer>";

    /* Garante que o item ativo fique visível na rolagem da barra lateral */
    var navLateral = document.querySelector(".sidebar__nav");
    var linkAtivo = navLateral.querySelector('[aria-current="page"]');
    if (linkAtivo) {
      navLateral.scrollTop = linkAtivo.offsetTop - navLateral.clientHeight / 2;
    }
  }

  /* ---------- Construção do Topo ---------- */
  function obterTextoTrilhaTopo() {
    if (trilhaPropria) {
      return escapar(trilhaPropria);
    }
    var prefixoGrupo = "";
    if (grupoAtual) {
      prefixoGrupo = escapar(grupoAtual) + " / ";
    }
    return prefixoGrupo + escapar(rotuloAtual || "");
  }

  /* Nome fantasia da empresa (Configurações) no início da trilha do topo */
  var nomeEmpresa = "";

  SF.atualizarNomeEmpresa = function (empresa) {
    nomeEmpresa = (empresa && empresa.configurada && (empresa.nome_fantasia || empresa.razao_social)) || "";
    var itemTrilha = document.getElementById("trilha-empresa");
    if (itemTrilha) {
      itemTrilha.textContent = nomeEmpresa || "Backoffice";
    }
  };

  function montarTopo(usuario) {
    var textoTrilha = obterTextoTrilhaTopo();
    var dadosUsuario = usuario || { nome: "", iniciais: "", perfil: "" };

    document.getElementById("topbar").innerHTML =
      '<button class="topbar__menu d-lg-none" type="button" data-bs-toggle="offcanvas" data-bs-target="#sidebar"' +
              ' aria-controls="sidebar" aria-label="Abrir menu">' +
        '<i class="bi bi-list" aria-hidden="true"></i>' +
      "</button>" +
      '<nav aria-label="Você está em">' +
        '<ol class="trilha">' +
          '<li id="trilha-empresa">' + escapar(nomeEmpresa || "Backoffice") + "</li>" +
          '<li aria-current="page">' + textoTrilha + "</li>" +
        "</ol>" +
      "</nav>" +
      '<div class="topbar__acoes">' +
        '<button class="btn-tema" type="button" id="btn-alternar-tema" aria-label="Alternar tema">' +
          '<i class="bi bi-sun" aria-hidden="true"></i><span class="btn-tema__texto">Claro</span>' +
        "</button>" +
        '<a class="topbar__totem" href="' + LINK_TOTEM + '" aria-label="Abrir autoatendimento">' +
          '<span class="topbar__totem-texto">Abrir autoatendimento →</span>' +
          '<i class="bi bi-tablet d-md-none" aria-hidden="true"></i>' +
        "</a>" +
        '<div class="perfil">' +
          '<span class="perfil__avatar" aria-hidden="true">' + escapar(dadosUsuario.iniciais) + "</span>" +
          '<span class="perfil__texto">' +
            '<span class="perfil__nome">' + escapar(dadosUsuario.nome) + "</span>" +
            '<span class="perfil__papel">' + escapar(dadosUsuario.perfil) + "</span>" +
          "</span>" +
        "</div>" +
        '<button class="btn-sair" type="button" id="btn-sair">' +
          '<i class="bi bi-box-arrow-right" aria-hidden="true"></i>' +
          '<span class="btn-sair__texto">Sair</span>' +
        "</button>" +
      "</div>";

    atualizarBotaoTema(lerTemaSalvo());
    document.getElementById("btn-alternar-tema").addEventListener("click", function () {
      SF.tema.alternar();
    });

    /* Botão Sair: encerra a sessão no servidor e redireciona para a tela de login */
    document.getElementById("btn-sair").addEventListener("click", function () {
      SF.sessao.encerrar().then(function () {
        window.location.href = "/";
      });
    });
  }

  function montarEstrutura(usuario) {
    montarLateral(usuario);
    montarTopo(usuario);
  }

  /* 1. Desenha imediatamente com a cópia local e 2. Confirma no servidor se houve mudança */
  var usuarioEmCache = SF.sessao.usuarioAtual();
  montarEstrutura(usuarioEmCache);

  SF.sessao.confirmar().then(function (usuarioDoServidor) {
    if (JSON.stringify(usuarioDoServidor) !== JSON.stringify(usuarioEmCache)) {
      montarEstrutura(usuarioDoServidor);
    }
  }).catch(function () {
    /* Em caso de 401 (sessão expirada), SF.api redireciona automaticamente ao login */
  });

  SF.api.get("/api/empresa/").then(function (dados) {
    SF.atualizarNomeEmpresa(dados.empresa);
  }).catch(function () {
    /* Sem os dados da empresa, o topo continua mostrando "Backoffice" */
  });
})();
