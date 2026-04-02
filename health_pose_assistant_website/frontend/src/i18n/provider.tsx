"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { de, enUS, fr, ja, zhCN } from "date-fns/locale";
import {
  DEFAULT_LOCALE,
  LOCALE_LABELS,
  type Locale,
  localeToLanguageTag,
} from "@/i18n/config";
import { translate } from "@/i18n/messages";

const STORAGE_KEY = "hpa_locale";
const COOKIE_KEY = "hpa_locale";

type LocaleObject = typeof enUS;

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  localeLabel: string;
  languageTag: string;
  dateFnsLocale: LocaleObject;
}

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

function getDateFnsLocale(locale: Locale): LocaleObject {
  switch (locale) {
    case "zh":
      return zhCN;
    case "fr":
      return fr;
    case "de":
      return de;
    case "ja":
      return ja;
    case "en":
    default:
      return enUS;
  }
}

function persistLocale(locale: Locale) {
  const languageTag = localeToLanguageTag(locale);
  window.localStorage.setItem(STORAGE_KEY, locale);
  document.documentElement.lang = languageTag;
  document.cookie = `${COOKIE_KEY}=${locale}; path=/; max-age=31536000; samesite=lax`;
}

export function I18nProvider({
  children,
  initialLocale = DEFAULT_LOCALE,
}: {
  children: React.ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = (nextLocale: Locale) => {
    setLocaleState(nextLocale);
    persistLocale(nextLocale);
  };

  useEffect(() => {
    persistLocale(locale);
  }, [locale]);

  const value = useMemo<I18nContextValue>(() => {
    return {
      locale,
      setLocale,
      t: (key, vars) => translate(locale, key, vars),
      localeLabel: LOCALE_LABELS[locale],
      languageTag: localeToLanguageTag(locale),
      dateFnsLocale: getDateFnsLocale(locale),
    };
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}
