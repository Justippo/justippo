// SPDX-License-Identifier: MIT
/**
 * Shared i18n key constants — EvidenceEU Cross-Platform
 *
 * Centralised translation keys so both web (Tolgee) and mobile
 * (@tolgee/react-native) import the same keys without duplicating strings.
 *
 * @platform web mobile
 */

export const SEARCH_KEYS = {
  PLACEHOLDER: "search.placeholder",
  BUTTON: "search.button",
  LOADING: "search.loading",
  ERROR: "search.error",
  NO_RESULTS: "search.noResults",
  RESULTS_HEADING: "search.resultsHeading",
  SOURCE_COUNT: "search.sourceCount",
} as const;

export const UPLOAD_KEYS = {
  TITLE: "upload.title",
  DROP_ZONE: "upload.dropZone",
  BROWSE: "upload.browse",
  PROCESSING: "upload.processing",
  SUCCESS: "upload.success",
  ERROR: "upload.error",
  FILE_TOO_LARGE: "upload.fileTooLarge",
  UNSUPPORTED_FORMAT: "upload.unsupportedFormat",
} as const;

export const TRANSLATE_KEYS = {
  TITLE: "translate.title",
  SOURCE_LANG: "translate.sourceLang",
  TARGET_LANG: "translate.targetLang",
  TRANSLATE_BUTTON: "translate.button",
  TRANSLATING: "translate.translating",
  DOWNLOAD: "translate.download",
  ERROR: "translate.error",
  TRUNCATED_WARNING: "translate.truncatedWarning",
} as const;

export const AUTH_KEYS = {
  LOGIN_TITLE: "auth.loginTitle",
  EMAIL_LABEL: "auth.emailLabel",
  PASSWORD_LABEL: "auth.passwordLabel",
  SIGN_IN: "auth.signIn",
  SIGN_OUT: "auth.signOut",
  REGISTER: "auth.register",
  FORGOT_PASSWORD: "auth.forgotPassword",
  INVALID_CREDENTIALS: "auth.invalidCredentials",
} as const;

export const CHAT_KEYS = {
  PLACEHOLDER: "chat.placeholder",
  SEND: "chat.send",
  LOADING: "chat.loading",
  ERROR: "chat.error",
  EMPTY_STATE: "chat.emptyState",
  MODEL_INFO: "chat.modelInfo",
} as const;

export const COMMON_KEYS = {
  APP_NAME: "common.appName",
  CANCEL: "common.cancel",
  CONFIRM: "common.confirm",
  SAVE: "common.save",
  DELETE: "common.delete",
  LOADING: "common.loading",
  RETRY: "common.retry",
  BACK: "common.back",
  NEXT: "common.next",
  CLOSE: "common.close",
  SEARCH: "common.search",
  SETTINGS: "common.settings",
  LANGUAGE: "common.language",
} as const;

export const SETTINGS_KEYS = {
  TITLE: "settings.title",
  THEME: "settings.theme",
  DARK_MODE: "settings.darkMode",
  LIGHT_MODE: "settings.lightMode",
  LANGUAGE_PICKER: "settings.languagePicker",
  NOTIFICATIONS: "settings.notifications",
  PRIVACY: "settings.privacy",
  ABOUT: "settings.about",
  VERSION: "settings.version",
} as const;

export const DOCUMENT_KEYS = {
  TITLE: "document.title",
  METADATA: "document.metadata",
  PAGES: "document.pages",
  TRANSLATIONS: "document.translations",
  UPLOAD_DATE: "document.uploadDate",
  STATUS_QUEUED: "document.statusQueued",
  STATUS_PROCESSING: "document.statusProcessing",
  STATUS_READY: "document.statusReady",
  STATUS_FAILED: "document.statusFailed",
} as const;

export type I18nKey =
  | (typeof SEARCH_KEYS)[keyof typeof SEARCH_KEYS]
  | (typeof UPLOAD_KEYS)[keyof typeof UPLOAD_KEYS]
  | (typeof TRANSLATE_KEYS)[keyof typeof TRANSLATE_KEYS]
  | (typeof AUTH_KEYS)[keyof typeof AUTH_KEYS]
  | (typeof CHAT_KEYS)[keyof typeof CHAT_KEYS]
  | (typeof COMMON_KEYS)[keyof typeof COMMON_KEYS]
  | (typeof SETTINGS_KEYS)[keyof typeof SETTINGS_KEYS]
  | (typeof DOCUMENT_KEYS)[keyof typeof DOCUMENT_KEYS];
