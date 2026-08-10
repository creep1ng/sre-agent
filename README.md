# midnight.agent design system

A framework-agnostic UI foundation for the midnight.agent gateway and incident-response surfaces. It translates the approved solution design into tokens, accessible core components, and domain patterns for operations and administration.

## Quick path

1. Serve the repository root with any static HTTP server.
2. Open `index.html` to review the live component catalog.
3. Import `styles/design-system.css` before product-specific styles.

```html
<link rel="stylesheet" href="/styles/design-system.css" />
```

## Structure

| Path                    | Responsibility                                               |
| ----------------------- | ------------------------------------------------------------ |
| `palette.css`           | Primitive brand and functional color values                  |
| `styles/fonts.css`      | Spline Sans, Offside, and Monaspace Neon font loading        |
| `styles/tokens.css`     | Light/dark semantic tokens and component aliases             |
| `styles/base.css`       | Reset, typography defaults, focus, and accessibility helpers |
| `styles/components.css` | Framework-agnostic component and domain-pattern classes      |
| `styles/showcase.css`   | Catalog layout only; do not ship with the product UI         |
| `scripts/showcase.js`   | Catalog theme, tabs, filters, and copy interactions          |
| `public/`               | Approved light/dark logos, mark, and favicon                 |

## Token rule

Components consume semantic or component tokens, never primitive values.

```css
/* Correct: intent survives theme changes. */
.product-panel {
  background: var(--ma-color-bg-surface);
  color: var(--ma-color-text-primary);
}

/* Avoid: the primitive has no usage contract. */
.product-panel {
  background: var(--ma-color-ghost-white);
}
```

The hierarchy is `primitive -> semantic -> component`. Theme switching changes semantic values while component APIs remain stable.

## Included patterns

- Buttons, icon buttons, badges, alerts, cards, panels, tabs, form controls, switches, tables, meters, and empty states
- Light, dark, and system-preference themes with persistent selection
- Incident summary, evidence timeline, governed-resource list, responder identity, and audit table
- Reduced-motion, forced-color, keyboard-focus, responsive, and screen-reader support

## Product principles

- Evidence stays attached to diagnoses, actions, and transitions.
- Permission state is visible before a governed action executes.
- Severity and policy outcomes never rely on color alone.
- Dense operational screens use hierarchy rather than decorative noise.
- Prefer spacing and alignment over nested cards when content already shares a clear parent.
- Prompt content is treated as sensitive; audit patterns foreground metadata.

## Scope

This release intentionally does not select a frontend framework. The solution design leaves that decision open, so future React, Vue, or mobile adapters should wrap these token and behavior contracts rather than fork them.
