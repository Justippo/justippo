import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { FeatureSection } from "./FeatureSection";

const features = [
  { id: "upload", headline: "Upload", description: "Drop docs.", stat: "98%", statLabel: "OCR" },
];

describe("FeatureSection", () => {
  it("renders feature cards", () => {
    render(<FeatureSection features={features} />);
    expect(screen.getByText("Upload")).toBeDefined();
  });

  it("renders section landmark", () => {
    render(<FeatureSection features={features} />);
    expect(screen.getByLabelText("Platform features")).toBeDefined();
  });
});
