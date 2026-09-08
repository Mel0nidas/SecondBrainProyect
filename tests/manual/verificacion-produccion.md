# Verificación en producción — Fases 10–16

Checklist para correr **desde Telegram, contra el bot real**. Las Fases
10 a 16 tienen código y tests en verde, pero (a diferencia de la 7 / 7.5 /
7.6) nunca se confirmó que funcionen en la instancia. Esto lo cierra.

Marcá cada casilla cuando el resultado coincida. Si algo no coincide,
anotá qué pasó y con qué mensaje.

---

## Pre-chequeos (automáticos, ya hechos el 2026-09-07)

- [x] `https://54-207-200-20.sslip.io/salud` → `200 {"estado":"ok"}`.
- [x] El código en producción es el de la Fase 16 (`commit 7acce4c`, el
  último push a `main` antes de la métrica del Bibliotecario, que es
  sólo de tests y no necesita deploy).

Si querés confirmar que el **loop proactivo** está vivo antes de
empezar (necesita `aws sso login --profile AdministratorAccess-685394895160`):

```
aws ssm send-command --instance-ids "i-09dd5125bc5615f73" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/segundo-cerebro && docker-compose logs --tail=120 app | grep -i -E \"proactiv|briefing|recordatorio|digest\""]' \
  --profile AdministratorAccess-685394895160 --region sa-east-1 \
  --query "Command.CommandId" --output text
```

---

## 1. Fase 10 — Recordatorio de una vez

| # | Mandá | Esperá |
|---|---|---|
| 1.1 | `en 2 minutos recordame probar el bot` | `Listo. Te recuerdo "probar el bot" el <día dd/mm hh:mm>.` (sin "y cada…") |
| 1.2 | `/recordatorios` | Lista con ese recordatorio y un **id** |
| 1.3 | *(esperá ~2 min)* | Llega un mensaje del bot con el texto del recordatorio |
| 1.4 | `/recordatorios` | Ya **no** aparece (era de una vez → quedó `enviado`) |

- [ ] 1.1  - [ ] 1.2  - [ ] 1.3  - [ ] 1.4

**Rechazo esperado:** `recordame algo ayer a las 8` → `Esa hora ya paso. Decime un momento futuro.`
- [ ] ok

---

## 2. Fase 13 — Recordatorio recurrente + briefing matutino

| # | Mandá | Esperá |
|---|---|---|
| 2.1 | `todos los lunes recordame mandar la factura` | `Listo. Te recuerdo "mandar la factura" el <lunes dd/mm hh:mm> y cada semana.` |
| 2.2 | `en 1 minuto recordame todos los días tomar agua` | `… y cada día.` |
| 2.3 | *(cuando llegue el de 2.2)* después `/recordatorios` | El recurrente **sigue** ahí, reprogramado al día siguiente (no desaparece) |
| 2.4 | *(a la mañana siguiente, después de las 8 hs)* | Llega el **briefing**: lo que vence hoy + listas abiertas. Si no hay nada, no manda (probá tener algo pendiente) |

- [ ] 2.1  - [ ] 2.2  - [ ] 2.3  - [ ] 2.4

Limpieza: `/cancelar <id>` de los que creaste → `Recordatorio cancelado.`
- [ ] ok

---

## 3. Fase 11 — Listas de tareas

| # | Mandá | Esperá |
|---|---|---|
| 3.1 | `comprá pan y leche la próxima vez que vayas al súper` | Confirmación de que sumó pan y leche a una lista (`compras`) |
| 3.2 | `/lista` | `Tus listas: compras…` |
| 3.3 | `/lista compras` | `Lista compras:` con `• pan` y `• leche` |
| 3.4 | `ya compré el pan` | Confirma que tachó `pan` |
| 3.5 | `/lista compras` | `pan` marcado como hecho, `leche` sigue abierto |

- [ ] 3.1  - [ ] 3.2  - [ ] 3.3  - [ ] 3.4  - [ ] 3.5

