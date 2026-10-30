import { FileText, Languages, Search, type LucideIcon } from "lucide-react";
import styles from "./HowItWorksSection.module.css";

interface Step {
  readonly number: string;
  readonly title: string;
  readonly description: string;
  readonly Icon: LucideIcon;
}

const STEPS: readonly Step[] = [
  {
    number: "1",
    title: "Upload",
    description: "Drop your PDF, DOCX, or scanned document. OCR extracts text instantly.",
    Icon: FileText,
  },
  {
    number: "2",
    title: "Translate",
    description: "Choose your target language. AI translates with legal terminology awareness.",
    Icon: Languages,
  },
  {
    number: "3",
    title: "Search & Compare",
    description: "Ask questions in natural language. Compare original and translated side-by-side.",
    Icon: Search,
  },
];

export function HowItWorksSection() {
  return (
    <section className={styles.section} aria-label="How it works">
      <h2 className={styles.heading}>How It Works</h2>
      <div className={styles.steps}>
        {STEPS.map((step) => (
          <div key={step.number} className={styles.step}>
            <span className={styles.icon} aria-hidden="true">
              <step.Icon size="1em" strokeWidth={1.75} />
            </span>
            <span className={styles.number}>{step.number}</span>
            <h3 className={styles.title}>{step.title}</h3>
            <p className={styles.description}>{step.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
