import { z } from "zod";

/**
 * zod v4 can compile validators with `new Function` (its JIT). Our CSP forbids eval in
 * production (review M3), so run zod in its interpreter mode: no eval is ever attempted.
 */
z.config({ jitless: true });
