# Trip notification emails (US-17 and US-20)

Each trip member, including the administrator, gets an individual Arabic and English message when a new batch of proposals is saved. The message links to the trip even if the batch contains just one usable option. When a revision is saved, members get a link to the current proposal and a link to the trip. Both links use the application's existing sign-in and membership checks.

## Enable delivery

For Gmail, first enable Google two-step verification and create an app password.
Set these values in `backend/.env`, apply the SQL migration described below, and
restart FastAPI. Gmail uses its address as the sender.

```dotenv
TRIP_EMAIL_PROVIDER=gmail
GMAIL_ADDRESS=your-account@gmail.com
GMAIL_APP_PASSWORD=your-app-password
TRIP_APP_URL=http://localhost:5173
TRIP_EMAILS_ENABLED=true
```

Use the deployed frontend URL when recipients open links on their own devices.
Gmail delivery uses encrypted SMTP. It retries temporary failures, but SMTP has
no provider idempotency guarantee. An ambiguous disconnect after submission or
a failed database acknowledgment can cause a duplicate email. Stable Message-ID
headers identify retries but do not guarantee recipient deduplication.

For Resend, set `TRIP_EMAIL_PROVIDER=resend` and follow these steps.

1. Apply pending Supabase migrations in filename order. The email migration is `20261118000200_trip_email_notifications.sql` and follows `20261118000100_proposal_feedback.sql`. It starts collecting new events as soon as it is applied.
2. Verify a sender domain in Resend and create an API key with sending access to that domain. [Resend domain setup](https://resend.com/docs/dashboard/domains/introduction)
3. Set the following in `backend/.env`. Replace the example addresses with your verified sender and the HTTPS frontend origin your members can open. The backend also uses its existing `SUPABASE_URL` and `SUPABASE_SECRET_KEY`.

   ```dotenv
   TRIP_EMAILS_ENABLED=true
   RESEND_API_KEY=your-resend-sending-key
   TRIP_EMAIL_FROM=Rihla <trips@your-verified-domain.example>
   TRIP_APP_URL=https://your-frontend.example
   ```

4. Restart FastAPI and keep it running for delivery. A local origin such as `http://localhost:5173` is suitable for testing links on the machine running Vite.

## Verify with test accounts

Generate and save proposals for a trip containing two test members. Each should receive one message and be able to open the trip after signing in. Refresh the trip page and check that no new email arrives. Submit a revision that saves successfully and open the proposal link as the other member. The current version appears first and earlier versions are available on the proposal page.

## Check delivery

The database queues messages in the same transaction as the proposal change. A backend worker delivers pending messages, including those queued while delivery was disabled. Removing a member cancels their queued jobs. The worker retries temporary failures with backoff and reuses the same provider idempotency key. It stops after eight attempts or when an earlier attempt is more than 23 hours old.

Inspect job totals from the Supabase SQL Editor:

```sql
select state, count(*) from rihla_private.trip_email_jobs group by state;
```

`pending` includes scheduled retries. `sent` means Resend accepted the email. Check the Resend dashboard for inbox delivery or bounce details. For `failed` jobs, check the sender configuration and provider logs.
