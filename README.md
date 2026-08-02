# Mega Brain

Interface local para usar modelos servidos pelo LM Studio em modo OpenAI-compatible, com foco em agente de engenharia de software e contexto compacto.

## Estado do app

O frontend concentra o fluxo principal do Mega Brain:

- Projetos e conversas organizados no navegador via armazenamento local.
- Roteamento `Auto` entre modelo rapido e modelo complexo por tipo de tarefa.
- Medidor de tokens estimados, janela e percentual usado.
- Skills enxutas ativadas por relevancia, no formato portatil `SKILL.md`.
- Leitura do workspace, preview de arquivos estruturados e scan de notas Markdown do Obsidian.
- Conexao GitHub por sessao, sem persistir o token no app.
- Loop visual Entender -> Construir -> Rechecar.

As referencias publicas usadas para os contratos de skills ficam em `skills.json`. O Mega Brain nao copia automaticamente repositorios de terceiros para dentro do prompt; ele mantem apenas instrucoes compactas e ativa o minimo necessario para preservar VRAM.

## Modelos e hardware

Com 16 GB de VRAM e 32 GB de RAM, use `Auto` como padrao. O roteador usa o modelo menor para leitura, respostas simples e tarefas de dados; tarefas de arquitetura, refatoracao e seguranca podem usar o modelo maior configurado por `MEGA_BRAIN_COMPLEX_MODEL`. Ajuste `MEGA_BRAIN_CONTEXT_WINDOW` se o modelo carregado tiver outra janela.

Para fontes externas, defina `MEGA_BRAIN_ALLOWED_ROOTS` com caminhos adicionais separados por `;` no Windows. Isso permite conectar um vault Obsidian sem liberar o computador inteiro.

## Uso via CLI

1. Abra o LM Studio.
2. Carregue o modelo desejado.
3. Inicie o servidor local em `Developer` / `Local Server`.
4. Confirme a URL do servidor, normalmente:

```powershell
http://localhost:1234/v1
```

5. No PowerShell, dentro desta pasta, rode:

```powershell
python .\cli\mega_brain.py "Explique o que e Mega Brain em 5 linhas"
```

Para conversar de forma interativa:

```powershell
python .\cli\mega_brain.py
```

Com outro modelo ou outra URL:

```powershell
$env:MEGA_BRAIN_BASE_URL="http://localhost:1234/v1"
$env:MEGA_BRAIN_MODEL="nome-do-modelo-no-lm-studio"
python .\cli\mega_brain.py
```

## Frontend local

Rode o servidor do Mega Brain nesta pasta:

```powershell
python .\server.py
```

Depois abra:

```text
http://localhost:4173/frontend/
```

O frontend usa `/api/chat` no mesmo servidor para evitar bloqueio de CORS do navegador.

## Desktop app and local voice

The Windows executable is built as `MegaBrain.exe`. The desktop launcher starts the local server and opens the frontend automatically.

Voice input uses Faster-Whisper locally with automatic language detection, including English and Brazilian Portuguese. Voice output uses Piper locally. Audio is processed by these endpoints and is never added to the LLM context; only the resulting transcript is sent to the model.

Install speech-to-text support:

```powershell
powershell -ExecutionPolicy Bypass -File .\voice_setup.ps1
```

Download Piper and one `en_US` voice plus one `pt_BR` voice from the Piper voice sources. Configure:

```powershell
$env:MEGA_BRAIN_PIPER_EN_VOICE="C:\path\to\en_US_voice.onnx"
$env:MEGA_BRAIN_PIPER_PT_VOICE="C:\path\to\pt_BR_voice.onnx"
python .\mega_brain_launcher.py
```

## Erro de grammar no LM Studio

O erro abaixo normalmente acontece quando algum cliente envia uma gramatica, JSON schema ou resposta estruturada em formato que o motor do modelo nao consegue interpretar:

```text
Engine protocol ngPredictTokens request returned 400:
Failed to initialize samplers: failed to parse grammar
```

Como corrigir:

1. Desative qualquer opcao de `grammar`, `response_format`, `json_schema`, `guided_json`, `guided_regex` ou structured output no cliente.
2. Reinicie o servidor local do LM Studio depois de trocar essas configuracoes.
3. Teste com uma chamada simples, sem schema:

```powershell
python .\cli\mega_brain.py "Responda apenas: ok"
```

Este projeto ja envia requisicoes simples por padrao e nao manda grammar para o LM Studio.

Se o CLI funcionar e o frontend antigo mostrar `Failed to fetch`, o problema era CORS. Use `python .\server.py`, nao `python -m http.server`.

## Perfil de agente e contexto

O comportamento principal fica em:

```text
agent_prompt.txt
```

Ele e curto de proposito para economizar VRAM/contexto. O servidor injeta a lista do workspace e trechos dos arquivos relevantes na mensagem atual; o frontend envia apenas as ultimas mensagens configuradas em `Historico enviado`.

Quando a tarefa pede uma alteracao, o agente pode retornar blocos no formato `mega-write`. O frontend e o CLI salvam esses blocos somente em caminhos relativos dentro deste workspace. Assim o Qwen consegue trabalhar como agente de codigo sem precisar de function calling, grammar ou structured output.

Inicie o servidor em um terminal normal do Windows, dentro da pasta do projeto:

```powershell
python .\server.py
```

O terminal precisa ter permissao de escrita na pasta do projeto; sem isso o agente ainda consegue analisar e responder, mas nao consegue persistir alteracoes.

Exemplos de pedidos:

```text
Inspecione o frontend atual e corrija o erro de conexao com o LM Studio. Altere os arquivos necessarios e diga como testar.
```

```text
Implemente uma tabela SQL e um pipeline Python para carregar os dados. Crie os arquivos e valide a estrutura.
```

Para tarefas maiores, trabalhe em etapas curtas: primeiro peca a analise, depois a implementacao, e por fim os testes. Isso reduz o uso de VRAM sem retirar a capacidade de codar.
