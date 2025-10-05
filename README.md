EndoFlix - Video Player

EndoFlix é um player de vídeos web robusto, construído com Flask e Bootstrap, para organizar e reproduzir arquivos de vídeo de forma prática e dinâmica. Escaneie pastas, crie playlists, salve sessões, randomize vídeos com shuffle (individual ou automático) e aproveite um layout com 4 players simultâneos, tudo integrado com PostgreSQL para gerenciamento de dados.

Funcionalidades

Escaneamento de Pastas: Carrega vídeos (.mp4, .mkv, .mov, .divx, .webm, .mpg, .avi) de qualquer diretório (ex.: X:\Tiktok).
Playlists: Crie, salve e carregue playlists diretamente no banco PostgreSQL.
Sessões: Salve e restaure sessões com os vídeos em reprodução.

Shuffle Inteligente:
Shuffle geral (4 vídeos aleatórios).
Shuffles individuais por player.
Auto Shuffle com intervalo configurável.
Prioriza vídeos não reproduzidos.

Drag-and-Drop: Arraste vídeos da lista para os players.
Interface Moderna:
Layout com 4 players em grade 2x2.
Barra lateral ajustável para playlists/sessões.
Filtros por nome e ordenação (A-Z, data).

Ultra Mode: Dashboard analítico com estatísticas em tempo real, gráficos de uso de playlists, tipos de arquivo, timeline de sessões e tabela de vídeos mais reproduzidos. Exportação de relatórios em CSV.
Sistema de Autenticação: Login e gerenciamento de usuários.
Processamento de Vídeos Cross-Platform: Usando python-ffmpeg para extração de metadados e processamento.
Cabeçalho Comum: Design consistente de cabeçalho em toda a aplicação.
Player de Vídeo Dedicado: Página dedicada para reprodução de vídeos individuais.
Operações em Lote: Execute ações em vários vídeos de uma vez, como adicionar/remover favoritos, remover de playlists.

Botão de Pânico: Abre um site aleatório (ex.: Google, YouTube) em caso de emergência.
Logs Detalhados: Debug facilitado com logs no backend e frontend.

Tecnologias
Backend: Flask, Python, psycopg2 (PostgreSQL)
Frontend: Bootstrap 5, JavaScript, HTML/CSS
Banco de Dados: PostgreSQL
Outros: Git para versionamento

Requisitos
Python 3.8+
PostgreSQL (com usuário postgres, senha admin)
Git
Navegador moderno (Chrome, Firefox, Edge)

Instalação
Clone o repositório:
git clone https://github.com/lscheffel/EndoFlix.git
cd EndoFlix


Configure o ambiente virtual (opcional, mas recomendado):
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows


Instale as dependências:
pip install flask psycopg2-binary


Configure o PostgreSQL:

Crie o banco videos:CREATE DATABASE videos;


Conecte-se ao banco:psql -U postgres -d videos


Crie as tabelas:CREATE TABLE endoflix_playlist (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    files TEXT[] NOT NULL
);

CREATE TABLE endoflix_session (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    videos TEXT[] NOT NULL
);


Verifique as credenciais: usuário postgres, senha admin, host localhost, porta 5432. Ajuste em main.py se necessário.


Estrutura do projeto:

EndoFlix/
├── main.py                    # Backend Flask principal
├── config.py                  # Configurações da aplicação
├── auth.py                    # Sistema de autenticação
├── db.py                      # Conexão e operações do banco de dados
├── models.py                  # Modelos de dados
├── utils.py                   # Utilitários diversos
├── file_processor.py          # Processamento de arquivos de vídeo
├── cache.py                   # Sistema de cache com Redis
├── limiter.py                 # Controle de taxa de requisições
├── blueprints/                # Módulos da aplicação
│   ├── __init__.py
│   ├── main.py                # Rotas principais
│   ├── auth.py                # Autenticação
│   ├── analytics.py           # Analytics e Ultra Mode
│   ├── favorites.py           # Favoritos
│   ├── playlists.py           # Playlists
│   ├── scan.py                # Escaneamento
│   ├── sessions.py            # Sessões
│   └── video.py               # Vídeo
├── services/                  # Serviços
│   ├── playlist_service.py
│   └── ultra_control_service.py
├── Static/                    # Arquivos estáticos
│   ├── favicon.ico
│   ├── js/
│   │   ├── header.js
│   │   └── ultra/
│   │       ├── app.js
│   │       ├── controls.js
│   │       ├── dashboard.js
│   │       └── websocket.js
│   └── keymap.js
├── Templates/                 # Templates HTML
│   ├── base.html
│   ├── header.html
│   ├── login.html
│   ├── player.html
│   ├── ultra.html
│   └── keymaps.html
├── tests/                     # Testes
├── logs/                      # Logs da aplicação
├── monitoring/                # Monitoramento
│   └── prometheus.yml
├── scripts/                   # Scripts auxiliares
│   └── init.sql
├── transcode/                 # Transcodificação
└── videos/                    # Vídeos (opcional)


