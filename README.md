# Empresa IA — fábrica autônoma de software

Uma "empresa" de agentes de IA que trabalha **em segundo plano** na sua máquina
para criar sistemas **web, Android e iOS** com potencial de lucro. Tem um
**gerente** e **17 setores** (pesquisa, produto, web designer, especialistas,
auditoria, financeiro, banco de dados, dev web, web developer, front-end,
back-end, python, android, iOS, QA, growth e gerência). Você vê cada setor
**trabalhando em sua sala no escritório** e, no celular, pode **pedir o
escritório pelo Telegram** (resumo + foto).

- Sem dependências externas de Python (só stdlib).
- Usa o **ollama** local para os agentes e o **opencode** para escrever o código
  de verdade dos apps.
- Roda como serviço **systemd de usuário** com prioridade baixa (`nice`, I/O
  `idle`), então não atrapalha o uso normal do PC.

## Como acessar

Dashboard: **http://127.0.0.1:8770**

## Destaques

- **Escritório vivo**: uma **sala por equipe** (20 salas), com mesas, cadeiras,
  sala de reunião e estantes. A vista **2D** é o padrão (leve, rola em qualquer
  máquina); há uma **vista 3D** opcional em Three.js. Os agentes se movimentam
  pelas salas e as **reuniões de setor** acontecem em tempo real (pauta → ata).
- **Telegram**: do celular você consulta a fábrica — `/fabrica` (resumo),
  `/print` (foto ao vivo do escritório), `/projetos`, `/reuniao <pauta>`,
  `/pausar`, `/retomar`, `/relatorio`, `/ideia <texto>`. A foto é renderizada no
  servidor com Pillow (`/api/print/escritorio.png`), sem abrir navegador.
- **Painel de ideias** (aba 💡 Ideias): você adiciona o produto que quer e o
  gerente tira da **fila do dono** antes de o LLM inventar algo novo.
- **Relatório diário** no banco, no Obsidian (`EmpresaIA/`) e no seu Telegram
  (automático às 18h ou pelo botão "Relatório agora").
- **Contrato "de verdade" por produto**: cada build compila (`py_compile`),
  é checado por boot HTTP, recebe `iniciar.sh`/`instalar.sh` (systemd),
  `Dockerfile`+`docker-compose.yml` (p/ vender para cliente) e documentação
  completa (`docs/INSTALACAO`, `USO`, `VENDEDOR`) — tudo registrado no banco.
- **Agentes especialistas**: cada setor tem um manual de conhecimento
  (`conhecimento/<setor>.md`) que entra no prompt de sistema do agente.

## Como funciona (o fluxo)

```
    Gerente (Aurélio)
        │  cria produto / despacha estágio / aprova relatório
        ▼
 Pesquisa → Produto → Web Designer → Banco de Dados → Dev → QA →
  ideia     spec      visual          arquitetura       build  teste
   Auditoria → Back-End → Front-End → Python → Especialista →
    revisão     backend    frontend    automação   consultoria
        ▼
   Growth → Financeiro      (mercado → monetização)
    preço    receita
        ▲                                   │
        └──────────── relatórios ───────────┘
```

O estágio `build` é roteado pelo tipo do produto: **web** → Dev Web,
**Android** → Desenvolvimento Android, **iOS** → iOS (Apple).

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
| `EMPRESA_MODELO_PLANEJADOR` | `qwen2.5:1.5b` | gerência, pesquisa, produto, design, auditoria, growth, financeiro |
| `EMPRESA_MODELO_CODIGO` | `qwen2.5-coder:1.5b` | dev web/android/iOS, backend, front-end, banco de dados, python e QA |
| `EMPRESA_MODO_BUILD` | `opencode` | `opencode` (código real) ou `llm` |
| `EMPRESA_INTENSIDADE` | `baixa` | intervalo entre ciclos (20/8/3 s) |
| `EMPRESA_MAX_PRODUTOS_ATIVOS` | `3` | quantos produtos em paralelo |
| `EMPRESA_MAX_BUILDS_DIA` | `6` | teto de builds com opencode por dia |
| `EMPRESA_META_MRR` | `10000` | meta de receita recorrente (R$) |
| `EMPRESA_HORA_RELATORIO` | `18` | hora do relatório diário (local) |
| `EMPRESA_OBSIDIAN` | `~/Obsidian/EmpresaIA` | onde escrever relatórios/resumos |
| `EMPRESA_PORTA` | `8770` | porta do dashboard |

> **Importante sobre desempenho:** nesta máquina (GTX 950, 2 GB de VRAM), modelos
> 7B rodam 95% na CPU a ~1,5 tok/s. Os modelos **1.5B** rodam a ~6 tok/s e
> passam quase despercebidos. Por isso o padrão são os 1.5B.

## Onde ficam as coisas

```
empresa-ia/
├── empresa/            # código Python (stdlib)
│   ├── config.py       # configuração
│   ├── db.py           # SQLite: setores, produtos, tarefas, ideias, office
│   ├── conhecimento.py # manuais de especialidade por setor
│   ├── empacotar.py    # compilar/rodar/instalar/documentar cada produto
│   ├── obsidian.py     # notas-resumo + relatórios no vault Obsidian
│   ├── relatorio.py    # relatório diário → Telegram + Obsidian
│   ├── print.py        # render PNG do escritório (foto p/ Telegram)
│   ├── llm.py          # ollama/localai + braço opencode
│   ├── setores.py      # organograma (17 setores) e pipeline (15 estágios)
│   ├── agentes.py      # gerente + funcionários
│   ├── reuniao.py      # reuniões de setor (pauta → ata)
│   ├── orquestrador.py # loop em segundo plano
│   └── dashboard.py    # servidor HTTP + API
├── conhecimento/       # manuais-mestres de cada setor
├── static/three.min.js # motor 3D (Three.js local)
├── templates/escritorio.html   # a tela do escritório (2D + 3D + abas)
├── produtos/<slug>/            # os apps e documentos gerados
└── var/                        # banco, logs, arquivo PAUSA
```

## Privacidade

Tudo roda local. Nada é publicado. Se algum dia quiser publicar no portfólio,
vale a regra do `~/.config/opencode/AGENTS.md` (sanear + pedir antes).
