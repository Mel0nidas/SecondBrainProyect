# Evaluación (DISEÑO.md §6)

Dos métricas, cada una con su script, su set y su baseline:

| Métrica | Script | Set | Baseline | Mide |
|---|---|---|---|---|
| **Router** (principal) | `evaluar.py` | `mensajes.jsonl` | `baseline.json` | tasa de acierto de la intención |
| **Bibliotecario** (secundaria) | `evaluar_bibliotecario.py` | `consultas_bibliotecario.jsonl` + `corpus_bibliotecario/` | `baseline_bibliotecario.json` | recall@3 de la búsqueda semántica |

Ninguna corre en cada push (pegan a APIs pagas). Las dispara
`.github/workflows/eval.yml`: a mano desde *Actions*, o en PRs que tocan
el código del que depende cada una.

---

## Evaluación del Router

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

---

## Evaluación del Bibliotecario (recall@3)

La contraparte del eval del Router. El del Router mide *a dónde* va el
mensaje; éste mide que, cuando va al Bibliotecario, la nota que responde
la pregunta aparezca entre las 3 primeras que trae la búsqueda semántica
(`rag/indexar.py`: Voyage + Chroma).

```bash
uv run --env-file .env python -m tests.eval.evaluar_bibliotecario
```

`--env-file .env` carga `VOYAGE_API_KEY` (mismo detalle del parser que
arriba: si el `.env` tiene la línea `RUTA_BOVEDA_OBSIDIAN=D:\Second Brain`
sin comillas, `uv` corta ahí — poné comillas o exportá `VOYAGE_API_KEY` a
mano). **No** llama al LLM: sólo evalúa recuperación, no cómo redacta el
Bibliotecario. Gasta 2 requests a Voyage por corrida (todo el corpus en
una, todas las consultas en otra).

### El corpus y el set

- `corpus_bibliotecario/*.md` — notas fijas, con grupos parecidos a
  propósito (3 sobre plata, 3 sobre software, 2 viajes, 2 recetas, 2
  sobre cumpleaños) para que el número pueda bajar si la recuperación se
  degrada.
- `consultas_bibliotecario.jsonl` — una línea por consulta:
  `{"consulta": ..., "nota_esperada": <archivo sin .md>, "fuente": ...}`.
  Cada consulta usa palabras **distintas** a las de su nota: si bastara
  un grep, no mediría nada.

Para agregar un caso: escribí la consulta en el `.jsonl` y, si hace
falta, la nota en `corpus_bibliotecario/`. `evaluar_bibliotecario.py`
chequea que todo `nota_esperada` exista en el corpus (y hay un test
unitario que lo verifica sin gastar API).

### El baseline

`baseline_bibliotecario.json` guarda `recall_at_3` (el que corta, margen
10 pts) y `recall_at_1` (informativo, más sensible pero más ruidoso).
Re-fijalo junto al cambio que lo justifique:

```bash
uv run --env-file .env python -m tests.eval.evaluar_bibliotecario --actualizar-baseline
```

El job `eval-bibliotecario` de CI corre esto en PRs que tocan
`src/rag/indexar.py`, `src/grafo/nodos/bibliotecario.py` o `tests/eval/**`.
Necesita `VOYAGE_API_KEY` como secret de GitHub.
