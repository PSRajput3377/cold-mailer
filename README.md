# Cold Mailer

A production-grade, modular system for sending **personalized cold emails** for
Software Engineer roles and referrals. It generates likely corporate email
addresses, resolves company domains, verifies deliverability, renders one of
200+ human-sounding templates with per-recipient personalization, attaches your
resume, sends through your provider of choice with retry, and logs everything.

Built for extension: LinkedIn automation, career-page / Greenhouse / Lever /
Ashby / Workday scraping, AI-generated emails, resume optimization, follow-up
scheduling, and an analytics dashboard all drop in as new modules without
touching the core pipeline.

---

## Features at a glance

| Step | Capability | Module |
|------|------------|--------|
| 1 | Generate every common corporate email format | `email_generator.py` |
| 2 | Auto-resolve company domain (Clearbit + DNS + guessing) | `domain_resolver.py` |
| 3 | 200+ templates across 10 categories (20 each) | `templates/`, `template_engine.py` |
| 4 | Auto-inject company, person, role, job id, resume highlights, skills, links | `context_builder.py` |
| 5 | `{{placeholder}}` support (Jinja2) | `template_engine.py` |
| 6 | 100+ subject-line variations | `subject_generator.py` |
| 7 | Personalization engine (greeting/closing/CTA/paragraph order) | `personalization.py` |
| 8 | Senders: Gmail, Outlook, SendGrid, AWS SES, MS Graph + retry | `email_sender.py` |
| 9 | Email verification (SMTP probe or API) | `email_verifier.py` |
| 10 | CSV logging (sent / failed / verified / duplicates / replies) | `logger.py` |
| 11 | Duplicate-contact avoidance | `logger.py` + `app.py` |
| 12 | Attachments (resume / cover letter / transcript / portfolio) | `email_sender.py` |
| 13 | Everything driven by `config.yaml` | `config.py` |

---

## Project structure

```
cold_mailer/
├── app.py                # orchestrator + CLI (send / preview / emails)
├── config.py             # config.yaml loader with ${ENV} expansion
├── models.py             # Candidate / Recipient / Designation
├── email_generator.py    # Step 1 — email-format permutations
├── domain_resolver.py    # Step 2 — company name -> domain
├── template_engine.py    # Step 3/5 — load + render templates
├── subject_generator.py  # Step 6 — 100+ subject lines
├── personalization.py    # Step 7 — vary surface features
├── context_builder.py    # Step 4/5 — assemble placeholder context
├── resume_parser.py      # extract skills/highlights/internship from PDF
├── email_verifier.py     # Step 9 — verify addresses
├── email_sender.py       # Step 8/12 — providers, MIME, attachments, retry
├── logger.py             # Step 10/11 — CSV logs + dedup
├── utils.py              # shared helpers
├── templates/            # per-category YAML template files
├── sources/              # job-board scrapers (Greenhouse / Lever / Ashby)
├── tests/                # offline test suite
├── assets/               # your resume / cover letter / etc. (git-ignored)
├── logs/                 # CSV output (git-ignored)
├── config.example.yaml   # config template — copy to config.yaml
├── config.yaml           # your local config (git-ignored)
├── ai_generator.py       # optional Claude-written emails
├── .env.example          # secrets template
└── requirements.txt
```

---

## Complete example (start to finish)

A full walkthrough for one realistic scenario: **Sam Lee, a new-grad software
engineer, reaching out to three companies.** Copy-paste each block.

**1. Set up the project**

```bash
git clone https://github.com/PSRajput3377/cold-mailer.git
cd cold-mailer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**2. Add Gmail credentials** to `.env` (copy `cp .env.example .env` first):

```env
GMAIL_USERNAME=sam.lee@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop      # 16-char Google App Password
```

**3. Create your config and set yourself as the sender.** Copy the template
(your real `config.yaml` is git-ignored, so it never ends up in the repo):

```bash
cp config.example.yaml config.yaml
```

Then edit `config.yaml`:

```yaml
sender:
  name: "Sam Lee"
  email: "sam.lee@gmail.com"
  phone: "+1-555-0100"
