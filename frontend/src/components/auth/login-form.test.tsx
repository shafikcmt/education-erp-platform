import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/app/[locale]/(auth)/login/login-form";
import bn from "@/messages/bn.json";
import en from "@/messages/en.json";

const push = vi.fn();
const replace = vi.fn();
vi.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push, replace }),
  Link: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

const post = vi.fn();
vi.mock("@/lib/api/browser", () => ({
  api: () => ({ POST: post }),
  ensureCsrf: () => Promise.resolve(),
}));

function renderLogin(locale: "en" | "bn" = "en") {
  return render(
    <NextIntlClientProvider locale={locale} messages={locale === "en" ? en : bn}>
      <QueryClientProvider client={new QueryClient()}>
        <LoginForm expired={false} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const ok = (data: unknown) => ({ data, response: new Response(null, { status: 200 }) });

describe("LoginForm", () => {
  beforeEach(() => {
    push.mockReset();
    replace.mockReset();
    post.mockReset();
  });

  it("uses the right autocomplete hints and validates required fields", async () => {
    renderLogin();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findAllByText("This field is required.")).toHaveLength(2);
    expect(post).not.toHaveBeenCalled();
  });

  it("routes to the MFA step when the API asks for it", async () => {
    post.mockResolvedValue(ok({ status: "mfa_required" }));
    renderLogin();
    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "a@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-pass-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith({ pathname: "/login/mfa", query: { next: "/dashboard" } }),
    );
  });

  it("shows one generic message for invalid credentials (no enumeration) and clears the password", async () => {
    post.mockResolvedValue({
      error: { code: "invalid_credentials" },
      response: new Response(null, { status: 401 }),
    });
    renderLogin("bn");
    fireEvent.change(screen.getByLabelText("ইমেইল ঠিকানা"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText("পাসওয়ার্ড"), { target: { value: "wrong-pass-1" } });
    fireEvent.click(screen.getByRole("button", { name: "সাইন ইন করুন" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "ইমেইল ঠিকানা বা পাসওয়ার্ড সঠিক নয়।",
    );
    expect(screen.getByLabelText("পাসওয়ার্ড")).toHaveValue("");
  });
});