Rode o servidor:
python main.py

Acesse http://localhost:5000 no navegador.


Uso

Carregar vídeos:

Insira o caminho da pasta (ex.: X:\Tiktok) no campo "Caminho da pasta".
Clique em "Carregar Pasta" para listar os vídeos.


Gerenciar playlists:

Após carregar vídeos, clique em "Save" para criar uma playlist.
Insira um nome e salve. A playlist aparece no dropdown "Selecionar Playlist".


Gerenciar sessões:

Arraste vídeos para os players ou use "Shuffle".
Clique em "Save Session" para salvar a sessão atual.
Use "Remove Session" para deletar uma sessão do dropdown "Selecionar Sessão".


Shuffle:

Clique em "Shuffle" para 4 vídeos aleatórios.
Use "Shuffle 1", "Shuffle 2", etc., para shuffles individuais.
Ative "Auto Shuffle" e ajuste o intervalo (em segundos).


Debug:

Verifique logs no terminal (backend) e no console do navegador (F12 > Console).
Exemplo de logs:
Backend: Playlist 'MinhaPlaylist' salva com 59 arquivos.
Frontend: Salvando sessão: 2025-05-11T04-37-34_Sem Playlist com 4 vídeos.





Estrutura do Projeto
EndoFlix/
├── main.py               # Backend Flask principal
├── config.py             # Configurações
├── auth.py               # Autenticação
├── db.py                 # Banco de dados
├── models.py             # Modelos
├── utils.py              # Utilitários
├── file_processor.py     # Processamento de vídeos
├── cache.py              # Cache Redis
├── limiter.py            # Rate limiting
├── blueprints/           # Módulos
│   ├── __init__.py
│   ├── main.py
│   ├── auth.py
│   ├── analytics.py
│   ├── favorites.py
│   ├── playlists.py
│   ├── scan.py
│   ├── sessions.py
│   └── video.py
├── services/             # Serviços
│   ├── playlist_service.py
│   └── ultra_control_service.py
├── Static/               # Estáticos
│   ├── js/
│   └── favicon.ico
├── Templates/            # Templates
│   ├── base.html
│   ├── header.html
│   ├── login.html
│   ├── player.html
│   ├── ultra.html
│   └── keymaps.html
├── tests/                # Testes
├── logs/                 # Logs
├── monitoring/           # Monitoramento
├── scripts/              # Scripts
├── transcode/            # Transcodificação
└── videos/               # Vídeos (opcional)

Versões

v5.1.0 (2025-10-05):
Adicionado Ultra Mode com analytics em tempo real.
Sistema de autenticação completo.
Processamento de vídeos cross-platform com python-ffmpeg.
Cabeçalho comum em todas as páginas.
Player de vídeo dedicado.
Operações em lote para gerenciamento de vídeos.
Removidas referências a thumbnails descontinuadas.

v5.0.0 (2025-10-03):
Sistema completo de autenticação e segurança.
Sistema de favoritos para vídeos.
Analytics e monitoramento avançado.
Containerização com Docker e docker-compose.
Arquitetura modular com blueprints.
Melhorias significativas de performance e segurança.
Pydantic para validação de dados.
Sistema de logs estruturado em JSON.
Integração com Redis para cache.
CI/CD com GitHub Actions.

v3.0.0 (2025-05-11):
Refatoração completa: removeu JSON, implementou PostgreSQL.
Corrigido gerenciamento de playlists e sessões.
Shuffles individuais e auto shuffle.
Logs detalhados.

v2.0.0:
Correções de layout e suporte a codecs (H.264).



Contribuição

Fork o repositório.
Crie uma branch (git checkout -b feature/nova-funcionalidade).
Commit suas mudanças (git commit -m "Adiciona nova funcionalidade").
Push para a branch (git push origin feature/nova-funcionalidade).
Abra um Pull Request.

Licença
MIT License. Veja LICENSE para detalhes.
Contato

GitHub: lscheffel
Issues: Crie uma issue para bugs ou sugestões.


Feito com 💪 por lscheffel. Bora rodar uns vídeos!