provider: "gmail"
dry_run: true                # keep true until you've previewed
```

**4. Drop your resume** at `assets/resume.pdf` (skills, highlights, and your most
recent internship are pulled from it automatically).

**5. Create `my_recipients.csv`:**

```csv
company_name,company_domain,person_first_name,person_last_name,designation,job_title,job_id
Stripe,stripe.com,Jane,Doe,Recruiter,Backend Engineer,JR-4821
DevRev,devrev.ai,John,Roe,Engineering Manager,Software Engineer,
Figma,,Pat,Loe,HR,New Grad Software Engineer,
```

Only `company_name`, `person_first_name`, `person_last_name`, and `designation`
are required. Leave `company_domain` blank to have it auto-resolved.

**6. Preview before anything is sent** (this never sends email):

```bash
python app.py preview \
  --recipients my_recipients.csv \
  --name "Sam Lee" \
  --from-email sam.lee@gmail.com \
  --linkedin "linkedin.com/in/samlee" \
  --github "github.com/samlee" \
  --portfolio "samlee.dev"
```

You'll see, for each person: the guessed address, a chosen subject line, the
template used, and the full rendered body. Example output:

```
======================================================================
To:      jane.doe@stripe.com
Subject: Referral for Job ID JR-4821
[template | applied_requesting_referral / applied_requesting_referral_18]
Attach:  ['/.../assets/resume.pdf']
----------------------------------------------------------------------
Hi Jane,

I recently applied to Backend Engineer (Job ID JR-4821) at Stripe...
```

**7. Dry-run the send** (logs to `logs/emails_sent.csv`, still sends nothing
because `dry_run: true`):

```bash
python app.py send --recipients my_recipients.csv \
  --name "Sam Lee" --from-email sam.lee@gmail.com \
  --linkedin "linkedin.com/in/samlee" --github "github.com/samlee" --portfolio "samlee.dev"
```

**8. Send for real** — set `dry_run: false` in `config.yaml`, then run the exact
same `send` command. Already-contacted people are skipped automatically.

> The detailed step-by-step guide below expands on each of these with options,
> other email providers, and troubleshooting.

---

## How to use (step by step)

Follow these steps in order the first time you run Cold Mailer. Each step builds
on the previous one.

### What you need before starting

- **Python 3.10+** installed on your machine (`python3 --version` to check).
- An **email account** you are allowed to send from (Gmail is the easiest to start
  with).
- A **resume PDF** you want to attach.
- A **recipients CSV** — a spreadsheet of people and companies you want to contact
  (a sample file is included).

---

### Step 1 — Get the code

Clone the repository and move into the project folder:

```bash
git clone https://github.com/PSRajput3377/cold-mailer.git
cd cold-mailer
```

If you already downloaded the folder, just `cd` into it.

---

### Step 2 — Create a virtual environment and install dependencies

A virtual environment keeps this project's packages separate from the rest of
your system.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

You should see `(.venv)` at the start of your terminal prompt. Run all later
commands from this folder with the venv activated.

---

### Step 3 — Add your secrets (`.env` file)

Credentials must **not** go in `config.yaml`. They live in a local `.env` file
that is never committed to git.

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in the values for your email provider.

**Gmail (recommended for beginners)**

1. Turn on [2-Step Verification](https://myaccount.google.com/security) on your
   Google account.
2. Create an [App Password](https://myaccount.google.com/apppasswords) (choose
   "Mail" and your device).
3. In `.env`, set:

```env
GMAIL_USERNAME=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

Use the 16-character App Password — **not** your normal Gmail login password.

**Other providers** — fill in the matching block in `.env` (`OUTLOOK_*`,
`SENDGRID_API_KEY`, `AWS_*`, or `MS_*`) and set `provider` in `config.yaml` to
`outlook`, `sendgrid`, `ses`, or `graph`.

---

### Step 4 — Create and edit `config.yaml`

Copy the template, then open `config.yaml` and update at least these sections.
Your `config.yaml` is git-ignored so your personal details stay local:

```bash
cp config.example.yaml config.yaml
```

| Setting | What to change |
|---------|----------------|
| `sender.name` | Your full name (appears in the email signature). |
| `sender.email` | The address you send from (must match your provider account). |
| `sender.phone` | Your phone number (optional, used in signature). |
| `provider` | `gmail` (or `outlook`, `sendgrid`, `ses`, `graph`). |
| `attachments.resume` | Path to your resume PDF (default: `assets/resume.pdf`). |
| `dry_run` | Leave as `true` until you are ready to send for real. |

Example:

```yaml
sender:
  name: "Alex Johnson"
  email: "alex.j@gmail.com"
  phone: "+1-555-123-4567"

provider: "gmail"

attachments:
  resume: "assets/resume.pdf"
  attach_resume: true

dry_run: true   # keep true until Step 9
```

**Rate limits** (optional but recommended): `rate_limit.emails_per_hour` and
`seconds_between_emails` control how fast emails go out. Defaults are conservative
(30/hour, 45 seconds apart).

