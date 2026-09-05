# HU-OPS-01 — Bandeja de alertas simuladas

Esta implementación cubre la historia **HU-OPS-01** sin adelantar HU-OPS-02.

## Evidencia de diseño

- Wireframe: `docs/wireframes/hu-ops-01-alert-inbox.svg`.
- Superficie implementada: `public/incident-ui/alerts.html`.
- Estilos de producto: `styles/incident-alerts.css` sobre `styles/design-system.css`.

## Cómo ejecutar

Con el stack local existente:

```bash
cp .env.example .env
# Completar los placeholders requeridos por el repositorio.
docker compose run --rm migrate
docker compose run --rm seed
docker compose up --build --wait
```

Abrir:

- Bandeja con datos: `http://127.0.0.1:8080/public/incident-ui/alerts.html`
- Estado vacío reproducible: `http://127.0.0.1:8080/public/incident-ui/alerts.html?fixture=empty`

El `web.Dockerfile` ya copia los directorios `public/` y `styles/`, por lo que estos archivos no requieren cambios de infraestructura.

## Contrato del fixture

`public/fixtures/alerts.json` contiene una colección reproducible con al menos dos servicios y dos severidades. Cada alerta expone:

- `alert_id`
- `title`
- `summary`
- `service`
- `severity`: `critical | warning | info`
- `timestamp`
- `status`: `new | acknowledged | monitoring`
- `source`
- `context`
- `origin` opcional

`origin`, cuando existe, es **metadata de origen de la alerta**. No representa una entidad `Anomaly` con lifecycle propio.

## Contrato de “Iniciar triage”

Sprint 1 no crea ni asocia incidentes. El botón emite en el DOM:

```text
midnight:triage-requested
```

con un `detail` equivalente a:

```json
{
  "alert_id": "alert-checkout-001",
  "service": "checkout-service",
  "source": "hu-ops-01-alert-inbox"
}
```

Un consumidor futuro de HU-OPS-02 puede reemplazar este contrato local por la integración real sin rediseñar la bandeja.

## Cobertura de criterios de aceptación

- Wireframe revisable incluido antes de la entrega del código.
- Fixtures versionados y reproducibles.
- Cada fila muestra resumen, servicio, severidad, estado y fecha/hora.
- Seleccionar una alerta actualiza el detalle sin retirar la bandeja.
- Estado vacío reproducible con `?fixture=empty`.
- “Iniciar triage” tiene un contrato explícito y no crea/asocia incidentes.
- La UI usa el design system existente y mantiene separada la fuente de datos para sustituir fixtures por backend posteriormente.
- El encabezado incluye un switch accesible para alternar tema claro/oscuro; la preferencia se conserva localmente en el navegador.
- Navegación de selección mediante controles `<button>` nativos y severidad/estado expresados también mediante texto, no solo color.

## Fuera de alcance preservado

No se implementan detección de anomalías, ingesta Grafana/OpenTelemetry en vivo, deduplicación/correlación, creación/asociación de incidentes, war room, timeline, hipótesis, mitigación ni autenticación de usuarios de UI.
