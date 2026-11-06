import type en from "../messages/en.json";

/** Type-checked translation keys: `tsc` fails on a missing or misspelled key. */
declare module "next-intl" {
  interface AppConfig {
    Messages: typeof en;
  }
}
