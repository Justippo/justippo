"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";

export type RegisterViewState = "loading" | "success" | "error" | "empty";

interface UseRegisterOptions {
  readonly onSuccess?: () => void;
  readonly returnPath?: string;
  readonly forcedState?: RegisterViewState;
}

interface PasswordRequirement {
  readonly id: string;
  readonly label: string;
  readonly met: boolean;
}

interface UseRegisterResult {
  readonly viewState: RegisterViewState;
  readonly fullName: string;
  readonly email: string;
  readonly password: string;
  readonly confirmPassword: string;
  readonly showPassword: boolean;
  readonly fieldErrors: Readonly<Record<string, string>>;
  readonly formError: string | null;
  readonly passwordRequirements: readonly PasswordRequirement[];
  readonly isSubmitDisabled: boolean;
  readonly isMatrixAuthEnabled: boolean;
  readonly setFullName: (value: string) => void;
  readonly setEmail: (value: string) => void;
  readonly setPassword: (value: string) => void;
  readonly setConfirmPassword: (value: string) => void;
  readonly toggleShowPassword: () => void;
  readonly validateFieldOnBlur: (
    field: "fullName" | "email" | "password" | "confirmPassword"
  ) => void;
  readonly submit: () => void;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function buildRequirements(password: string): readonly PasswordRequirement[] {
  return [
    { id: "length", label: "At least 8 characters", met: password.length >= 8 },
    { id: "upper", label: "One uppercase letter", met: /[A-Z]/.test(password) },
    { id: "lower", label: "One lowercase letter", met: /[a-z]/.test(password) },
    { id: "number", label: "One number", met: /\d/.test(password) },
  ];
}

export function useRegister({
  onSuccess,
  returnPath = "/onboarding",
  forcedState,
}: Readonly<UseRegisterOptions> = {}): UseRegisterResult {
  const { isMatrixAuthEnabled, login, loginWithCredentials } = useAuth();
  const [viewState, setViewState] = useState<RegisterViewState>("empty");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
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

  const passwordRequirements = useMemo(() => buildRequirements(password), [password]);

  const allRequirementsMet = passwordRequirements.every((req) => req.met);

  const validateFieldOnBlur = useCallback(
    (field: "fullName" | "email" | "password" | "confirmPassword") => {
      setFieldErrors((prev) => {
        const next = { ...prev };
        if (field === "fullName" && !fullName.trim()) {
          next.fullName = "Full name is required.";
        } else if (field === "fullName") {
          delete next.fullName;
        }

        if (field === "email") {
          if (!email.trim()) next.email = "Email is required.";
          else if (!EMAIL_PATTERN.test(email.trim())) next.email = "Enter a valid email address.";
          else delete next.email;
        }

        if (field === "password") {
          if (!allRequirementsMet) next.password = "Password does not meet all requirements.";
          else delete next.password;
        }

        if (field === "confirmPassword") {
          if (password !== confirmPassword) next.confirmPassword = "Passwords must match.";
          else delete next.confirmPassword;
        }

        return next;
      });
    },
    [allRequirementsMet, confirmPassword, email, fullName, password]
  );

  const isSubmitDisabled =
    !isMatrixAuthEnabled &&
    (!fullName.trim() ||
      !email.trim() ||
      !password ||
      !confirmPassword ||
      !allRequirementsMet ||
      password !== confirmPassword ||
      Object.keys(fieldErrors).length > 0);

  const submit = useCallback(() => {
    if (isMatrixAuthEnabled) {
      setViewState("loading");
      setFormError(null);
      loginWithCredentials("", "", returnPath);
      return;
    }
    validateFieldOnBlur("fullName");
    validateFieldOnBlur("email");
    validateFieldOnBlur("password");
    validateFieldOnBlur("confirmPassword");

    if (
      !fullName.trim() ||
      !EMAIL_PATTERN.test(email.trim()) ||
      !allRequirementsMet ||
      password !== confirmPassword
    ) {
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
      login();
      setViewState("success");
      onSuccess?.();
    }, 800);
  }, [
    allRequirementsMet,
    confirmPassword,
    email,
    fullName,
    isMatrixAuthEnabled,
    login,
    loginWithCredentials,
    onSuccess,
    password,
    returnPath,
    validateFieldOnBlur,
  ]);

  if (forcedState) {
    return {
      viewState: forcedState,
      fullName: forcedState === "empty" ? "" : "Alex Morgan",
      email: forcedState === "empty" ? "" : "alex@example.eu",
      password: forcedState === "empty" ? "" : "Password1",
      confirmPassword: forcedState === "empty" ? "" : "Password1",
      showPassword: false,
      fieldErrors: forcedState === "error" ? { email: "Enter a valid email address." } : {},
      formError: forcedState === "error" ? "Check the highlighted fields and try again." : null,
      passwordRequirements: buildRequirements(forcedState === "empty" ? "" : "Password1"),
      isSubmitDisabled: forcedState !== "empty",
      isMatrixAuthEnabled,
      setFullName: () => {},
      setEmail: () => {},
      setPassword: () => {},
      setConfirmPassword: () => {},
      toggleShowPassword: () => {},
      validateFieldOnBlur: () => {},
      submit: () => {},
    };
  }

  return {
    viewState,
    fullName,
    email,
    password,
    confirmPassword,
    showPassword,
    fieldErrors,
    formError,
    passwordRequirements,
    isSubmitDisabled,
    isMatrixAuthEnabled,
    setFullName,
    setEmail,
    setPassword,
    setConfirmPassword,
    toggleShowPassword: () => setShowPassword((prev) => !prev),
    validateFieldOnBlur,
    submit,
  };
}
