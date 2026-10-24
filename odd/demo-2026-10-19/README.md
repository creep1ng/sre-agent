# Plan hasta la demo del lunes 2026-10-19 17:00 (Bogotá)

Mensajes por persona: [camilo.md](camilo.md), [daniel.md](daniel.md), [mario.md](mario.md).
Auditoría de origen: 2026-10-16 sobre `origin/main` aa789d9.

## Prerrequisitos de Ricardo (viernes 17)

- Mergear #649 y luego #650.
- Definir nombre y versión del contrato de comandos nuevos (`verification_passed`,
  `verification_failed`, `close_incident`).
- Definir el recorte mínimo de #335 (artefacto de postmortem persistido y guard de cierre).
- Decidir #482 contra #648 (recomendado: mergear #482 y rebasar la cadena de consola).
- Cerrar las 24 drafts `triage-23` (#524 a #539, #540, #545, #561 a #566) ya integradas por
  #546, y las 9 del stack #454 (#569, #573 a #579, #581) integradas por #616; cerrar issue #454.
- Decidir #600, #619 y #625.
- Board: poner `Priority` a la cadena E2E; #29 figura "In progress" pero cerró el 2026-10-03.
- `git pull` en el checkout principal (510 commits detrás de `origin/main`).

## Cronograma común

| Cuándo | Qué |
| --- | --- |
| Viernes 17 noche | Higiene de PRs, decisiones, asignaciones. Camilo arranca la prueba real. |
| Sábado 18 14:00 | Contrato de comandos publicado por Camilo. |
| Sábado 18 noche | Integración a main; stack fresco con `setup_sre.py`; recorrido completo de Ricardo. |
| Domingo 19 | Pruebas humanas con tres evaluadores; lista de fallos; congelar RC (#52). |
| Lunes 19 | Solo correcciones P0. OTel listo a las 15:00; fallo inyectado a las 16:30. |

Riesgo: si verificación, postmortem y cierre no entran el sábado, los evaluadores llegan hasta
`verifying`. La demo aún muestra alerta, triage, investigación agéntica real y aprobación humana.
