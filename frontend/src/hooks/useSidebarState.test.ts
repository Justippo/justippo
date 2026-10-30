import { renderHook, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useSidebarState } from "./useSidebarState";

describe("useSidebarState", () => {
  it("starts closed", () => {
    const { result } = renderHook(() => useSidebarState());
    expect(result.current.isOpen).toBe(false);
  });

  it("toggle opens", () => {
    const { result } = renderHook(() => useSidebarState());
    act(() => {
      result.current.toggle();
    });
    expect(result.current.isOpen).toBe(true);
  });

  it("toggle again closes", () => {
    const { result } = renderHook(() => useSidebarState());
    act(() => {
      result.current.toggle();
    });
    act(() => {
      result.current.toggle();
    });
    expect(result.current.isOpen).toBe(false);
  });

  it("close sets to false", () => {
    const { result } = renderHook(() => useSidebarState());
    act(() => {
      result.current.toggle();
    });
    act(() => {
      result.current.close();
    });
    expect(result.current.isOpen).toBe(false);
  });

  it("close when already closed does nothing", () => {
    const { result } = renderHook(() => useSidebarState());
    expect(result.current.isOpen).toBe(false);
    act(() => {
      result.current.close();
    });
    expect(result.current.isOpen).toBe(false);
  });

  it("maintains referential equality for toggle and close across re-renders", () => {
    const { result, rerender } = renderHook(() => useSidebarState());

    const initialToggle = result.current.toggle;
    const initialClose = result.current.close;

    act(() => {
      result.current.toggle();
    });
    rerender();

    expect(result.current.toggle).toBe(initialToggle);
    expect(result.current.close).toBe(initialClose);
  });
});
