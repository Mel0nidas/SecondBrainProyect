---
fecha: 2026-07-05
origen: telegram
tags: [software, infra]
estado: inbox
---

# Guardar sesiones fuera de la base

Idea para la app: mantener los datos de sesion de los usuarios en un
almacen en memoria en vez de pegarle a la base relacional en cada
request. Menos latencia y menos carga sobre el motor principal.
