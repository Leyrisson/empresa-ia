# Empresa IA — fábrica autônoma de software

Uma "empresa" de agentes de IA que trabalha **em segundo plano** na sua máquina
para criar sistemas **web e Android** com potencial de lucro. Tem um **gerente**
e **setores** (pesquisa, produto, dev, QA, growth, financeiro). Você vê cada
setor **graficamente trabalhando em sua mesa virtual**, trocando mensagens com o
gerente, que responde e repassa demandas.

- Sem dependências externas de Python (só stdlib).
- Usa o **ollama** local para os agentes e o **opencode** para escrever o código
  de verdade dos apps.
- Roda como serviço **systemd de usuário** com prioridade baixa (`nice`, I/O
  `idle`), então não atrapalha o uso normal do PC.

## Como acessar

Dashboard: **http://127.0.0.1:8770**

## Como funciona (o fluxo)

```
    Gerente (Aurélio)
        │  cria produto / despacha estágio / aprova relatório
        ▼
 Pesquisa → Produto → Dev (Web/Android) → QA → Growth → Financeiro
   ideia     spec        build             teste  preço    receita
        ▲                                                   │
        └──────────────── relatórios ───────────────────────┘
```

Cada setor tem um funcionário-agente. O gerente cria um produto, despacha o
estágio atual para o setor responsável; o funcionário produz um **artefato em
disco** (pasta `produtos/<slug>/`), manda relatório ao gerente; o gerente aprova,
avança o estágio e despacha o próximo. Ao fim do pipeline o produto é marcado
como **lançado**.

O estágio `build` usa o `opencode run --auto` dentro da pasta do produto — ou
seja, o app é **escrito de verdade**, não só descrito.

## Comandos

```bash
./empresa.sh status       # resumo no terminal
./empresa.sh doutor       # checa ollama/opencode/modelos
./empresa.sh um-ciclo     # uma rodada (útil para testar)
./empresa.sh servir       # só o dashboard (bloqueante)
./empresa.sh trabalhar    # só o turno em segundo plano
./empresa.sh tudo         # dashboard + turno no mesmo processo
```

## Serviços (systemd de usuário)

```bash
systemctl --user status  empresa-ia-trabalhar
systemctl --user status  empresa-ia-dashboard
systemctl --user stop    empresa-ia-trabalhar     # parar o trabalho
systemctl --user start   empresa-ia-trabalhar     # retomar
systemctl --user disable --now empresa-ia-trabalhar  # tirar do boot
```

No dashboard dá para **⏸ Pausar / ▶ Retomar**, mudar a **intensidade** e a
**meta de MRR**. Pausar também funciona criando o arquivo `var/PAUSA`.

## Configuração (variáveis de ambiente, prefixo `EMPRESA_`)

| Variável | Padrão | Para quê |
|---|---|---|
| `EMPRESA_BACKEND` | `ollama` | `ollama`, `localai` ou `offline` |
| `EMPRESA_MODELO_PLANEJADOR` | `qwen2.5:1.5b` | gerente/pesquisa/produto/growth/financeiro |
| `EMPRESA_MODELO_CODIGO` | `qwen2.5-coder:1.5b` | QA e geração de código por texto |
| `EMPRESA_MODO_BUILD` | `opencode` | `opencode` (código real) ou `llm` |
| `EMPRESA_INTENSIDADE` | `baixa` | intervalo entre ciclos (20/8/3 s) |
| `EMPRESA_MAX_PRODUTOS_ATIVOS` | `3` | quantos produtos em paralelo |
| `EMPRESA_MAX_BUILDS_DIA` | `6` | teto de builds com opencode por dia |
| `EMPRESA_META_MRR` | `10000` | meta de receita recorrente (R$) |
| `EMPRESA_PORTA` | `8770` | porta do dashboard |

> **Importante sobre desempenho:** nesta máquina (GTX 950, 2 GB de VRAM), modelos
> 7B rodam 95% na CPU a ~1,5 tok/s. Os modelos **1.5B** rodam a ~6 tok/s e
> passam quase despercebidos. Por isso o padrão são os 1.5B.

## Onde ficam as coisas

```
empresa-ia/
├── empresa/            # código Python (stdlib)
│   ├── config.py       # configuração
│   ├── db.py           # SQLite: setores, produtos, tarefas, mensagens
│   ├── llm.py          # ollama/localai + braço opencode
│   ├── setores.py      # organograma e pipeline
│   ├── agentes.py      # gerente + funcionários
│   ├── orquestrador.py # loop em segundo plano
│   └── dashboard.py    # servidor HTTP + API
├── templates/escritorio.html   # a tela do escritório
├── produtos/<slug>/            # os apps e documentos gerados
└── var/                        # banco, logs, arquivo PAUSA
```

## Privacidade

Tudo roda local. Nada é publicado. Se algum dia quiser publicar no portfólio,
vale a regra do `~/.config/opencode/AGENTS.md` (sanear + pedir antes).
