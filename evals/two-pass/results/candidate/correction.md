A collaborator who opens the same link after an edit should see the document as it was when the link was created. That includes someone opening it for the first time after the edit.

The original run still passes as a first-open check. Seeing version one before any edit fits both a snapshot and a live link, so snapshot behavior remains unverified.

**Proposed check:** Create a link while the document says “Meet Monday.” Change the text to “Meet Tuesday” and confirm the edit was saved. Have a collaborator open the original URL in a fresh browser session. Seeing “Meet Monday” passes the snapshot check. Seeing “Meet Tuesday” violates the confirmed promise.

Access after deletion remains undecided and has no pass or fail expectation.
