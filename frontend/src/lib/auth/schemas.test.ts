import { describe, expect, it } from "vitest";

import { emailSchema, newPasswordSchema, otpSchema } from "./schemas";

const t = (key: string) => key;

describe("auth form schemas", () => {
  it("enforces password length, non-numeric and confirmation", () => {
    const schema = newPasswordSchema(t);
    expect(schema.safeParse({ password: "short", confirm: "short" }).success).toBe(false);
    expect(schema.safeParse({ password: "1234567890123", confirm: "1234567890123" }).success).toBe(
      false,
    );
    const mismatch = schema.safeParse({ password: "Long-enough-1", confirm: "Different-1" });
    expect(mismatch.success).toBe(false);
    expect(mismatch.error?.issues[0]?.message).toBe("validation.passwordsMatch");
    expect(schema.safeParse({ password: "Long-enough-1", confirm: "Long-enough-1" }).success).toBe(
      true,
    );
  });

  it("validates OTP codes and emails", () => {
    expect(otpSchema(t).safeParse("123456").success).toBe(true);
    expect(otpSchema(t).safeParse("12345a").success).toBe(false);
    expect(emailSchema(t).safeParse(" person@example.com ").success).toBe(true);
    expect(emailSchema(t).safeParse("not-an-email").success).toBe(false);
  });
});
