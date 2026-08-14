# Lovify — MVP

Jogo para dois jogadores usando Flask + Flask-SocketIO.

## 1. Instalar

Python 3.10+ recomendado.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\\Scripts\\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Depois:

```bash
pip install -r requirements.txt
```

## 2. Rodar

```bash
python app.py
```

Abra:

```text
http://localhost:5000
```

Para testar dois jogadores, abra a página em duas abas/janelas.

## 3. IA com OpenRouter

A IA é opcional. Sem chave, o jogo usa perguntas locais.

Windows PowerShell:

```powershell
$env:OPENROUTER_API_KEY="SUA_CHAVE"
$env:OPENROUTER_MODEL="openai/gpt-4o-mini"
python app.py
```

Linux/macOS:

```bash
export OPENROUTER_API_KEY="SUA_CHAVE"
export OPENROUTER_MODEL="openai/gpt-4o-mini"
python app.py
```

A chave fica no backend e NÃO deve ser colocada no JavaScript do navegador.

## 4. Fluxo implementado

1. Jogador cria sala.
2. Backend gera código de 4 dígitos.
3. Segundo jogador entra pelo código.
4. Admin inicia.
5. Backend seleciona uma pergunta.
6. A pergunta é enviada por Socket.IO.
7. Os dois respondem.
8. Os dois tentam adivinhar a resposta do parceiro.
9. O backend calcula pontos.
10. Resultado aparece para os dois.
11. Admin inicia a próxima rodada.

## 5. Próximos upgrades recomendados

- Link compartilhável `/room/1234`.
- Melhor sistema de pontuação com IA para respostas semanticamente parecidas.
- Banco de dados SQLite/PostgreSQL.
- Autenticação por sessão.
- Reconexão automática.
- Contagem regressiva.
- Categorias de perguntas.
- Tela inicial mais bonita.
- Histórico de partidas.
- Deploy em Render/Railway/Fly.io.
