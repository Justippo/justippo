"use client";

import { useScrollReveal } from "@/hooks/useScrollReveal";
import styles from "./RevealSection.module.css";

interface RevealSectionProps {
  readonly children: React.ReactNode;
  readonly className?: string;
  readonly id?: string;
}

export function RevealSection({ children, className = "", id }: Readonly<RevealSectionProps>) {
  const { ref, isVisible } = useScrollReveal();

  return (
    <section
      id={id}
      ref={ref}
      className={`${styles.reveal} ${isVisible ? styles.revealVisible : styles.revealHidden} ${className}`}
    >
      {children}
    </section>
  );
}
