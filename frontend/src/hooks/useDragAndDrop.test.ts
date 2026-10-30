import { renderHook, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useDragAndDrop } from "./useDragAndDrop";

describe("useDragAndDrop", () => {
  it("starts with no file and not dragging", () => {
    const { result } = renderHook(() => useDragAndDrop());
    expect(result.current.isDragging).toBe(false);
    expect(result.current.file).toBeNull();
  });

  it("sets isDragging on dragEnter", () => {
    const { result } = renderHook(() => useDragAndDrop());
    const event = { preventDefault: () => {}, stopPropagation: () => {} } as any;
    act(() => {
      result.current.onDragEnter(event);
    });
    expect(result.current.isDragging).toBe(true);
  });

  it("clears isDragging on dragLeave", () => {
    const { result } = renderHook(() => useDragAndDrop());
    const event = { preventDefault: () => {}, stopPropagation: () => {} } as any;
    act(() => {
      result.current.onDragEnter(event);
    });
    act(() => {
      result.current.onDragLeave(event);
    });
    expect(result.current.isDragging).toBe(false);
  });

  it("sets file on drop", () => {
    const { result } = renderHook(() => useDragAndDrop());
    const file = new File(["x"], "test.pdf");
    const event = {
      preventDefault: () => {},
      stopPropagation: () => {},
      dataTransfer: { files: [file] },
    } as any;
    act(() => {
      result.current.onDrop(event);
    });
    expect(result.current.file).toBe(file);
    expect(result.current.isDragging).toBe(false);
  });

  it("onFileSelect sets file", () => {
    const { result } = renderHook(() => useDragAndDrop());
    const file = new File(["x"], "doc.pdf");
    act(() => {
      result.current.onFileSelect(file);
    });
    expect(result.current.file).toBe(file);
  });

  it("clearFile resets file", () => {
    const { result } = renderHook(() => useDragAndDrop());
    const file = new File(["x"], "doc.pdf");
    act(() => {
      result.current.onFileSelect(file);
    });
    act(() => {
      result.current.clearFile();
    });
    expect(result.current.file).toBeNull();
  });
});
