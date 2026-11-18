"""Fachada de compatibilidade para as APIs de cadastro, divididas por domínio.

As implementações agora vivem em módulos coesos e fáceis de navegar:
- `funcionarios.py`: colaboradores operacionais (Totem), importação CSV e usuários backoffice
- `produtos.py`: catálogo de EPIs e consumíveis
- `organizacao.py`: setores/centros de custo, fornecedores e dados da empresa empregadora
- `politicas.py`: regras de fornecimento (limites mensais e periodicidade)
- `cargos.py`: catálogo de cargos (RH), funções (SST) e habilitações/NRs
"""
from .cargos import *  # noqa: F401,F403
from .cargos import (  # noqa: F401
    _catalogo_cargos,
    _catalogo_funcoes,
    _catalogo_habilitacoes,
    _eh_prefixado_especial,
    _listar_catalogo_habilitacoes,
    _normalizar_cargo_catalogo,
    _normalizar_funcao_catalogo,
    _normalizar_habilitacao_catalogo,
    _registrar_evento_cargo,
    _registrar_evento_catalogo,
)
from .funcionarios import *  # noqa: F401,F403
from .funcionarios import (  # noqa: F401
    _extrair_tamanhos,
    _func_json,
    _gerar_matricula_administrativa,
)
from .organizacao import *  # noqa: F401,F403
from .politicas import *  # noqa: F401,F403
from .politicas import _regra_json  # noqa: F401
from .produtos import *  # noqa: F401,F403
from .produtos import _data_opcional, _produto_json  # noqa: F401
