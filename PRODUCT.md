# Product

<!-- impeccable:product-schema 1 -->

Ficha de producto que lee la skill de diseño `impeccable` antes de proponer o tocar una
pantalla. Son hechos del producto, no decisiones visuales: esas viven en `INTERFAZ.md`.

## Platform

web

## Users

- **Principal:** un programador que trabaja solo y tiene varios agentes de IA (Claude Code y
  Codex) corriendo a la vez, cada uno en la carpeta de un proyecto distinto. Lo usa en su
  propia PC con Windows, muchas horas seguidas y casi siempre de noche; también lo sigue
  desde el teléfono.
- **Confirmado el 2026-11-10:** además tiene que convencer a **otros programadores y
  agencias** que evalúen la versión pública (Panel de agentes AOP) y a **clientes** que ven
  la pantalla cuando se comparte en una reunión.

## Product Purpose

Un panel local (`localhost:8750`) para orquestar agentes: ver de un vistazo cuál está
trabajando, cuál terminó y te espera, y hablarle a cualquiera. Suma un asistente de voz y un
transcriptor de audios que corren en la placa de video de la máquina.

Éxito, en palabras del dueño: que sea premium, que dé ganas de pagar por verlo todos los días.

## Positioning

Todo corre en la PC del usuario, sin subir nada. Las sesiones quedan vivas entre un mensaje y
otro, con su trabajo en segundo plano, y se manejan muchas a la vez desde una sola pantalla o
desde el celular.

## Operating Context

- La pantalla más usada es `/sesiones`: columna de carpetas, pestañas de charlas abiertas, el
  hilo de la charla y la caja de escribir. Se usa en monitor ancho y en monitor vertical.
- Hay siete pantallas (Panel, Guardia, Sesiones, Pizarra, Estudio, Avisos, Servidores) y una
  versión para el teléfono (`/movil`).
- El usuario viste el panel desde el 🎨: tema claro u oscuro, estilo, color por carpeta, color
  por charla, foto de fondo, tamaño de letra y de botones.

## Capabilities and Constraints

- Sin paso de compilación: HTML y JavaScript servidos tal cual. El aspecto cuelga de clases
  en `<html>` que pone `app/estaticos/aspecto.js`.
- **Nada se baja de internet al abrir la página**: tiene que andar sin conexión. Una
  tipografía nueva se sirve desde el propio proyecto.
- Ninguna función se pierde en un rediseño. Confirmado el 2026-11-10: la disposición de
  `/sesiones` **sí** puede cambiar.
- No se tocan: los colores y emojis que el usuario eligió para sus carpetas, y la foto de
  fondo.
- Lo que haría que un resultado prolijo igual esté mal: **que quede recargado** (brillos,
  efectos, cosas moviéndose).

## Brand Commitments

- Nombres: "Servidor IA" (uso propio) y "Panel de agentes AOP" (versión pública).
- Idioma: español rioplatense, voseo, sin jerga.
- El rojo es solo para lo que está mal. Ningún color de acento puede confundirse con el
  semáforo (verde, amarillo, rojo): esos son estados.

## Evidence on Hand

- La pantalla real funcionando, con datos reales del usuario.
- No hay logotipo propio (se usa un emoji), ni testimonios, ni precios: no se inventan.

## Product Principles

1. El estado de cada agente se lee de un vistazo, sin abrir nada.
2. Lo que hoy se encuentra de memoria sigue en su lugar o queda más fácil de encontrar.
3. Lo que el usuario eligió (colores, emojis, foto) es suyo y manda.
4. Calma: nada se mueve si no cambió un estado.
