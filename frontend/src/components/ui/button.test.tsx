import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "./button";

describe("Button", () => {
  it("renders an accessible button with variant classes", () => {
    render(<Button variant="outline">Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("data-slot", "button");
    expect(button.className).toContain("border");
  });

  it("renders its child element when asChild is set", () => {
    render(
      <Button asChild>
        <a href="https://example.com/x">Go</a>
      </Button>,
    );
    expect(screen.getByRole("link", { name: "Go" })).toHaveAttribute(
      "href",
      "https://example.com/x",
    );
  });
});
