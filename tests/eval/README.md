# Evaluación del Router (DISEÑO.md §6)

El Router es el nodo del que depende todo lo demás: si clasifica mal la
intención, el mensaje va al agente equivocado. Esto mide su tasa de
acierto contra un set de mensajes etiquetados a mano.

**No corre en cada push** (pega a la API real de Claude y cuesta unos
centavos). Se dispara solo cuando un PR toca `src/grafo/prompts/**`,
`src/grafo/nodos/router.py` o `src/grafo/estado.py`, o a mano desde la
pestaña *Actions* de GitHub. Ver `.github/workflows/eval.yml`.

## Correr localmente

```bash
uv run --env-file .env python -m tests.eval.evaluar
```

`--env-file .env` carga `ANTHROPIC_API_KEY` (el script no usa
`load_dotenv`). Códigos de salida: `0` OK, `1` regresión, `2` error de
setup (falta la key o el set).

> El parser de `uv --env-file` es más estricto que `python-dotenv` y
> tira un warning en la línea `RUTA_BOVEDA_OBSIDIAN=D:\Second Brain`
> (valor con espacio sin comillas). No rompe nada — igual carga la key.
> Para que no moleste, poné comillas en esa línea del `.env`, o exportá
> `ANTHROPIC_API_KEY` a mano y corré sin `--env-file`.

## El baseline

`baseline.json` guarda la tasa de la última medición aceptada. Cada
corrida falla si la tasa cae más de 5 puntos por debajo de ese número
(margen para el ruido del modelo). Para fijar o actualizar el baseline
después de un cambio que mejora las cosas:

```bash
uv run --env-file .env python -m tests.eval.evaluar --actualizar-baseline
```

Commitealo junto con el cambio de prompt que lo justifica.

## El set (`mensajes.jsonl`)

Una línea por caso: `{"mensaje": ..., "intencion": ..., "fuente": ...}`.
`fuente` es `"real"` (mensaje que Melo mandó de verdad) o `"sintetico"`
(inventado para cubrir un caso). `intencion` es una de
`capturar | consultar | tarea | imagen | comando | ambiguo`.

El set arranca chico y mayormente sintético. Crece con uso real:

1. En Telegram, `/corregir <intencion>` cuando el bot clasifica mal.
   El bot mueve la nota y anota el caso en
   `90-sistema/correcciones.jsonl` de la bóveda (Syncthing lo trae acá).
2. `uv run --env-file .env python -m tests.eval.incorporar` (o con
   `--dry-run` primero) mergea esas líneas a `mensajes.jsonl`, sin
   duplicar.
3. Revisás las etiquetas nuevas, corrés `evaluar.py`, y commiteás el
   set (y `baseline.json` si lo re-fijaste).

Cuanto más real el set, más sirve el número.

## La regla (DISEÑO.md §6)

Ningún cambio de prompt o de modelo del Router se mergea sin correr esto.
El job de CI lo fuerza para los PRs que tocan esos archivos.
