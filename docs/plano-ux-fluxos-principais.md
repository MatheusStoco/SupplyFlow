# Plano Técnico de Evolução de UX — Fluxos Principais (SupplyFlow)

**Objetivo:** Servir como base sólida de continuidade para implementar melhorias de Experiência do Usuário (UX), velocidade operacional e segurança nos 3 fluxos centrais do sistema, preservando 100% da arquitetura e regras de negócio existentes.

---

## 1. Regras e Padrões Obrigatórios (Não Quebrar)

- **Zero migrations novas:** Não alterar `core/models.py` nem criar novas migrations em `core/migrations/`.
- **Separação estrita HTML / CSS / JS:** Zero `style="..."`, zero `<style>`, zero `<script>` inline e zero `onclick=` nos arquivos HTML/JS.
- **Identidade visual:** Tema **Industrial Moderno** (Dark Mode `#0b0f17` / `#121824` + Safety Orange `#f97316`, bordas `4px–6px`).
- **Semântica HTML5:** Manter `<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<footer>`, `<fieldset>` e hierarquia correta de headings (`h1` único, modais com `h2.modal-title`).
- **Helpers compartilhados:** Reutilizar `SF.escapar` e `SF.ui` (`mostrarAviso`, `preencherSelectCatalogo`, `selecionarOuAdicionar`) em `static/js/backoffice.js`.
- **Controle Git:** `1 etapa = 1 commit local` em Conventional Commits; **nunca executar `git push`** sem autorização explícita.

---

## 2. Estado Base do Repositório (Ponto de Partida)

- **Commit base:** `948e82f` (`style(funcionarios): alinhar campos, corrigir dark mode e melhorar UX do modal`)
- **Refatoração prévia concluída:**
  - `core/views/cadastros.py` modularizado em `funcionarios.py`, `produtos.py`, `organizacao.py`, `politicas.py` e `cargos.py`.
  - `core/servicos/elegibilidade.py`, `core/servicos/rh.py` e `core/views/relatorios.py` simplificados com helpers coesos.
  - Todo o frontend validado com `node --check` e zero estilos/scripts inline.

---

## 3. Especificação das Etapas de UX

### Etapa UX-1 — Fluxo de Solicitação no Totem (`totem/`)

**Arquivos alvo:**
- `totem/index.html`
- `static/js/totem.js`
- `static/css/totem.css`

**Endpoints consumidos (sem alterar contrato):**
- `POST /api/totem/identificar/`
- `POST /api/totem/login/`
- `POST /api/totem/trocar-pin/`
- `GET /api/totem/produtos/?totem_codigo=...`
- `POST /api/totem/solicitar/`
- `GET /api/totem/solicitacoes/`
- `POST /api/totem/solicitacoes/<id>/cancelar/`
- `POST /api/totem/sair/`

**Melhorias planejadas:**
1. **Continuar pedindo na mesma sessão:** No modal `#modal-sucesso`, adicionar botão **"Solicitar outro item"** (cancela o timer regressivo, fecha o modal e recarrega a vitrine mantendo o colaborador autenticado) ao lado de **"Concluir e sair (5s)"**.
2. **Confirmação antes de retirada regular + trava de duplo clique:** Ao clicar em `Solicitar retirada`, exibir modal/confirmação rápida com nome do produto e tamanho antes de disparar `POST /api/totem/solicitar/`, desabilitando o botão durante o envio.
3. **Substituir `alert()` e `confirm()` nativos:** Criar banner de aviso inline touch-friendly nos passos do Totem e confirmação visual no modal para cancelar pedido ou reiniciar sessão.
4. **Matrícula alfanumérica + entrada direta:** Aceitar letras e hífen no teclado físico (`keydown` em `#passo-matricula`), oferecer atalho/prefixo ou teclado compacto para matrículas com letras (ex.: `MAT-`) e reduzir o destaque do card inativo de RFID na tela inicial.
5. **Filtros rápidos na vitrine:** Chips no topo de `#passo-vitrine` (`Todos`, `Disponíveis`, `EPIs`, `Consumíveis`) + busca simples por nome do item.

**Commit sugerido:** `feat(totem): melhorar fluxo de solicitacao, confirmacao e feedback inline`

---

### Etapa UX-2 — Fluxo de Aprovação / Triagem (`backoffice/solicitacoes*`)

**Arquivos alvo:**
- `backoffice/solicitacoes.html`
- `static/js/solicitacoes.js`
- `backoffice/solicitacao.html`
- `static/js/solicitacao-detalhe.js`
- `static/css/supplyflow.css`

**Endpoints consumidos:**
- `GET /api/solicitacoes/`
- `GET /api/solicitacoes/<id>/`
- `POST /api/solicitacoes/<id>/decidir/`

**Melhorias planejadas:**
1. **Contadores nas abas + busca rápida na lista:** Exibir contagem em cada aba (`Excepcionais (N)`, `Aguardando análise (N)`, `Todas (N)`), selecionar automaticamente `Aguardando análise` ao abrir se houver pendências, e incluir busca instantânea por colaborador/código/produto.
2. **Continuidade na tela de detalhe:** Adicionar estado de carregamento (`spinner`) enquanto busca `/api/solicitacoes/<id>/`, e após gravar a decisão mostrar atalhos diretos: **"Próxima aguardando →"** (buscando a próxima pendente), **"Ir para Entregas"** (se aprovada) e **"Voltar à lista"**.
3. **Alinhamento entre checkbox de devolução e botões de decisão:** Ao marcar `#exigir-devolucao`, destacar visualmente `Aprovar com condição` e orientar o usuário de forma clara, evitando erro punitivo por clique reflexo.
4. **Adequação ao Dark Mode:** Substituir `<div class="alert alert-light border mb-0">` em `#decisao-tomada` por classe escura industrial coerente com o tema.

**Commit sugerido:** `feat(solicitacoes): agilizar triagem com contadores, busca e navegacao sequencial`

---

### Etapa UX-3 — Fluxo de Confirmação de Entrega (`backoffice/entregas*`)

**Arquivos alvo:**
- `backoffice/entregas.html`
- `static/js/entregas.js`
- `core/views/entregas.py` (apenas se precisar incluir campo já existente como `tamanho`/`ca` no JSON de pendentes, sem mudar schema)

**Endpoints consumidos:**
- `GET /api/entregas/`
- `POST /api/entregas/<id>/confirmar/`

**Melhorias planejadas:**
1. **Busca instantânea no balcão do almoxarifado:** Campo de busca rápida acima da tabela `Aguardando retirada` filtrando em tempo real por nome, matrícula, código da solicitação ou produto.
2. **Modal rápido de conferência física:** Em vez de dar baixa irreversível no estoque em 1 clique, abrir modal curto exibindo `Colaborador`, `Matrícula`, `Produto`, `Quantidade` e `Código`, com botão **"Confirmar entrega física"**.
3. **Clareza em bloqueios por devolução e dados de separação:** Exibir tamanho/CA quando disponíveis na fila pendente e deixar claro o motivo do bloqueio com atalho direto para devoluções.

**Commit sugerido:** `feat(entregas): adicionar busca no balcao e modal de conferencia antes da entrega`

---

## 4. Checklist Padrão de Validação Após Cada Etapa

1. `node --check static/js/*.js` sem erros.
2. Varredura confirmando `0` ocorrências de `style=`, `<style>`, `<script>` inline e `onclick=`.
3. `python manage.py test` (no ambiente virtual local do usuário) com todos os testes passando.
4. Teste manual no navegador com `Ctrl + F5` percorrendo o fluxo completo da etapa alterada.
