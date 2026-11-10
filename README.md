# igrp-scripts

Some scripts I use to automate my workflow at the IGRP platform: sign in,
open the daily summary page, download the absence report, export a grade
template and import the filled grades. The platform is in Portuguese, so some
UI strings in the script are in this language.

## Tech Stack

Python 3.10+, Selenium 4 (Selenium Manager handles the browser driver),
`python-dotenv`, `openpyxl`.

## Features

| Menu option | What it does |
| --- | --- |
| 1 - write summary | Opens `Sala Aula > Resumo do dia` |
| 2 - download absences | Opens `Diretor Turma > Alunos - Faltas e Notas`, selects the class (Ano/Turma), clicks **Pesquisar** to generate the absence list, then downloads the **PDF report** into `downloads/` |
| 3 - grade template | Asks which trimester to download (Enter = all), then opens `Atribuir de Notas`, reads every class/subject and **all** its scheduled assessments, and writes **one Excel workbook per selected trimester** (`downloads/pautas_1T_<timestamp>.xlsx`, `2T`, `3T`) with one sheet per class |
| 4 - import grades | Asks which trimester workbook to import (Enter = all), saves each grade in the matching assessment, then re-reads the page to confirm it persisted |
| 5 - quit | Closes the browser and exits |

For option 1 the browser stays open so you can do the actual work in SIGE.

### Absence report (option 2)

1. Opens `Diretor Turma > Alunos - Faltas e Notas`.
2. Selects the class in **Ano/Turma** (auto-picked when the account has a
   single turma; otherwise set `IGRP_TURMA`).
3. Sets the reporting period **De/Até** to **1 September of the current
   school year → today** (e.g. `01-09-2026` to `10-11-2026`).
4. Clicks **Pesquisar** to generate the per-student absence list.
5. Downloads the **PDF** report (`Relatorio`) to
   `downloads/faltas_<turma>_<timestamp>.pdf`.

The `downloads/` folder is gitignored.

### Grade template (option 3)

1. Opens `Atribuir de Notas` (the menu entry is hidden until the section is
   expanded, so the script follows its `href`).
2. Lists the trimesters and asks **which one to download** (press Enter for
   all). Only the selected trimester is read, so it downloads just that one.
3. Walks through every **Ano/Turma/Disc** of that trimester, keeping the
   combinations that have scheduled assessments.
4. For each combination reads the students and the current grades, and lists
   **all** scheduled assessments of that class, so the template already shows
   what is in SIGE and has one column per assessment.
5. Writes **one workbook per trimester** that has assessments:
   `downloads/pautas_1T_<timestamp>.xlsx`, `pautas_2T_…`, `pautas_3T_…`.
   Each workbook has:
   - a **Leia-me** sheet with the trimester, instructions and the mapping
     sheet → codes;
   - one sheet per class (e.g. `7ª - D - FRA`), with the students as rows and
     every scheduled assessment as a column.

The hidden row/column with the portal codes is only there to make the import
reliable; you do not need to touch it.

### Import grades (option 4)

By default it looks for the newest `pautas_1T_*.xlsx`, `pautas_2T_*.xlsx` and
`pautas_3T_*.xlsx` in `downloads/`, lists them and asks **which trimester to
import** (press Enter for all; `IGRP_GRADES_FILE` skips the question and
imports that single file). For each sheet it:

1. selects the school year, period, class and assessment (matching the codes
   first, then the labels);
2. matches each student by id, falling back to the name;
3. writes every non-empty cell, one **Confirmar** per assessment column;
4. re-reads the assessment to verify that the grades persisted.

Cells:

- **empty** → the current grade is left untouched;
- **number** (0–20, dot or comma) → written;
- **`-`** → the grade is erased.

Set `IGRP_GRADES_DRY_RUN=true` to preview everything without saving.

## Setup

```bash
# 1. Create an isolated environment (recommended)
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your local configuration
copy .env.example .env      # Windows
cp .env.example .env        # Linux / macOS
```

Then edit `.env` and fill in `IGRP_USERNAME`. For `IGRP_PASSWORD` you have two
options:

