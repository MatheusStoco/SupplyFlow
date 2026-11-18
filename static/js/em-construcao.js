/* =====================================================================
   SupplyFlow — Tela Provisória ("Em construção")
   ===================================================================== */

(function () {
  var titulo = document.getElementById("titulo-tela");
  if (titulo && SF.paginaAtual && SF.paginaAtual.rotulo) {
    titulo.textContent = SF.paginaAtual.rotulo + " em construção";
  }
})();
