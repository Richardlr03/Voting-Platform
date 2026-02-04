## Reopen and Continue Project

1. cd "C:\Users\Li Zhang Tam\OneDrive - The University of Sydney (Students)\Desktop\Voting Project"
2. venv\Scripts\activate
3. Set-ExecutionPolicy -Scope CurrentUser RemoteSigned (if needed)
4. flask --app app --debug run
5. Database Migration: flask --app app db upgrade

## Commit Messages Guidelines

1. (feat) - Implementing new features
2. (update) - Updating and modifying an existing feature
3. (update UI) - Modifying certain UI
4. (bug fix) - Fixing bugs
