import { Button, EmptyState, Skeleton, buttonVariants } from "@fsp/ui";
import { useNavigate, useParams, Link } from "react-router-dom";

import { useInviteAcceptCompanyInvitesTokenAcceptPost, useInvitePreviewCompanyInvitesTokenGet } from "@/api/endpoints/companies/companies";
import { ApiError } from "@/api/mutator";
import { AuthCard, ErrorNote } from "@/features/auth/ui";
import { useAuth } from "@/shared/lib/auth";
import { INVITE as T } from "./text";

/**
 * Приглашение в команду компании: `/invite/company/:token`, без входа видно, кто и куда зовёт.
 * Аноним — «Войти» / «Зарегистрироваться» с возвратом сюда; работодатель — «Принять».
 */
export default function InviteAccept() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const { me, status, reloadMe } = useAuth();
  const q = useInvitePreviewCompanyInvitesTokenGet(token, { query: { retry: false } });
  const accept = useInviteAcceptCompanyInvitesTokenAcceptPost({
    mutation: {
      onSuccess: async () => {
        await reloadMe();
        navigate("/employer/company", { replace: true });
      },
    },
  });
  const here = `/invite/company/${token}`;

  if (q.isPending || status === "loading") return <Skeleton className="mx-auto my-8 h-64 w-full max-w-[440px]" />;
  const invite = q.data?.status === 200 ? q.data.data : null;
  if (!invite)
    return (
      <div className="mx-auto w-full max-w-xl px-4 py-8" data-testid="invite-invalid">
        <EmptyState
          title={T.invalid}
          description={T.invalidHint}
          action={
            <Link to="/" className={buttonVariants({ variant: "outline" })}>
              {T.toHome}
            </Link>
          }
        />
      </div>
    );

  const code = accept.error instanceof ApiError ? accept.error.code : undefined;
  return (
    <AuthCard title={T.title} lead={T.lead(invite.company_name, invite.inviter_name ?? null)}>
      <div className="flex flex-col gap-2 text-14" data-testid="invite-card">
        <p>{T.role}</p>
        <p className="text-muted" data-testid="invite-email">
          {T.forEmail(invite.email_masked)}
        </p>
      </div>
      {status !== "authenticated" || !me ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <Link to="/login" state={{ from: here }} className={buttonVariants({ size: "lg" })} data-testid="invite-login">
            {T.login}
          </Link>
          <Link to="/register" state={{ from: here, role: "employer" }} className={buttonVariants({ size: "lg", variant: "outline" })} data-testid="invite-register">
            {T.register}
          </Link>
        </div>
      ) : me.role !== "employer" ? (
        <ErrorNote data-testid="invite-not-employer">{T.notEmployer}</ErrorNote>
      ) : (
        <>
          {accept.isError && <ErrorNote data-testid="invite-error">{T.error(code)}</ErrorNote>}
          <Button size="lg" loading={accept.isPending} onClick={() => accept.mutate({ token })} data-testid="invite-accept">
            {T.accept}
          </Button>
        </>
      )}
    </AuthCard>
  );
}
