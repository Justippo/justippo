"use client";

import { useRouter } from "next/navigation";
import { Check, Eye, EyeOff } from "lucide-react";
import { Button, Input } from "@/components/atoms";
import { useRegister } from "@/hooks/useRegister";
import { useAuthDestination } from "@/hooks/useAuthDestination";
import styles from "./AuthScreens.module.css";

interface RegisterViewProps {
  readonly forcedState?: "loading" | "success" | "error" | "empty";
}

export function RegisterView({ forcedState }: Readonly<RegisterViewProps>) {
  const router = useRouter();
  const authDestination = useAuthDestination("/onboarding");
  const register = useRegister({
    forcedState,
    returnPath: authDestination.destination,
    onSuccess: () => router.push(authDestination.destination),
  });

  if (register.viewState === "loading") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.loadingState} role="status" aria-label="Creating account">
            <p>Creating your account…</p>
          </div>
        </div>
      </div>
    );
  }

  if (register.viewState === "success") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <h1 className={styles.heading}>Create your account</h1>
          <p className={styles.subheading}>Preparing your workspace…</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.heading}>Create your account</h1>
        <p className={styles.subheading}>Start working with multilingual EU documents.</p>

        {register.formError && (
          <p className={styles.formError} role="alert">
            {register.formError}
          </p>
        )}

        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            register.submit();
          }}
        >
          {register.isMatrixAuthEnabled ? (
            <>
              <p className={styles.subheading}>
                Continue to the secure account service to create your account.
              </p>
              <Button
                type="submit"
                variant="primary"
                disabled={register.isSubmitDisabled}
                data-testid="matrix-register-submit"
              >
                Continue securely
              </Button>
            </>
          ) : (
            <>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="register-name">
                  Full name
                </label>
                <Input
                  id="register-name"
                  value={register.fullName}
                  onChange={(event) => register.setFullName(event.target.value)}
                  onBlur={() => register.validateFieldOnBlur("fullName")}
                  data-testid="register-name"
                />
                {register.fieldErrors.fullName && (
                  <p className={styles.fieldError}>{register.fieldErrors.fullName}</p>
                )}
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="register-email">
                  Email
                </label>
                <Input
                  id="register-email"
                  type="email"
                  value={register.email}
                  onChange={(event) => register.setEmail(event.target.value)}
                  onBlur={() => register.validateFieldOnBlur("email")}
                  data-testid="register-email"
                />
                {register.fieldErrors.email && (
                  <p className={styles.fieldError}>{register.fieldErrors.email}</p>
                )}
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="register-password">
                  Password
                </label>
                <div className={styles.passwordWrap}>
                  <Input
                    id="register-password"
                    type={register.showPassword ? "text" : "password"}
                    value={register.password}
                    onChange={(event) => register.setPassword(event.target.value)}
                    onBlur={() => register.validateFieldOnBlur("password")}
                    data-testid="register-password"
                  />
                  <button
                    type="button"
                    className={styles.toggleButton}
                    onClick={register.toggleShowPassword}
                    aria-label={register.showPassword ? "Hide password" : "Show password"}
                  >
                    {register.showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <ul className={styles.requirements} aria-label="Password requirements">
                  {register.passwordRequirements.map((req) => (
                    <li
                      key={req.id}
                      className={`${styles.requirement} ${req.met ? styles.requirementMet : ""}`}
                    >
                      <Check size={14} aria-hidden="true" />
                      {req.label}
                    </li>
                  ))}
                </ul>
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="register-confirm">
                  Confirm password
                </label>
                <Input
                  id="register-confirm"
                  type="password"
                  value={register.confirmPassword}
                  onChange={(event) => register.setConfirmPassword(event.target.value)}
                  onBlur={() => register.validateFieldOnBlur("confirmPassword")}
                  data-testid="register-confirm"
                />
                {register.fieldErrors.confirmPassword && (
                  <p className={styles.fieldError}>{register.fieldErrors.confirmPassword}</p>
                )}
              </div>

              <Button
                type="submit"
                variant="primary"
                disabled={register.isSubmitDisabled}
                data-testid="register-submit"
              >
                Create account
              </Button>
            </>
          )}
        </form>

        <p className={styles.footerText}>
          Already have an account?{" "}
          <a href={authDestination.loginHref} className={styles.link}>
            Sign in
          </a>
        </p>
      </div>
    </div>
  );
}
