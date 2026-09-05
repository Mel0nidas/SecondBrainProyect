# Segundo Cerebro

Agentes LangGraph sobre una bóveda Obsidian, con Telegram como interfaz de entrada.

Ver [`DISEÑO.md`](./DISEÑO.md) — documento fundacional con el stack, la arquitectura y el plan de desarrollo fase por fase.

**Estado actual**: Fase 0 (fundaciones del repo).

## Desarrollo

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run mypy
uv run pytest
```