Comprobá en Obsidian (PC): `20-tareas/compras.md` tiene `- [x] pan` y `- [ ] leche`.
- [ ] ok

---

## 4. Fase 12 — Índice al día con la bóveda

| # | Hacé | Esperá |
|---|---|---|
| 4.1 | En Obsidian (PC), creá una nota nueva con un dato inventado y raro (ej. "El código del candado del galpón es 4417") | Syncthing la lleva al server en segundos |
| 4.2 | En Telegram: `/reindexar` | `Índice al día: N reindexada(s), M borrada(s).` (N ≥ 1) |
| 4.3 | `qué número era el del candado del galpón` | El Bibliotecario responde con `4417` y cita `Fuentes: [[…]]` |
| 4.4 | En Obsidian, borrá esa nota; esperá ~5 min o `/reindexar` | La próxima consulta ya no la trae |

- [ ] 4.1  - [ ] 4.2  - [ ] 4.3  - [ ] 4.4

---

## 5. Fase 14 — Digestor semanal

| # | Mandá | Esperá |
|---|---|---|
| 5.1 | `/digest` | Llega el repaso: qué capturaste en la semana + inbox viejo + estado de listas |
| 5.2 | En Obsidian (PC) | Quedó una nota nueva en `90-sistema/` con el repaso completo |

- [ ] 5.1  - [ ] 5.2

---

## 6. Fase 15 — Calculador de costos

| # | Mandá | Esperá |
|---|---|---|
| 6.1 | `/costos` | Desglose por modelo (Claude Sonnet / Haiku con tokens y USD), costo fijo estimado de AWS, y aclaración de que Groq/Voyage están en tier gratuito |
| 6.2 | — | Los números tienen sentido (no todo en cero después de haber usado el bot en esta verificación) |

- [ ] 6.1  - [ ] 6.2

Comprobá en Obsidian: `90-sistema/costos.jsonl` creció con las llamadas de hoy.
- [ ] ok

---

## 7. Fase 16 — Citas del Bibliotecario + editar la última nota

| # | Mandá | Esperá |
|---|---|---|
| 7.1 | `guardá que el proveedor nuevo cotizó la caja a 200` | Confirmación de captura (nota en `00-inbox/`) |
| 7.2 | `agregale que viene con garantía de un año` | `Agregado a "00-inbox/….md".` |
| 7.3 | En Obsidian | Esa nota tiene la línea de la garantía al final |
| 7.4 | `qué guardé sobre el proveedor nuevo` | Respuesta que **termina** en `Fuentes: [[…]]` y menciona los 200 y la garantía |

- [ ] 7.1  - [ ] 7.2  - [ ] 7.3  - [ ] 7.4

**Borde:** `agregale que algo` como **primer** mensaje del día (sin haber
guardado nada antes) → `No tengo una nota reciente para editar. Guardá algo primero.`
- [ ] ok

---

## 8. Regresión del cluster `sonnet-5` (commit a04f3f3)

Los agentes pasaron de `claude-sonnet-4-6` a `claude-sonnet-5` y se
reescribió el dispatch de comandos. Chequeo rápido de que nada básico se
rompió:

| # | Mandá | Esperá |
|---|---|---|
| 8.1 | `guardá esta idea: probé el sistema de punta a punta el 7/9` | Nota creada en `00-inbox/` con título y tags razonables |
| 8.2 | `/estado` | El texto de estado (corriendo en producción, 24/7…) |
| 8.3 | `/ayuda` | La lista de comandos completa |
| 8.4 | una nota de voz corta hablando una idea | Se transcribe y se guarda como nota (Fase 7.5) |

- [ ] 8.1  - [ ] 8.2  - [ ] 8.3  - [ ] 8.4

---

## Resultado

- [ ] **Todo verde** → actualizar `DISEÑO.md` (Fases 10–16 "verificadas en
  producción") y `CONTEXTO.md`, y anotarlo en memoria.
- [ ] **Algo falló** → abrir el detalle acá abajo y priorizar el fix.

```
Fallas encontradas:
-
```
