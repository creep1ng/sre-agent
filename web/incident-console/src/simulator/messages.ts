import { registerCatalogs } from "@/i18n";

// The simulator's texts (src/i18n/<language>/simulator.ts) load with it, never in a live build.
registerCatalogs(import.meta.glob<Record<string, string>>("@/i18n/*/simulator.ts", { eager: true, import: "default" }));
