# Mega Brain

Interface local simples para usar modelos servidos pelo LM Studio em modo OpenAI-compatible.

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

Ele e curto de proposito para economizar VRAM/contexto. O frontend tambem envia apenas as ultimas mensagens configuradas em `Historico enviado`, mantendo o sistema mais leve para modelos locais como Qwen.
