import { Children, type ReactNode } from "react";
import styles from "./ScrollNarrative.module.css";

interface NarrativeStep {
  readonly id: string;
  readonly label: string;
}

interface ScrollNarrativeProps {
  readonly children: ReactNode;
  readonly steps: readonly NarrativeStep[];
}

export function ScrollNarrative({ children, steps }: Readonly<ScrollNarrativeProps>) {
  const panels = Children.toArray(children);

  if (panels.length !== steps.length) {
    throw new Error("ScrollNarrative requires one child panel for every journey step");
  }

  return (
    <div className={styles.narrative}>
      <div className={styles.panels}>
        {steps.map((step, index) => (
          <div className={styles.panel} id={step.id} key={step.id}>
            {panels[index]}
          </div>
        ))}
      </div>
    </div>
  );
}
