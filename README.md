# Scholarship Watch

Checks the scholarship pages listed in `sources.json` every morning and emails you
only the posts that are new since the last check. Runs free on GitHub, so your
phone and computer do not need to be on.

## Set up (about 15 minutes)

1. **Make a GitHub account** at github.com if you do not have one.
2. **Create a new repository.** Name it `scholarship-watch`. Set it to **Private**.
3. **Upload these files** with "Add file > Upload files". Drag in everything from
   this folder, including the hidden `.github` folder. If the phone or browser hides
   it, create the file `.github/workflows/check.yml` by hand and paste the contents.
4. **Make a Gmail app password.** In your Google account, turn on 2-Step Verification,
   then open "App passwords" and create one. Copy the 16 letters.
5. **Add three secrets.** In the repository go to Settings > Secrets and variables >
   Actions > New repository secret, and add:
   - `SMTP_USER` : your Gmail address
   - `SMTP_PASS` : the 16-letter app password (not your normal password)
   - `MAIL_TO` : the address that should receive the alerts (can be the same Gmail)
6. **Run it once.** Open the Actions tab, choose "Scholarship Watch", press "Run workflow".

The first run only records what is already on each page, so it sends no email.
From the second run on, you get an email whenever a page has something new.

## Changing the sources

Open `sources.json` and add a line like this for each page:

    {"name": "KNUST Scholarships", "scope": "Local", "url": "https://..."}

Point `url` at the page that lists the scholarship posts, not the home page.

## Good to know

- Some websites block automated visits or load their posts with scripts. If a source
  shows "FAILED" in the Actions log, or never finds posts, that source needs a
  different page or a manual check. The email lists any source that failed.
- The deadline in the email is a guess from the page text. Confirm on the official
  page before forwarding to students.
- Check each website's terms of use. The checker visits each page once a day with a
  pause between pages.
