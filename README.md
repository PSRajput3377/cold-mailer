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
├── templates/            # 10 YAML files, 20 templates each
├── tests/                # offline test suite
├── assets/               # your resume / cover letter / etc. (git-ignored)
├── logs/                 # CSV output (git-ignored)
├── config.yaml           # all configuration
├── .env.example          # secrets template
└── requirements.txt
```

---

## Quick start

```bash
# 1. Install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure secrets
cp .env.example .env          # then fill in your provider credentials

# 3. Configure behaviour
#    Edit config.yaml — set `sender`, `provider`, attachment paths, etc.
#    Put your resume at assets/resume.pdf (or update attachments.resume).

# 4. Build your recipient list (see recipients.sample.csv)

# 5. Preview without sending (no emails go out)
python app.py preview --recipients recipients.sample.csv \
    --name "Your Name" --from-email you@gmail.com \
    --linkedin "linkedin.com/in/you" --github "github.com/you" \
    --portfolio "you.dev"

# 6. Just inspect generated candidate addresses
python app.py emails --recipients recipients.sample.csv --name "Your Name"

# 7. Send (config.yaml `dry_run: true` logs without sending — flip to false to send)
python app.py send --recipients recipients.sample.csv \
    --name "Your Name" --from-email you@gmail.com
```

> **Safety:** `dry_run: true` is the default in `config.yaml`. Nothing is sent
> until you set it to `false`. Always run `preview` first.

---

## Recipient CSV format

Required: `company_name`, `person_first_name`, `person_last_name`, `designation`.
Optional: `company_domain`, `job_title`, `job_id`, `job_url`.

```csv
company_name,company_domain,person_first_name,person_last_name,designation,job_title,job_id,job_url
Stripe,,Jane,Doe,Recruiter,Backend Engineer,JR-4821,https://stripe.com/jobs/4821
DevRev,devrev.ai,Aarav,Sharma,Engineering Manager,Software Engineer,,
```

`designation` is one of: `HR`, `Recruiter`, `Talent Acquisition`,
`Engineering Manager`, `Software Engineer`, `Founder`. The system picks a
sensible template category per designation (e.g. engineers → referral requests,
recruiters → job inquiries) unless you force one with `--category`.

---

## Template categories (10 × 20 = 200)

`referral_request`, `job_opening_inquiry`, `resume_review_request`,
`circulate_resume`, `swe_opportunity`, `new_grad`,
`applied_requesting_referral`, `followup_after_application`,
`followup_after_recruiter`, `informational_chat`.

Templates live in `templates/<category>.yaml` and use `{{placeholders}}`. Add or
edit freely — they're loaded at runtime. Available placeholders include
`{{first_name}}`, `{{company}}`, `{{role}}`, `{{job_title}}`, `{{job_id}}`,
`{{skills}}`, `{{resume_highlights}}`, `{{top_highlight}}`,
`{{recent_internship}}`, `{{github}}`, `{{linkedin}}`, `{{portfolio}}`,
`{{greeting}}`, `{{cta}}`, and `{{signature}}`.

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

## Extending

The orchestrator (`app.py`) only sequences modules, so new capability is mostly
new modules:

- **New sender** → subclass `EmailProvider` in `email_sender.py`, add to
  `build_provider`.
- **Job-board scraping** (Greenhouse / Lever / Ashby / Workday) → a new
  `sources/` module that yields `Recipient` objects into the existing pipeline.
- **AI-generated emails** → a `TemplateEngine`-compatible renderer backed by an
  LLM; swap it in `prepare()`.
- **Follow-up scheduling** → a scheduler reading `emails_sent.csv` /
  `reply_tracking.csv` and re-queuing recipients with a follow-up category.
- **Analytics dashboard** → read the CSVs (already pandas-friendly via
  `CsvLogger.load`).

---

## Responsible use

Send only to people you have a legitimate reason to contact, honor unsubscribe
requests, respect each provider's terms and rate limits, and comply with
anti-spam law (CAN-SPAM, GDPR, CASL). The built-in rate limiting and `dry_run`
default exist to keep you on the right side of this.
