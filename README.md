# My AI Office — fábrica autônoma de software de infraestrutura

Uma "empresa" de agentes de IA que trabalha **em segundo plano** na sua máquina
para projetar, construir e entregar **software de infraestrutura de TI** para
empresas — monitoramento de rede, observabilidade, gestão de mudanças (GMUD),
conformidade (ISO 27001 / CIS), automação de operação (AIOps) e afins. Tem um
**gerente** e **24 setores** (gerência, pesquisa, produto, web designer,
front-end, dev web, back-end, banco de dados, dados & BI, ML & IA, QA, auditoria,
plataforma, engenharia de redes, DevOps, AIOps, segurança & SOC, GMUD,
compliance, automação, especialistas, marketing, vendas B2B e financeiro). Você
vê cada setor **trabalhando na sua sala temática no escritório** e, no celular,
pode **pedir o escritório pelo Telegram** (resumo + foto).

- **Núcleo sem dependências externas de Python** (só stdlib). A **foto** pelo
  Telegram (`/api/print/escritorio.png`) usa **Pillow** — único extra opcional,
  carregado só nessa rota; sem ele o resto funciona igual.
- Usa o **ollama** local para os agentes e o **opencode** para escrever o código
  de verdade dos produtos.
- Roda como serviço **systemd de usuário** com prioridade baixa (`nice`, I/O
  `idle`), então não atrapalha o uso normal do PC.

## Como acessar

Dashboard: **http://127.0.0.1:8770**

## Destaques

- **Escritório vivo (3D padrão)**: uma **sala temática por setor** (racks, NOC,
  SOC, mesas de reunião, copa, recepção), renderizada em **Three.js** local. Dê
  **duplo-clique** numa sala para a câmera **voar até ela**. Há também a vista
  **2D** opcional (leve, rola em qualquer máquina). Os agentes se movimentam e as
  **reuniões de setor** acontecem em tempo real (pauta → ata).
- **Camada de adaptadores multi-fabricante**: todo produto de infra nasce com a
  pasta `dispositivos/` — um **simulador local** + adaptadores para **Palo Alto,
  FortiGate e MikroTik** (mesmo contrato). O produto roda **100% no modo
  simulado** (sem hardware) e, para operar gear real, é só preencher o inventário
  e as credenciais (`.env`). Backup de config e **rollback à prova de falha** já
  vêm prontos.
- **Telegram**: do celular você consulta a fábrica — `/fabrica` (resumo),
  `/print` (foto ao vivo do escritório), `/projetos`, `/reuniao <pauta>`,
  `/pausar`, `/retomar`, `/relatorio`, `/ideia <texto>`. A foto é renderizada no
  servidor com Pillow (`/api/print/escritorio.png`), sem abrir navegador.
- **Painel de ideias** (aba 💡 Ideias): você adiciona o produto que quer e o
  gerente tira da **fila do dono** antes de inventar algo novo.
- **Motor de ideias travado no domínio**: por padrão a fábrica **inventa**
  produtos, mas **só dentro do domínio** de infraestrutura de TI B2B — uma trava
  por palavras-âncora rejeita ideias fora de escopo (app de consumo, rede social,
  e-commerce…). Para construir **apenas** o que você pede, use
  `EMPRESA_SO_IDEIAS_DO_DONO=1`.
- **Relatório diário** no banco, no Obsidian (`EmpresaIA/`) e no seu Telegram
  (automático às 18h ou pelo botão "Relatório agora").
- **Contrato "de verdade" por produto**: cada build compila (`py_compile`),
  é checado por boot HTTP, recebe `iniciar.sh`/`instalar.sh` (systemd),
  `Dockerfile`+`docker-compose.yml` (p/ vender para cliente) e documentação
  completa (`docs/INSTALACAO`, `USO`, `VENDEDOR`) — tudo registrado no banco.
- **A empresa conduz, o opencode executa**: o arquiteto-chefe (LLM local) quebra
  a construção em **3–5 tarefas** e o **opencode escreve o código uma tarefa por
  vez**; a empresa **verifica** (compila os `.py` **e** confere que a camada de
  adaptadores existe) e **manda corrigir** quando reprova. O opencode é ferramenta
  da fábrica, não a fábrica.
- **Só projetos reais (padrão)**: o produto **não passa do `build` enquanto não
  houver código de verdade** e, para **web, um app que abra** (ponto de entrada
  único `app.py`). O build tem uma etapa de **consolidação**: se o resultado
  vier como módulos soltos, o opencode integra tudo num só `app.py`; se ainda
  faltar, o produto **fica retido no `build`**. **Nenhum é marcado "lançado" no
  papel**. Com `EMPRESA_MAX_PRODUTOS_ATIVOS=1`, a fábrica trabalha **um produto
  por vez** (a sua ideia fura a fila quando há ideia pendente).
- **Monitor de build real** (`empresa monitorar`): avisa no **Telegram** e no PC
  quando o build termina com código, **sobe o app** e manda o link. O link fica
  salvo no produto e aparece no painel como **▶ Abrir** (aba Produtos); se o app
  ainda não estiver rodando, o botão **▶ Rodar** sobe e abre.
