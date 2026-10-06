# Manual test cases

Questions to ask the assistant by hand, with the answers to expect. They check every feature, the access rules, and that the assistant refuses rather than invents.

The expected answers come from the fake bank (`backend/packs/banking/adapters/fake.py`) and the sample documents (`backend/packs/banking/evals/documents/`). They hold only while the stack runs on the fake bank (`JUTANT_BANKING_ADAPTERS=fake`) with those documents ingested. The automated version of most of these is `manage.py run_evals` (see the README).

## Setup

1. Start the stack and open the assistant at http://localhost:8080 (see "Run with Docker" in the README).
2. Ingest the sample documents, as `backend/packs/banking/evals/documents/README.md` shows. This needs the embedding model.
3. Create a test user, and give them a staff record with role `teller` and attributes `{"branch": "ACC-01"}`:
   - create the user with `docker compose -f infra/docker-compose.yml exec api python manage.py createsuperuser`;
   - add the staff record in the admin at http://localhost:8080/admin, under Identity → Staff.
4. Sign in to the assistant as that user.

Some cases need a different role or branch. Change them on the user's staff record in the admin; the change applies to the next question, with no need to sign in again. Set the user back to teller at ACC-01 afterwards.

On a CPU model host an answer takes 1–3 minutes. The customer summary is the slowest.

## As a teller at ACC-01

| # | Ask | Expect |
|---|---|---|
| 1 | What ID do joint account holders need? | Each holder's own photo ID (Ghana Card or passport) and proof of address from the last 3 months; all holders sign the joint mandate form. Source: KYC Policy, 4.2 |
| 2 | What does a minor need to open an account? | The guardian's ID and the minor's birth certificate. Source: KYC Policy, 4.3 |
| 3 | What does error code E12 mean? | Insufficient funds. Also try E51 (beneficiary account closed) and E91 (issuer unavailable) |
| 4 | What is the interest rate on Standard Savings? | 8.5% |
| 5 | What is the monthly fee on the Business Current account? | 25.00 |
| 6 | Why did transfer TX-0002 fail? | Failed with E51, beneficiary account closed |
| 7 | Show the last 3 transactions on account 0011223344 | Newest first: TX-0003 salary +3000, TX-0002 failed −1200, TX-0001 ATM withdrawal −250 |
| 8 | Show the credits on account 0011223355 | TX-0004, +500 |
| 9 | What forms and signatures does a joint account opening need? | Account opening form and joint mandate form; all account holders sign; the customer service supervisor approves |
| 10 | Summarise circular 14/2026 | Tellers can reactivate dormant accounts at any branch; the customer completes the form and shows photo ID; branch manager approval only if dormant for more than 5 years; effective 1 November 2026 |
| 11 | A customer's card is blocked. Walk me through it. | Step cards: verify the customer, then pick the block reason. "Fraud hold" leads to referring the case to the fraud team; "expired" leads to ordering a replacement. Typing `cancel` ends the walkthrough |
| 11b | I had a failed transfer (then reply `12345678`, then `TX-0002`) | Step 1 asks for the reference. `12345678` is refused: "I could not find a reference in that". `TX-0002` is looked up, the status step answers itself ("Check the status: failed (from the record)"), and step 3 reads "Transfer TX-0002 failed: Beneficiary account closed (code E51)…". At branch KSI-02, the same reference gives "You don't have access to TX-0002" |

## Refusals: nothing invented, nothing leaked

| # | Ask | Expect |
|---|---|---|
| 12 | Show the transactions on account 0099887766 | Refused: the account belongs to branch KSI-02 |
| 13 | Give me a summary of customer C1001 | Refused: tellers may not use the customer summary |
| 14 | Why did transfer TX-0099 fail? | Not found; no made-up reason |
| 15 | What is the bank's policy on cryptocurrency? | "I could not find a source…", not an invented answer |

## As customer service at ACC-01

| # | Ask | Expect |
|---|---|---|
| 16 | Give me a summary of customer C1001 | Ama Mensah, 2 accounts, total balance GHS 6021.25, failed transaction TX-0002, open request REQ-77 (card replacement) |
| 17 | Give me a summary of customer C1002 | Refused: the customer belongs to branch KSI-02. Change the branch to KSI-02 and ask again: Kofi Asante, a dormant savings account, flag `kyc_review_due` |

## As a branch manager

| # | Ask | Expect |
|---|---|---|
| 18 | Show the transactions on account 0099887766 | Allowed at any branch: TX-0005, account maintenance fee −40 |

## Upload

| # | Do | Expect |
|---|---|---|
| 19 | Upload a photo or PDF of an ID card and ask "Extract the fields from this ID card" | Full name, ID number, date of birth and expiry date. A field it cannot read shows as "not found", never a guess |

## After each answer, check

- The sources listed under the answer match the expected document section or record.
- The tool activity shown while it runs matches the question (search, product, transaction or customer lookup).
- In the admin, the audit log has an entry for each tool call, with account numbers masked to their last 4 digits.

## If something fails

- **Sign-in says "too many failed sign-ins".** After 5 wrong passwords a username is locked for 15 minutes, even for the right password. Wait, or delete the user's recent rows in the admin's sign-in attempts (Identity → Login attempts).
- **"The assistant is unavailable right now".** The model host is unreachable. Check `JUTANT_LLM_BASE_URL` in `backend/.env` and the health page at http://localhost:8080/api/health.
- **Policy questions give "I could not find a source".** The sample documents are not ingested, or were embedded with a different model. Run `manage.py reindex`.