---

### Step 5 — Put your resume in `assets/`

```bash
mkdir -p assets
cp /path/to/your/resume.pdf assets/resume.pdf
```

The `assets/` folder is git-ignored so your personal files stay local. You can
also add `cover_letter.pdf`, `transcript.pdf`, or `portfolio.pdf` and point to
them in `config.yaml` under `attachments`.

Cold Mailer reads your resume PDF to pull **skills**, **highlights**, and
**internship** details into the email body automatically.

---

### Step 6 — Build your recipients CSV

Copy the sample file and edit it with your targets:

```bash
cp recipients.sample.csv my_recipients.csv
```

Open `my_recipients.csv` in Excel, Google Sheets, or a text editor.

**Required columns**

| Column | Example | Notes |
|--------|---------|-------|
| `company_name` | `Stripe` | Company you are reaching out to. |
| `person_first_name` | `Jane` | Recipient's first name. |
| `person_last_name` | `Doe` | Recipient's last name. |
| `designation` | `Recruiter` | See allowed values below. |

**Optional columns** (improve personalization)

| Column | Example | Notes |
|--------|---------|-------|
| `company_domain` | `stripe.com` | Skip domain guessing if you know it. |
| `job_title` | `Backend Engineer` | Role you are applying for. |
| `job_id` | `JR-4821` | Internal job ID if you have it. |
| `job_url` | `https://...` | Link to the job posting. |

**Allowed `designation` values:** `HR`, `Recruiter`, `Talent Acquisition`,
`Engineering Manager`, `Software Engineer`, `Founder`.

The system picks an email template category based on designation:

| Designation | Category | What the email does |
|-------------|----------|---------------------|
| HR, Recruiter, Talent Acquisition | `professional_application` | A formal application — introduces you and asks them to consider you for openings. **Does not** ask for a referral. |
| Engineering Manager, Software Engineer, Founder | `referral_request` | A warmer note asking the person to refer you. |

Override the auto-pick with `--category professional_application` (or
`--category referral_request`) on the command line.

**Linking specific roles in a referral:** put one or more job URLs in the
`job_url` column, separated by `|` (or `;`) for multiple roles:

```csv
DevRev,devrev.ai,John,Roe,Software Engineer,,,https://devrev.ai/jobs/1|https://devrev.ai/jobs/2
```

When `job_url` has a value, the referral email automatically lists the role
links and adjusts its wording ("this role" vs. "either of these roles"). With no
`job_url`, it sends a clean general referral note instead.

---

### Step 7 — Preview emails (nothing is sent)

Always preview first. This renders the full subject, body, and attachment list
for every row in your CSV **without** sending anything.

```bash
python app.py preview \
  --recipients my_recipients.csv \
  --name "Alex Johnson" \
  --from-email alex.j@gmail.com \
  --linkedin "linkedin.com/in/alexjohnson" \
  --github "github.com/alexjohnson" \
  --portfolio "alexjohnson.dev" \
  --role "Software Engineer"
```

**CLI flags you can pass**

| Flag | Purpose |
|------|---------|
| `--name` | Your name (overrides `config.yaml` sender name). |
| `--from-email` | Your sending address. |
| `--resume` | Path to resume PDF (overrides config). |
| `--linkedin`, `--github`, `--portfolio` | Inserted into templates and signature. |
| `--role` | Target role (default: `Software Engineer`). |
| `--category` | Force a template category (e.g. `referral_request`). |
| `--config` | Use a different config file (default: `config.yaml`). |

Read each preview block carefully. Check spelling, tone, placeholders, and that
the right template was chosen.

---

### Step 8 — Inspect generated email addresses (optional)

Cold Mailer guesses corporate email formats (e.g. `jane.doe@stripe.com`,
`jdoe@stripe.com`) and verifies them. To see candidate addresses without
rendering full emails:

```bash
python app.py emails --recipients my_recipients.csv --name "Alex Johnson"
```

If a company's domain is wrong, add `company_domain` to that row in your CSV and
run again.

---

### Step 9 — Dry-run send (logs only, still no real emails)

With `dry_run: true` in `config.yaml` (the default), the `send` command runs the
full pipeline — verification, template rendering, attachment prep, and logging —
but **does not** deliver mail to inboxes.

```bash
python app.py send \
  --recipients my_recipients.csv \
  --name "Alex Johnson" \
  --from-email alex.j@gmail.com \
  --linkedin "linkedin.com/in/alexjohnson" \
  --github "github.com/alexjohnson"
```

