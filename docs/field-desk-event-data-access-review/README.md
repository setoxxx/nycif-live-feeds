# Field Desk event-data access review package

This agent cannot push to `nycif-field-desk` (GitHub 403 for cursor[bot]).

## Import into Field Desk

```bash
cd /path/to/nycif-field-desk
git fetch /path/to/nycif-live-feeds/dist/nycif-field-desk-event-data-access-review.bundle \
  refs/heads/cursor/review-complete-event-data-access:refs/heads/cursor/review-complete-event-data-access
git switch cursor/review-complete-event-data-access
git push -u origin cursor/review-complete-event-data-access
# then open PR: "Review and improve complete NYCIF event-data access"
```

Or copy the JS/HTML/CSS/SW files from this directory onto a branch from main.
