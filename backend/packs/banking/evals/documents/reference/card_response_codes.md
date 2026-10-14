# Card response codes (SAMPLE)

The scheme's response codes on card transactions, as the card system logs them, and what to do.

## Code 05 Do not honour

The issuer declined the transaction without a specific reason, often a fraud rule. Next step:
check the card's status; if it is active, raise a ticket with the card centre.

## Code 51 Insufficient funds

The linked account's available balance did not cover the transaction. Funds on hold do not
count. Next step: the customer should fund the account.

## Code 55 Incorrect PIN

The PIN entered was wrong. After three wrong PINs in a day the card is blocked (code 75).

## Code 57 Transaction not permitted to cardholder

The card's settings do not allow this kind of transaction: most often an international or
online payment with that use switched off. Next step: the customer can switch international or
online use on in the mobile app, or at a branch with ID.

## Code 61 Exceeds withdrawal limit

The amount is above the card's daily limit. Next step: withdraw a smaller amount, or ask for a
temporary limit increase at a branch with ID.

## Code 75 PIN tries exceeded

The card was blocked after too many wrong PINs. Next step: verify the customer's identity at a
branch, then unblock the card and reset the PIN (see the blocked card procedure).