Check the terminal output and the log files in `logs/`:

| File | Contents |
|------|----------|
| `emails_sent.csv` | Emails that would be / were sent successfully. |
| `emails_failed.csv` | Failures with error messages. |
| `verified_addresses.csv` | Address verification results. |
| `duplicate_addresses.csv` | Skipped because already contacted before. |

Re-running `send` later skips anyone already listed in `emails_sent.csv`.

---

### Step 10 — Send for real

When previews look good and dry-run logs are correct:

1. Open `config.yaml`.
2. Set `dry_run: false`.
3. Run the same `send` command from Step 9.

```bash
python app.py send \
  --recipients my_recipients.csv \
  --name "Alex Johnson" \
  --from-email alex.j@gmail.com
```

Emails are sent one at a time with a delay between each (`seconds_between_emails`
in config) to respect rate limits. The run stops after `max_per_run` recipients
(default: 100).

> **Safety:** Start with a small CSV (2–3 people) for your first real send.
> Set `dry_run: true` again when you are done testing.

---

### Step 11 — Run tests (optional)

Verify the pipeline works offline (no network, no SMTP):

```bash
python tests/test_pipeline.py
```

---

### Quick reference — all commands

```bash
# Preview rendered emails (safe — never sends)
python app.py preview --recipients my_recipients.csv --name "Your Name" --from-email you@gmail.com

# List guessed email addresses only
python app.py emails --recipients my_recipients.csv --name "Your Name"

# Send (respects dry_run in config.yaml)
python app.py send --recipients my_recipients.csv --name "Your Name" --from-email you@gmail.com

# Scrape open roles from a company's ATS board (optional)
python app.py jobs --source greenhouse --board stripe --keywords "Software Engineer"
```

---

### Troubleshooting

| Problem | What to try |
|---------|-------------|
| `Authentication failed` (Gmail) | Use an App Password, not your login password. Enable 2FA first. |
| No email address found for recipient | Add `company_domain` to the CSV row. |
| Recipient skipped as duplicate | They are in `logs/emails_sent.csv` from a prior run. |
| Recipient skipped as invalid | Check `logs/verified_addresses.csv`. Set `verification.accept_risky: true` for catch-all domains, or use `strategy: none`. |
| `dry_run is ON` warning | Expected while testing. Set `dry_run: false` only when ready. |
| Resume skills not showing | Confirm `assets/resume.pdf` exists and is a readable PDF. |
| Module not found | Activate the venv: `source .venv/bin/activate` |

---

### Optional: AI-generated emails

Set in `config.yaml`:

```yaml
ai:
  enabled: true
  api_key: "${ANTHROPIC_API_KEY}"
```

Add `ANTHROPIC_API_KEY=sk-...` to `.env`. When enabled, each email is written
by the AI using the recipient and job details, with templates as fallback.

### Optional: Job-board scraping

Set `job_sources.enabled: true` in `config.yaml`, or use the CLI:

```bash
python app.py jobs --source lever --board company-slug
```

Add `ats_vendor` and `ats_board_token` columns to your CSV to auto-fill job
titles and URLs per company.

---

## Recipient CSV format

Required: `company_name`, `person_first_name`, `person_last_name`, `designation`.
Optional: `company_domain`, `job_title`, `job_id`, `job_url`.

```csv
company_name,company_domain,person_first_name,person_last_name,designation,job_title,job_id,job_url
Stripe,,Jane,Doe,Recruiter,Backend Engineer,JR-4821,https://stripe.com/jobs/4821
DevRev,devrev.ai,John,Roe,Engineering Manager,Software Engineer,,
```

`designation` is one of: `HR`, `Recruiter`, `Talent Acquisition`,
`Engineering Manager`, `Software Engineer`, `Founder`. The system picks a
sensible template category per designation (e.g. engineers → referral requests,
recruiters → job inquiries) unless you force one with `--category`.

---

## Template categories

Two categories are wired to the designation auto-pick and used by default:

- **`professional_application`** — formal application for HR / Recruiters.
- **`referral_request`** — referral ask for engineers / managers / founders,
  with optional role-link support (see the recipient CSV section).

A larger library of generic categories also ships and can be enabled in
`config.yaml` (`templates.enabled_categories`) or forced with `--category`:
`job_opening_inquiry`, `resume_review_request`, `circulate_resume`,
`swe_opportunity`, `new_grad`, `applied_requesting_referral`,
`followup_after_application`, `followup_after_recruiter`, `informational_chat`.

