"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";

export type LoginViewState = "loading" | "success" | "error" | "empty";

interface UseLoginOptions {
  readonly onSuccess?: () => void;
  readonly returnPath?: string;
  readonly forcedState?: LoginViewState;
}

interface UseLoginResult {
  readonly viewState: LoginViewState;
  readonly email: string;
  readonly password: string;
  readonly showPassword: boolean;
  readonly emailError: string | null;
  readonly passwordError: string | null;
  readonly formError: string | null;
  readonly isSubmitDisabled: boolean;
  readonly isMatrixAuthEnabled: boolean;
  readonly setEmail: (value: string) => void;
  readonly setPassword: (value: string) => void;
  readonly toggleShowPassword: () => void;
  readonly validateEmailOnBlur: () => void;
  readonly validatePasswordOnBlur: () => void;
  readonly submit: () => void;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function isValidEmail(email: string): boolean {
  return EMAIL_PATTERN.test(email.trim());
}

export function useLogin({
  onSuccess,
  returnPath = "/dashboard",
  forcedState,
}: Readonly<UseLoginOptions> = {}): UseLoginResult {
  const { isMatrixAuthEnabled, loginWithCredentials } = useAuth();
  const [viewState, setViewState] = useState<LoginViewState>("empty");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const submitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (submitTimerRef.current) {
        clearTimeout(submitTimerRef.current);
        submitTimerRef.current = null;
      }
    };
  }, []);

  const validateEmailOnBlur = useCallback(() => {
    if (!email.trim()) {
      setEmailError("Email address is required.");
      return;
    }
    if (!isValidEmail(email)) {
      setEmailError("Enter a valid email address.");
      return;
    }
    setEmailError(null);
  }, [email]);

  const validatePasswordOnBlur = useCallback(() => {
    if (!password) {
      setPasswordError("Password is required.");
      return;
    }
    setPasswordError(null);
  }, [password]);

  const isSubmitDisabled =
    !isMatrixAuthEnabled &&
    (!email.trim() ||
      !password ||
      !isValidEmail(email) ||
      Boolean(emailError) ||
      Boolean(passwordError));

  const submit = useCallback(() => {
    if (isMatrixAuthEnabled) {
      setViewState("loading");
      setFormError(null);
      loginWithCredentials("", "", returnPath);
      return;
    }
    validateEmailOnBlur();
    validatePasswordOnBlur();
    if (!email.trim() || !password || !isValidEmail(email)) {
      setViewState("error");
      setFormError("Check the highlighted fields and try again.");
      return;
    }

    setViewState("loading");
    setFormError(null);

    if (submitTimerRef.current) {
      clearTimeout(submitTimerRef.current);
    }
    submitTimerRef.current = setTimeout(() => {
      submitTimerRef.current = null;
      if (!mountedRef.current) return;
      const ok = loginWithCredentials(email, password);
      if (ok) {
        setViewState("success");
        onSuccess?.();
        return;
      }
      setViewState("error");
      setFormError("Email or password is incorrect. Please try again.");
    }, 600);
  }, [
    email,
    password,
    returnPath,
    isMatrixAuthEnabled,
    loginWithCredentials,
    onSuccess,
    validateEmailOnBlur,
    validatePasswordOnBlur,
  ]);

  if (forcedState) {
    return {
      viewState: forcedState,
      email: forcedState === "empty" ? "" : "user@example.eu",
      password: forcedState === "empty" ? "" : "********",
      showPassword: false,
      emailError: forcedState === "error" ? null : null,
      passwordError: forcedState === "error" ? null : null,
      formError:
        forcedState === "error" ? "Email or password is incorrect. Please try again." : null,
      isSubmitDisabled: forcedState !== "empty",
      isMatrixAuthEnabled,
      setEmail: () => {},
      setPassword: () => {},
      toggleShowPassword: () => {},
      validateEmailOnBlur: () => {},
      validatePasswordOnBlur: () => {},
      submit: () => {},
    };
  }

  return {
    viewState,
    email,
    password,
    showPassword,
    emailError,
    passwordError,
    formError,
    isSubmitDisabled,
    isMatrixAuthEnabled,
    setEmail,
    setPassword,
    toggleShowPassword: () => setShowPassword((prev) => !prev),
    validateEmailOnBlur,
    validatePasswordOnBlur,
    submit,
  };
}
