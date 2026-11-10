import * as simulated from "@/simulator";
import { appMode } from "./mode";

/** The scenario simulator (`src/simulator/`) in mock mode, `null` in live mode. */
export const simulator = appMode === "mock" ? simulated : null;