> By default `config.yaml` enables only `professional_application` and
> `referral_request`. Set `enabled_categories: []` to load every category.

Templates live in `templates/<category>.yaml` and use `{{placeholders}}`. Add or
edit freely — they're loaded at runtime. Available placeholders include
`{{first_name}}`, `{{company}}`, `{{role}}`, `{{job_title}}`, `{{job_id}}`,
`{{job_url}}`, `{{job_urls_list}}` (a list, for `{% for %}`), `{{candidate_name}}`,
`{{candidate_email}}`, `{{skills}}`, `{{resume_highlights}}`, `{{top_highlight}}`,
`{{recent_internship}}`, `{{github}}`, `{{linkedin}}`, `{{portfolio}}`,
`{{greeting}}`, `{{cta}}`, and `{{signature}}`. A template may define its own
`subject:` (rendered with the same placeholders); otherwise a subject is
auto-generated.

---

## Providers

Set `provider` in `config.yaml` to one of `gmail | outlook | sendgrid | ses |
graph` and fill the matching block. Gmail requires an **App Password** (not your
login). SendGrid/SES/Graph extras are commented in `requirements.txt` — install
the one you use.

---

## Verification

`config.yaml → verification.strategy`:
- `none` — syntax check only.
- `smtp` — free MX + SMTP RCPT probe (no third party; install `dnspython` for
  proper MX lookup). Big providers often return "unknown"; `accept_risky`
  controls whether those are sent.
- `api` — Abstract / Hunter / NeverBounce (set the key in `.env`).

Invalid addresses are skipped and logged to `logs/verified_addresses.csv`.

---

## Logs (`logs/`)

`emails_sent.csv`, `emails_failed.csv`, `verified_addresses.csv`,
`duplicate_addresses.csv`, `reply_tracking.csv`. The sent log doubles as the
dedup source — a recipient already in it is skipped on future runs.

---

## Tests

```bash
python tests/test_pipeline.py          # or: python -m pytest tests/ -q
```

Fully offline — no network, SMTP, or API calls.

---

## Job-board scraping (Greenhouse / Lever / Ashby)

Pull open roles straight from a company's applicant-tracking system (no API key
needed) to auto-fill `job_title` / `job_id` / `job_url` — and to feed the AI
generator the real job description.

List roles from the CLI:

```bash
python app.py jobs --source greenhouse --board stripe --keywords "Software Engineer"
python app.py jobs --source ashby      --board Ashby  --keywords Engineer
python app.py jobs --source lever      --board <slug>
```

`--board` is the company's slug on that ATS (e.g. `stripe` →
`boards.greenhouse.io/stripe`). To enrich recipients automatically during a
send, set `job_sources.enabled: true` in `config.yaml` and add `ats_vendor` /
`ats_board_token` columns to your recipients CSV. The pipeline matches the best
open role per recipient and fills any empty job fields.

Adding another ATS (Workday, SmartRecruiters, …) is one `JobSource` subclass in
`sources/` registered in `sources/__init__.py` — nothing else changes.

## AI-generated emails (Claude)

Instead of templates, let Claude write each email tailored to the recipient,
category, and scraped job description. Set in `config.yaml`:

```yaml
ai:
  enabled: true
  model: "claude-opus-4-8"
  effort: "medium"
```

and put `ANTHROPIC_API_KEY` in `.env` (or `ai.api_key`). The generator returns a
validated `{subject, body}`, reuses the same greeting/signature/personalization,
and **falls back to the template engine** on any error (no key, network failure,
refusal) — so a missing key degrades gracefully rather than breaking a run. The
`source` column in `emails_sent.csv` records whether each email was `ai` or
`template`.

## Extending further

The orchestrator (`app.py`) only sequences modules, so new capability is mostly
new modules:

- **New sender** → subclass `EmailProvider` in `email_sender.py`, add to
  `build_provider`.
- **Follow-up scheduling** → a scheduler reading `emails_sent.csv` /
  `reply_tracking.csv` and re-queuing recipients with a follow-up category.
- **Analytics dashboard** → read the CSVs (already pandas-friendly via
  `CsvLogger.load`).
- **LinkedIn automation / career-page scraping** → new `sources/` adapters that
  yield `Recipient` objects into the existing pipeline.

---

## Responsible use

Send only to people you have a legitimate reason to contact, honor unsubscribe
requests, respect each provider's terms and rate limits, and comply with
anti-spam law (CAN-SPAM, GDPR, CASL). The built-in rate limiting and `dry_run`
default exist to keep you on the right side of this.
