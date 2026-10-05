# Payment error codes (SAMPLE)

## E12 Insufficient funds

The paying account did not have enough available balance. Next step: ask the customer to fund
the account and retry the payment.

## E51 Beneficiary account closed

The receiving bank reports that the beneficiary account is closed. The funds are returned to
the customer's account within two working days. Next step: ask the customer for new
beneficiary details.

## E91 Issuer unavailable

The card issuer or the receiving bank did not respond in time. Next step: retry after 30
minutes; if it fails again, raise a ticket with payments operations.
