"use client";

import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { Button, Input } from "@/components/atoms";
import { useLogin } from "@/hooks/useLogin";
import { useAuthDestination } from "@/hooks/useAuthDestination";
import styles from "./AuthScreens.module.css";

interface LoginViewProps {
  readonly forcedState?: "loading" | "success" | "error" | "empty";
}

export function LoginView({ forcedState }: Readonly<LoginViewProps>) {
  const router = useRouter();
  const authDestination = useAuthDestination("/dashboard");
  const login = useLogin({
    forcedState,
    returnPath: authDestination.destination,
    onSuccess: () => {
      router.push(authDestination.destination);
    },
  });

  if (login.viewState === "loading") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <div className={styles.loadingState} role="status" aria-label="Signing in">
            <p>Signing in…</p>
          </div>
        </div>
      </div>
    );
  }

  if (login.viewState === "success") {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <h1 className={styles.heading}>Welcome back</h1>
          <p className={styles.subheading}>Redirecting to your dashboard…</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.heading}>Welcome back</h1>
        <p className={styles.subheading}>Sign in to continue with your documents.</p>

        {login.formError && (
          <p className={styles.formError} role="alert">
            {login.formError}
          </p>
        )}

        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            login.submit();
          }}
        >
          {login.isMatrixAuthEnabled ? (
            <>
              <p className={styles.subheading}>
                Continue to your institution&apos;s secure sign-in page.
              </p>
              <Button
                type="submit"
                variant="primary"
                disabled={login.isSubmitDisabled}
                data-testid="matrix-login-submit"
              >
                Continue securely
              </Button>
            </>
          ) : (
            <>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="login-email">
                  Email address
                </label>
                <Input
                  id="login-email"
                  type="email"
                  value={login.email}
                  onChange={(event) => login.setEmail(event.target.value)}
                  onBlur={login.validateEmailOnBlur}
                  data-testid="login-email"
                />
                {login.emailError && <p className={styles.fieldError}>{login.emailError}</p>}
              </div>

              <div className={styles.field}>
                <div className={styles.labelRow}>
                  <label className={styles.label} htmlFor="login-password">
                    Password
                  </label>
                  <a href="/login" className={styles.link}>
                    Forgot password?
                  </a>
                </div>
                <div className={styles.passwordWrap}>
                  <Input
                    id="login-password"
                    type={login.showPassword ? "text" : "password"}
                    value={login.password}
                    onChange={(event) => login.setPassword(event.target.value)}
                    onBlur={login.validatePasswordOnBlur}
                    data-testid="login-password"
                  />
                  <button
                    type="button"
                    className={styles.toggleButton}
                    onClick={login.toggleShowPassword}
                    aria-label={login.showPassword ? "Hide password" : "Show password"}
                  >
                    {login.showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {login.passwordError && <p className={styles.fieldError}>{login.passwordError}</p>}
              </div>

              <Button
                type="submit"
                variant="primary"
                disabled={login.isSubmitDisabled}
                data-testid="login-submit"
              >
                Sign in
              </Button>
            </>
          )}
        </form>

        {!login.isMatrixAuthEnabled && (
          <p className={styles.footerText}>
            Don&apos;t have an account?{" "}
            <a href={authDestination.registerHref} className={styles.link}>
              Sign up
            </a>
          </p>
        )}
      </div>
    </div>
  );
}
