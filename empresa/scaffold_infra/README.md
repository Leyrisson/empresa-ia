# Camada de adaptadores multi-fabricante

Todo produto desta fábrica fala com equipamentos através desta camada. O app
**nunca** chama a API de um fabricante direto.

## Como usar

```python
from dispositivos import carregar_inventario, fabricar

for ativo in carregar_inventario("inventario.json"):
    dev = fabricar(ativo)
    print(dev.coletar())          # inventário/estado
    cfg = dev.backup_config()     # config ANTES de mudar
    print(dev.mudar({             # aplica com backup + rollback automático
        "tipo": "adicionar_rota",
        "destino": "10.20.0.0/16",
        "gateway": "10.0.0.254",
    }))
```

## Modo SIMULADO (sem equipamento)

O inventário padrão aponta tudo para o fabricante `simulado`:

```bash
python3 -c "from dispositivos import *; \
d=fabricar(carregar_inventario('inventario.json')[0]); print(d.coletar())"
```

Assim você desenvolve e testa o app inteiro sem nenhum gear.

## Ligar no equipamento REAL

1. Crie as variáveis de ambiente com as credenciais (**nunca** no código):
   ```bash
   export FW_EDGE_SENHA='...'      # API key do Palo Alto, token do FortiGate
   export SW_CORE_SENHA='...'
   ```
2. Edite `inventario.json` trocando `"fabricante": "simulado"` por
   `paloalto` | `fortigate` | `mikrotik` e o `host`/`porta` reais.
3. Nada no app muda — a fábrica `fabricar()` escolhe o adaptador.

## Fabricantes suportados

| fabricante | via | credencial |
|---|---|---|
| `paloalto` | PAN-OS XML API | API key (`env_senha`) |
| `fortigate` | FortiOS REST `/api/v2` | API token (`env_senha`) |
| `mikrotik` | RouterOS REST `/rest` | usuário/senha (`usuario` + `env_senha`) |
| `simulado` | em memória | — |

## Contrato (`dispositivos/base.py`)

- `conectar()` — abre sessão
- `coletar()` — inventário/estado
- `backup_config()` — configuração atual (obrigatório antes de aplicar)
- `aplicar(mudanca)` — aplica uma mudança
- `mudar(mudanca)` — backup + aplicar + **rollback** automático em falha
- `saude()` — latência, CPU, memória, uptime

Certificados auto-assinados são aceitos de propósito (equipamentos de rede
costumam usá-los). Decida isso conscientemente ao ligar no gear real.
