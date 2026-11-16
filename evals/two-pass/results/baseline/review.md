The run confirms that a newly created link opened and displayed version one. It doesn’t distinguish two promises: a link to the document as it changes, or a link to the version that was shared. Both would pass that run.

- **First open — partially verified.** Given a document at version one and a newly created link, a collaborator opens the link and reads version one without requesting an export. The run recorded the open and the version displayed. It didn’t establish whether the opener was a collaborator rather than the document owner.
- **Open after an edit — proposed; expected result open.** Given that same link, the author saves version two. A collaborator then opens the original link. The version they see distinguishes a live link from a snapshot. No run covered this case.

Deleted-document access stays deferred. I’d recommend a live link because a collaborator can keep using it after an edit without asking the author to share again. A snapshot makes more sense if the collaborator needs to review exactly what the author originally shared. **After the author saves version two, should the original link show version two or keep showing version one?**
