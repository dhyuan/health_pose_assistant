export const SUPPORTED_LOCALES = ["en", "zh", "fr", "de", "ja"] as const;

export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  zh: "中文",
  fr: "Francais",
  de: "Deutsch",
  ja: "日本語",
};

export function normalizeLocale(input?: string | null): Locale {
  if (!input) return DEFAULT_LOCALE;
  const lowered = input.toLowerCase();
  const matched = SUPPORTED_LOCALES.find(
    (locale) => lowered === locale || lowered.startsWith(`${locale}-`),
  );
  return matched ?? DEFAULT_LOCALE;
}

export function localeToLanguageTag(locale: Locale): string {
  switch (locale) {
    case "zh":
      return "zh-CN";
    case "fr":
      return "fr-FR";
    case "de":
      return "de-DE";
    case "ja":
      return "ja-JP";
    case "en":
    default:
      return "en-US";
  }
}