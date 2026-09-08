---
fecha: 2026-04-18
origen: telegram
tags: [software, diseño]
estado: inbox
---

# Puertos y adaptadores

Apunte de diseño: el nucleo del sistema no conoce la infraestructura.
Se comunica con el mundo exterior a traves de interfaces, y cada
tecnologia concreta (base de datos, cola, HTTP) es un adaptador
enchufable. Facilita testear el dominio sin levantar nada.
