"use client";

import { useTranslations } from "next-intl";
import { uzs } from "@/lib/format";
import type { Plan, PlanId } from "@/lib/types";

/**
 * The three plans side by side. Presentational: the landing page shows them, the sign-up
 * flow lets the blogger pick one. The "coming soon" badge marks the channel watcher,
 * which is promised on Premium but not built yet.
 */
export function PlanCards({
  plans,
  selected,
  onSelect,
  compact,
}: {
  plans: Plan[];
  selected?: PlanId | null;
  onSelect?: (id: PlanId) => void;
  /** Landing page: no notes below the grid. */
  compact?: boolean;
}) {
  const t = useTranslations("signup");
  const common = useTranslations("common");
  return (
    <div>
      <div className="plan-grid" role={onSelect ? "radiogroup" : undefined}>
        {plans.map((p) => {
          const active = selected === p.id;
          const Tag = onSelect ? "button" : "div";
          return (
            <Tag
              key={p.id}
              type={onSelect ? "button" : undefined}
              role={onSelect ? "radio" : undefined}
              aria-checked={onSelect ? active : undefined}
              onClick={onSelect ? () => onSelect(p.id) : undefined}
              className="plan-card"
              data-plan={p.id}
              data-selected={active || undefined}
            >
              <span className="plan-name">{t(`plans.${p.id}.name`)}</span>
              <span className="plan-tagline">{t(`plans.${p.id}.tagline`)}</span>
              <span className="plan-price">
                {uzs(p.monthly_uzs)}
                <small>
                  {t("currency")}
                  {t("perMonth")}
                </small>
              </span>
              <ul className="plan-features">
                {(["f1", "f2", "f3", "f4"] as const).map((k) => {
                  const soon = p.id === "premium" && k === "f4";
                  const off = p.id === "archive" && k === "f4";
                  return (
                    <li key={k} data-off={off || undefined}>
                      {t(`plans.${p.id}.${k}`)}
                      {soon ? (
                        <span className="plan-soon">
                          {common("comingSoon")}
                        </span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              {p.id === "premium" ? (
                <span className="plan-note">{t("plans.aiNote")}</span>
              ) : null}
            </Tag>
          );
        })}
      </div>
      {compact ? null : (
        <p className="landing-note">{t("plans.readersNote")}</p>
      )}
    </div>
  );
}