- **Leave it empty** (recommended): the script asks for the password at runtime
  with a hidden prompt and never writes it to disk.
- **Fill it in**: convenient, but the password is stored in plain text in
  `.env`. Keep that file private.

Firefox is used by default; set `IGRP_BROWSER=chrome` or `edge` to change it.
No manual webdriver download is needed.

## Run

```bash
python igrp-script.py
```

or use the launchers, which pick up `.venv` automatically:

- Windows: `start_IGRP.bat`
- Linux / macOS: `./start.sh`

## Security notes

- `.env` is **gitignored** and must never be committed. `config.py` (the old
  approach) is ignored as well.
- Credentials are never printed: only a masked username is shown.
- Prefer the runtime prompt over storing the password in `.env`.
- On Linux / macOS, lock down the file: `chmod 600 .env`.
- If a password was ever committed or shared, change it.
- The script does not store cookies or browser profiles beyond the current
  Selenium session, and it closes the browser on exit.

## Configuration

All settings are optional except the username/password.

| Variable | Default | Purpose |
| --- | --- | --- |
| `IGRP_USERNAME` | *(prompt)* | Login user |
| `IGRP_PASSWORD` | *(prompt)* | Login password |
| `IGRP_LOGIN_URL` | NOSi login page | Change if the portal moves |
| `IGRP_BROWSER` | `firefox` | `firefox`, `chrome` or `edge` |
| `IGRP_TIMEOUT` | `30` | Seconds to wait per element |
| `IGRP_HEADLESS` | `false` | Run without a window (smoke tests only) |
| `IGRP_TURMA` | *(auto)* | Class to use, e.g. `7ªD` or `1-126106`. Empty = auto-pick when there is only one. Also filters option 3 when set (use the full label, e.g. `7ª / D / FRA`, or its code) |
| `IGRP_DOWNLOAD_DIR` | `downloads` | Folder for the downloaded PDFs and Excel workbooks |
| `IGRP_GRADES_FILE` | *(newest per trimester)* | Workbook imported by option 4. Empty = asks which of the newest `pautas_1T/2T/3T_*.xlsx` to import; set a path to import a single file without asking |
| `IGRP_NOTA_MAX` | `20` | Highest grade accepted on import |
| `IGRP_GRADES_DRY_RUN` | `false` | Preview option 4 without saving |

## Troubleshooting

- **Login page**: NOSi migrated the portal to **Autentika SSO**
  (`autentika.gov.cv`). The script follows the redirect and clicks the
  `Entrar` button, so no action is needed while that stays stable.
- **`ElementClickInterceptedException` / click blocked**: the portal shows a
  full-screen loader (`<body class="... loading">`). `_wait_idle()` waits for it
  to finish and the click is retried once; if a new overlay appears, adjust
  that helper.
- **No PDF in `downloads/`**: check that `IGRP_DOWNLOAD_DIR` exists and is
  writable; if the browser blocks the download, the script falls back to
  fetching the report URL directly.
- **`TimeoutException` on a link** like `Sala Aula`: the portal UI text
  changed. Update the `By.LINK_TEXT` string in `igrp-script.py`.
- **Login fails after a while**: the SSO form may change again. Dump the page
  with `driver.page_source` and update the IDs/locators in `login()`.
- **`ModuleNotFoundError: dotenv`**: `pip install -r requirements.txt`
  (the script still works with plain environment variables).
- **`ModuleNotFoundError: openpyxl`**: `pip install -r requirements.txt`.
  Options 1/2 still work without it; only the Excel features need it.
- **Option 3 writes no workbook**: there are no scheduled assessments for the
  current school year in any trimester. Create them in SIGE
  (`Atribuir de Notas`) first, and check that the chosen year is the one you
  expect. Only trimesters with assessments produce a file.
- **Option 4 reports "assessment/class not found"**: the workbook was made in
  a different school year or the assessment was deleted. Run option 3 again
  and fill the new workbook; do not rename the sheets or headers.

## Author

- [David Nunes](https://www.github.com/Dnuns)

## License

MIT - see [LICENSE](LICENSE).