- **Cada produto vira um serviço systemd** (`empresa/servico.py`): quando o build
  fica pronto, a fábrica cria `empresa-produto-<slug>.service` (systemd de
  usuário) que roda `python3 app.py` na porta do produto, **reinicia sozinho** se
  cair (`Restart=on-failure`) e **sobe no boot** (`linger`). Assim o **▶ Abrir**
  aponta para algo que não morre. CLI: `python -m empresa servico`
  (`--todos`, `--listar` ou um `slug`); logs em
  `journalctl --user -u empresa-produto-<slug>`.
- **Agentes especialistas**: cada setor tem um manual de conhecimento
  (`conhecimento/<setor>.md`) que entra no prompt de sistema do agente.

## Como funciona (o fluxo)

```
    Gerente (Aurélio)
        │  cria produto / despacha estágio / aprova relatório
        ▼
 Pesquisa (ideia, validação) → Produto (spec, design) → Web Designer (visual) →
 Eng. de Redes (arquitetura) → Banco de Dados (esquema) → Dev Web (build) →
 Plataforma (deploy) → DevOps (pipeline) → QA (teste) → Auditoria (revisão) →
 Segurança (hardening) → GMUD (mudança) → Compliance (conformidade) →
 AIOps (observabilidade) → ML (anomalia) → Dados & BI (métricas) →
 Back-End → Front-End → Automação → Especialista (consultoria) →
 Marketing (posicionamento) → Vendas (monetização) → Financeiro (lançamento)
        ▲                                   │
        └──────────── relatórios ───────────┘
```

Pipeline de **25 estágios** (de `ideia` a `lancamento`); o estágio `build` é
roteado para **Dev Web** (os produtos de infra são web — painel/CLI com interface
web).

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
| `EMPRESA_MODELO_PLANEJADOR` | `qwen2.5:1.5b` | gerência, pesquisa, produto, design, auditoria, marketing, financeiro |
| `EMPRESA_MODELO_CODIGO` | `qwen2.5-coder:1.5b` | dev web, back-end, front-end, banco de dados, automação e QA |
| `EMPRESA_MODELO_IDEIA` | `llama3.1:latest` | inventar ideias de produto (travadas no domínio B2B) |
| `EMPRESA_MODO_BUILD` | `opencode` | `opencode` (código real) ou `llm` |
| `EMPRESA_INTENSIDADE` | `baixa` | intervalo entre ciclos (20/8/3 s) |
| `EMPRESA_MAX_PRODUTOS_ATIVOS` | `1` | produtos ativos ao mesmo tempo (1 = um por vez) |
| `EMPRESA_EXIGIR_CODIGO` | `1` | só avança do `build` (e só "lança") com código real |
| `EMPRESA_SO_IDEIAS_DO_DONO` | `0` | `1` = só as ideias do dono; `0` = inventa (dentro do domínio) |
| `EMPRESA_MAX_TAREFAS_BUILD` | `4` | em quantas tarefas a empresa quebra o build |
| `EMPRESA_TIMEOUT_TAREFA` | `600` | teto (s) por tarefa do opencode |
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
│   ├── config.py       # configuração + domínio de ideias
│   ├── db.py           # SQLite: setores, produtos, tarefas, ideias, office
│   ├── conhecimento.py # manuais de especialidade por setor
│   ├── scaffold_infra/ # camada de adaptadores multi-fabricante (copiada em cada build)
│   │   ├── dispositivos/  # base, simulador, paloalto, fortigate, routeros
│   │   ├── inventario.json
│   │   └── README.md
│   ├── empacotar.py    # compilar/rodar/instalar/documentar cada produto
│   ├── obsidian.py     # notas-resumo + relatórios no vault Obsidian
│   ├── relatorio.py    # relatório diário → Telegram + Obsidian
│   ├── print.py        # render PNG do escritório (foto p/ Telegram)
│   ├── llm.py          # ollama/localai + braço opencode
│   ├── setores.py      # organograma (24 setores), planta e pipeline (25 estágios)
│   ├── agentes.py      # gerente + funcionários + motor de ideias
│   ├── reuniao.py      # reuniões de setor (pauta → ata)
│   ├── orquestrador.py # loop em segundo plano
│   ├── monitor.py      # avisa (Telegram/PC) quando o build real termina
│   └── dashboard.py    # servidor HTTP + API
├── conhecimento/       # manuais-mestres de cada setor
├── static/three.min.js # motor 3D (Three.js local)
├── templates/escritorio.html   # a tela do escritório (3D + 2D + abas)
├── produtos/<slug>/            # os apps e documentos gerados
└── var/                        # banco, logs, arquivo PAUSA
```

## Privacidade

Tudo roda local. Nada é publicado. Se algum dia quiser publicar no portfólio,
vale a regra do `~/.config/opencode/AGENTS.md` (sanear + pedir antes).
