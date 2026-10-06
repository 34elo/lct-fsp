import { Badge, Button, Card, ErrorState, Field, FieldInput, Skeleton } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  getGetProfileCandidatesMeProfileGetQueryKey,
  useGetProfileCandidatesMeProfileGet,
  usePatchProfileCandidatesMeProfilePatch,
} from "@/api/endpoints/candidates/candidates";
import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { CandidateProfile, ProfileIn, StackItem } from "@/api/model";
import { RoleSlug } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { ErrorNote } from "@/features/auth/ui";
import { editText as E, roleLabel } from "@/features/profile/text";
import { cn } from "@/shared/lib/cn";

interface TaxSkill {
  slug: string;
  name: string;
  kind?: string;
}

const ROLES = Object.values(RoleSlug) as string[];
const MAX_ROLES = 5;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Проверка полей контактов: пустое значение допустимо. Возвращает текст ошибки по имени поля. */
export function validateContacts(v: { email: string; phone: string; telegram: string; months: string }): Record<string, string> {
  const err: Record<string, string> = {};
  if (v.email && !EMAIL_RE.test(v.email)) err.email = E.invalidEmail;
  if (v.phone && v.phone.replace(/\D/g, "").length < 7) err.phone = E.invalidPhone;
  if (v.telegram && !/^@?[A-Za-z0-9_]{5,32}$/.test(v.telegram)) err.telegram = E.invalidTelegram;
  if (v.months) {
    const n = Number(v.months);
    if (!Number.isInteger(n) || n < 0 || n > 600) err.months = E.invalidExp;
  }
  return err;
}

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "unknown_skill") return E.errorUnknownSkill;
    if (err.code === "consent_required") return E.errorConsent;
  }
  return E.errorFallback;
}

function Chip({ on, children, ...p }: { on: boolean; children: React.ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-pressed={on}
      className={cn(
        "min-h-11 rounded-full border px-3 text-14 font-medium",
        on ? "border-brand bg-brand-tint text-brand-fg" : "border-hairline bg-card text-ink hover:border-brand-mid",
      )}
      {...p}
    >
      {children}
    </button>
  );
}

function Form({ p, skills }: { p: CandidateProfile; skills: TaxSkill[] }) {
  const qc = useQueryClient();
  const patch = usePatchProfileCandidatesMeProfilePatch();

  const nameOf = useMemo(() => new Map(skills.map((s) => [s.slug, s.name])), [skills]);
  const softAll = useMemo(() => skills.filter((s) => s.kind === "soft"), [skills]);

  const initialStack = useMemo<StackItem[]>(
    () => (p.skills ?? []).filter((s) => s.sources.includes("self")).map((s) => ({ slug: s.skill.slug, years: null })),
    [p.skills],
  );
  const initialSoft = useMemo(() => {
    const claimed = new Set((p.claimed_soft ?? []).map((x) => x.toLowerCase()));
    return softAll.filter((s) => claimed.has(s.slug) || claimed.has(s.name.toLowerCase())).map((s) => s.slug);
  }, [p.claimed_soft, softAll]);

  const [email, setEmail] = useState(p.contacts?.email ?? "");
  const [phone, setPhone] = useState(p.contacts?.phone ?? "");
  const [telegram, setTelegram] = useState(p.contacts?.telegram ?? "");
  const [months, setMonths] = useState(p.experience_months != null ? String(p.experience_months) : "");
  const [roles, setRoles] = useState<string[]>(p.desired_roles ?? []);
  const [stack, setStack] = useState<StackItem[]>(initialStack);
  const [stackTouched, setStackTouched] = useState(false);
  const [soft, setSoft] = useState<string[]>(initialSoft);
  const [softTouched, setSoftTouched] = useState(false);
  const [minor, setMinor] = useState(p.age_group === "minor");
  const [parent, setParent] = useState(!!p.parent_consent);
  const [ageTouched, setAgeTouched] = useState(false);
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [note, setNote] = useState<"saved" | string | null>(null);

  // Справочник приходит позже профиля: подставляем софт-навыки, пока человек их не трогал.
  useEffect(() => {
    if (!softTouched) setSoft(initialSoft);
  }, [initialSoft, softTouched]);

  const errors = validateContacts({ email: email.trim(), phone: phone.trim(), telegram: telegram.trim(), months: months.trim() });
  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const have = new Set(stack.map((s) => s.slug));
    return skills.filter((s) => !have.has(s.slug) && s.kind !== "soft" && (s.slug.includes(q) || s.name.toLowerCase().includes(q))).slice(0, 8);
  }, [query, skills, stack]);

  const editStack = (next: StackItem[]) => {
    setStack(next);
    setStackTouched(true);
  };
  const toggle = (list: string[], v: string, max = 99) => (list.includes(v) ? list.filter((x) => x !== v) : list.length >= max ? list : [...list, v]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    setNote(null);
    if (Object.keys(errors).length) return;
    const body: ProfileIn = {
      contacts: email.trim() || phone.trim() || telegram.trim() ? { email: email.trim() || null, phone: phone.trim() || null, telegram: telegram.trim() || null } : null,
      experience_months: months.trim() ? Number(months) : null,
      desired_roles: roles as ProfileIn["desired_roles"],
    };
    if (stackTouched) body.stack = stack;
    if (softTouched) body.soft_skills = soft;
    if (ageTouched) {
      body.age_group = minor ? "minor" : "adult";
      body.parent_consent = minor && parent;
    }
    try {
      await patch.mutateAsync({ data: body });
      await qc.invalidateQueries({ queryKey: getGetProfileCandidatesMeProfileGetQueryKey() });
      setNote("saved");
    } catch (err) {
      setNote(errorText(err));
    }
  }

  const show = (k: string) => (submitted ? errors[k] : undefined);

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4" data-testid="profile-edit-form">
      <Card className="flex flex-col gap-3 p-5">
        <h2 className="font-mono text-17 font-semibold">{E.contactsTitle}</h2>
        <p className="text-13 text-muted">{E.contactsHint}</p>
        <Field label={E.email} error={show("email")}>
          <FieldInput type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="profile-edit-email" />
        </Field>
        <Field label={E.phone} error={show("phone")}>
          <FieldInput type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} data-testid="profile-edit-phone" />
        </Field>
        <Field label={E.telegram} error={show("telegram")}>
          <FieldInput value={telegram} placeholder="@username" onChange={(e) => setTelegram(e.target.value)} data-testid="profile-edit-telegram" />
        </Field>
      </Card>

      <Card className="flex flex-col gap-3 p-5">
        <h2 className="font-mono text-17 font-semibold">{E.expTitle}</h2>
        <Field label={E.expMonths} error={show("months")}>
          <FieldInput inputMode="numeric" value={months} onChange={(e) => setMonths(e.target.value.replace(/\D/g, ""))} data-testid="profile-edit-months" />
        </Field>
      </Card>

      <Card className="flex flex-col gap-3 p-5" data-testid="profile-edit-roles">
        <h2 className="font-mono text-17 font-semibold">{E.rolesTitle}</h2>
        <p className="text-13 text-muted">{E.rolesHint}</p>
        <div className="flex flex-wrap gap-2">
          {ROLES.map((r) => (
            <Chip key={r} on={roles.includes(r)} onClick={() => setRoles((l) => toggle(l, r, MAX_ROLES))} data-testid={`profile-edit-role-${r}`}>
              {roleLabel(r)}
            </Chip>
          ))}
        </div>
      </Card>

      <Card className="flex flex-col gap-3 p-5" data-testid="profile-edit-stack">
        <h2 className="font-mono text-17 font-semibold">{E.stackTitle}</h2>
        <p className="text-13 text-muted">{E.stackHint}</p>
        <Field label={E.stackSearch}>
          <FieldInput value={query} onChange={(e) => setQuery(e.target.value)} data-testid="profile-edit-stack-search" />
        </Field>
        {suggestions.length > 0 && (
          <ul className="flex flex-wrap gap-2" data-testid="profile-edit-stack-suggest">
            {suggestions.map((s) => (
              <li key={s.slug}>
                <Chip
                  on={false}
                  data-testid={`profile-edit-stack-add-${s.slug}`}
                  onClick={() => {
                    editStack([...stack, { slug: s.slug, years: null }]);
                    setQuery("");
                  }}
                >
                  + {s.name}
                </Chip>
              </li>
            ))}
          </ul>
        )}
        {stack.length === 0 ? (
          <p className="text-13 text-muted">{E.stackNone}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {stack.map((s) => (
              <li key={s.slug} className="flex flex-wrap items-center gap-2" data-testid={`profile-edit-stack-${s.slug}`}>
                <Badge className="min-h-9">{nameOf.get(s.slug) ?? s.slug}</Badge>
                <label className="flex items-center gap-1 text-13 text-muted">
                  <input
                    aria-label={`${nameOf.get(s.slug) ?? s.slug}: ${E.stackYears}`}
                    inputMode="numeric"
                    className="h-11 w-16 rounded-lg border border-hairline bg-card px-2 text-ink"
                    value={s.years ?? ""}
                    onChange={(e) => {
                      const v = e.target.value.replace(/\D/g, "");
                      editStack(stack.map((x) => (x.slug === s.slug ? { ...x, years: v ? Math.min(60, Number(v)) : null } : x)));
                    }}
                  />
                  {E.stackYears}
                </label>
                <Button type="button" variant="ghost" size="sm" onClick={() => editStack(stack.filter((x) => x.slug !== s.slug))} data-testid={`profile-edit-stack-remove-${s.slug}`}>
                  {E.stackRemove}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {softAll.length > 0 && (
        <Card className="flex flex-col gap-3 p-5" data-testid="profile-edit-soft">
          <h2 className="font-mono text-17 font-semibold">{E.softTitle}</h2>
          <p className="text-13 text-muted">{E.softHint}</p>
          <div className="flex flex-wrap gap-2">
            {softAll.map((s) => (
              <Chip
                key={s.slug}
                on={soft.includes(s.slug)}
                data-testid={`profile-edit-soft-${s.slug}`}
                onClick={() => {
                  setSoftTouched(true);
                  setSoft((l) => toggle(l, s.slug));
                }}
              >
                {s.name}
              </Chip>
            ))}
          </div>
        </Card>
      )}

      <Card className="flex flex-col gap-3 p-5" data-testid="profile-edit-age">
        <h2 className="font-mono text-17 font-semibold">{E.ageTitle}</h2>
        <p className="text-13 text-muted">{E.ageHint}</p>
        <label className="flex min-h-11 items-center gap-2 text-14">
          <input
            type="checkbox"
            className="size-5 accent-brand"
            checked={minor}
            onChange={(e) => {
              setMinor(e.target.checked);
              if (!e.target.checked) setParent(false);
              setAgeTouched(true);
            }}
            data-testid="profile-edit-age-minor"
          />
          {E.ageMinor}
        </label>
        {minor && (
          <>
            <label className="flex min-h-11 items-center gap-2 text-14">
              <input
                type="checkbox"
                className="size-5 shrink-0 accent-brand"
                checked={parent}
                onChange={(e) => {
                  setParent(e.target.checked);
                  setAgeTouched(true);
                }}
                data-testid="profile-edit-age-parent"
              />
              {E.ageParent}
            </label>
            {!parent && (
              <p className="rounded-lg bg-tint-50 px-3 py-2 text-13" data-testid="profile-edit-age-hidden">
                {E.ageHidden}
              </p>
            )}
          </>
        )}
      </Card>

      {note === "saved" && (
        <p role="status" data-testid="profile-edit-saved" className="rounded-lg bg-tint-50 px-3 py-2 text-14">
          {E.saved}
        </p>
      )}
      {note && note !== "saved" && <ErrorNote data-testid="profile-edit-error">{note}</ErrorNote>}
      <Button type="submit" size="lg" loading={patch.isPending} data-testid="profile-edit-save">
        {patch.isPending ? E.saving : E.save}
      </Button>
    </form>
  );
}

export default function ProfileEdit() {
  const q = useGetProfileCandidatesMeProfileGet();
  const tax = useGetTaxonomyTaxonomyGet();
  const skills = useMemo(() => (tax.data?.data as { skills?: TaxSkill[] } | undefined)?.skills ?? [], [tax.data]);
  const p = q.data?.status === 200 ? (q.data.data as CandidateProfile) : null;

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-4" data-testid="profile-edit">
      <header className="flex flex-col gap-1">
        <Link to="/me" className="inline-flex min-h-11 items-center text-14 font-semibold text-brand-fg" data-testid="profile-edit-back">
          {E.back}
        </Link>
        <h1 className="text-24 font-bold">{E.title}</h1>
        <p className="text-14 text-muted">{E.lead}</p>
      </header>
      {q.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : q.isError || !p ? (
        <ErrorState title={E.loadError} onRetry={() => q.refetch()} />
      ) : (
        <Form p={p} skills={skills} />
      )}
    </section>
  );
}
